"""Stage 3 / MR-0303 — date validation: future / past warnings."""
from __future__ import annotations

from datetime import date

from core.domain.date_warnings import (
    DateWarningKind,
    classify_sheet_date,
)

# ── core classification ────────────────────────────────────────────────

def test_today_is_ok() -> None:
    ref = date(2026, 7, 20)
    w = classify_sheet_date("20.07.2026", reference=ref)
    assert w.kind == DateWarningKind.OK


def test_near_future_within_window_is_ok() -> None:
    ref = date(2026, 7, 20)
    w = classify_sheet_date("15.08.2026", reference=ref, future_days=31)
    assert w.kind == DateWarningKind.OK


def test_far_future_is_flagged() -> None:
    """The 2029 anomaly from TZ section 2 must surface as FUTURE."""
    ref = date(2026, 7, 20)
    w = classify_sheet_date("01.01.2029", reference=ref)
    assert w.kind == DateWarningKind.FUTURE
    assert "future" in w.detail.lower()


def test_distant_past_is_flagged() -> None:
    ref = date(2026, 7, 20)
    w = classify_sheet_date("01.01.2020", reference=ref)
    assert w.kind == DateWarningKind.DISTANT_PAST
    assert "past" in w.detail.lower()


def test_recent_past_is_ok() -> None:
    """A sheet from a few months ago is normal (catching up on backlog)."""
    ref = date(2026, 7, 20)
    w = classify_sheet_date("20.04.2026", reference=ref)
    assert w.kind == DateWarningKind.OK


# ── configuration ───────────────────────────────────────────────────────

def test_custom_future_window() -> None:
    ref = date(2026, 7, 20)
    # future_days=2: anything more than 2 days ahead is suspicious.
    w = classify_sheet_date("25.07.2026", reference=ref, future_days=2)
    assert w.kind == DateWarningKind.FUTURE


def test_custom_past_window() -> None:
    ref = date(2026, 7, 20)
    # past_days=7: anything older than a week is suspicious.
    w = classify_sheet_date("01.07.2026", reference=ref, past_days=7)
    assert w.kind == DateWarningKind.DISTANT_PAST


# ── boundary behaviour ─────────────────────────────────────────────────

def test_exact_future_boundary_is_ok() -> None:
    """Exactly future_days ahead is still OK (boundary is inclusive)."""
    ref = date(2026, 7, 20)
    # 31 days ahead.
    w = classify_sheet_date("20.08.2026", reference=ref, future_days=31)
    assert w.kind == DateWarningKind.OK


def test_one_day_past_future_boundary_is_flagged() -> None:
    ref = date(2026, 7, 20)
    # 32 days ahead.
    w = classify_sheet_date("21.08.2026", reference=ref, future_days=31)
    assert w.kind == DateWarningKind.FUTURE


# ── defensive parsing ─────────────────────────────────────────────────

def test_unparseable_date_does_not_crash() -> None:
    """A garbage string should not crash the classifier.

    The caller (ingestion pipeline) is expected to filter these via
    ``extract_date_from_sheet`` first, but the classifier must defend in
    depth.
    """
    ref = date(2026, 7, 20)
    w = classify_sheet_date("not-a-date", reference=ref)
    # Returns OK with a detail message; the alternative (raising) would
    # crash the pipeline on the first malformed sheet name.
    assert w.kind == DateWarningKind.OK
    assert "unparseable" in w.detail


def test_warning_serialises_to_dict() -> None:
    w = classify_sheet_date("01.01.2029", reference=date(2026, 7, 20))
    d = w.as_dict()
    assert d["kind"] == "future"
    assert d["sheet_date"] == "2029-01-01"
    assert "future" in d["detail"]


# ── default reference is today ─────────────────────────────────────────

def test_default_reference_is_today() -> None:
    """Without an explicit reference, the classifier uses today."""
    from datetime import date as _date
    today = _date.today()
    today_str = today.strftime("%d.%m.%Y")
    w = classify_sheet_date(today_str)
    assert w.kind == DateWarningKind.OK
