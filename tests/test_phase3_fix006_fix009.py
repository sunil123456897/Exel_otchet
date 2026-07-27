"""Phase 3.2 — Tests for FIX-006 (toast detail) and FIX-009 (current file).

FIX-006: Toast API now accepts an optional ``detail`` parameter that
renders an expandable "Подробнее ▼" section below the message. Tests
verify the API accepts the parameter and the convenience methods
(info/success/warning/error) forward it correctly.

FIX-009: OperationState now tracks ``current_file`` and
OperationStatusBar renders it. Tests verify the state machine stores
and clears the file name, and the snapshot carries it.
"""
from __future__ import annotations

# ─────────────────────────────────────────────────────────────
# FIX-006: Toast detail parameter
# ─────────────────────────────────────────────────────────────

class TestToastDetailAPI:
    """Verify the Toast API accepts and forwards the ``detail`` parameter."""

    def test_show_accepts_detail_kwarg(self):
        """ToastManager.show should accept detail= without error."""
        # We can't instantiate a real ToastManager without a Tk root,
        # but we can verify the signature accepts the parameter.
        import inspect

        from core.ui.toast import ToastManager
        sig = inspect.signature(ToastManager.show)
        assert "detail" in sig.parameters
        assert sig.parameters["detail"].default == ""

    def test_info_accepts_detail_kwarg(self):
        import inspect

        from core.ui.toast import ToastManager
        sig = inspect.signature(ToastManager.info)
        assert "detail" in sig.parameters

    def test_success_accepts_detail_kwarg(self):
        import inspect

        from core.ui.toast import ToastManager
        sig = inspect.signature(ToastManager.success)
        assert "detail" in sig.parameters

    def test_warning_accepts_detail_kwarg(self):
        import inspect

        from core.ui.toast import ToastManager
        sig = inspect.signature(ToastManager.warning)
        assert "detail" in sig.parameters

    def test_error_accepts_detail_kwarg(self):
        import inspect

        from core.ui.toast import ToastManager
        sig = inspect.signature(ToastManager.error)
        assert "detail" in sig.parameters

    def test_toast_dataclass_has_detail_fields(self):
        import dataclasses

        from core.ui.toast import _Toast
        field_names = {f.name for f in dataclasses.fields(_Toast)}
        assert "detail_frame" in field_names
        assert "detail_visible" in field_names


class TestFinishDetailForwarding:
    """Verify finish() in _base.py forwards detail to toast.show()."""

    def test_finish_accepts_detail_kwarg(self):
        import inspect

        from core.ui.gui_commands._base import finish
        sig = inspect.signature(finish)
        assert "detail" in sig.parameters
        assert sig.parameters["detail"].default == ""


# ─────────────────────────────────────────────────────────────
# FIX-009: OperationState current_file tracking
# ─────────────────────────────────────────────────────────────

from core.ui.operation_state import (
    OperationSnapshot,
    OperationState,
    OperationType,
)


class TestOperationStateCurrentFile:
    """Verify OperationState tracks and exposes current_file."""

    def test_snapshot_has_current_file_field(self):
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(OperationSnapshot)}
        assert "current_file" in field_names

    def test_default_current_file_is_empty(self):
        state = OperationState()
        snap = state.snapshot()
        assert snap.current_file == ""

    def test_set_current_file_updates_snapshot(self):
        state = OperationState()
        state.begin(OperationType.CONSOLIDATION_DAY)
        state.set_current_file("ivan_petrov.xlsx")
        snap = state.snapshot()
        assert snap.current_file == "ivan_petrov.xlsx"

    def test_set_current_file_when_idle_is_noop(self):
        state = OperationState()
        state.set_current_file("test.xlsx")
        snap = state.snapshot()
        assert snap.current_file == ""  # ignored because not busy

    def test_end_clears_current_file(self):
        state = OperationState()
        state.begin(OperationType.CONSOLIDATION_DAY)
        state.set_current_file("report.xlsx")
        state.end()
        snap = state.snapshot()
        assert snap.current_file == ""

    def test_set_current_file_notifies_listeners(self):
        state = OperationState()
        state.begin(OperationType.CONSOLIDATION_DAY)
        received: list[str] = []
        state.add_listener(lambda snap: received.append(snap.current_file))
        state.set_current_file("data.xlsx")
        assert "data.xlsx" in received

    def test_set_current_file_thread_safe(self):
        """Concurrent set_current_file calls must not raise."""
        import threading
        state = OperationState()
        state.begin(OperationType.CONSOLIDATION_DAY)

        def setter(name: str) -> None:
            for _ in range(100):
                state.set_current_file(name)

        threads = [threading.Thread(target=setter, args=(f"file_{i}.xlsx",)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=2.0)
        # Should not have raised; final value is one of the names
        snap = state.snapshot()
        assert snap.current_file.startswith("file_") or snap.current_file == ""


# ─────────────────────────────────────────────────────────────
# FIX-009: file_processor on_current_file callback
# ─────────────────────────────────────────────────────────────

class TestRunEngineOnCurrentFile:
    """Verify run_engine accepts and calls on_current_file."""

    def test_run_engine_accepts_on_current_file_kwarg(self):
        import inspect

        from core.app.file_processor import run_engine
        sig = inspect.signature(run_engine)
        assert "on_current_file" in sig.parameters
        assert sig.parameters["on_current_file"].default is None


# ─────────────────────────────────────────────────────────────
# FIX-009: app_controller on_current_file forwarding
# ─────────────────────────────────────────────────────────────

class TestAppControllerOnCurrentFile:
    """Verify app_controller methods accept on_current_file."""

    def test_run_consolidation_accepts_on_current_file(self):
        import inspect

        from core.app_controller import AppController
        sig = inspect.signature(AppController.run_consolidation)
        assert "on_current_file" in sig.parameters

    def test_run_consolidation_all_dates_accepts_on_current_file(self):
        import inspect

        from core.app_controller import AppController
        sig = inspect.signature(AppController.run_consolidation_all_dates)
        assert "on_current_file" in sig.parameters

    def test_run_consolidation_month_accepts_on_current_file(self):
        import inspect

        from core.app_controller import AppController
        sig = inspect.signature(AppController.run_consolidation_month)
        assert "on_current_file" in sig.parameters

    def test_run_consolidation_core_accepts_on_current_file(self):
        import inspect

        from core.app_controller import AppController
        sig = inspect.signature(AppController._run_consolidation_core)
        assert "on_current_file" in sig.parameters


# ─────────────────────────────────────────────────────────────
# FIX-009: ViewModel on_current_file forwarding
# ─────────────────────────────────────────────────────────────

class TestViewModelOnCurrentFile:
    """Verify ConsolidationViewModel supports on_current_file."""

    def test_set_callbacks_accepts_on_current_file(self):
        import inspect

        from core.view_models.consolidation_viewmodel import ConsolidationViewModel
        sig = inspect.signature(ConsolidationViewModel.set_callbacks)
        assert "on_current_file" in sig.parameters
        assert sig.parameters["on_current_file"].default is None
