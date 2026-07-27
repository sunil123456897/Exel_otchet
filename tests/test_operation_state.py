"""Tests for the global operation state machine."""
import threading
import time

import pytest
from core.ui.operation_state import (
    OPERATION_LABELS,
    OperationSnapshot,
    OperationState,
    OperationType,
)


@pytest.fixture
def state():
    return OperationState()


def test_initial_state_is_idle(state):
    snap = state.snapshot()
    assert snap.current is OperationType.NONE
    assert snap.cancelling is False
    assert snap.progress == 0.0
    assert snap.started_at is None
    assert not state.is_busy
    assert not state.is_cancelling


def test_begin_returns_true_when_idle(state):
    assert state.begin(OperationType.CONSOLIDATION_DAY) is True
    assert state.is_busy
    assert state.current is OperationType.CONSOLIDATION_DAY
    assert state.started_at is not None
    assert state.progress == 0.0


def test_begin_returns_false_when_busy(state):
    assert state.begin(OperationType.CONSOLIDATION_DAY) is True
    assert state.begin(OperationType.RSCH_DAY) is False
    assert state.current is OperationType.CONSOLIDATION_DAY


def test_end_releases_busy_state(state):
    state.begin(OperationType.CONSOLIDATION_DAY)
    state.end()
    assert not state.is_busy
    assert state.current is OperationType.NONE
    assert state.started_at is None
    assert state.progress == 0.0


def test_end_is_idempotent(state):
    state.end()
    state.end()
    assert not state.is_busy


def test_request_cancel_sets_event_and_flag(state):
    state.begin(OperationType.CONSOLIDATION_MONTH)
    assert state.request_cancel() is True
    assert state.is_cancelling
    assert state.cancel_event.is_set()


def test_request_cancel_when_idle_returns_false(state):
    assert state.request_cancel() is False


def test_end_clears_cancel_flag_and_event(state):
    state.begin(OperationType.CONSOLIDATION_DAY)
    state.request_cancel()
    state.end()
    assert not state.is_cancelling
    assert not state.cancel_event.is_set()


def test_progress_clamps_to_range(state):
    state.begin(OperationType.CONSOLIDATION_DAY)
    state.set_progress(-5.0)
    assert state.progress == 0.0
    state.set_progress(150.0)
    assert state.progress == 100.0
    state.set_progress(42.5)
    assert state.progress == 42.5


def test_set_progress_is_noop_when_idle(state):
    state.set_progress(50.0)
    assert state.progress == 0.0


def test_listener_fires_on_transition(state):
    events: list[OperationSnapshot] = []
    state.add_listener(events.append)
    state.begin(OperationType.RSCH_DAY)
    state.set_progress(25.0)
    state.request_cancel()
    state.end()
    assert len(events) == 4
    assert events[0].current is OperationType.RSCH_DAY
    assert events[1].progress == 25.0
    assert events[2].cancelling is True
    assert events[3].current is OperationType.NONE


def test_removed_listener_does_not_fire(state):
    events: list = []
    def listener(snap):
        events.append(snap)
    state.add_listener(listener)
    state.remove_listener(listener)
    state.begin(OperationType.RSCH_DAY)
    assert events == []


def test_broken_listener_does_not_break_others(state):
    events: list = []

    def bad(_snap):
        raise RuntimeError("boom")

    state.add_listener(bad)
    state.add_listener(events.append)
    state.begin(OperationType.CONSOLIDATION_DAY)
    assert len(events) == 1


def test_can_restart_after_end(state):
    state.begin(OperationType.CONSOLIDATION_DAY)
    state.end()
    assert state.begin(OperationType.RSCH_DAY) is True
    assert state.current is OperationType.RSCH_DAY


def test_concurrent_begin_only_one_wins(state):
    winners: list = []
    barrier = threading.Barrier(8)

    def attempt(op: OperationType):
        barrier.wait()
        if state.begin(op):
            winners.append(op)

    threads = [
        threading.Thread(target=attempt, args=(OperationType.CONSOLIDATION_DAY,))
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(winners) == 1
    assert state.current is OperationType.CONSOLIDATION_DAY


def test_label_uses_russian_for_display(state):
    state.begin(OperationType.CONSOLIDATION_MONTH)
    assert OPERATION_LABELS[OperationType.CONSOLIDATION_MONTH] == "Сборка за период"
    snap = state.snapshot()
    assert snap.label == "Сборка за период"


def test_cancel_event_can_be_polled_by_worker(state):
    """The cancel_event must be observable from a worker thread."""
    state.begin(OperationType.CONSOLIDATION_ALL)
    observed = []

    def worker():
        for _ in range(20):
            if state.cancel_event.is_set():
                observed.append("cancelled")
                return
            time.sleep(0.005)
        observed.append("timeout")

    t = threading.Thread(target=worker)
    t.start()
    time.sleep(0.01)
    state.request_cancel()
    t.join(timeout=1.0)
    assert observed == ["cancelled"]
