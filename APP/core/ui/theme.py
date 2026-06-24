"""Centralised colour palette and ttk style configuration.

Exposes two palettes (light + dark) and a runtime ``set_theme`` that
re-applies the ttk styles so widgets that are created later pick up
the active palette. Widgets already in the tree pick up the changes
on the next ``configure`` call, which the GuiMaster triggers after
the user switches themes.

Design tokens
-------------
- ``COLORS``    : active palette (dict of hex strings).
- ``FONTS``     : typography hierarchy (display / heading / body / ...).
- ``SPACING``   : 4-step spacing scale (xs/sm/md/lg/xl/xxl).
- ``animate_background`` : classmethod helper for smooth bg transitions.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import ClassVar

# ---------------------------------------------------------------------------
# Palettes
# ---------------------------------------------------------------------------
# All pre-existing keys (primary, primary_active, success, success_active,
# danger, warning, info, info_active, bg_main, bg_sidebar, bg_panel, trough,
# text, text_inverse, accent, tooltip_bg, tooltip_fg) are preserved verbatim
# so existing call sites keep working. New refined keys are appended:
#   danger_active, text_muted, border_subtle, border_default,
#   success_subtle, danger_subtle, warning_subtle, info_subtle.
_LIGHT = {
    # --- accent / semantic ---
    "primary": "#2563eb",
    "primary_active": "#1d4ed8",
    "success": "#16a34a",
    "success_active": "#15803d",
    "danger": "#dc2626",
    "danger_active": "#b91c1c",
    "warning": "#d97706",
    "info": "#0891b2",
    "info_active": "#0e7490",
    "accent": "#2563eb",
    # --- backgrounds (warm off-white) ---
    "bg_main": "#f3f4f6",
    "bg_sidebar": "#ffffff",
    "bg_panel": "#e9ecef",
    "trough": "#cbd5e1",
    # --- text ---
    "text": "#334155",
    "text_muted": "#64748b",
    "text_inverse": "#ffffff",
    # --- borders ---
    "border_subtle": "#e2e8f0",
    "border_default": "#cbd5e1",
    # --- subtle semantic fills (badges / cards) ---
    "success_subtle": "#dcfce7",
    "danger_subtle": "#fee2e2",
    "warning_subtle": "#fef3c7",
    "info_subtle": "#e0f2fe",
    # --- misc ---
    "tooltip_bg": "#0f172a",
    "tooltip_fg": "#e2e8f0",
}

_DARK = {
    # --- accent / semantic ---
    "primary": "#60a5fa",
    "primary_active": "#93c5fd",
    "success": "#4ade80",
    "success_active": "#86efac",
    "danger": "#f87171",
    "danger_active": "#fca5a5",
    "warning": "#fbbf24",
    "info": "#22d3ee",
    "info_active": "#67e8f9",
    "accent": "#60a5fa",
    # --- backgrounds (rich charcoal) ---
    "bg_main": "#0f172a",
    "bg_sidebar": "#1e293b",
    "bg_panel": "#334155",
    "trough": "#334155",
    # --- text ---
    "text": "#e2e8f0",
    "text_muted": "#94a3b8",
    "text_inverse": "#0f172a",
    # --- borders ---
    "border_subtle": "#334155",
    "border_default": "#475569",
    # --- subtle semantic fills ---
    "success_subtle": "#052e16",
    "danger_subtle": "#450a0a",
    "warning_subtle": "#422006",
    "info_subtle": "#082f49",
    # --- misc ---
    "tooltip_bg": "#020617",
    "tooltip_fg": "#e2e8f0",
}


def _lerp_hex(a: str, b: str, t: float) -> str:
    """Linearly interpolate between two ``#rrggbb`` colours (0<=t<=1)."""
    ar, ag, ab = int(a[1:3], 16), int(a[3:5], 16), int(a[5:7], 16)
    br, bg, bb = int(b[1:3], 16), int(b[3:5], 16), int(b[5:7], 16)
    r = round(ar + (br - ar) * t)
    g = round(ag + (bg - ag) * t)
    bl = round(ab + (bb - ab) * t)
    return f"#{r:02x}{g:02x}{bl:02x}"


