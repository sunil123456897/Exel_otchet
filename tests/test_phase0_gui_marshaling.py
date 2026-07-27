"""Phase 0 — stability: GUI progress callback marshaling.

Regression for the worker-thread → Tk race. The consolidation progress
callback used to call ``root.event_generate`` directly from the
consolidation worker thread; under load (several concurrent
consolidations + cancel) this races the Tcl event loop and corrupts Tk
state. The callback must now marshal every Tk call onto the GUI thread
via ``root.after(0, …)``.

We can't spin a real Tk root in this headless harness, so we bind a
fake root that records every ``after``/``event_generate`` dispatch and
assert the worker touches Tk only through the ``after`` channel.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from core.ui.gui_master import GuiMaster  # noqa: F401 — import guards wiring


class _FakeRoot:
    """Stand-in for tk.Tk that records Tk-channel dispatches."""

    def __init__(self) -> None:
        self.after_calls: list[tuple[int, object]] = []
        self.event_generate_calls: list[tuple[str, dict]] = []
        self._lock = threading.Lock()

    def after(self, ms: int, fn) -> None:
        # Record but DO NOT execute — the point is that the worker must
        # hand the call off, not run it inline.
        with self._lock:
            self.after_calls.append((ms, fn))

    def event_generate(self, sequence: str, **kw) -> None:
        with self._lock:
            self.event_generate_calls.append((sequence, kw))


def _build_handler(fake_root, operation_state):
    """Construct a GuiMaster-shaped bound method for the progress callback.

    We bypass ``__init__`` (which builds the whole UI) and instead pull
    the unbound method, binding the minimum state the callback needs.
    """
    instance = SimpleNamespace(
        root=fake_root,
        operation_state=operation_state,
    )
    # Grab the function defined on GuiMaster and bind it to our stub so
    # we test the real code path, not a copy.
    fn = GuiMaster._on_consolidation_progress.__get__(instance, SimpleNamespace)
    return fn


@pytest.fixture
def fake_root():
    return _FakeRoot()


@pytest.fixture
def operation_state():
    state = MagicMock()
    state.set_progress = MagicMock()
    return state


def test_progress_callback_marshals_event_generate_via_after(
    fake_root, operation_state
):
    """The worker must not call event_generate directly.

    Calling ``root.event_generate`` from a background thread races the
    Tcl event loop. After the fix the callback should defer it to the
    GUI thread via ``root.after(0, …)``.
    """
    handler = _build_handler(fake_root, operation_state)

    # Simulate the consolidation worker calling back.
    handler(42.0)

    # OperationState update is thread-safe and may run inline.
    operation_state.set_progress.assert_called_once_with(42.0)
    # The Tk call must be deferred, not executed inline.
    assert len(fake_root.after_calls) == 1
    ms, deferred = fake_root.after_calls[0]
    assert ms == 0
    # No direct event_generate from the worker — only the deferred one.
    assert fake_root.event_generate_calls == []
    # Executing the deferred closure on the GUI thread issues the event.
    deferred()
    assert fake_root.event_generate_calls == [("<<TitleUpdate>>", {})]


def test_progress_callback_is_safe_from_multiple_worker_threads(
    fake_root, operation_state
):
    """Many concurrent workers must all funnel through ``root.after``.

    This mirrors the stress scenario from the plan: several parallel
    reconciliations pushing progress simultaneously. Before the fix this
    sprayed ``event_generate`` directly from N threads; now every call
    lands on the ``after`` channel.
    """
    handler = _build_handler(fake_root, operation_state)

    barrier = threading.Barrier(10)

    def worker(i: int) -> None:
        barrier.wait()
        for p in (i * 10, i * 10 + 5):
            handler(float(p))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=2.0)

    # Every worker call queued exactly one after(0, …).
    assert len(fake_root.after_calls) == 20
    # None of them touched Tk directly.
    assert fake_root.event_generate_calls == []
