"""Status bar widget showing the active operation with progress, elapsed time, and cancel.

Addresses the user pain point: "не понятно сколько программа еще будет работать".
The bar shows:
  - operation name (Russian label from OperationState)
  - progress percentage
  - elapsed time
  - linear ETA estimate
  - Cancel button (visible only while busy)

Sits at the bottom of the sidebar, replacing the single-purpose StatsPanel progress.
"""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from core.ui.theme import ThemeManager
from core.ui.operation_state import (
    OPERATION_LABELS,
    OperationState,
    OperationSnapshot,
    OperationType,
)


def _format_duration(seconds: float) -> str:
    """Format seconds as M:SS (e.g. 0:42, 12:30, 1:05:30 for >1h)."""
    if seconds < 0:
        seconds = 0
    s = int(seconds)
    if s < 3600:
        return f"{s // 60}:{s % 60:02d}"
    return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"


class OperationStatusBar(ttk.Frame):
    """Bottom-of-sidebar status bar showing the running operation."""

    def __init__(
        self,
        parent: tk.Misc,
        operation_state: OperationState,
        on_cancel: Callable[[], None],
    ) -> None:
        super().__init__(parent, style="StatusBar.TFrame", padding=(6, 4))
        self._operation_state = operation_state
        self._on_cancel = on_cancel

        self._label_var = tk.StringVar(value="")
        self._progress_var = tk.DoubleVar(value=0.0)
        self._elapsed_var = tk.StringVar(value="")
        self._eta_var = tk.StringVar(value="")
        self._file_var = tk.StringVar(value="")  # FIX-009: current file

        self._title_label = ttk.Label(
            self,
            textvariable=self._label_var,
            style="StatusBar.TLabel",
            font=ThemeManager.FONTS["caption_bold"],
            anchor=tk.W,
        )
        self._title_label.pack(fill=tk.X, anchor=tk.W)

        # FIX-009: current file label, shown below the operation title
        # when a file is being processed. Small font, muted colour.
        self._file_label = ttk.Label(
            self,
            textvariable=self._file_var,
            style="StatusBar.TLabel",
            font=ThemeManager.FONTS["micro"],
            anchor=tk.W,
        )
        self._file_label.pack(fill=tk.X, anchor=tk.W)

        row = ttk.Frame(self, style="StatusBar.TFrame")
        row.pack(fill=tk.X, pady=(2, 0))

        self._progress_bar = ttk.Progressbar(
            row,
            orient=tk.HORIZONTAL,
            mode="determinate",
            maximum=100.0,
            variable=self._progress_var,
        )
        self._progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self._pct_label = ttk.Label(
            row,
            text="0%",
            style="StatusBar.TLabel",
            width=5,
            anchor=tk.E,
        )
        self._pct_label.pack(side=tk.LEFT, padx=(4, 0))

        timings = ttk.Frame(self, style="StatusBar.TFrame")
        timings.pack(fill=tk.X, pady=(2, 0))

        self._elapsed_label = ttk.Label(
            timings,
            textvariable=self._elapsed_var,
            style="StatusBar.TLabel",
            font=ThemeManager.FONTS["mono"],
        )
        self._elapsed_label.pack(side=tk.LEFT)

        self._eta_label = ttk.Label(
            timings,
            textvariable=self._eta_var,
            style="StatusBar.TLabel",
            font=ThemeManager.FONTS["micro"],
        )
        self._eta_label.pack(side=tk.RIGHT)

        self._cancel_btn = ttk.Button(
            self,
            text="⛔ Отмена",
            style="Danger.TButton",
            command=self._on_cancel_clicked,
            width=12,
        )
        self._cancel_btn.pack(fill=tk.X, pady=(4, 0))

        self._operation_state.add_listener(self._on_snapshot)
        self._render(OperationType.NONE, 0.0, None, False, "")

    def _on_cancel_clicked(self) -> None:
        try:
            self._on_cancel()
        except Exception:
            pass

    def _on_snapshot(self, snap: OperationSnapshot) -> None:
        # ``self.after`` raises ``TclError`` once the widget is torn down.
        # If that happens, unsubscribe from OperationState so we stop
        # receiving snapshots (otherwise every future notify would
        # schedule another doomed ``after`` call and log a TclError).
        try:
            self.after(0, lambda: self._render(
                snap.current, snap.progress, snap.started_at, snap.cancelling,
                snap.current_file,
            ))
        except tk.TclError:
            self._operation_state.remove_listener(self._on_snapshot)

    def _render(
        self,
        current: OperationType,
        progress: float,
        started_at: Optional[float],
        cancelling: bool,
        current_file: str = "",
    ) -> None:
        busy = current is not OperationType.NONE
        if not busy:
            self._label_var.set("Готово к работе")
            self._progress_var.set(0.0)
            self._elapsed_var.set("")
            self._eta_var.set("")
            self._file_var.set("")
            self._pct_label.config(text="")
            self._cancel_btn.config(state="disabled")
            return

        if cancelling:
            label = f"⏳ {OPERATION_LABELS.get(current, '')} (отмена...)"
        else:
            label = f"🔄 {OPERATION_LABELS.get(current, '')}"
        self._label_var.set(label)
        # FIX-009: show current file below the operation title
        self._file_var.set(f"📄 {current_file}" if current_file else "")
        self._progress_var.set(progress)
        self._pct_label.config(text=f"{progress:.0f}%")

        if started_at is not None:
            elapsed = time.monotonic() - started_at
            self._elapsed_var.set(f"⏱ {_format_duration(elapsed)}")
            if progress > 1.0 and progress < 100.0:
                eta = elapsed / progress * (100.0 - progress)
                self._eta_var.set(f"~ {_format_duration(eta)} осталось")
            elif progress >= 100.0:
                self._eta_var.set("завершено")
            else:
                self._eta_var.set("")
        else:
            self._elapsed_var.set("")
            self._eta_var.set("")

        self._cancel_btn.config(state="disabled" if cancelling else "normal")
