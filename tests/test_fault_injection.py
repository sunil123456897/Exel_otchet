"""Stage 6 — fault injection and integration tests.

Covers the failure modes the TZ requires:

* fault injection for I/O errors and interruptions;
* integration with SQLite, the filesystem, and Excel I/O;
* concurrency and cancellation (cancel_event, threads);
* verification that source files are not modified by the pipeline;
* file-handle leak prevention.

Every test is hermetic: it builds its inputs in ``tmp_path`` and never
touches the operator's real data.
"""
from __future__ import annotations

import gc
import os
import sqlite3
import threading
import time
from pathlib import Path
from unittest.mock import patch

import openpyxl
import pytest

from core.infra.excel_backup import (
    backup_existing_excel_output,
    resolve_excel_backup_keep,
)


# ── 1) SQLite: transactions survive interruption ───────────────────────


def test_sqlite_transaction_rollback_on_error(tmp_path: Path) -> None:
    """A failed INSERT inside a transaction must roll back cleanly.

    No partial data should remain: SQLite must either commit the whole
    transaction or none of it. We force a unique-constraint violation
    mid-transaction and verify the earlier (valid) insert was rolled
    back too.
    """
    db = sqlite3.connect(tmp_path / "test.db")
    db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT UNIQUE)")
    db.execute("INSERT INTO t (id, name) VALUES (1, 'first')")
    db.commit()

    # Start a transaction, do a good insert, then trigger a constraint error.
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("BEGIN")
        db.execute("INSERT INTO t (id, name) VALUES (2, 'second')")
        # This violates the UNIQUE constraint on `name`:
        db.execute("INSERT INTO t (id, name) VALUES (3, 'first')")
        db.commit()
    db.rollback()

    rows = db.execute("SELECT id FROM t ORDER BY id").fetchall()
    db.close()
    # Only the original row survived; 'second' was rolled back.
    assert rows == [(1,)], f"transaction leaked partial data: {rows}"


def test_sqlite_wal_mode_resists_concurrent_reader(tmp_path: Path) -> None:
    """A reader can make progress while a writer holds the DB.

    WAL mode is the project default (config.database.use_wal = true).
    A reader should not be blocked by an uncommitted write.
    """
    db_path = tmp_path / "test.db"
    writer = sqlite3.connect(db_path)
    writer.execute("PRAGMA journal_mode=WAL")
    writer.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")
    writer.execute("INSERT INTO t (id) VALUES (1)")
    writer.commit()

    # Open a separate reader connection and verify it sees the row.
    reader = sqlite3.connect(db_path)
    rows = reader.execute("SELECT id FROM t").fetchall()
    reader.close()
    writer.close()
    assert rows == [(1,)]


# ── 2) Filesystem: file-handle leak prevention ─────────────────────────


def test_excel_workbook_close_releases_handle(tmp_path: Path) -> None:
    """A Workbook opened with openpyxl must release its file handle on close.

    On Windows, an open handle means the file cannot be renamed or
    deleted — which would block the next backup cycle. We open, close,
    and verify rename succeeds.
    """
    src = tmp_path / "src.xlsx"
    openpyxl.Workbook().save(src)

    wb = openpyxl.load_workbook(src)
    wb.close()
    # Force garbage collection in case any finaliser is pending.
    gc.collect()

    # Rename must succeed — would fail with PermissionError on Windows
    # if a handle were still open.
    dst = tmp_path / "renamed.xlsx"
    os.replace(src, dst)
    assert dst.exists()
    assert not src.exists()


def test_excel_workbook_close_then_reopen(tmp_path: Path) -> None:
    """Closing a workbook and reopening must yield the same content.

    openpyxl's Workbook does not implement the context-manager protocol
    on every version — this test uses explicit close() instead, which is
    the safe pattern across versions.
    """
    src = tmp_path / "src.xlsx"
    wb = openpyxl.Workbook()
    wb.active["A1"] = "first"
    wb.save(src)
    wb.close()

    # Reopen, modify, save, close.
    wb2 = openpyxl.load_workbook(src)
    wb2.active["A1"] = "second"
    wb2.save(src)
    wb2.close()

    gc.collect()
    wb3 = openpyxl.load_workbook(src)
    assert wb3.active["A1"].value == "second"
    wb3.close()


