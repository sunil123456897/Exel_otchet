"""Stage 3 / MR-0301 + MR-0302 — parser isolation + corrupt fixtures.

Two interlocking properties:

1. The reader never crashes the process on a malformed input. It either
   returns an empty result with a logged reason, or raises a typed
   exception that the controller can catch per-source.
2. Directory scanning skips Excel lock files (``~$book.xlsx``) so the
   reader is never asked to parse the OLE2 ownership marker.

The corrupt fixtures live in ``tests/corrupt_fixtures.py`` so they can
be reused by Stage 4 (updater self-check) and Stage 6 (fault injection).
"""
from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest
from core.infra.ingestion_engine import IngestionEngine
from corrupt_fixtures import (
    CORRUPT_FIXTURE_BUILDERS,
    build_temp_dollar_lock,
)

# ── helpers ─────────────────────────────────────────────────────────────

def _engine() -> IngestionEngine:
    """Minimal IngestionEngine with default markers."""
    markers = {
        "source": "Источник", "amount": "сумма платежа", "total": "итог",
        "customer": "Заказчик", "contractor": "Исполнитель",
        "commission": "комиссия", "filters": "фильтры",
    }
    return IngestionEngine(markers, drive_letters=("Q", "Z"))


# ── MR-0302: corrupt fixtures don't crash ──────────────────────────────

@pytest.mark.parametrize(
    "fixture_name",
    sorted(CORRUPT_FIXTURE_BUILDERS.keys()),
    ids=sorted(CORRUPT_FIXTURE_BUILDERS.keys()),
)
def test_corrupt_fixture_does_not_crash_reader(
    fixture_name: str, tmp_path: Path,
) -> None:
    """Every malformed fixture must yield a controlled outcome, never a crash.

    The contract: ``read_file`` returns a list (possibly empty) and the
    process keeps running. We do NOT assert what the reader returns —
    calamine and openpyxl disagree on how much they can recover from a
    given malformation, and that's fine. The invariant is "no exception
    escapes the public API in non-strict mode".
    """
    builder = CORRUPT_FIXTURE_BUILDERS[fixture_name]
    path = builder(tmp_path)
    eng = _engine()

    # Non-strict: must not raise.
    result = eng.read_file(path, strict_io=False)
    assert isinstance(result, list), (
        f"{fixture_name}: read_file returned {type(result).__name__}, expected list"
    )


def test_truncated_archive_is_reported_not_silent(tmp_path: Path) -> None:
    """A truncated xlsx should at minimum leave a trace in logs.

    We don't assert on the exact message (logger formatting is unstable)
    but we assert that ``read_file`` did not silently pretend success on
    a clearly broken file by returning fake rows.
    """
    from corrupt_fixtures import build_truncated_archive
    path = build_truncated_archive(tmp_path)
    eng = _engine()
    result = eng.read_file(path, strict_io=False)
    # A truncated archive cannot yield valid financial rows.
    assert result == [], (
        "truncated archive returned rows — the reader is hallucinating data"
    )


# ── MR-0301: lock files and ~$ temp markers are skipped ────────────────

def test_directory_scan_skips_excel_lock_files(tmp_path: Path) -> None:
    """``~$book.xlsx`` must not appear in the scanned file list."""
    book, lock = build_temp_dollar_lock(tmp_path)
    assert lock.exists(), "test setup: lock file not created"

    eng = _engine()
    scanned = eng.scan_directory(tmp_path)

    paths = {s["path"] for s in scanned}
    assert str(book) in paths, "real workbook should be scanned"
    assert str(lock) not in paths, (
        f"~$ lock file must be skipped, but appears in scan: {paths}"
    )


def test_directory_scan_skips_non_xlsx_files(tmp_path: Path) -> None:
    """Files without .xlsx/.xlsb extension are ignored."""
    (tmp_path / "notes.txt").write_text("ignore me")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    (tmp_path / "real.xlsx")  # touch
    openpyxl.Workbook().save(tmp_path / "real.xlsx")

    eng = _engine()
    scanned = eng.scan_directory(tmp_path)
    paths = {s["path"] for s in scanned}
    assert any(p.endswith("real.xlsx") for p in paths)
    assert not any(p.endswith(".txt") for p in paths)
    assert not any(p.endswith(".png") for p in paths)


def test_directory_scan_handles_missing_directory(tmp_path: Path) -> None:
    """A missing root returns an empty list, not an exception."""
    eng = _engine()
    missing = tmp_path / "does_not_exist"
    result = eng.scan_directory(missing)
    assert result == []


