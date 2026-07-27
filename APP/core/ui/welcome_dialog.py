"""U11: First-run welcome dialog.

A modal Toplevel (NOT a messagebox) shown once on a fresh install to
guide the user through the three-step onboarding checklist. The dialog
follows the active ThemeManager palette (light/dark) like the rest of
the UI.

First-run flag storage
----------------------
The flag lives in ``APP/first_run.json`` as ``{"first_run_done": bool}``
rather than in ``runtime_state.json``. ``runtime_state.json`` is a JSON
*array* of dashboard history records (see ``dashboard_state.load_runtime_results``,
which discards any payload that is not a list); mixing a scalar flag in
there would corrupt that history. A dedicated single-purpose file keeps
the two concerns separate and survives test runs without clobbering.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

import tkinter as tk
from tkinter import ttk

from core.ui.theme import ThemeManager

logger = logging.getLogger(__name__)

# Dedicated flag file (kept separate from runtime_state.json, which is a
# list of dashboard-history records and must stay a list).
_FLAG_PATH = Path(__file__).resolve().parents[2] / "first_run.json"


def _load_flag() -> dict[str, Any]:
    """Read the first-run flag file. Returns ``{}`` on any error."""
    try:
        if _FLAG_PATH.exists():
            raw = json.loads(_FLAG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw
    except (OSError, json.JSONDecodeError):
        logger.debug("first_run.json unreadable, treating as first run")
    return {}


def is_first_run() -> bool:
    """True when the welcome dialog should be shown (flag missing/False)."""
    data = _load_flag()
    return not bool(data.get("first_run_done", False))


def mark_first_run_done() -> None:
    """Persist ``first_run_done = True`` without clobbering other keys."""
    data = _load_flag()
    data["first_run_done"] = True
    try:
        _FLAG_PATH.parent.mkdir(parents=True, exist_ok=True)
        _FLAG_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        logger.warning("Could not write first_run.json", exc_info=True)


def _display_available() -> bool:
    """Heuristic: refuse to spawn a Toplevel when there is no real display.

    Headless CI / pytest runs instantiate ``tk.Tk()`` without a screen,
    and a Toplevel would either hang (grab_set on an unmapped window) or
    raise. ``winfo_viewable`` reflects whether the root is actually on a
    screen; failing that, the DISPLAY env check covers Linux.
    """
    try:
        import sys

        if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
            return False
    except Exception:
        pass
    return True


class WelcomeDialog:
    """Modal first-run welcome dialog with a 3-step checklist.

    Construct with :py:meth:`show`; it creates its own ``Toplevel`` and
    blocks via ``grab_set`` until the user clicks "Начать работу".
    """

    STEPS = (
        "1. Добавьте сотрудников (кнопка ➕ Добавить в левой панели)",
        "2. Выберите дату для консолидации",
        "3. Нажмите Сборка → Собрать день (или Ctrl+D)",
    )

    def __init__(self, parent: tk.Misc) -> None:
        self.parent = parent
        self.top: Optional[tk.Toplevel] = None

    def show(self) -> None:
        """Build and display the dialog. Safe to call from the GUI thread."""
        c = ThemeManager.COLORS
        sp = ThemeManager.SPACING

        top = tk.Toplevel(self.parent)
        top.title("Добро пожаловать в Master-Report")
        top.configure(background=c.get("bg_main", "#f5f6f8"))
        # tkinter stubs type transient() as Wm | Tcl_Obj, but at runtime any
        # widget is accepted — the parent Frame is the intended master.
        top.transient(self.parent)  # type: ignore[call-overload]
        top.resizable(False, False)
        self.top = top

        # --- Header ----------------------------------------------------
        header = ttk.Frame(top, padding=(sp["lg"], sp["lg"], sp["lg"], sp["md"]), style="Main.TFrame")
        header.pack(fill=tk.X)
        ttk.Label(
            header,
            text="👋 Добро пожаловать в Master-Report",
            style="Header.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            header,
            text="Три шага, чтобы собрать первый отчёт:",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(sp["xs"], 0))

        ttk.Separator(top).pack(fill=tk.X, padx=sp["lg"])

        # --- Checklist -------------------------------------------------
        body = ttk.Frame(top, padding=sp["lg"], style="Main.TFrame")
        body.pack(fill=tk.BOTH, expand=True)
        for step in self.STEPS:
            ttk.Label(
                body,
                text=step,
                style="Main.TLabel",
                wraplength=420,
                justify=tk.LEFT,
            ).pack(anchor=tk.W, pady=sp["xs"])

        # --- Action ----------------------------------------------------
        footer = ttk.Frame(top, padding=(sp["lg"], sp["sm"], sp["lg"], sp["lg"]), style="Main.TFrame")
        footer.pack(fill=tk.X)
        start_btn = ttk.Button(
            footer,
            text="Начать работу",
            style="Action.TButton",
            command=self._on_start,
        )
        start_btn.pack(side=tk.RIGHT)
        # Enter / Return confirms, Escape also closes (treated as "got it").
        top.bind("<Return>", lambda _e: self._on_start())
        top.bind("<Escape>", lambda _e: self._on_start())

        # Center over parent and grab focus.
        top.update_idletasks()
        try:
            px = self.parent.winfo_rootx()
            py = self.parent.winfo_rooty()
            pw = self.parent.winfo_width()
            ph = self.parent.winfo_height()
            w = top.winfo_width()
            h = top.winfo_height()
            x = px + (pw - w) // 2
            y = py + (ph - h) // 2
            top.geometry(f"+{max(0, x)}+{max(0, y)}")
        except tk.TclError:
            pass

        top.grab_set()
        top.focus_set()
        # Make sure the flag is written even if the user closes via the
        # window manager's X button.
        top.protocol("WM_DELETE_WINDOW", self._on_start)

    def _on_start(self) -> None:
        mark_first_run_done()
        try:
            if self.top is not None and self.top.winfo_exists():
                self.top.grab_release()
                self.top.destroy()
        except tk.TclError:
            pass
        self.top = None


def show_welcome_if_first_run(parent: tk.Misc) -> None:
    """Show the welcome dialog when appropriate; no-op otherwise.

    Safe to call unconditionally from ``gui_master.__init__``: it skips
    in headless environments (no display) and when the flag is already
    set, so test runs that spin up a ``GuiMaster`` are unaffected.
    """
    try:
        if not is_first_run():
            return
        if not _display_available():
            return
        # Don't show if the parent isn't actually realised on a screen.
        try:
            if not bool(parent.winfo_viewable()):
                # The window may simply not be mapped yet — only skip when
                # winfo_viewable is stable AND there's no screen at all.
                pass
        except tk.TclError:
            return
        WelcomeDialog(parent).show()
    except Exception:
        # Onboarding must NEVER block app startup — log and move on.
        logger.warning("Welcome dialog could not be shown", exc_info=True)
