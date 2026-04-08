import pytest
import threading
import os
from unittest.mock import MagicMock, patch
from core.app_controller import AppController
from datetime import datetime
from pathlib import Path


@pytest.fixture
def mock_deps():
    return {
        "config_controller": MagicMock(),
        "ingestion": MagicMock(),
        "persistence": MagicMock(),
        "validator": MagicMock(),
        "logic_service": MagicMock(),
        "writer": MagicMock(),
    }


@pytest.fixture
def app_controller(mock_deps):
    with patch("core.app_controller.DiscoveryService"):
        controller = AppController(**mock_deps)
        return controller


@pytest.fixture(autouse=True)
def mock_executor(mocker):
    mock_exec = MagicMock()
    mock_exec.__enter__.return_value = mock_exec

    def sync_submit(fn, *args, **kwargs):
        res = fn(*args, **kwargs)
        f = MagicMock()
        f.result.return_value = res
        f.done.return_value = True
        return f

    mock_exec.submit.side_effect = sync_submit
    mocker.patch("concurrent.futures.ThreadPoolExecutor", return_value=mock_exec)
    mocker.patch("concurrent.futures.as_completed", side_effect=lambda fs: list(fs))
    return mock_exec


def test_refresh_status(app_controller, mock_deps, mocker):
    # Mock DiscoveryService instance
    mock_discovery = app_controller.discovery
    mock_discovery.get_employees_map.return_value = {
        "Alice": [{"path": "alice.xlsx"}],
        "Bob": [],
    }
    mock_discovery.rename_detected = False

    mocker.patch("core.app_controller.check_master_lock", return_value=True)

    # Mock os.path.exists and stat
    mocker.patch("os.path.exists", side_effect=lambda p: p == "alice.xlsx")
    mocker.patch("os.path.basename", side_effect=lambda p: p)
    mocker.patch("os.stat", return_value=MagicMock(st_mtime=100, st_size=1000))

    # Mock ingestion.get_available_dates
    mock_deps["ingestion"].get_available_dates.return_value = ["01.01.2023"]

    on_progress = MagicMock()
    on_complete = MagicMock()
    selected_date = datetime(2023, 1, 1)

    # Run task synchronously by mocking Thread
    with patch("threading.Thread") as mock_thread:
        app_controller.refresh_status(selected_date, on_progress, on_complete)
        # Get the task function passed to Thread
        task = mock_thread.call_args[1]["target"]
        task()

    on_complete.assert_called_once()
    args = on_complete.call_args[0]
    # Alice should be ready, Bob missing
    assert args[0][0] == ("Alice", "🟢 ГОТОВО", "alice.xlsx", "ready")
    assert args[0][1] == ("Bob", "🔴 НЕТ ФАЙЛА", "---", "missing")


def test_refresh_status_error(app_controller, mock_deps, mocker, caplog):
    mock_discovery = app_controller.discovery
    mock_discovery.get_employees_map.side_effect = Exception("Discovery error")

    on_progress = MagicMock()
    on_complete = MagicMock()

    with patch("threading.Thread") as mock_thread:
        app_controller.refresh_status(datetime.now(), on_progress, on_complete)
        task = mock_thread.call_args[1]["target"]
        task()

    assert "Refresh error: Discovery error" in caplog.text


def test_run_consolidation(app_controller, mock_deps, mocker):
    app_controller._cached_employees = {"Alice": [{"path": "alice.xlsx"}]}
    mocker.patch("os.path.exists", return_value=True)

    mock_deps["persistence"].save_file_metadata.return_value = [1]
    mock_deps["ingestion"].read_file.return_value = [
        {"date": "01.01.2023", "amount": 100}
    ]
    mock_deps["validator"].validate_row.return_value = True
    mock_deps["logic_service"].consolidate.return_value = [{"consolidated": True}]
    mock_deps["writer"].write_report.return_value = True

    on_progress = MagicMock()
    on_complete = MagicMock()
    selected_date = datetime(2023, 1, 1)

    with patch("threading.Thread") as mock_thread:
        app_controller.run_consolidation(selected_date, on_progress, on_complete)
        task = mock_thread.call_args[1]["target"]
        task()

    on_complete.assert_called_with(True, "Успешно!", mocker.ANY)
    mock_deps["persistence"].save_staging_data.assert_called_once()


def test_run_consolidation_no_files(app_controller, mock_deps, mocker):
    app_controller._cached_employees = {}

    on_progress = MagicMock()
    on_complete = MagicMock()
    selected_date = datetime(2023, 1, 1)

    with patch("threading.Thread") as mock_thread:
        app_controller.run_consolidation(selected_date, on_progress, on_complete)
        task = mock_thread.call_args[1]["target"]
        task()

    on_complete.assert_called_with(False, "Нет файлов", None)


def test_run_consolidation_no_data(app_controller, mock_deps, mocker):
    app_controller._cached_employees = {"Alice": [{"path": "alice.xlsx"}]}
    mocker.patch("os.path.exists", return_value=True)
    mock_deps["persistence"].save_file_metadata.return_value = [1]
    mock_deps["ingestion"].read_file.return_value = []
    mock_deps["logic_service"].consolidate.return_value = []

    on_progress = MagicMock()
    on_complete = MagicMock()

    with patch("threading.Thread") as mock_thread:
        app_controller.run_consolidation(datetime.now(), on_progress, on_complete)
        task = mock_thread.call_args[1]["target"]
        task()

    on_complete.assert_called_with(False, "Нет данных за дату", None)


def test_run_consolidation_all_dates(app_controller, mock_deps, mocker):
    mock_discovery = app_controller.discovery
    mock_discovery.get_employees_map.return_value = {"Alice": [{"path": "alice.xlsx"}]}
    mocker.patch("os.path.exists", return_value=True)

    mock_deps["persistence"].save_file_metadata.return_value = [1]
    mock_deps["ingestion"].read_file.return_value = [
        {"date": "01.01.2023", "amount": 100}
    ]
    mock_deps["validator"].validate_row.return_value = True
    mock_deps["logic_service"].consolidate.return_value = [{"consolidated": True}]
    mock_deps["persistence"].get_template_errors.return_value = []
    mock_deps["writer"].write_report.return_value = True

    on_progress = MagicMock()
    on_complete = MagicMock()

    with patch("threading.Thread") as mock_thread:
        app_controller.run_consolidation_all_dates(on_progress, on_complete)
        task = mock_thread.call_args[1]["target"]
        task()

    on_complete.assert_called_with(True, "Готово!", mocker.ANY)


def test_rename_detected_property(app_controller):
    app_controller.discovery.rename_detected = True
    assert app_controller.rename_detected is True
