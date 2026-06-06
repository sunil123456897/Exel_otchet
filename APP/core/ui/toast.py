"""Non-modal toast notifications.

Replaces blocking ``messagebox.showinfo``/``showerror`` for non-critical
notifications. Stack of up to 3 toasts in the bottom-right corner of the
root window, each fades out after ``duration_ms``.

For notifications that genuinely require user choice (e.g. "open the
finished file?"), keep using ``messagebox.askyesno``.
"""
from __future__ import annotations

import logging
import tkinter as tk
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ToastLevel(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


_LEVEL_COLORS = {
    ToastLevel.INFO: ("#17a2b8", "#ffffff"),
    ToastLevel.SUCCESS: ("#28a745", "#ffffff"),
    ToastLevel.WARNING: ("#ffc107", "#212529"),
    ToastLevel.ERROR: ("#dc3545", "#ffffff"),
}

_LEVEL_ICONS = {
    ToastLevel.INFO: "ℹ",
    ToastLevel.SUCCESS: "✓",
    ToastLevel.WARNING: "⚠",
    ToastLevel.ERROR: "✕",
}


@dataclass
class _Toast:
    level: ToastLevel
    title: str
    message: str
    frame: tk.Frame
    after_id: Optional[str]


class ToastManager:
    """Stack of non-modal toast popups anchored to a Tk root."""

    def __init__(self, root: tk.Misc, max_stack: int = 3) -> None:
        self._root = root
        self._max_stack = max_stack
        self._stack: list[_Toast] = []

    def show(
        self,
        level: ToastLevel,
        title: str,
        message: str,
        duration_ms: int = 4000,
    ) -> None:
        """Show a toast. Older toasts above ``max_stack`` are dismissed early."""
        try:
            bg, fg = _LEVEL_COLORS[level]
            icon = _LEVEL_ICONS[level]
        except (KeyError, tk.TclError):
            return

        while len(self._stack) >= self._max_stack:
            self._dismiss(self._stack[0], early=True)

        frame = tk.Frame(
            self._root,
            bg=bg,
            highlightthickness=0,
            bd=0,
            padx=12,
            pady=8,
        )

        title_label = tk.Label(
            frame,
            text=f"{icon}  {title}",
            bg=bg,
            fg=fg,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        title_label.pack(fill="x")

        if message:
            msg_label = tk.Label(
                frame,
                text=message,
                bg=bg,
                fg=fg,
                font=("Segoe UI", 9),
                anchor="w",
                wraplength=320,
                justify="left",
            )
            msg_label.pack(fill="x", pady=(2, 0))

        frame.place(relx=1.0, rely=1.0, anchor="se", x=-20, y=-20)

        toast = _Toast(
            level=level, title=title, message=message, frame=frame, after_id=None
        )
        after_id = self._root.after(duration_ms, lambda t=toast: self._dismiss(t))
        toast.after_id = after_id
        self._stack.append(toast)
        self._repack()

    def _dismiss(self, toast: _Toast, early: bool = False) -> None:
        if toast not in self._stack:
            return
        if toast.after_id is not None:
            try:
                self._root.after_cancel(toast.after_id)
            except tk.TclError:
                pass
        self._stack.remove(toast)
        try:
            toast.frame.destroy()
        except tk.TclError:
            pass
        if not early:
            self._repack()

    def _repack(self) -> None:
        """Re-anchor all visible toasts vertically, newest at the bottom."""
        offset = 20
        for toast in reversed(self._stack):
            try:
                toast.frame.place(relx=1.0, rely=1.0, anchor="se", x=-20, y=-offset)
            except tk.TclError:
                continue
            try:
                toast.frame.update_idletasks()
                offset += toast.frame.winfo_reqheight() + 8
            except tk.TclError:
                offset += 60

    def info(self, title: str, message: str = "", **kwargs) -> None:
        self.show(ToastLevel.INFO, title, message, **kwargs)

    def success(self, title: str, message: str = "", **kwargs) -> None:
        self.show(ToastLevel.SUCCESS, title, message, **kwargs)

    def warning(self, title: str, message: str = "", **kwargs) -> None:
        self.show(ToastLevel.WARNING, title, message, **kwargs)

    def error(self, title: str, message: str = "", **kwargs) -> None:
        self.show(ToastLevel.ERROR, title, message, **kwargs)
