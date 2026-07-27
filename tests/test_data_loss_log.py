"""Tests for the data loss audit logger."""
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


def test_record_loss_writes_structured_json():
    """record_loss should append a JSON line with all fields to logs/data_loss.log."""
    record_loss(
        source="dummy.xlsx",
        kind="trash_filter",
        reason="row matched trash keyword",
        row_index=5,
        sheet="01.01.2026",
        field="customer",
        original_value="итого",
    )
    log_path = Path(os.getcwd()) / "logs" / "data_loss.log"
    assert log_path.exists(), "data_loss.log was not created"
    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines, "Log file is empty"
    payload = json.loads(lines[-1].split(" ", 1)[1])
    assert payload["source"] == "dummy.xlsx"
    assert payload["kind"] == "trash_filter"
    assert payload["reason"] == "row matched trash keyword"
    assert payload["row"] == 5
    assert payload["sheet"] == "01.01.2026"
    assert payload["field"] == "customer"
    assert payload["value"] == "итого"


def test_record_loss_handles_unserialisable_value():
    """Non-JSON-serialisable values should still be logged via str()."""
    sentinel = object()
    record_loss(
        source="x.xlsx",
        kind="numeric_coercion",
        reason="oops",
        original_value=sentinel,
    )
    log_path = Path(os.getcwd()) / "logs" / "data_loss.log"
    assert log_path.exists()
    payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1].split(" ", 1)[1])
    assert payload["kind"] == "numeric_coercion"
    assert payload["value"] == str(sentinel)
