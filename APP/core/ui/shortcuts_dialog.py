"""U12-A: Keyboard shortcuts reference dialog.

A modal themed ``Toplevel`` (NOT a messagebox) that shows the list of
global keyboard shortcuts available in the application. Follows the
active ThemeManager palette (light/dark) exactly like ``welcome_dialog``
and the rest of the UI.

The shortcut bindings themselves live in ``gui_master._bind_shortcuts``;
this dialog only *displays* them to the user (F1 or the sidebar button).
The list below is intentionally a copy of the bindings so that the help
text does not depend on importing gui_master (which would pull in the
whole GUI stack). If a binding is added in ``_bind_shortcuts``, update
``SHORTCUTS`` here to match.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import tkinter as tk
from tkinter import ttk

from core.ui.theme import ThemeManager

logger = logging.getLogger(__name__)

# Ordered list of (combination, action) pairs shown in the dialog.
# Mirrors the bindings in ``GuiMaster._bind_shortcuts`` — keep in sync.
SHORTCUTS: tuple[tuple[str, str], ...] = (
    ("Ctrl+D", "Собрать отчёт за день"),
    ("Ctrl+Shift+D", "Собрать по всем датам"),
    ("Ctrl+M", "Собрать за период"),
    ("Ctrl+R", "Сформировать РСЧ за день"),
    ("Ctrl+Shift+R", "Сформировать РСЧ за период"),
    ("Ctrl+E", "Сверка данных"),
    ("F5", "Обновить статус"),
    ("Escape", "Отменить операцию"),
)


def _display_available() -> bool:
    """Heuristic: refuse to spawn a Toplevel when there is no real display.

    Mirrors ``welcome_dialog._display_available`` so the dialog never
    hangs a headless CI / pytest run that instantiated ``tk.Tk()`` without
    a screen (``grab_set`` on an unmapped window can hang or raise).
    """
    try:
        import sys

        if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
            return False
    except Exception:
        pass
    return True


class ShortcutsDialog:
    """Modal reference dialog listing all keyboard shortcuts.

    Construct with :py:meth:`show`; it creates its own ``Toplevel`` and
    blocks via ``grab_set`` until the user clicks "Закрыть" (or presses
    Enter / Escape).
    """

    def __init__(self, parent: tk.Misc) -> None:
        self.parent = parent
        self.top: Optional[tk.Toplevel] = None

    def show(self) -> None:
        """Build and display the dialog. Safe to call from the GUI thread."""
        c = ThemeManager.COLORS
        f = ThemeManager.FONTS
        sp = ThemeManager.SPACING

        top = tk.Toplevel(self.parent)
        top.title("Горячие клавиши")
        top.configure(background=c.get("bg_main", "#f5f6f8"))
        top.transient(self.parent)  # type: ignore[call-overload]
        top.resizable(False, False)
        self.top = top

        # --- Header ----------------------------------------------------
        header = ttk.Frame(
            top,
            padding=(sp["lg"], sp["lg"], sp["lg"], sp["md"]),
            style="Main.TFrame",
        )
        header.pack(fill=tk.X)
        ttk.Label(
            header,
            text="⌨ Горячие клавиши",
            style="Header.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            header,
            text="Доступные сочетания клавиш для быстрых действий:",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(sp["xs"], 0))

        ttk.Separator(top).pack(fill=tk.X, padx=sp["lg"])

        # --- Shortcuts table ------------------------------------------
        body = ttk.Frame(top, padding=sp["lg"], style="Main.TFrame")
        body.pack(fill=tk.BOTH, expand=True)

        # Two-column grid: key (mono, right-aligned) | action.
        # Column 0 gets a fixed weight-0 so it hugs the key text; column
        # 1 expands so long action descriptions are never clipped.
        for idx, (combo, action) in enumerate(SHORTCUTS):
            ttk.Label(
                body,
                text=combo,
                font=f["mono"],
                style="Main.TLabel",
                justify=tk.LEFT,
            ).grid(row=idx, column=0, sticky=tk.W, padx=(0, sp["md"]), pady=sp["xs"])
            ttk.Label(
                body,
                text=action,
                style="Main.TLabel",
                wraplength=360,
                justify=tk.LEFT,
            ).grid(row=idx, column=1, sticky=tk.W, pady=sp["xs"])

        body.grid_columnconfigure(0, weight=0)
        body.grid_columnconfigure(1, weight=1)

        # --- Action ---------------------------------------------------
        footer = ttk.Frame(
            top,
            padding=(sp["lg"], sp["sm"], sp["lg"], sp["lg"]),
            style="Main.TFrame",
        )
        footer.pack(fill=tk.X)
        close_btn = ttk.Button(
            footer,
            text="Закрыть",
            style="Action.TButton",
            command=self._on_close,
        )
        close_btn.pack(side=tk.RIGHT)
        # Enter / Return closes, Escape closes too.
        top.bind("<Return>", lambda _e: self._on_close())
        top.bind("<Escape>", lambda _e: self._on_close())

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
        # Closing via the window manager's X button is equivalent to
        # "Закрыть" — just tear the dialog down without any side effects.
        top.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self) -> None:
        try:
            if self.top is not None and self.top.winfo_exists():
                self.top.grab_release()
                self.top.destroy()
        except tk.TclError:
            pass
        self.top = None


def show_shortcuts(parent: tk.Misc) -> None:
    """Show the shortcuts reference dialog.

    Safe to call unconditionally (F1 handler, sidebar button): it skips
    silently in headless environments and swallows any Tk error so a
    broken help popup can never crash the app.
    """
    try:
        if not _display_available():
            return
        ShortcutsDialog(parent).show()
    except Exception:
        # Help must NEVER block the app — log and move on.
        logger.warning("Shortcuts dialog could not be shown", exc_info=True)
