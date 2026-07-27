"""Stage 3 / MR-0304 — data loss log: anonymisation invariants.

The existing tests in ``test_data_loss_log.py`` cover the basic JSON
shape. This module pins the privacy contract that the TZ demands:

* monetary amounts are redacted before they hit disk;
* Windows user paths and UNC shares are scrubbed;
* no row/sheet coordinates are redacted (the operator needs them to
  locate the problem);
* the redaction never throws — a failure to redact is still a write,
  not a dropped log entry.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from core.domain.data_loss_log import record_loss, reset_for_testing


@pytest.fixture(autouse=True)
def _reset_logger(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    reset_for_testing()
    yield
    reset_for_testing()


def _last_entry() -> dict:
    log_path = Path(os.getcwd()) / "logs" / "data_loss.log"
    assert log_path.exists(), "data_loss.log not created"
    raw = log_path.read_text(encoding="utf-8").splitlines()[-1]
    # Format: "<timestamp> <json>". Strip timestamp.
    return json.loads(raw.split(" ", 1)[1])


# ── monetary amount redaction ──────────────────────────────────────────

def test_monetary_amount_in_value_is_redacted() -> None:
    """A large amount in ``original_value`` must hit disk as [AMOUNT]."""
    record_loss(
        source="book.xlsx", kind="numeric_coercion", reason="bad",
        original_value="Сумма: 12345.67 руб",
    )
    payload = _last_entry()
    # The original literal must NOT appear in the serialised value.
    assert "12345.67" not in payload["value"]
    assert "[AMOUNT]" in payload["value"]


def test_monetary_amount_with_comma_decimal_is_redacted() -> None:
    """European-style decimal comma is also redacted (3+ digit amounts).

    Note: the regex requires 3+ digits before the separator specifically
    so two-digit values like ``12,50`` (which could be row indices, dates
    or version numbers) are preserved. ``999,50`` is unambiguously money.
    """
    record_loss(
        source="book.xlsx", kind="numeric_coercion", reason="bad",
        original_value="999,50",
    )
    payload = _last_entry()
    assert "999,50" not in payload["value"]
    assert "[AMOUNT]" in payload["value"]


def test_small_two_digit_amounts_are_not_redacted() -> None:
    """Small numbers that look like IDs / row indices are preserved.

    The redaction regex requires 3+ digits before the decimal separator
    so it doesn't nuke dates like ``12.05`` or version numbers like
    ``v5.50``. Verify that contract.
    """
    record_loss(
        source="book.xlsx", kind="ok", reason="row 12 dropped",
        original_value="12.50",
    )
    payload = _last_entry()
    # 12.50 is a 2-digit pre-decimal — must survive.
    assert "12.50" in payload["value"]
    assert "[AMOUNT]" not in payload["value"]


def test_date_like_value_is_not_redacted() -> None:
    """DD.MM.YYYY must not be mistaken for an amount."""
    record_loss(
        source="book.xlsx", kind="date", reason="bad date",
        original_value="12.05.2026",
    )
    payload = _last_entry()
    assert "12.05.2026" in payload["value"]


# ── path scrubbing ─────────────────────────────────────────────────────

def test_windows_user_path_in_source_is_scrubbed() -> None:
    """``C:\\Users\\vanya\\...`` must not appear in the log."""
    record_loss(
        source=r"C:\Users\vanya\Documents\secret\book.xlsx",
        kind="trash", reason="x",
    )
    payload = _last_entry()
    flat = json.dumps(payload, ensure_ascii=False)
    assert "vanya" not in flat.lower(), "Windows username leaked into log"
    assert r"C:\Users" not in flat


def test_unc_share_in_source_is_scrubbed() -> None:
    """``\\\\server\\share`` must not leak the internal server name."""
    record_loss(
        source=r"\\firmserver\finance$\book.xlsx",
        kind="trash", reason="x",
    )
    payload = _last_entry()
    flat = json.dumps(payload, ensure_ascii=False)
    assert "firmserver" not in flat.lower()


# ── coordinates are preserved ─────────────────────────────────────────

def test_row_index_is_preserved() -> None:
    """Operators need the row number to find the problem in Excel."""
    record_loss(
        source="book.xlsx", kind="x", reason="y", row_index=417,
        sheet="15.05.2026", field="amount",
    )
    payload = _last_entry()
    assert payload["row"] == 417
    assert payload["sheet"] == "15.05.2026"
    assert payload["field"] == "amount"


# ── never throws ───────────────────────────────────────────────────────

def test_record_loss_with_unserialisable_payload_does_not_throw() -> None:
    """A weird ``original_value`` must never crash the caller's pipeline."""
    class Weird:
        def __str__(self):
            raise RuntimeError("broken __str__")

    # Should return None silently, not raise.
    record_loss(
        source="x.xlsx", kind="k", reason="r",
        original_value=Weird(),
    )
    # The log was still written.
    payload = _last_entry()
    assert payload["kind"] == "k"


def test_record_loss_with_none_fields() -> None:
    """All optional fields can be None without breaking."""
    record_loss(source="x.xlsx", kind="k", reason="r")
    payload = _last_entry()
    assert payload["row"] is None
    assert payload["sheet"] is None
    assert payload["field"] is None
    assert payload["value"] is None


# ── privacy self-audit: scan whole log for forbidden patterns ─────────

def test_no_forbidden_patterns_in_log_after_mixed_entries() -> None:
    """End-to-end: a burst of varied entries must leave a clean log."""
    for i in range(5):
        record_loss(
            source=rf"C:\Users\user{i}\finance\book.xlsx",
            kind="numeric_coercion",
            reason=f"row {i} bad",
            row_index=100 + i,
            sheet="15.05.2026",
            original_value=f"{1000 + i}.99 rub",
        )
    log_path = Path(os.getcwd()) / "logs" / "data_loss.log"
    content = log_path.read_text(encoding="utf-8")

    # The forbidden substrings must never appear.
    forbidden = ["user0", "user1", "user2", "user3", "user4",
                 "1000.99", "1001.99", "1002.99", "1003.99", "1004.99",
                 r"C:\Users"]
    for pat in forbidden:
        assert pat not in content, f"forbidden pattern {pat!r} leaked into log"
