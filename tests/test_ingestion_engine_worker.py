from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.infra.ingestion_engine import (
    IngestionEngine,
    _run_calamine_worker,
    _should_isolate_calamine,
)


def test_should_isolate_calamine_matches_reports_path():
    assert _should_isolate_calamine(Path("C:/REPORTS/a.xlsx")) is True
    assert _should_isolate_calamine("C:/reports/sub/a.xlsx") is True
    assert _should_isolate_calamine(Path("C:/data/a.xlsx")) is False


def test_run_calamine_worker_success_with_stderr_payload():
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = '{"ok": true, "result": ["01.01.2026"]}'
    proc.stderr = "worker warning"

    with patch("core.infra.ingestion_engine.subprocess.run", return_value=proc):
        payload = _run_calamine_worker("dates", "C:/reports/a.xlsx", {}, {})

    assert payload["ok"] is True
    assert payload["result"] == ["01.01.2026"]
    assert payload["stderr"] == "worker warning"


def test_run_calamine_worker_returns_error_on_nonzero_exit():
    proc = MagicMock()
    proc.returncode = 2
    proc.stdout = ""
    proc.stderr = "boom"

    with patch("core.infra.ingestion_engine.subprocess.run", return_value=proc):
        payload = _run_calamine_worker("dates", "C:/reports/a.xlsx", {}, {})

    assert payload["ok"] is False
    assert payload["error"] == "boom"


def test_run_calamine_worker_returns_error_on_invalid_json():
    proc = MagicMock()
    proc.returncode = 0
    proc.stdout = "not-json"
    proc.stderr = ""

    with patch("core.infra.ingestion_engine.subprocess.run", return_value=proc):
        payload = _run_calamine_worker("rows", "C:/reports/a.xlsx", {}, {})

    assert payload["ok"] is False
    assert payload["error"] == "not-json"


def test_get_available_dates_worker_result_and_stderr(tmp_path):
    engine = IngestionEngine({})
    file_path = tmp_path / "any.xlsx"

    with (
        patch(
            "core.infra.ingestion_engine.get_local_copy",
            return_value=(str(file_path), None),
        ),
        patch(
            "core.infra.ingestion_engine._should_isolate_calamine", return_value=True
        ),
        patch(
            "core.infra.ingestion_engine._run_calamine_worker",
            return_value={
                "ok": True,
                "result": ["02.04", "", "01.04"],
                "stderr": "minor worker warning",
            },
        ),
        patch("core.infra.ingestion_engine.logger.warning") as mock_warn,
    ):
        dates = engine.get_available_dates(file_path)

    assert dates == ["01.04", "02.04"]
    mock_warn.assert_called_once_with("minor worker warning")


def test_get_available_dates_reraises_keyboardinterrupt(tmp_path):
    engine = IngestionEngine({})
    file_path = tmp_path / "interrupt.xlsx"

    with (
        patch(
            "core.infra.ingestion_engine.get_local_copy",
            return_value=(str(file_path), None),
        ),
        patch(
            "core.infra.ingestion_engine._should_isolate_calamine", return_value=True
        ),
        patch(
            "core.infra.ingestion_engine._run_calamine_worker",
            side_effect=KeyboardInterrupt,
        ),
    ):
        with pytest.raises(KeyboardInterrupt):
            engine.get_available_dates(file_path)


def test_get_available_dates_cleanup_ignores_remove_errors(tmp_path):
    engine = IngestionEngine({})
    file_path = tmp_path / "cleanup.xlsx"
    temp_file = str(tmp_path / "temp-copy.xlsx")

    with (
        patch(
            "core.infra.ingestion_engine.get_local_copy",
            return_value=(str(file_path), temp_file),
        ),
        patch(
            "core.infra.ingestion_engine._should_isolate_calamine", return_value=False
        ),
        patch.object(engine, "_get_available_dates_direct", return_value=[]),
        patch(
            "core.infra.ingestion_engine.os.path.exists",
            side_effect=lambda p: p == temp_file,
        ),
        patch(
            "core.infra.ingestion_engine.os.remove", side_effect=OSError("locked")
        ) as mock_remove,
    ):
        dates = engine.get_available_dates(file_path)

    assert dates == []
    mock_remove.assert_called_once_with(temp_file)


def test_read_file_logs_worker_stderr_and_returns_rows(tmp_path):
    engine = IngestionEngine({})
    file_path = tmp_path / "rows.xlsx"
    file_path.touch()

    with (
        patch(
            "core.infra.ingestion_engine._should_isolate_calamine", return_value=True
        ),
        patch(
            "core.infra.ingestion_engine._run_calamine_worker",
            return_value={
                "ok": True,
                "result": [{"date": "01.04.2026", "amount": "10"}],
                "stderr": "stderr-note",
            },
        ),
        patch("core.infra.ingestion_engine.logger.warning") as mock_warn,
    ):
        rows = engine.read_file(file_path, strict_io=False)

    assert rows == [{"date": "01.04.2026", "amount": "10"}]
    mock_warn.assert_called_once_with("stderr-note")


def test_read_file_reraises_unexpected_exception(tmp_path):
    engine = IngestionEngine({})
    file_path = tmp_path / "unexpected.xlsx"
    file_path.touch()

    engine.reader.read = MagicMock(side_effect=ValueError("bad parse"))

    with patch(
        "core.infra.ingestion_engine._should_isolate_calamine", return_value=False
    ):
        with pytest.raises(ValueError, match="bad parse"):
            engine.read_file(file_path, strict_io=False)
