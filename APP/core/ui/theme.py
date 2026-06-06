"""Centralised colour palette and ttk style configuration.

Exposes two palettes (light + dark) and a runtime ``set_theme`` that
re-applies the ttk styles so widgets that are created later pick up
the active palette. Widgets already in the tree pick up the changes
on the next ``configure`` call, which the GuiMaster triggers after
the user switches themes.
"""
from __future__ import annotations

from tkinter import ttk
from typing import ClassVar, Optional

_LIGHT = {
    "primary": "#1f4e79",
    "primary_active": "#153654",
    "success": "#28a745",
    "success_active": "#218838",
    "danger": "#dc3545",
    "warning": "#ffc107",
    "info": "#17a2b8",
    "info_active": "#138496",
    "bg_main": "#f0f2f5",
    "bg_sidebar": "#ffffff",
    "bg_panel": "#e9ecef",
    "text": "#212529",
    "text_inverse": "#ffffff",
}

_DARK = {
    "primary": "#3a7bc8",
    "primary_active": "#5a96dc",
    "success": "#3fb950",
    "success_active": "#5cc76d",
    "danger": "#f47174",
    "warning": "#d4a72c",
    "info": "#39c5cf",
    "info_active": "#5dd2dc",
    "bg_main": "#1e1e1e",
    "bg_sidebar": "#252526",
    "bg_panel": "#2d2d30",
    "text": "#e4e6eb",
    "text_inverse": "#1e1e1e",
}


class ThemeManager:
    """Static palette + ttk style configuration."""

    _PALETTES: ClassVar[dict[str, dict[str, str]]] = {
        "light": _LIGHT,
        "dark": _DARK,
    }

    COLORS: ClassVar[dict[str, str]] = dict(_LIGHT)
    _current: ClassVar[str] = "light"

    @classmethod
    def current_theme(cls) -> str:
        return cls._current

    @classmethod
    def set_theme(cls, name: str) -> None:
        """Switch the palette AND re-apply ttk styles.

        Unknown theme names raise ``ValueError`` — the caller's UI
        should only offer choices that have been registered.
        """
        if name not in cls._PALETTES:
            raise ValueError(
                f"Unknown theme {name!r}. Known: {sorted(cls._PALETTES)}"
            )
        cls._current = name
        cls.COLORS = dict(cls._PALETTES[name])
        try:
            cls.apply_styles()
        except Exception:
            # If there is no Tk yet (e.g. unit test importing the module),
            # the styles are still in place and the next GUI boot will
            # call apply_styles() with the right palette active.
            pass

    @classmethod
    def palette(cls) -> dict[str, str]:
        """Return a fresh copy of the active palette."""
        return dict(cls._PALETTES[cls._current])

    @classmethod
    def resolve_effective(cls, preference: str) -> str:
        """Resolve "system" to the actual light/dark value.

        Used by the GUI when the user has "follow system" selected.
        On Windows 8 the registry key is absent, so we fall back to
        the light theme and let the user switch manually.
        """
        if preference != "system":
            return preference
        # Local import: avoid pulling in GUI/registry code at module
        # import time during tests.
        from core.ui.system_theme import detect_system_theme

        return detect_system_theme() or "light"

    @classmethod
    def apply_styles(cls) -> None:
        c = cls.COLORS
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            # Some custom themes may not exist on a system. The default
            # 'clam' is bundled with Tk; if even that fails we leave
            # whatever theme is active so the app still starts.
            pass
        style.configure("Main.TFrame", background=c["bg_main"])
        style.configure("Sidebar.TFrame", background=c["bg_sidebar"], relief="flat")
        style.configure(
            "TLabel",
            background=c["bg_main"],
            foreground=c["text"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Sidebar.TLabel",
            background=c["bg_sidebar"],
            foreground=c["text"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "Header.TLabel",
            font=("Segoe UI", 12, "bold"),
            foreground=c["primary"],
            background=c["bg_main"],
        )
        style.configure("TButton", font=("Segoe UI", 10), padding=5)
        style.configure(
            "Action.TButton", background=c["primary"], foreground=c["text_inverse"]
        )
        style.map(
            "Action.TButton",
            background=[("active", c["primary_active"])],
            foreground=[("disabled", c["text"])],
        )
        style.configure(
            "Success.TButton", background=c["success"], foreground=c["text_inverse"]
        )
        style.map(
            "Success.TButton",
            background=[("active", c["success_active"])],
            foreground=[("disabled", c["text"])],
        )
        style.configure(
            "Audit.TButton", background=c["info"], foreground=c["text_inverse"]
        )
        style.map(
            "Audit.TButton",
            background=[("active", c["info_active"])],
            foreground=[("disabled", c["text"])],
        )
        style.configure(
            "TLabelframe",
            background=c["bg_sidebar"],
            relief="groove",
            borderwidth=1,
        )
        style.configure(
            "TLabelframe.Label",
            background=c["bg_sidebar"],
            foreground=c["primary"],
            font=("Segoe UI", 9, "bold"),
        )
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=30)
        style.configure(
            "Treeview.Heading",
            font=("Segoe UI", 10, "bold"),
            background=c["bg_panel"],
        )
        style.map(
            "Treeview",
            background=[("selected", c["primary"])],
            foreground=[("selected", c["text_inverse"])],
        )
        style.configure(
            "TProgressbar",
            thickness=15,
            troughcolor=c["bg_panel"],
            background=c["primary"],
        )


__all__ = ["ThemeManager"]
