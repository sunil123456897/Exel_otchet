import threading
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from core.app_controller import AppController


@pytest.fixture
def controller_and_deps():
    deps = {
        "config_controller": MagicMock(),
        "ingestion": MagicMock(),
        "persistence": MagicMock(),
        "validator": MagicMock(),
        "logic_service": MagicMock(),
        "writer": MagicMock(),
    }
    with patch("core.app_controller.DiscoveryService") as mock_discovery:
        ctl = AppController(**deps)
        ctl.discovery = mock_discovery.return_value
    return ctl, deps


def test_refresh_status_completes_with_real_thread(controller_and_deps):
    ctl, _deps = controller_and_deps
    ctl.discovery.get_employees_map.return_value = {
        "Alice": [{"path": "C:/reports/missing.xlsx"}],
    }
    ctl.discovery.rename_detected = False

    done = threading.Event()
    payload = {}

    def on_complete(data, employees_map, rename_detected):
        payload["data"] = data
        payload["employees_map"] = employees_map
        payload["rename_detected"] = rename_detected
        done.set()

    with (
        patch("core.app_controller.check_master_lock", return_value=True),
        patch("os.path.exists", return_value=False),
    ):
        ctl.refresh_status(datetime(2026, 4, 1), lambda _p: None, on_complete)

    assert done.wait(2.0)
    assert payload["data"][0] == ("Alice", "🔴 НЕТ ФАЙЛА", "---", "missing")
    assert payload["employees_map"]["Alice"][0]["path"].endswith("missing.xlsx")
    assert payload["rename_detected"] is False

    ctl.shutdown()


def test_run_consolidation_completes_failure_path_with_real_thread(controller_and_deps):
    ctl, deps = controller_and_deps
    ctl._cached_employees = {"Alice": [{"path": "C:/reports/a.xlsx"}]}

    done = threading.Event()
    result = {}

    def on_complete(ok, msg, path):
        result["ok"] = ok
        result["msg"] = msg
        result["path"] = path
        done.set()

    with (
        patch("core.app_controller.check_master_lock", return_value=True),
        patch("core.app_controller.run_engine", return_value=False),
    ):
        ctl.run_consolidation(datetime(2026, 4, 1), lambda _p: None, on_complete)

        assert done.wait(2.0)
        assert result == {"ok": False, "msg": "Нет файлов", "path": None}
        deps["persistence"].update_session_status.assert_called()

    ctl.shutdown()


def test_shutdown_waits_threads_and_closes_persistence(controller_and_deps):
    ctl, deps = controller_and_deps

    started = threading.Event()
    finished = threading.Event()

    def target():
        started.set()
        time.sleep(0.05)
        finished.set()

    ctl._start_thread(target)
    assert started.wait(1.0)

    ctl.shutdown()

    assert finished.is_set()
    deps["persistence"].wait_for_writes.assert_called_once()
    deps["persistence"].close.assert_called_once()
