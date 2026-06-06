"""Lightweight tooltip widget for Tk/ttk.

A ``Tooltip`` is attached to any widget and shows a small Toplevel
next to the cursor on hover. The tooltip is non-modal, follows the
cursor, and hides itself as soon as the pointer leaves the bound
widget. No third-party dependency, no images.

Usage::

    btn = ttk.Button(parent, text="Run")
    Tooltip(btn, "Run the consolidation")

The widget is a thin wrapper — it does not own its data and can be
garbage-collected normally once the underlying widget is destroyed.
"""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Optional

_logger = logging.getLogger(__name__)

_DEFAULT_DELAY_MS = 400
_DEFAULT_OFFSET_PX = 12


class Tooltip:
    """Bind a tooltip to a Tk widget.

    Parameters
    ----------
    widget:
        The widget to attach the tooltip to. Must support the standard
        ``<Enter>``, ``<Leave>``, ``<Motion>``, and ``<Destroy>``
        events (all built-in Tk widgets do).
    text:
        Either a plain string or a callable that returns the text
        dynamically. The callable form is useful for status messages
        that depend on the current state of the application.
    delay_ms:
        Hover delay before the tooltip appears.
    """

    def __init__(
        self,
        widget: tk.Misc,
        text: str,
        delay_ms: int = _DEFAULT_DELAY_MS,
    ) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms

        self._tip: Optional[tk.Toplevel] = None
        self._after_id: Optional[str] = None
        self._last_x = 0
        self._last_y = 0

        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<Motion>", self._on_motion, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")
        widget.bind("<Destroy>", self._on_destroy, add="+")

    def set_text(self, text: str) -> None:
        """Replace the tooltip text. Updates the visible window if any."""
        self.text = text
        if self._tip is not None and self._tip.winfo_exists():
            label = getattr(self._tip, "_label", None)
            if label is not None:
                label.configure(text=text)

    def _on_enter(self, event: tk.Event) -> None:
        self._last_x, self._last_y = event.x_root, event.y_root
        self._cancel_pending()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _on_leave(self, _event: Optional[tk.Event] = None) -> None:
        self._cancel_pending()
        self._hide()

    def _on_motion(self, event: tk.Event) -> None:
        self._last_x, self._last_y = event.x_root, event.y_root
        if self._tip is not None and self._tip.winfo_exists():
            self._tip.geometry(
                f"+{self._last_x + _DEFAULT_OFFSET_PX}+{self._last_y + _DEFAULT_OFFSET_PX}"
            )

    def _on_destroy(self, _event: tk.Event) -> None:
        self._cancel_pending()
        self._hide()

    def _cancel_pending(self) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _show(self) -> None:
        self._after_id = None
        if self._tip is not None and self._tip.winfo_exists():
            return
        try:
            tip = tk.Toplevel(self.widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(
                f"+{self._last_x + _DEFAULT_OFFSET_PX}+{self._last_y + _DEFAULT_OFFSET_PX}"
            )
            frame = ttk.Frame(tip, relief="solid", borderwidth=1, padding=4)
            frame.pack()
            label = ttk.Label(
                frame,
                text=self._resolved_text(),
                background="#ffffe0",
                foreground="#212529",
                wraplength=320,
                justify="left",
            )
            label.pack()
            tip._label = label  # type: ignore[attr-defined]
            self._tip = tip
        except tk.TclError as e:
            # The widget tree may have been destroyed between the
            # after-schedule and the show call. Silently ignore —
            # the tooltip simply won't appear.
            _logger.debug("Tooltip show failed: %s", e)

    def _resolved_text(self) -> str:
        if callable(self.text):
            try:
                return str(self.text())
            except Exception as e:  # noqa: BLE001
                _logger.debug("Tooltip text callable raised: %s", e)
                return ""
        return str(self.text)

    def _hide(self) -> None:
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


__all__ = ["Tooltip"]