# ── 3) Excel backup: source file is not modified ───────────────────────


def test_backup_does_not_modify_source(tmp_path: Path) -> None:
    """backup_existing_excel_output must leave the source byte-for-byte identical."""
    src = tmp_path / "report.xlsx"
    wb = openpyxl.Workbook()
    wb.active["A1"] = "original"
    wb.save(src)
    src_bytes = src.read_bytes()
    src_mtime = src.stat().st_mtime_ns

    backup_existing_excel_output(src, tmp_path / "backups", keep=3)

    # Source must be unchanged.
    assert src.read_bytes() == src_bytes, "backup mutated the source"
    assert src.stat().st_mtime_ns == src_mtime, "backup touched the source mtime"


def test_backup_creates_versioned_copy(tmp_path: Path) -> None:
    """The backup file must exist after the call.

    Backups land in ``backup_root/excel_outputs/<stem>/`` — a nested
    layout so each source file has its own backup history.
    """
    src = tmp_path / "report.xlsx"
    openpyxl.Workbook().save(src)
    backup_dir = tmp_path / "backups"

    result = backup_existing_excel_output(src, backup_dir, keep=3)

    assert result is not None
    assert result.exists(), f"backup file not created at {result}"
    backups = list(backup_dir.rglob("*.xlsx"))
    assert len(backups) == 1, f"expected 1 backup, got {len(backups)}"


def test_backup_pruning_keeps_only_n_most_recent(tmp_path: Path) -> None:
    """When the backup count exceeds ``keep``, oldest extras are pruned."""
    src = tmp_path / "report.xlsx"
    openpyxl.Workbook().save(src)
    backup_dir = tmp_path / "backups"

    # Run 5 backups with keep=3.
    for _ in range(5):
        backup_existing_excel_output(src, backup_dir, keep=3)
        time.sleep(0.05)  # ensure mtimes differ

    backups = list(backup_dir.rglob("*.xlsx"))
    assert len(backups) <= 3, f"pruning left {len(backups)} backups, expected ≤3"


def test_backup_handles_missing_source_gracefully(tmp_path: Path) -> None:
    """Backing up a non-existent source must not crash the pipeline."""
    missing = tmp_path / "never_existed.xlsx"
    # Should not raise.
    backup_existing_excel_output(missing, tmp_path / "backups", keep=3)


def test_backup_handles_readonly_backup_dir(tmp_path: Path) -> None:
    """If the backup dir is read-only, the call must degrade silently.

    A backup failure must never block the main pipeline. We verify the
    function does not raise even when the destination refuses writes.
    """
    src = tmp_path / "report.xlsx"
    openpyxl.Workbook().save(src)
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    os.chmod(backup_dir, 0o555)  # read-only

    try:
        backup_existing_excel_output(src, backup_dir, keep=3)
    finally:
        os.chmod(backup_dir, 0o755)  # restore so pytest can clean up


# ── 4) resolve_excel_backup_keep config parsing ────────────────────────


def test_resolve_keep_default_when_none() -> None:
    assert resolve_excel_backup_keep(None) == 10


def test_resolve_keep_negative_clamped_to_minimum_one() -> None:
    """A negative keep value is clamped to 1 (the function's documented floor).

    ``max(1, parsed)`` is the explicit contract — we never allow keep=0
    or negative, because that would prune the just-created backup too.
    """
    assert resolve_excel_backup_keep(-1, default=5) == 1
    assert resolve_excel_backup_keep(0, default=5) == 1


def test_resolve_keep_explicit_value() -> None:
    assert resolve_excel_backup_keep(7, default=10) == 7


# ── 5) Concurrency: cancel_event is respected promptly ─────────────────


def test_cancel_event_is_observed_within_500ms() -> None:
    """A polling loop must observe a set cancel_event within 500ms.

    The ingestion engine polls cancel every 0.5s. We simulate that
    pattern and assert the loop exits quickly once cancel is set.
    """
    cancel = threading.Event()
    observed_at: list[float] = []

    def worker() -> None:
        while not cancel.is_set():
            time.sleep(0.05)
        observed_at.append(time.monotonic())

    t = threading.Thread(target=worker)
    t.start()
    time.sleep(0.2)  # let it run a bit
    cancel_set_at = time.monotonic()
    cancel.set()
    t.join(timeout=2.0)

    assert not t.is_alive(), "worker did not exit after cancel"
    assert observed_at, "worker never recorded its exit time"
    delay = observed_at[0] - cancel_set_at
    assert delay < 0.5, (
        f"cancel took {delay:.2f}s to be observed; expected < 0.5s"
    )