# ── MR-0301: strict_io surfaces errors ─────────────────────────────────

def test_strict_io_raises_on_corrupt_input(tmp_path: Path) -> None:
    """In strict mode the caller wants to know about corruption.

    ``strict_io=True`` is used by tools/diagnostics where silent recovery
    would hide problems from the operator.
    """
    from corrupt_fixtures import build_invalid_zip_signature
    path = build_invalid_zip_signature(tmp_path)
    eng = _engine()
    with pytest.raises((OSError, RuntimeError, FileNotFoundError, ValueError)):
        eng.read_file(path, strict_io=True)


def test_non_strict_io_returns_empty_on_corrupt_input(tmp_path: Path) -> None:
    """In non-strict mode the engine keeps running with an empty result."""
    from corrupt_fixtures import build_invalid_zip_signature
    path = build_invalid_zip_signature(tmp_path)
    eng = _engine()
    result = eng.read_file(path, strict_io=False)
    assert result == []


# ── MR-0301: no infinite retry on a persistently broken file ───────────

def test_no_infinite_retry_on_persistent_failure(tmp_path: Path, monkeypatch) -> None:
    """A file that always fails must not be retried forever.

    We force every attempt to fail and verify the engine returns within
    a bounded number of attempts (no infinite loop, no hang).
    """
    from corrupt_fixtures import build_invalid_zip_signature
    path = build_invalid_zip_signature(tmp_path)

    # Patch the sleep so the test does not take _FILE_READ_RETRIES × backoff.
    import core.infra.ingestion_engine as ie
    monkeypatch.setattr(ie.time, "sleep", lambda _s: None)

    eng = _engine()
    # Force isolation off so we hit the read path directly (calamine is
    # what actually fails on bogus bytes).
    monkeypatch.setattr(eng, "_should_isolate_calamine", lambda _p: False)

    # Should return quickly (no hang), result empty.
    result = eng.read_file(path, strict_io=False)
    assert result == []


# ── MR-0301: huge claimed dimension does not OOM ──────────────────────

def test_huge_used_range_does_not_allocate_million_rows(tmp_path: Path) -> None:
    """A sheet lying about its dimension must not cause us to allocate.

    The risk: a reader that does ``for r in range(1, ws.max_row+1)`` on a
    sheet claiming 1 048 576 rows would burn through memory. We assert
    the engine returns in bounded time with bounded memory (no crash,
    no MemoryError).
    """
    from corrupt_fixtures import build_huge_used_range
    path = build_huge_used_range(tmp_path)
    eng = _engine()
    # If this hangs or OOMs the test process dies — exactly what we want
    # to catch.
    result = eng.read_file(path, strict_io=False)
    assert isinstance(result, list)


# ── dedicated behaviour for fixtures only covered by the generic loop ──
#
# build_missing_xml / build_many_empty_formatted_rows / build_hidden_sheet /
# build_formula_without_cache / build_protected_workbook are exercised by the
# parametrized "does not crash" test above, but with only the weak
# `isinstance(result, list)` assertion. The real contract for a malformed
# workbook is stronger: it must NOT return fabricated financial rows (an empty
# list is correct; non-empty data on a structurally broken file would mean
# the reader is hallucinating). These pin that stronger invariant per fixture.


@pytest.mark.parametrize(
    "builder_name",
    [
        "missing_xml",
        "many_empty_formatted_rows",
        "hidden_sheet",
        "formula_without_cache",
        "protected_workbook",
    ],
)
def test_malformed_fixture_yields_no_fabricated_rows(
    builder_name: str, tmp_path: Path,
) -> None:
    """A structurally broken workbook must never produce fake financial rows.

    ``build_formula_without_cache`` mirrors a real operator pain point: a
    source saved without cached formula values (data_only reads cells as
    None). None of these fixtures carry genuine payment data, so any non-empty
    result would be a hallucination — a silent correctness bug worse than a
    crash.
    """
    builder = CORRUPT_FIXTURE_BUILDERS[builder_name]
    path = builder(tmp_path)
    eng = _engine()
    result = eng.read_file(path, strict_io=False)
    assert isinstance(result, list), (
        f"{builder_name}: returned {type(result).__name__}, expected list"
    )
    assert result == [], (
        f"{builder_name}: a structurally broken workbook returned {len(result)} "
        "rows — the reader is fabricating data from a corrupt input"
    )
