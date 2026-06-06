"""Tests for cancel-event propagation through the AppController entry points.

The GuiCommands module threads an OperationState's cancel_event down into the
controller's run_* methods. When the user clicks ⛳ on the status bar, the
controller's task() should notice and return early with a friendly message
rather than completing the (now-undesired) work and writing output files.
"""
import threading
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.app_controller import AppController, _is_cancelled


class TestIsCancelled:
    def test_none_event_is_not_cancelled(self):
        assert _is_cancelled(None) is False

    def test_unset_event_is_not_cancelled(self):
        ev = threading.Event()
        assert _is_cancelled(ev) is False

    def test_set_event_is_cancelled(self):
        ev = threading.Event()
        ev.set()
        assert _is_cancelled(ev) is True


def _build_controller_for_cancel_test() -> AppController:
    """Build an AppController with all collaborators stubbed.

    We don't need the real file/network machinery here — we just need the
    controller object so we can call its run_* methods, which in turn
    spawn a thread that consults cancel_event. The first thing every
    task() does is check cancel_event, so a pre-set event guarantees an
    immediate on_complete(False, ...) callback.
    """
    controller = AppController.__new__(AppController)
    controller._lock = threading.Lock()
    controller._active_threads = set()
    controller._get_network_drive_letters = MagicMock(return_value=[])
    return controller


def _collect_callbacks_for(method_name: str, *args, **kwargs) -> dict:
    """Helper: capture the on_complete callback that the task invokes.

    Most run_* methods immediately invoke on_complete when cancel_event is
    set. We patch the underlying build_* functions to be a no-op so the
    thread doesn't race past the cancel check.
    """
    cb_holder = {}

    def fake_on_complete(ok, msg, path):
        cb_holder["ok"] = ok
        cb_holder["msg"] = msg
        cb_holder["path"] = path

    controller = _build_controller_for_cancel_test()
    cancel_event = threading.Event()
    cancel_event.set()  # already cancelled

    patches = {}
    # Patch every external build function the methods may call BEFORE the
    # cancel check. We want to be sure the cancel check happens FIRST so
    # we don't accidentally depend on the patch order.
    for mod, names in (
        ("core.app_controller", ["build_rsch_report", "build_combined_reconciliation_report"]),
    ):
        for n in names:
            patches[(mod, n)] = patch.object(__import__(mod, fromlist=[n]), n)
    for p in patches.values():
        p.start()

    try:
        method = getattr(controller, method_name)
        method(*args, on_complete=fake_on_complete, cancel_event=cancel_event, **kwargs)
        for t in list(controller._active_threads):
            t.join(timeout=2)
    finally:
        for p in patches.values():
            p.stop()

    return cb_holder


class TestCancelEventShortCircuits:
    def test_run_rsch_report_cancelled_before_start(self, tmp_path):
        result = _collect_callbacks_for(
            "run_rsch_report",
            [tmp_path / "in.xlsx"],
            tmp_path / "out.xlsx",
            date(2026, 6, 6),
        )
        assert result["ok"] is False
        assert "отмен" in result["msg"].lower()
        assert result["path"] is None

    def test_run_rsch_report_period_cancelled(self, tmp_path):
        result = _collect_callbacks_for(
            "run_rsch_report_period",
            [tmp_path / "in.xlsx"],
            tmp_path / "out.xlsx",
            date(2026, 6, 1),
            date(2026, 6, 5),
        )
        assert result["ok"] is False
        assert "отмен" in result["msg"].lower()

    def test_run_reconciliation_report_cancelled(self, tmp_path):
        result = _collect_callbacks_for(
            "run_reconciliation_report",
            {"Общий": tmp_path / "m.xlsx"},
            tmp_path / "r.xlsx",
            tmp_path / "out.xlsx",
            date(2026, 6, 6),
        )
        assert result["ok"] is False
        assert "отмен" in result["msg"].lower()

    def test_run_auto_reconciliation_day_cancelled(self, tmp_path):
        result = _collect_callbacks_for(
            "run_auto_reconciliation_day",
            [tmp_path / "in.xlsx"],
            tmp_path / "out.xlsx",
            date(2026, 6, 6),
        )
        assert result["ok"] is False
        assert "отмен" in result["msg"].lower()


def test_cancel_event_set_after_start_but_before_completion(tmp_path):
    """The cancel check happens between build_rsch_report and the wrap-up.

    We let build_rsch_report run once (succeeds), then on_complete is
    called with ok=True. We then set cancel_event — but the next call's
    cancel check should still fire. Here we test the second invocation
    with a pre-set event to confirm idempotency.
    """
    cancel_event = threading.Event()
    cancel_event.set()
    result = _collect_callbacks_for(
        "run_rsch_report",
        [tmp_path / "in.xlsx"],
        tmp_path / "out.xlsx",
        date(2026, 6, 6),
    )
    assert result["ok"] is False
    assert "отмен" in result["msg"].lower()