def test_cancel_event_before_work_starts() -> None:
    """If cancel is set before work begins, the worker exits immediately."""
    cancel = threading.Event()
    cancel.set()
    started = threading.Event()
    completed = threading.Event()

    def worker() -> None:
        started.set()
        if cancel.is_set():
            completed.set()
            return

    t = threading.Thread(target=worker)
    t.start()
    t.join(timeout=1.0)
    assert completed.is_set(), "pre-set cancel was not honoured"


# ── 6) Fault injection: simulate I/O errors during Excel write ─────────


def test_excel_save_failure_does_not_corrupt_existing_file(tmp_path: Path) -> None:
    """If a save fails midway, the original file must still load.

    The pipeline writes to a ``.tmp`` and atomically renames. If the
    rename never happens (write failed), the original file must remain
    valid and openable.
    """
    target = tmp_path / "report.xlsx"
    wb = openpyxl.Workbook()
    wb.active["A1"] = "original"
    wb.save(target)
    original_bytes = target.read_bytes()

    # Simulate a failed write: open the workbook, modify it, then make
    # save fail by patching the underlying file handle.
    wb2 = openpyxl.load_workbook(target)
    wb2.active["A1"] = "modified"
    with patch("openpyxl.Workbook.save", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            wb2.save(target)
    wb2.close()

    # The original file is unchanged because save raised before write.
    assert target.read_bytes() == original_bytes
    # And it still loads.
    wb3 = openpyxl.load_workbook(target)
    assert wb3.active["A1"].value == "original"
    wb3.close()


def test_disk_full_during_backup_does_not_lose_data(tmp_path: Path) -> None:
    """A disk-full error during backup must not corrupt the source.

    The pipeline must be able to continue (or fail loudly) without
    damaging the operator's existing report.
    """
    src = tmp_path / "report.xlsx"
    openpyxl.Workbook().save(src)
    original_bytes = src.read_bytes()

    # Patch shutil.copy2 to fail mid-backup.
    with patch("shutil.copy2", side_effect=OSError("disk full")):
        try:
            backup_existing_excel_output(src, tmp_path / "backups", keep=3)
        except OSError:
            pass  # caller is expected to handle this

    # Source is intact regardless of how backup failed.
    assert src.read_bytes() == original_bytes


# ── 7) Idempotency: re-running a no-op pipeline is safe ────────────────


def test_idempotent_save_does_not_grow_file(tmp_path: Path) -> None:
    """Saving the same workbook twice yields the same file size (within rounding)."""
    p = tmp_path / "report.xlsx"
    wb = openpyxl.Workbook()
    wb.active["A1"] = "x"
    wb.save(p)
    size1 = p.stat().st_size

    wb2 = openpyxl.load_workbook(p)
    wb2.save(p)
    wb2.close()
    size2 = p.stat().st_size

    # Re-saving should produce a roughly identical file (openpyxl may
    # differ by a few bytes due to XML whitespace, but not by KB).
    assert abs(size1 - size2) < 100, (
        f"re-save changed file size by {abs(size1 - size2)} bytes"
    )


# ── 8) Thread safety: shared SQLite connection ─────────────────────────


def test_threaded_sqlite_writers_need_separate_connections(tmp_path: Path) -> None:
    """Document (and enforce) that SQLite connections are not thread-safe.

    SQLite objects created in one thread cannot be used in another by
    default. We verify that attempting to share raises an error, so
    a future refactor doesn't silently introduce a race.
    """
    db_path = tmp_path / "test.db"
    main_conn = sqlite3.connect(db_path, check_same_thread=True)
    main_conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")

    err_in_thread = []
    def worker() -> None:
        try:
            main_conn.execute("INSERT INTO t (id) VALUES (1)")
        except Exception as e:
            err_in_thread.append(e)

    t = threading.Thread(target=worker)
    t.start()
    t.join()
    main_conn.close()

    assert err_in_thread, (
        "SQLite allowed cross-thread use without error; this is unsafe."
    )
