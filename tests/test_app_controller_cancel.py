"""Tests for the cancellation helpers in app_controller.

The cancel path (``_is_cancelled`` + ``_cancel_message``) is shared by all
six ``run_*`` operations but previously had no tests — the reviewer flagged
that operation cancellation was unverified. These pin:

* ``_is_cancelled`` — the cheap per-iteration check (None / unset / set).
* ``_cancel_message`` — reports cancellation via ``on_complete(False, …)``
  and renames in-flight ``*.xlsx`` outputs to ``.partial`` so a cancelled
  run never leaves a half-written file that looks complete.

The full ``AppController`` orchestrator is not constructed here (it wires a
real DiscoveryService + thread pool in ``__init__``); these helpers are the
module-level cancel mechanism and are testable in isolation.
"""
from __future__ import annotations

import threading

import core.app.cancellation as cancellation
import core.app_controller as ac


# ── _is_cancelled ──────────────────────────────────────────────────────


def test_is_cancelled_none_is_false():
    assert ac._is_cancelled(None) is False


def test_is_cancelled_unset_event_is_false():
    assert ac._is_cancelled(threading.Event()) is False


def test_is_cancelled_set_event_is_true():
    ev = threading.Event()
    ev.set()
    assert ac._is_cancelled(ev) is True


# ── _cancel_message ────────────────────────────────────────────────────


def test_cancel_message_reports_failure(tmp_path, monkeypatch):
    # Hermetic: don't touch the real local-copy cache.
    monkeypatch.setattr(cancellation, "cleanup_local_copy_cache", lambda **kw: None)

    calls = []
    ac._cancel_message(lambda ok, msg, path: calls.append((ok, msg, path)))

    assert len(calls) == 1
    ok, message, path = calls[0]
    assert ok is False
    assert path is None
    assert "отменена" in str(message).lower()


def test_cancel_message_marks_partial_outputs(tmp_path, monkeypatch):
    monkeypatch.setattr(cancellation, "cleanup_local_copy_cache", lambda **kw: None)

    out = tmp_path / "report.xlsx"
    out.write_bytes(b"half-written")

    received = {}
    ac._cancel_message(
        lambda ok, msg, path: received.update(ok=ok, msg=str(msg)),
        out,
    )

    assert received["ok"] is False
    # The in-flight file was renamed to a .partial variant, and the user
    # message mentions it.
    assert not out.exists()
    assert any(p.name.startswith("report") for p in tmp_path.iterdir())
    assert "partial" in received["msg"].lower()


def test_cancel_message_handles_missing_output(tmp_path, monkeypatch):
    """A path that was never created must not crash the cancel branch."""
    monkeypatch.setattr(cancellation, "cleanup_local_copy_cache", lambda **kw: None)

    calls = []
    ac._cancel_message(
        lambda ok, msg, path: calls.append((ok, msg, path)),
        tmp_path / "never_created.xlsx",
    )
    assert calls and calls[0][0] is False
