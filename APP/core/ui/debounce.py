"""Tiny debounce helper for tkinter variable traces.

The employee search box fires ``filter_tree`` on every keystroke via a
``StringVar`` trace. For a list of a few hundred employees that's still
cheap, but the goal is to keep the GUI snappy under the maximum data
load and avoid re-running the filter while the user is still typing.

The implementation schedules the callback via ``widget.after`` so it
runs on the same Tk thread — no locking, no extra dependency.
"""
from __future__ import annotations

from typing import Callable, Optional


class Debouncer:
    """Call ``fn`` no more than once per ``delay_ms`` milliseconds.

    A new call resets the timer. The scheduled ``after`` id is held on
    the instance, so cancelling the widget (or replacing the callback)
    also cancels any pending call.

    Usage::

        debouncer = Debouncer(self.search_var, self.controller.filter_tree, 300)
        self.search_var.trace_add("write", lambda *_: debouncer())

        # When the widget is destroyed:
        debouncer.cancel()
    """

    def __init__(
        self,
        widget,
        fn: Callable[[], None],
        delay_ms: int = 300,
    ) -> None:
        self._widget = widget
        self._fn = fn
        self._delay_ms = int(delay_ms)
        self._after_id: Optional[str] = None

    def __call__(self) -> None:
        """Schedule ``fn`` to run after ``delay_ms``.

        Resets the timer if a call is already pending. Safe to call
        from inside a trace callback (the trace fires synchronously,
        the scheduled call runs later).
        """
        self.cancel()
        try:
            self._after_id = self._widget.after(self._delay_ms, self._fire)
        except Exception:
            self._after_id = None

    def cancel(self) -> None:
        """Cancel any pending call. Idempotent."""
        if self._after_id is None:
            return
        try:
            self._widget.after_cancel(self._after_id)
        except Exception:
            pass
        self._after_id = None

    def _fire(self) -> None:
        self._after_id = None
        try:
            self._fn()
        except Exception:
            pass

    @property
    def pending(self) -> bool:
        return self._after_id is not None


__all__ = ["Debouncer"]
