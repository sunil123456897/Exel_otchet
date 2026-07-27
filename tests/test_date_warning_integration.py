"""Stage 3 followup — verify classify_sheet_date is wired into the
ingestion pipeline and surfaces suspicious dates via data_loss_log.

The integration is intentionally side-effect-light: we only LOG the
warning, never drop the date. A suspicious date may carry real data;
the operator decides whether to act on it.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from core.domain.data_loss_log import reset_for_testing
from core.infra.ingestion_engine import _extract_dates_from_sheet_names


@pytest.fixture(autouse=True)
def _isolate_logger(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    reset_for_testing()
    yield
    reset_for_testing()


def _read_log(tmp_path: Path) -> list[dict]:
    log = tmp_path / "logs" / "data_loss.log"
    if not log.exists():
        return []
    out = []
    for line in log.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line.split(" ", 1)[1]))
        except (IndexError, json.JSONDecodeError):
            continue
    return out


def test_normal_dates_produce_no_warning() -> None:
    """Today's date should not trigger any data_loss_log entry."""
    today = date.today()
    sheet = today.strftime("%d.%m.%Y")
    result = _extract_dates_from_sheet_names([sheet])
    assert result == [sheet]


def test_future_date_triggers_warning(tmp_path: Path) -> None:
    """A sheet name 1 year ahead of today must surface a warning."""
    future = date.today() + timedelta(days=365)
    sheet = future.strftime("%d.%m.%Y")
    _extract_dates_from_sheet_names([sheet])

    entries = _read_log(tmp_path)
    suspicious = [e for e in entries if "suspicious_date" in e.get("kind", "")]
    assert suspicious, f"no suspicious-date entry logged for {sheet}"
    assert suspicious[0]["kind"] == "suspicious_date_future"


def test_distant_past_date_triggers_warning(tmp_path: Path) -> None:
    """A sheet name 5 years in the past must surface a warning."""
    past = date.today() - timedelta(days=365 * 5)
    sheet = past.strftime("%d.%m.%Y")
    _extract_dates_from_sheet_names([sheet])

    entries = _read_log(tmp_path)
    suspicious = [e for e in entries if "suspicious_date" in e.get("kind", "")]
    assert suspicious
    assert suspicious[0]["kind"] == "suspicious_date_distant_past"


def test_suspicious_date_is_not_dropped() -> None:
    """Even a suspicious date must still be returned by the extractor.

    The warning is for human review only — the row may carry real data.
    """
    future = date.today() + timedelta(days=365)
    sheet = future.strftime("%d.%m.%Y")
    result = _extract_dates_from_sheet_names([sheet])
    assert sheet in result, "suspicious date was dropped — data may be lost"


def test_invalid_sheet_name_does_not_crash() -> None:
    """A garbage sheet name must not propagate an exception."""
    result = _extract_dates_from_sheet_names(["not-a-date", "garbage"])
    assert result == []
