"""Tests for the OperationStatusBar and ToastManager widgets.

These tests run with a real Tk root (no mocking) but avoid showing
windows: the root is created and withdrawn after the test.
"""
import tkinter as tk
import time
from unittest.mock import MagicMock

import pytest

from core.ui.operation_state import OperationState, OperationType
from core.ui.operation_status_bar import OperationStatusBar, _format_duration
from core.ui.toast import ToastLevel, ToastManager


@pytest.fixture(scope="module")
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"Tk not available: {e}")
    root.withdraw()
    yield root
    root.destroy()


# --- OperationStatusBar --------------------------------------------------


def test_status_bar_shows_idle_text_when_no_operation(tk_root):
    state = OperationState()
    bar = OperationStatusBar(tk_root, state, on_cancel=lambda: None)
    assert "Готово" in bar._label_var.get()
    assert bar._progress_var.get() == 0.0
    assert bar._cancel_btn.instate(["disabled"])


def test_status_bar_shows_operation_label_when_busy(tk_root):
    state = OperationState()
    bar = OperationStatusBar(tk_root, state, on_cancel=lambda: None)
    state.begin(OperationType.CONSOLIDATION_DAY)
    state.set_progress(42.0)
    bar.update()
    label = bar._label_var.get()
    assert "Сборка за день" in label
    assert "42" in bar._pct_label.cget("text") or "42%" in bar._pct_label.cget("text")


def test_status_bar_cancel_button_invokes_callback(tk_root):
    state = OperationState()
    callback = MagicMock()
    bar = OperationStatusBar(tk_root, state, on_cancel=callback)
    state.begin(OperationType.CONSOLIDATION_DAY)
    bar.update()
    bar._cancel_btn.invoke()
    assert callback.called


def test_status_bar_cancel_button_disabled_when_idle(tk_root):
    state = OperationState()
    bar = OperationStatusBar(tk_root, state, on_cancel=lambda: None)
    assert bar._cancel_btn.instate(["disabled"])


def test_status_bar_cancel_button_disabled_when_cancelling(tk_root):
    state = OperationState()
    bar = OperationStatusBar(tk_root, state, on_cancel=lambda: None)
    state.begin(OperationType.CONSOLIDATION_DAY)
    state.request_cancel()
    bar.update()
    assert bar._cancel_btn.instate(["disabled"])


def test_status_bar_elapsed_grows_over_time(tk_root):
    state = OperationState()
    bar = OperationStatusBar(tk_root, state, on_cancel=lambda: None)
    state.begin(OperationType.CONSOLIDATION_MONTH)
    state.set_progress(10.0)
    bar.update()
    first = bar._elapsed_var.get()
    time.sleep(0.05)
    bar._render(state.current, state.progress, state.started_at, state.is_cancelling)
    bar.update()
    second = bar._elapsed_var.get()
    assert first != "" and second != ""
    assert "0:" in first and "0:" in second


def test_status_bar_eta_shown_only_when_progress_1_to_99(tk_root):
    state = OperationState()
    bar = OperationStatusBar(tk_root, state, on_cancel=lambda: None)
    state.begin(OperationType.CONSOLIDATION_DAY)
    state.set_progress(0.5)
    bar.update()
    assert bar._eta_var.get() == ""
    state.set_progress(50.0)
    bar.update()
    assert "осталось" in bar._eta_var.get()
    state.set_progress(100.0)
    bar.update()
    assert bar._eta_var.get() == "завершено"


def test_status_bar_renders_cancelling_label(tk_root):
    state = OperationState()
    bar = OperationStatusBar(tk_root, state, on_cancel=lambda: None)
    state.begin(OperationType.RSCH_DAY)
    state.request_cancel()
    bar.update()
    assert "отмена" in bar._label_var.get().lower()


# --- _format_duration ----------------------------------------------------


def test_format_duration_under_minute():
    assert _format_duration(0) == "0:00"
    assert _format_duration(42) == "0:42"


def test_format_duration_minutes():
    assert _format_duration(60) == "1:00"
    assert _format_duration(125) == "2:05"


def test_format_duration_over_hour():
    assert _format_duration(3600) == "1:00:00"
    assert _format_duration(3725) == "1:02:05"


def test_format_duration_negative_clamps_to_zero():
    assert _format_duration(-10) == "0:00"


# --- ToastManager --------------------------------------------------------


def test_toast_appears_and_disappears(tk_root):
    manager = ToastManager(tk_root, max_stack=3)
    manager.info("Title", "body", duration_ms=200)
    tk_root.update_idletasks()
    assert len(manager._stack) == 1
    tk_root.after(300, tk_root.quit)
    tk_root.mainloop()
    assert len(manager._stack) == 0


def test_toast_max_stack_evicts_oldest(tk_root):
    manager = ToastManager(tk_root, max_stack=2)
    manager.info("A")
    tk_root.update_idletasks()
    manager.info("B")
    tk_root.update_idletasks()
    manager.info("C")
    tk_root.update_idletasks()
    assert len(manager._stack) == 2
    assert manager._stack[0].title in {"B", "C"}


def test_toast_levels_create_widgets(tk_root):
    manager = ToastManager(tk_root, max_stack=4)
    for level_method, level in (
        ("info", ToastLevel.INFO),
        ("success", ToastLevel.SUCCESS),
        ("warning", ToastLevel.WARNING),
        ("error", ToastLevel.ERROR),
    ):
        getattr(manager, level_method)("Title", "body", duration_ms=5000)
    tk_root.update_idletasks()
    assert len(manager._stack) == 4
    seen = {t.level for t in manager._stack}
    assert seen == set(ToastLevel)


def test_toast_renders_title_and_message(tk_root):
    manager = ToastManager(tk_root, max_stack=1)
    manager.error("Error title", "Detail here", duration_ms=5000)
    tk_root.update_idletasks()
    toast = manager._stack[0]
    assert toast.title == "Error title"
    assert toast.message == "Detail here"
    assert toast.level is ToastLevel.ERROR