class ThemeManager:
    """Static palette + ttk style configuration."""

    _PALETTES: ClassVar[dict[str, dict[str, str]]] = {
        "light": _LIGHT,
        "dark": _DARK,
    }

    COLORS: ClassVar[dict[str, str]] = dict(_LIGHT)
    _current: ClassVar[str] = "light"
    _scale: ClassVar[float] = 1.0
    _scaled_fonts: ClassVar[dict[str, tuple]] = {}

    # Typography hierarchy. "Segoe UI Semibold" is not universally available
    # on Windows; ("Segoe UI", N, "bold") is, and visually close enough.
    _BASE_FONTS: ClassVar[dict[str, tuple]] = {
        "display": ("Segoe UI", 14, "bold"),
        "heading": ("Segoe UI", 12, "bold"),
        "body": ("Segoe UI", 10),
        "body_bold": ("Segoe UI", 10, "bold"),
        "caption": ("Segoe UI", 9),
        "mono": ("Consolas", 10),
        "button": ("Segoe UI", 10),
    }
    FONTS: ClassVar[dict[str, tuple]] = dict(_BASE_FONTS)

    # 4-step spacing scale (pixels). Other modules may reference
    # ThemeManager.SPACING["md"] instead of hardcoded numbers.
    _BASE_SPACING: ClassVar[dict[str, int]] = {
        "xs": 4,
        "sm": 8,
        "md": 12,
        "lg": 16,
        "xl": 24,
        "xxl": 32,
    }
    SPACING: ClassVar[dict[str, int]] = dict(_BASE_SPACING)

    # Widgets that use explicit ``background=ThemeManager.COLORS[...]``
    # (tk.Canvas, tk.Text, DateEntry, ...) do not pick up ttk style
    # changes automatically. Register them here so ``set_theme`` can
    # re-apply the current palette's colours to each. Entries are
    # ``(widget, bg_key, fg_key)`` tuples; destroyed widgets are pruned
    # lazily on the next ``set_theme`` call.
    _themed_widgets: ClassVar[list] = []

    @classmethod
    def register(cls, widget, *, bg_key: str = "bg_panel", fg_key: str = "text") -> None:
        """Track a non-ttk widget so its colours follow theme switches."""
        cls._themed_widgets.append((widget, bg_key, fg_key))

    @classmethod
    def init_scaling(cls, root: tk.Tk) -> None:
        """Calculate adaptive scale based on DPI AND screen height.

        On small screens (e.g. 1366x768, 1024x600) the scale factor
        is reduced so the whole UI fits without scrolling. On large
        high-DPI screens the DPI component dominates so text stays
        crisp.

        Fonts and spacing are rebuilt afterwards. Must be called once
        after ``root = tk.Tk()``.
        """
        try:
            dpi = root.winfo_fpixels("1i")
            dpi_scale = max(1.0, round(dpi / 96.0 * 2) / 2)
        except Exception:
            dpi_scale = 1.0

        # --- screen-height factor -------------------------------------------
        # 900 px  → factor 1.0  (full-size)
        # 768 px  → factor 0.85 (compact — 1366×768 laptop)
        # 600 px  → factor 0.78 (very compact — netbook)
        try:
            screen_h = root.winfo_screenheight()
            height_factor = min(1.0, max(0.78, (screen_h or 768) / 900))
        except Exception:
            height_factor = 1.0

        cls._scale = max(0.78, dpi_scale * height_factor)
        cls._rebuild_fonts()
        cls._rebuild_spacing()

    @classmethod
    def _rebuild_fonts(cls) -> None:
        s = cls._scale
        cls._scaled_fonts = {}
        for key, val in cls._BASE_FONTS.items():
            font_name = val[0]
            font_size = max(8, int(val[1] * s))
            font_opts = val[2:]
            cls._scaled_fonts[key] = (font_name, font_size, *font_opts)
        cls.FONTS = cls._scaled_fonts

    @classmethod
    def _rebuild_spacing(cls) -> None:
        s = cls._scale
        cls.SPACING = {k: max(2, int(v * s)) for k, v in cls._BASE_SPACING.items()}

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
            raise ValueError(f"Unknown theme {name!r}. Known: {sorted(cls._PALETTES)}")
        cls._current = name
        cls.COLORS = dict(cls._PALETTES[name])
        try:
            cls.apply_styles()
        except Exception:
            # If there is no Tk yet (e.g. unit test importing the module),
            # the styles are still in place and the next GUI boot will
            # call apply_styles() with the right palette active.
            pass
        # Re-apply explicit colours to non-ttk widgets (Canvas, Text,
        # DateEntry, ...). Destroyed widgets are pruned silently.
        for entry in list(cls._themed_widgets):
            try:
                widget, bg_key, fg_key = entry
                widget.configure(background=cls.COLORS[bg_key], foreground=cls.COLORS[fg_key])
            except Exception:
                try:
                    cls._themed_widgets.remove(entry)
                except ValueError:
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

    # ------------------------------------------------------------------
    # Smooth background animation helper
    # ------------------------------------------------------------------
    @classmethod
    def animate_background(
        cls,
        widget,
        target: str,
        steps: int = 8,
        delay_ms: int = 16,
    ) -> None:
        """Interpolate ``widget`` background to ``target`` over ~``steps*delay_ms`` ms.

        Cancels any in-flight animation for the same widget before starting
        a new one (avoids flicker when Enter/Leave fire in quick succession).
        Intended for plain ``tk`` widgets (Frame, Label, ...). ttk widgets
        ignore ``background=`` for the most part — callers should pick
        appropriate targets. Best-effort: silently bails on any Tcl error.
        """
        try:
            current = widget.cget("background")
        except Exception:
            return
        # Cancel pending animation for this widget, if any.
        prev = getattr(widget, "_theme_anim_ids", None)
        if prev:
            for aid in prev:
                try:
                    widget.after_cancel(aid)
                except Exception:
                    pass
        ids: list[str] = []

        def _step(i: int) -> None:
            if i > steps:
                return
            t = i / steps
            try:
                widget.configure(background=_lerp_hex(current, target, t))
            except Exception:
                return

        for i in range(1, steps + 1):
            try:
                ids.append(widget.after(delay_ms * i, _step, i))
            except Exception:
                return
        try:
            widget._theme_anim_ids = ids  # type: ignore[attr-defined]
        except Exception:
            pass

    # ------------------------------------------------------------------
    # ttk style configuration
    # ------------------------------------------------------------------
    @classmethod
    def apply_styles(cls) -> None:
        c = cls.COLORS
        f = cls.FONTS
        s = cls._scale
        sp = cls.SPACING
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            # Some custom themes may not exist on a system. The default
            # 'clam' is bundled with Tk; if even that fails we leave
            # whatever theme is active so the app still starts.
            pass

        # --- Frames -------------------------------------------------------
        style.configure("Main.TFrame", background=c["bg_main"])
        style.configure("Sidebar.TFrame", background=c["bg_sidebar"], relief="flat")

        # --- Labels -------------------------------------------------------
        style.configure(
            "TLabel",
            background=c["bg_main"],
            foreground=c["text"],
            font=f["body"],
        )
        style.configure(
            "Sidebar.TLabel",
            background=c["bg_sidebar"],
            foreground=c["text"],
            font=f["body"],
        )
        style.configure(
            "Header.TLabel",
            font=f["display"],
            foreground=c["primary"],
            background=c["bg_main"],
        )

        # --- Buttons (base + variants) -----------------------------------
        # Flat, breathable padding. Hover handled via style.map (instant,
        # reliable). Smooth animation is available via animate_background
        # for non-ttk widgets (toast frames, etc.).
        style.configure(
            "TButton",
            font=f["button"],
            padding=(4, 2),
            relief="flat",
            borderwidth=0,
            background=c["bg_panel"],
            foreground=c["text"],
        )
        style.map(
            "TButton",
            background=[
                ("active", c["primary"]),
                ("disabled", c["bg_panel"]),
            ],
            foreground=[
                ("active", c["text_inverse"]),
                ("disabled", c["text_muted"]),
            ],
        )
        # Primary action (was: Action.TButton). Keep exact name.
        style.configure(
            "Action.TButton",
            font=f["button"],
            padding=(4, 2),
            relief="flat",
            borderwidth=0,
            background=c["primary"],
            foreground=c["text_inverse"],
        )
        style.map(
            "Action.TButton",
            background=[("active", c["primary_active"]), ("disabled", c["bg_panel"])],
            foreground=[("disabled", c["text_muted"])],
        )
        # Success (positive actions).
        style.configure(
            "Success.TButton",
            font=f["button"],
            padding=(4, 2),
            relief="flat",
            borderwidth=0,
            background=c["success"],
            foreground=c["text_inverse"],
        )
        style.map(
            "Success.TButton",
            background=[("active", c["success_active"]), ("disabled", c["bg_panel"])],
            foreground=[("disabled", c["text_muted"])],
        )
        # Audit (informational, was: info/blue).
        style.configure(
            "Audit.TButton",
            font=f["button"],
            padding=(4, 2),
            relief="flat",
            borderwidth=0,
            background=c["info"],
            foreground=c["text_inverse"],
        )
        style.map(
            "Audit.TButton",
            background=[("active", c["info_active"]), ("disabled", c["bg_panel"])],
            foreground=[("disabled", c["text_muted"])],
        )
        # Danger (destructive actions like delete).
        style.configure(
            "Danger.TButton",
            font=f["button"],
            padding=(4, 2),
            relief="flat",
            borderwidth=0,
            background=c["danger"],
            foreground=c["text_inverse"],
        )
        style.map(
            "Danger.TButton",
            background=[("active", c["danger_active"]), ("disabled", c["bg_panel"])],
            foreground=[("disabled", c["text_muted"])],
        )
        # Ghost (transparent secondary; border surfaces on hover).
        style.configure(
            "Ghost.TButton",
            font=f["button"],
            padding=(4, 2),
            relief="flat",
            borderwidth=0,
            background=c["bg_main"],
            foreground=c["text"],
        )
        style.map(
            "Ghost.TButton",
            background=[
                ("active", c["bg_panel"]),
                ("disabled", c["bg_main"]),
            ],
            foreground=[
                ("active", c["primary"]),
                ("disabled", c["text_muted"]),
            ],
        )

        # --- LabelFrame / Card -------------------------------------------
        # Modern flat card: subtle border, muted label (not primary —
        # muted reads as a refined card title rather than a heading).
        style.configure(
            "TLabelframe",
            background=c["bg_sidebar"],
            relief="flat",
            borderwidth=1,
            bordercolor=c["border_subtle"],
        )
        style.configure(
            "TLabelframe.Label",
            background=c["bg_sidebar"],
            foreground=c["text_muted"],
            font=f["heading"],
        )
        # Card variant — same look, explicit so callers can opt in.
        style.configure(
            "Card.TLabelframe",
            background=c["bg_sidebar"],
            relief="flat",
            borderwidth=1,
            bordercolor=c["border_subtle"],
        )
        style.configure(
            "Card.TLabelframe.Label",
            background=c["bg_sidebar"],
            foreground=c["text_muted"],
            font=f["heading"],
        )

        # --- Treeview -----------------------------------------------------
        style.configure(
            "Treeview",
            font=f["body"],
            rowheight=int(32 * s),
            background=c["bg_sidebar"],
            fieldbackground=c["bg_sidebar"],
            foreground=c["text"],
            bordercolor=c["border_subtle"],
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            font=f["body_bold"],
            background=c["bg_panel"],
            foreground=c["text_muted"],
            relief="flat",
            borderwidth=0,
            padding=(sp["sm"], int(6 * s)),
        )
        style.map(
            "Treeview",
            background=[("selected", c["primary"])],
            foreground=[("selected", c["text_inverse"])],
        )
        style.map(
            "Treeview.Heading",
            background=[("active", c["border_default"])],
        )

        # --- Entry / Combobox --------------------------------------------
        style.configure(
            "TEntry",
            fieldbackground=c["bg_sidebar"],
            background=c["bg_sidebar"],
            foreground=c["text"],
            insertcolor=c["primary"],
            bordercolor=c["border_default"],
            lightcolor=c["border_default"],
            darkcolor=c["border_default"],
            selectbackground=c["primary"],
            selectforeground=c["text_inverse"],
            padding=(sp["xs"], int(4 * s)),
        )
        style.map(
            "TEntry",
            bordercolor=[("focus", c["primary"])],
            lightcolor=[("focus", c["primary"])],
            darkcolor=[("focus", c["primary"])],
        )
        style.configure(
            "TCombobox",
            fieldbackground=c["bg_sidebar"],
            background=c["bg_sidebar"],
            foreground=c["text"],
            arrowcolor=c["text_muted"],
            bordercolor=c["border_default"],
            lightcolor=c["border_default"],
            darkcolor=c["border_default"],
            selectbackground=c["primary"],
            selectforeground=c["text_inverse"],
            padding=(sp["xs"], int(4 * s)),
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", c["bg_sidebar"])],
            foreground=[("readonly", c["text"])],
            bordercolor=[("focus", c["primary"])],
            lightcolor=[("focus", c["primary"])],
            darkcolor=[("focus", c["primary"])],
            arrowcolor=[("active", c["primary"])],
        )

        # --- Scrollbars (thinner, subtler) -------------------------------
        for orient in ("Vertical", "Horizontal"):
            style.configure(
                f"{orient}.TScrollbar",
                background=c["border_default"],
                troughcolor=c["bg_main"],
                arrowcolor=c["text_muted"],
                bordercolor=c["bg_main"],
                relief="flat",
                width=int(10 * s) if orient == "Vertical" else int(10 * s),
            )
            style.map(
                f"{orient}.TScrollbar",
                background=[("active", c["text_muted"])],
                arrowcolor=[("active", c["text"])],
            )

        # --- Notebook / Tabs ---------------------------------------------
        style.configure(
            "TNotebook",
            background=c["bg_main"],
            borderwidth=0,
            tabmargins=(0, 4, 0, 0),
        )
        style.configure(
            "TNotebook.Tab",
            font=f["body"],
            background=c["bg_main"],
            foreground=c["text_muted"],
            padding=(sp["lg"], int(10 * s)),
            borderwidth=0,
        )
        style.map(
            "TNotebook.Tab",
            background=[
                ("selected", c["bg_sidebar"]),
                ("active", c["bg_panel"]),
            ],
            foreground=[
                ("selected", c["primary"]),
                ("active", c["text"]),
            ],
        )

        # --- Checkbutton / Radiobutton -----------------------------------
        style.configure(
            "TCheckbutton",
            background=c["bg_sidebar"],
            foreground=c["text"],
            font=f["body"],
        )
        style.map(
            "TCheckbutton",
            background=[("active", c["bg_sidebar"])],
            foreground=[("disabled", c["text_muted"])],
        )
        style.configure(
            "TRadiobutton",
            background=c["bg_sidebar"],
            foreground=c["text"],
            font=f["body"],
        )
        style.map(
            "TRadiobutton",
            background=[("active", c["bg_sidebar"])],
            foreground=[("disabled", c["text_muted"])],
        )

        # --- Progressbar (slimmer) ---------------------------------------
        style.configure(
            "TProgressbar",
            thickness=int(12 * s),
            troughcolor=c["bg_panel"],
            background=c["primary"],
            bordercolor=c["border_subtle"],
            lightcolor=c["primary"],
            darkcolor=c["primary"],
        )

        # --- Status bar ---------------------------------------------------
        style.configure(
            "StatusBar.TFrame",
            background=c["bg_panel"],
            relief="flat",
        )
        style.configure(
            "StatusBar.TLabel",
            background=c["bg_panel"],
            foreground=c["text_muted"],
            font=f["caption"],
        )


__all__ = ["ThemeManager"]
