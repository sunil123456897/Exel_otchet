"""Tests for the Debouncer helper used by the employee search box."""
import time
import tkinter as tk
from unittest.mock import MagicMock

import pytest
from core.ui.debounce import Debouncer


@pytest.fixture(scope="module")
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"Tk not available: {e}")
    root.withdraw()
    yield root
    root.destroy()


def _pump(root, ms):
    """Advance the Tk event loop and real wall-clock by ~ms.

    ``root.update()`` runs any after() callbacks whose deadline has
    passed; ``time.sleep`` makes sure the test waits long enough for
    those deadlines to elapse.
    """
    deadline = time.monotonic() + ms / 1000.0
    while time.monotonic() < deadline:
        root.update()
        time.sleep(0.005)


def test_call_invokes_callback_after_delay(tk_root):
    cb = MagicMock()
    deb = Debouncer(tk_root, cb, delay_ms=50)
    deb()
    assert cb.call_count == 0
    _pump(tk_root, 100)
    assert cb.call_count == 1


def test_rapid_calls_only_fire_once(tk_root):
    cb = MagicMock()
    deb = Debouncer(tk_root, cb, delay_ms=80)
    for _ in range(5):
        deb()
        _pump(tk_root, 10)  # 10 < 80, so timer keeps resetting
    assert cb.call_count == 0
    _pump(tk_root, 200)
    assert cb.call_count == 1


def test_cancel_prevents_fire(tk_root):
    cb = MagicMock()
    deb = Debouncer(tk_root, cb, delay_ms=50)
    deb()
    deb.cancel()
    _pump(tk_root, 100)
    assert cb.call_count == 0


def test_pending_reflects_schedule_state(tk_root):
    cb = MagicMock()
    deb = Debouncer(tk_root, cb, delay_ms=100)
    assert deb.pending is False
    deb()
    assert deb.pending is True
    _pump(tk_root, 150)
    assert deb.pending is False


def test_callback_exception_does_not_break_debouncer(tk_root):
    cb = MagicMock(side_effect=ValueError("boom"))
    deb = Debouncer(tk_root, cb, delay_ms=20)
    deb()
    _pump(tk_root, 80)
    # First call: scheduled, fired, raised and was swallowed.
    assert cb.call_count == 1
    # Second call: still works.
    deb()
    _pump(tk_root, 80)
    assert cb.call_count == 2


def test_repeated_calls_within_window_keep_extending(tk_root):
    """Each call inside the window resets the timer; last call wins."""
    cb = MagicMock()
    deb = Debouncer(tk_root, cb, delay_ms=60)
    for _ in range(3):
        deb()
        _pump(tk_root, 30)  # 30 < 60 → reset
    _pump(tk_root, 100)
    assert cb.call_count == 1
