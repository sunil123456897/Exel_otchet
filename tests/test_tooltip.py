"""Tests for the Tooltip widget.

These tests use a withdrawn Tk root to avoid showing windows during
the test run. We exercise the show/hide lifecycle and the text
update API.
"""
import tkinter as tk
from unittest.mock import MagicMock

import pytest
from core.ui.tooltip import Tooltip


@pytest.fixture(scope="module")
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"Tk not available: {e}")
    root.withdraw()
    yield root
    root.destroy()


def test_tooltip_starts_hidden(tk_root):
    btn = tk.Button(tk_root, text="Run")
    tip = Tooltip(btn, "Run the consolidation", delay_ms=10)
    assert tip._tip is None


def _wait_until(condition, timeout_ms=1000, root=None):
    """Pump the Tk event loop until ``condition`` is truthy or we time out."""
    import time
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        if condition():
            return True
        if root is not None:
            root.update()
        time.sleep(0.01)
    return False


def _fake_enter(tip, widget):
    """Drive the Tooltip's enter handler directly.

    Tk's ``event_generate`` does not invoke bindings on a non-mapped
    widget under the test runner, so we call the bound Python method
    directly with a minimal mock event that has the attributes the
    handler reads (``x_root`` and ``y_root``).
    """
    event = MagicMock(spec=["x_root", "y_root"])
    event.x_root = 100
    event.y_root = 200
    tip._on_enter(event)
    # event_generate on a mapped widget would also work; this is the
    # safe path for headless tests.
    _ = widget  # keep the signature consistent with the previous version


def test_tooltip_shows_on_hover(tk_root):
    btn = tk.Button(tk_root, text="Run")
    tip = Tooltip(btn, "Run it", delay_ms=10)
    _fake_enter(tip, btn)
    assert _wait_until(lambda: tip._tip is not None, root=tk_root)
    assert tip._tip.winfo_exists()
    tip._on_leave(None)
    tk_root.update_idletasks()
    assert tip._tip is None


def test_tooltip_cancel_pending_hides(tk_root):
    btn = tk.Button(tk_root, text="Run")
    tip = Tooltip(btn, "x", delay_ms=1000)
    _fake_enter(tip, btn)
    tip._on_leave(None)
    tk_root.update_idletasks()
    assert tip._tip is None


def test_tooltip_set_text_updates_visible(tk_root):
    btn = tk.Button(tk_root, text="Run")
    tip = Tooltip(btn, "old", delay_ms=10)
    _fake_enter(tip, btn)
    assert _wait_until(lambda: tip._tip is not None, root=tk_root)
    tip.set_text("new")
    tk_root.update_idletasks()
    label = getattr(tip._tip, "_label", None)
    assert label is not None
    assert label.cget("text") == "new"
    tip._on_leave(None)


def test_tooltip_callable_text(tk_root):
    btn = tk.Button(tk_root, text="Run")
    counter = MagicMock(return_value="dynamic text")
    tip = Tooltip(btn, counter, delay_ms=10)
    _fake_enter(tip, btn)
    assert _wait_until(lambda: tip._tip is not None, root=tk_root)
    counter.assert_called()
    tip._on_leave(None)


def test_tooltip_callable_raising_returns_empty(tk_root):
    def boom():
        raise RuntimeError("nope")
    btn = tk.Button(tk_root, text="Run")
    tip = Tooltip(btn, boom, delay_ms=10)
    _fake_enter(tip, btn)
    assert _wait_until(lambda: tip._tip is not None, root=tk_root)
    label = getattr(tip._tip, "_label", None)
    assert label is not None
    assert label.cget("text") == ""
    tip._on_leave(None)


def test_tooltip_destroyed_with_widget(tk_root):
    btn = tk.Button(tk_root, text="x")
    tip = Tooltip(btn, "x", delay_ms=10)
    btn.destroy()
    assert tip._tip is None
