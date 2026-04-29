import os
import sys
from unittest.mock import MagicMock, patch

import pytest

import headless_run
import toxic_run


def test_headless_run_shutdowns_controller_on_success(monkeypatch):
    app_ctl = MagicMock()
    db = MagicMock()
    event = MagicMock()
    event.wait.return_value = True

    monkeypatch.setattr(sys, "argv", ["headless_run.py"])

    with (
        patch("headless_run.Bootstrap.setup", return_value=(None, app_ctl, db)),
        patch("headless_run.threading.Event", return_value=event),
    ):
        headless_run.main()

    app_ctl.run_consolidation_all_dates.assert_called_once()
    app_ctl.shutdown.assert_called_once()
    db.close.assert_not_called()


def test_headless_run_shutdowns_controller_on_timeout(monkeypatch):
    app_ctl = MagicMock()
    db = MagicMock()
    event = MagicMock()
    event.wait.return_value = False

    monkeypatch.setattr(sys, "argv", ["headless_run.py"])

    with (
        patch("headless_run.Bootstrap.setup", return_value=(None, app_ctl, db)),
        patch("headless_run.threading.Event", return_value=event),
        pytest.raises(SystemExit),
    ):
        headless_run.main()

    app_ctl.shutdown.assert_called_once()
    db.close.assert_not_called()


def test_headless_run_respects_timeout_env_override(monkeypatch):
    app_ctl = MagicMock()
    db = MagicMock()
    event = MagicMock()
    event.wait.return_value = True

    monkeypatch.setattr(sys, "argv", ["headless_run.py"])
    monkeypatch.setenv("HEADLESS_RUN_TIMEOUT", "0")

    with (
        patch("headless_run.Bootstrap.setup", return_value=(None, app_ctl, db)),
        patch("headless_run.threading.Event", return_value=event),
    ):
        headless_run.main()

    event.wait.assert_called_once_with()
    app_ctl.shutdown.assert_called_once()


def test_toxic_run_shutdowns_controller_on_success(monkeypatch):
    app_ctl = MagicMock()
    db = MagicMock()
    event = MagicMock()
    event.wait.return_value = True

    monkeypatch.setattr(sys, "argv", ["toxic_run.py"])
    monkeypatch.setenv("CONFIG_PATH", "config.yaml")

    with (
        patch("toxic_run.Bootstrap.setup", return_value=(None, app_ctl, db)),
        patch("toxic_run.threading.Event", return_value=event),
    ):
        toxic_run.main()

    app_ctl.run_consolidation_all_dates.assert_called_once()
    app_ctl.shutdown.assert_called_once()
    db.close.assert_not_called()


def test_toxic_run_shutdowns_controller_on_timeout(monkeypatch):
    app_ctl = MagicMock()
    db = MagicMock()
    event = MagicMock()
    event.wait.return_value = False

    monkeypatch.setattr(sys, "argv", ["toxic_run.py"])
    monkeypatch.setenv("CONFIG_PATH", "config.yaml")

    with (
        patch("toxic_run.Bootstrap.setup", return_value=(None, app_ctl, db)),
        patch("toxic_run.threading.Event", return_value=event),
        pytest.raises(SystemExit),
    ):
        toxic_run.main()

    app_ctl.shutdown.assert_called_once()
    db.close.assert_not_called()


def test_toxic_run_respects_timeout_env_override(monkeypatch):
    app_ctl = MagicMock()
    db = MagicMock()
    event = MagicMock()
    event.wait.return_value = True

    monkeypatch.setattr(sys, "argv", ["toxic_run.py"])
    monkeypatch.setenv("CONFIG_PATH", "config.yaml")
    monkeypatch.setenv("HEADLESS_RUN_TIMEOUT", "0")

    with (
        patch("toxic_run.Bootstrap.setup", return_value=(None, app_ctl, db)),
        patch("toxic_run.threading.Event", return_value=event),
    ):
        toxic_run.main()

    event.wait.assert_called_once_with()
    app_ctl.shutdown.assert_called_once()


def test_toxic_run_counts_eligible_files():
    app_ctl = MagicMock()
    app_ctl._get_employees_map.return_value = {
        "ToxicTester": [{"path": "one.xlsx"}, {"path": "two.xlsx"}],
        "Empty": [],
    }

    assert toxic_run._count_eligible_files(app_ctl) == 2
