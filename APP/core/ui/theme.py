"""Centralised colour palette, ttk style configuration and adaptive scaling v2.

Exposes two palettes (light + dark) and a runtime ``set_theme`` that
re-applies the ttk styles so widgets that are created later pick up
the active palette.

Design tokens (v2)
------------------
- ``COLORS``    : active palette (dict of hex strings).
- ``FONTS``     : typography hierarchy (display / heading / body / ...).
- ``SPACING``   : 6-step spacing scale (xs/sm/md/lg/xl/xxl).
- ``RADIUS``    : border-radius scale (none / sm / md / lg / pill).
- ``CONTROL``   : geometry of controls (button_h, row_h, scrollbar_w, …).

Scaled values derive from a single ``_scale ∈ [0.72, 2.0]`` factor
computed from **four** independent signals:

  1. DPI — ``winfo_fpixels("1i") / 96``, rounded to 0.25.
  2. Screen height — linear interpolation [600, 1440] → [0.78, 1.15].
  3. Viewport width — linear interpolation [700, 1600] → [0.85, 1.12],
     recalculated on every window resize (debounced 120 ms).
  4. User multiplier — ``[0.80, 1.50]``, manual override.
"""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk
from typing import Callable, ClassVar

# ---------------------------------------------------------------------------
# Palettes
# ---------------------------------------------------------------------------
_LIGHT = {
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
    "bg_main": "#f3f4f6",
    "bg_sidebar": "#ffffff",
    "bg_panel": "#e9ecef",
    "trough": "#cbd5e1",
    "text": "#334155",
    "text_secondary": "#475569",
    "text_muted": "#64748b",
    "text_inverse": "#ffffff",
    "border_subtle": "#e2e8f0",
    "border_default": "#cbd5e1",
    "success_subtle": "#dcfce7",
    "danger_subtle": "#fee2e2",
    "warning_subtle": "#fef3c7",
    "info_subtle": "#e0f2fe",
    "tooltip_bg": "#0f172a",
    "tooltip_fg": "#e2e8f0",
}

_DARK = {
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
    "bg_main": "#0f172a",
    "bg_sidebar": "#1e293b",
    "bg_panel": "#334155",
    "trough": "#334155",
    "text": "#e2e8f0",
    "text_secondary": "#cbd5e1",
    "text_muted": "#94a3b8",
    "text_inverse": "#0f172a",
    "border_subtle": "#334155",
    "border_default": "#475569",
    "success_subtle": "#052e16",
    "danger_subtle": "#450a0a",
    "warning_subtle": "#422006",
    "info_subtle": "#082f49",
    "tooltip_bg": "#020617",
    "tooltip_fg": "#e2e8f0",
}


def _lerp_hex(a: str, b: str, t: float) -> str:
    ar, ag, ab = int(a[1:3], 16), int(a[3:5], 16), int(a[5:7], 16)
    br, bg, bb = int(b[1:3], 16), int(b[3:5], 16), int(b[5:7], 16)
    r = round(ar + (br - ar) * t)
    g = round(ag + (bg - ag) * t)
    bl = round(ab + (bb - ab) * t)
    return f"#{r:02x}{g:02x}{bl:02x}"


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _lerp(lo: float, hi: float, t: float) -> float:
    """Linearly interpolate (clamped)."""
    return lo + (hi - lo) * _clamp(t, 0.0, 1.0)


# ---------------------------------------------------------------------------
# ThemeManager
# ---------------------------------------------------------------------------
class ThemeManager:
    """Static palette + ttk style configuration + adaptive scaling v2."""

    _PALETTES: ClassVar[dict[str, dict[str, str]]] = {
        "light": _LIGHT,
        "dark": _DARK,
    }

    COLORS: ClassVar[dict[str, str]] = dict(_LIGHT)
    _current: ClassVar[str] = "light"

    # ── scaling state ─────────────────────────────────────────
    _scale: ClassVar[float] = 1.0
    _scale_mode: ClassVar[str] = "auto"  # "auto" | "manual"
    _user_scale: ClassVar[float] = 1.0  # ∈ [0.80, 1.50]
    _density: ClassVar[str] = "normal"  # "compact" | "normal" | "comfortable"

    # cached inputs for scale recomputation
    _dpi: ClassVar[float] = 96.0
    _screen_h: ClassVar[int] = 768
    _viewport_w: ClassVar[int] = 1100
    _viewport_h: ClassVar[int] = 700

    _SCALE_MIN: ClassVar[float] = 0.72
    _SCALE_MAX: ClassVar[float] = 2.0

    _DENSITY_FACTORS: ClassVar[dict[str, float]] = {
        "compact": 0.70,
        "normal": 1.00,
        "comfortable": 1.35,
    }

    # ── resize listener ───────────────────────────────────────
    _resize_after_id: ClassVar[str | None] = None  # type: ignore[valid-type]
    _scale_listeners: ClassVar[list[Callable[[float, str], None]]] = []

    # ── typography ────────────────────────────────────────────
    _BASE_FONTS: ClassVar[dict[str, tuple]] = {
        "display": ("Segoe UI", 14, "bold"),
        "heading": ("Segoe UI", 12, "bold"),
        "body": ("Segoe UI", 10),
        "body_bold": ("Segoe UI", 10, "bold"),
        "caption": ("Segoe UI", 9),
        "caption_bold": ("Segoe UI", 9, "bold"),
        "micro": ("Segoe UI", 8),
        "mono": ("Consolas", 10),
        "button": ("Segoe UI", 10),
    }
    FONTS: ClassVar[dict[str, tuple]] = dict(_BASE_FONTS)
    _scaled_fonts: ClassVar[dict[str, tuple]] = {}

    # ── spacing scale ─────────────────────────────────────────
    _BASE_SPACING: ClassVar[dict[str, int]] = {
        "xs": 4,
        "sm": 8,
        "md": 12,
        "lg": 16,
        "xl": 24,
        "xxl": 32,
    }
    SPACING: ClassVar[dict[str, int]] = dict(_BASE_SPACING)

    # ── border-radius tokens ──────────────────────────────────
    _BASE_RADIUS: ClassVar[dict[str, int]] = {
        "none": 0,
        "sm": 4,
        "md": 8,
        "lg": 12,
        "pill": 20,
    }
    RADIUS: ClassVar[dict[str, int]] = dict(_BASE_RADIUS)

    # ── control-geometry tokens ───────────────────────────────
    _BASE_CONTROL: ClassVar[dict[str, int]] = {
        "button_h": 30,
        "button_pad_x": 12,
        "button_pad_y": 6,
        "row_h": 32,
        "row_h_compact": 26,
        "scrollbar_w": 10,
        "entry_h": 28,
        "tab_pad_x": 16,
        "tab_pad_y": 10,
        "sidebar_min": 240,
        "sidebar_max": 380,
        "icon": 16,
        "progress_h": 12,
        "statusbar_h": 24,
    }
    CONTROL: ClassVar[dict[str, int]] = dict(_BASE_CONTROL)

    # ── non-ttk widget registry ───────────────────────────────
    _themed_widgets: ClassVar[list] = []

    # ── public: registration ──────────────────────────────────

    @classmethod
    def register(cls, widget, *, bg_key: str = "bg_panel", fg_key: str | None = "text") -> None:
        """Track a non-ttk widget so its colours follow theme switches.

        Pass ``fg_key=None`` for widgets that have no ``foreground``
        option (e.g. ``tk.Canvas``).
        """
        cls._themed_widgets.append((widget, bg_key, fg_key))

    # ── public: scaling ───────────────────────────────────────

    @classmethod
    def init_scaling(cls, root: tk.Tk) -> None:
        """Initialise scale inputs from the display. Called once after root creation."""
        try:
            cls._dpi = root.winfo_fpixels("1i")
        except Exception:
            cls._dpi = 96.0
        try:
            cls._screen_h = root.winfo_screenheight() or 768
        except Exception:
            cls._screen_h = 768
        try:
            cls._viewport_w = root.winfo_width() or 1100
            cls._viewport_h = root.winfo_height() or 700
        except Exception:
            cls._viewport_w = 1100
            cls._viewport_h = 700
        cls._recompute_scale()
        cls._rebuild_tokens()

    @classmethod
    def attach_resize_listener(cls, root: tk.Tk) -> None:
        """Subscribe to ``<Configure>`` on *root* and recalculate scale on resize.

        Uses a 120 ms debounce so fast window resizes don't trigger a
        cascade of style rebuilds.
        """
        cls._resize_after_id = None

        def _on_configure(event: tk.Event) -> None:
            if event.widget is not root:
                return
            if event.width == cls._viewport_w and event.height == cls._viewport_h:
                return
            cls._viewport_w = event.width
            cls._viewport_h = event.height
            if cls._resize_after_id is not None:
                try:
                    root.after_cancel(cls._resize_after_id)
                except Exception:
                    pass
            cls._resize_after_id = root.after(120, cls._on_resize_tick, root)

        root.bind("<Configure>", _on_configure, add="+")

    @classmethod
    def _on_resize_tick(cls, _root: tk.Tk) -> None:
        old = cls._scale
        cls._recompute_scale()
        # Only rebuild if scale actually changed (within 4th decimal).
        if abs(cls._scale - old) < 0.0001:
            return
        cls._rebuild_tokens()

    @classmethod
    def apply_preferences(
        cls,
        *,
        scale_mode: str | None = None,
        user_scale: float | None = None,
        density: str | None = None,
    ) -> None:
        """Apply external prefs and rebuild if anything changed.

        Called by the settings dialog (live preview) and by
        :meth:`GuiMasterSettingsMixin.apply_ui_preferences`.
        """
        changed = False
        if scale_mode is not None and scale_mode != cls._scale_mode:
            cls._scale_mode = scale_mode
            changed = True
        if user_scale is not None and abs(user_scale - cls._user_scale) > 0.001:
            cls._user_scale = user_scale
            changed = True
        if density is not None and density != cls._density:
            cls._density = density
            changed = True
        if changed:
            old = cls._scale
            cls._recompute_scale()
            if abs(cls._scale - old) >= 0.0001 or changed:
                cls._rebuild_tokens()

    @classmethod
    def add_scale_listener(cls, cb: Callable[[float, str], None]) -> None:
        """Register a callback invoked when scale (or density) changes.

        The callback receives ``(new_scale, viewport_mode)``.
        Use :meth:`remove_scale_listener` to unsubscribe.
        """
        if cb not in cls._scale_listeners:
            cls._scale_listeners.append(cb)

    @classmethod
    def remove_scale_listener(cls, cb: Callable[[float, str], None]) -> None:
        """Unregister a previously added scale-listener callback."""
        try:
            cls._scale_listeners.remove(cb)
        except ValueError:
            pass

    @classmethod
    def viewport_mode(cls) -> str:
        """Classify the current window width.

        Returns ``"compact"`` (<900 px), ``"normal"`` (900-1400 px),
        or ``"large"`` (>1400 px).
        """
        w = cls._viewport_w
        if w < 900:
            return "compact"
        if w <= 1400:
            return "normal"
        return "large"

    # ── internal: scale recomputation ─────────────────────────

    @classmethod
    def _recompute_scale(cls) -> None:
        if cls._scale_mode == "manual":
            cls._scale = _clamp(cls._user_scale, cls._SCALE_MIN, cls._SCALE_MAX)
            return

        dpi_factor = max(1.0, round(cls._dpi / 96.0 * 4) / 4)
        h = max(480, cls._screen_h)
        height_factor = _lerp(0.78, 1.15, (h - 600) / (1440 - 600))
        height_factor = _clamp(height_factor, 0.78, 1.15)

        vw = max(640, cls._viewport_w)
        viewport_factor = _lerp(0.85, 1.12, (vw - 700) / (1600 - 700))
        viewport_factor = _clamp(viewport_factor, 0.85, 1.12)

        combined = dpi_factor * height_factor * viewport_factor * cls._user_scale
        cls._scale = _clamp(combined, cls._SCALE_MIN, cls._SCALE_MAX)

    @classmethod
    def _rebuild_tokens(cls) -> None:
        """Rebuild all token groups from current ``_scale`` and ``_density``."""
        cls._rebuild_fonts()
        cls._rebuild_spacing()
        cls._rebuild_radius()
        cls._rebuild_control()
        try:
            cls.apply_styles()
        except Exception:
            pass
        mode = cls.viewport_mode()
        for cb in cls._scale_listeners:
            try:
                cb(cls._scale, mode)
            except Exception:
                pass

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
        s = cls._scale * cls._DENSITY_FACTORS.get(cls._density, 1.0)
        cls.SPACING = {k: max(2, int(v * s)) for k, v in cls._BASE_SPACING.items()}

    @classmethod
    def _rebuild_radius(cls) -> None:
        s = cls._scale
        cls.RADIUS = {k: max(0, math.ceil(v * s)) for k, v in cls._BASE_RADIUS.items()}

    @classmethod
    def _rebuild_control(cls) -> None:
        s = cls._scale
        d = cls._DENSITY_FACTORS.get(cls._density, 1.0)
        cls.CONTROL = {k: max(4, int(v * s)) for k, v in cls._BASE_CONTROL.items()}
        # density only affects padding, not button/row heights
        cls.CONTROL["button_pad_x"] = max(4, int(cls._BASE_CONTROL["button_pad_x"] * s * d))
        cls.CONTROL["button_pad_y"] = max(2, int(cls._BASE_CONTROL["button_pad_y"] * s * d))
        cls.CONTROL["tab_pad_x"] = max(4, int(cls._BASE_CONTROL["tab_pad_x"] * s * d))
        cls.CONTROL["tab_pad_y"] = max(4, int(cls._BASE_CONTROL["tab_pad_y"] * s * d))

    # ── public: theme switching ───────────────────────────────

    @classmethod
    def current_theme(cls) -> str:
        return cls._current

    @classmethod
    def set_theme(cls, name: str) -> None:
        if name not in cls._PALETTES:
            raise ValueError(f"Unknown theme {name!r}. Known: {sorted(cls._PALETTES)}")
        cls._current = name
        cls.COLORS = dict(cls._PALETTES[name])
        try:
            cls.apply_styles()
        except Exception:
            pass
        for entry in list(cls._themed_widgets):
            try:
                widget, bg_key, fg_key = entry
                # Update background and foreground separately so that a
                # widget lacking one option (e.g. Canvas has no
                # foreground) still gets the other updated.  Without
                # this, a single configure() call with both options
                # would fail atomically and the widget would be removed
                # from the list without any colour change — leaving a
                # white patch in dark mode.
                try:
                    widget.configure(background=cls.COLORS[bg_key])
                except Exception:
                    pass
                if fg_key:
                    try:
                        widget.configure(foreground=cls.COLORS[fg_key])
                    except Exception:
                        pass
            except Exception:
                try:
                    cls._themed_widgets.remove(entry)
                except ValueError:
                    pass

    @classmethod
    def palette(cls) -> dict[str, str]:
        return dict(cls._PALETTES[cls._current])

    @classmethod
    def resolve_effective(cls, preference: str) -> str:
        if preference != "system":
            return preference
        from core.ui.system_theme import detect_system_theme

        return detect_system_theme() or "light"

    # ── smooth background animation ───────────────────────────

    @classmethod
    def animate_background(
        cls,
        widget,
        target: str,
        steps: int = 8,
        delay_ms: int = 16,
    ) -> None:
        try:
            current = widget.cget("background")
        except Exception:
            return
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
            widget._theme_anim_ids = ids
        except Exception:
            pass

    # ── ttk style configuration ───────────────────────────────

    @classmethod
    def apply_styles(cls) -> None:
        c = cls.COLORS
        f = cls.FONTS
        s = cls._scale
        sp = cls.SPACING
        ctrl = cls.CONTROL
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # --- Frames ---
        # Base TFrame — widgets without an explicit style inherit this.
        # Without it, ttk defaults to the clam theme's built-in colour
        # (light grey) which shows up as a white patch in dark mode.
        style.configure("TFrame", background=c["bg_main"])
        style.configure("Main.TFrame", background=c["bg_main"])
        style.configure("Sidebar.TFrame", background=c["bg_sidebar"], relief="flat")

        # --- Labels ---
        # Typography hierarchy:
        #   Header.TLabel  → display  (section titles, primary colour)
        #   TLabelframe.Label → heading (group titles, muted)
        #   *.TLabel (body)   → body    (default text)
        #   Muted.TLabel   → caption (secondary/hint text, muted)
        style.configure("TLabel", background=c["bg_main"], foreground=c["text"], font=f["body"])
        style.configure(
            "Sidebar.TLabel", background=c["bg_sidebar"], foreground=c["text"], font=f["body"]
        )
        style.configure(
            "Header.TLabel", font=f["display"], foreground=c["primary"], background=c["bg_main"]
        )
        # Main-area label — explicit bg_main so the label blends with the
        # dashboard content area rather than inheriting a sidebar-coloured
        # fallback. Previously missing; code referenced it but ttk silently
        # fell back to the base TLabel (which happened to match by luck).
        style.configure(
            "Main.TLabel", font=f["body"], foreground=c["text"], background=c["bg_main"]
        )
        # Secondary/hint text — caption size, muted colour. Used for
        # helper lines under headings (e.g. aliases tab subtitle, "double-
        # click to edit" hints). Previously missing; ttk fell back to the
        # full-size body label, so the helper text read as loud as the
        # heading instead of receding.
        style.configure(
            "Muted.TLabel", font=f["caption"], foreground=c["text_muted"], background=c["bg_main"]
        )

        # --- Buttons (all use control tokens for padding) ---
        # Every button style follows ONE consistent state matrix so hover,
        # active and disabled read identically across the app:
        #   background: [("active", *_active), ("disabled", bg_panel)]
        #   foreground: [("active", text_inverse), ("disabled", text_muted)]
        # Ghost is the exception: it has no solid fill, so active bg is the
        # panel tint and active fg is primary (the link-like affordance).
        btn_pad = (ctrl["button_pad_x"], ctrl["button_pad_y"])
        style.configure(
            "TButton",
            font=f["button"],
            padding=btn_pad,
            relief="flat",
            borderwidth=0,
            background=c["bg_panel"],
            foreground=c["text"],
        )
        style.map(
            "TButton",
            background=[("active", c["primary"]), ("disabled", c["bg_panel"])],
            foreground=[("active", c["text_inverse"]), ("disabled", c["text_muted"])],
        )

        style.configure(
            "Action.TButton",
            font=f["button"],
            padding=btn_pad,
            relief="flat",
            borderwidth=0,
            background=c["primary"],
            foreground=c["text_inverse"],
        )
        style.map(
            "Action.TButton",
            background=[("active", c["primary_active"]), ("disabled", c["bg_panel"])],
            foreground=[("active", c["text_inverse"]), ("disabled", c["text_muted"])],
        )

        style.configure(
            "Success.TButton",
            font=f["button"],
            padding=btn_pad,
            relief="flat",
            borderwidth=0,
            background=c["success"],
            foreground=c["text_inverse"],
        )
        style.map(
            "Success.TButton",
            background=[("active", c["success_active"]), ("disabled", c["bg_panel"])],
            foreground=[("active", c["text_inverse"]), ("disabled", c["text_muted"])],
        )

        style.configure(
            "Audit.TButton",
            font=f["button"],
            padding=btn_pad,
            relief="flat",
            borderwidth=0,
            background=c["info"],
            foreground=c["text_inverse"],
        )
        style.map(
            "Audit.TButton",
            background=[("active", c["info_active"]), ("disabled", c["bg_panel"])],
            foreground=[("active", c["text_inverse"]), ("disabled", c["text_muted"])],
        )

        style.configure(
            "Danger.TButton",
            font=f["button"],
            padding=btn_pad,
            relief="flat",
            borderwidth=0,
            background=c["danger"],
            foreground=c["text_inverse"],
        )
        style.map(
            "Danger.TButton",
            background=[("active", c["danger_active"]), ("disabled", c["bg_panel"])],
            foreground=[("active", c["text_inverse"]), ("disabled", c["text_muted"])],
        )

        style.configure(
            "Ghost.TButton",
            font=f["button"],
            padding=btn_pad,
            relief="flat",
            borderwidth=0,
            background=c["bg_main"],
            foreground=c["text"],
        )
        style.map(
            "Ghost.TButton",
            background=[("active", c["bg_panel"]), ("disabled", c["bg_main"])],
            foreground=[("active", c["primary"]), ("disabled", c["text_muted"])],
        )

        # --- LabelFrame / Card ---
        # Base TLabelframe uses bg_sidebar (for sidebar context).
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
        # Main-area LabelFrame — matches bg_main so it blends with the
        # dashboard tabs instead of showing a white sidebar-coloured patch.
        style.configure(
            "Main.TLabelframe",
            background=c["bg_main"],
            relief="flat",
            borderwidth=1,
            bordercolor=c["border_subtle"],
        )
        style.configure(
            "Main.TLabelframe.Label",
            background=c["bg_main"],
            foreground=c["text_muted"],
            font=f["heading"],
        )
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

        # --- Treeview ---
        style.configure(
            "Treeview",
            font=f["body"],
            rowheight=ctrl.get("row_h_compact" if cls._density == "compact" else "row_h", 32),
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
        # On hover the heading text lifts from text_muted to text so the
        # bold header stays readable: text_muted on border_default falls
        # below WCAG 3:1 in dark mode (2.96:1). Foreground follows the
        # active state to match the brightened background.
        style.map(
            "Treeview.Heading",
            background=[("active", c["border_default"])],
            foreground=[("active", c["text"])],
        )

        # --- Entry / Combobox ---
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

        # --- Scrollbars ---
        sw = ctrl.get("scrollbar_w", 10)
        for orient in ("Vertical", "Horizontal"):
            style.configure(
                f"{orient}.TScrollbar",
                background=c["border_default"],
                troughcolor=c["bg_main"],
                arrowcolor=c["text_muted"],
                bordercolor=c["bg_main"],
                relief="flat",
                width=sw,
            )
            style.map(
                f"{orient}.TScrollbar",
                background=[("active", c["text_muted"])],
                arrowcolor=[("active", c["text"])],
            )

        # --- Notebook ---
        # The clam Notebook.client element has bordercolor/lightcolor/
        # darkcolor that default to white — these show as a thin white
        # frame around the tab content in dark mode.  Set them all to
        # the main background so the frame is invisible.
        style.configure(
            "TNotebook",
            background=c["bg_main"],
            borderwidth=0,
            tabmargins=(0, 4, 0, 0),
            padding=0,
            bordercolor=c["bg_main"],
            lightcolor=c["bg_main"],
            darkcolor=c["bg_main"],
        )
        style.configure(
            "TNotebook.Tab",
            font=f["body"],
            background=c["bg_main"],
            foreground=c["text_muted"],
            padding=(ctrl["tab_pad_x"], ctrl["tab_pad_y"]),
            borderwidth=0,
            bordercolor=c["bg_main"],
            lightcolor=c["bg_main"],
            darkcolor=c["bg_main"],
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", c["bg_sidebar"]), ("active", c["bg_panel"])],
            foreground=[("selected", c["primary"]), ("active", c["text"])],
            bordercolor=[("selected", c["bg_sidebar"])],
            lightcolor=[("selected", c["bg_sidebar"])],
            darkcolor=[("selected", c["bg_sidebar"])],
        )

        # --- Checkbutton / Radiobutton ---
        style.configure(
            "TCheckbutton", background=c["bg_sidebar"], foreground=c["text"], font=f["body"]
        )
        style.map(
            "TCheckbutton",
            background=[("active", c["bg_sidebar"])],
            foreground=[("disabled", c["text_muted"])],
        )
        style.configure(
            "TRadiobutton", background=c["bg_sidebar"], foreground=c["text"], font=f["body"]
        )
        style.map(
            "TRadiobutton",
            background=[("active", c["bg_sidebar"])],
            foreground=[("disabled", c["text_muted"])],
        )

        # --- Progressbar ---
        style.configure(
            "TProgressbar",
            thickness=ctrl.get("progress_h", 12),
            troughcolor=c["bg_panel"],
            background=c["primary"],
            bordercolor=c["border_subtle"],
            lightcolor=c["primary"],
            darkcolor=c["primary"],
        )

        # --- Status bar ---
        style.configure("StatusBar.TFrame", background=c["bg_panel"], relief="flat")
        style.configure(
            "StatusBar.TLabel",
            background=c["bg_panel"],
            foreground=c["text_muted"],
            font=f["caption"],
        )

        # --- Spinbox ---
        style.configure(
            "TSpinbox",
            fieldbackground=c["bg_sidebar"],
            background=c["bg_sidebar"],
            foreground=c["text"],
            arrowcolor=c["text_muted"],
            bordercolor=c["border_default"],
            lightcolor=c["border_default"],
            darkcolor=c["border_default"],
            insertcolor=c["primary"],
            selectbackground=c["primary"],
            selectforeground=c["text_inverse"],
        )
        style.map(
            "TSpinbox",
            fieldbackground=[("focus", c["bg_sidebar"])],
            arrowcolor=[("active", c["primary"])],
            bordercolor=[("focus", c["primary"])],
            lightcolor=[("focus", c["primary"])],
            darkcolor=[("focus", c["primary"])],
        )


# ---------------------------------------------------------------------------
# Popup styling helpers (shared by toast.py and tooltip.py)
# ---------------------------------------------------------------------------
# Both modules independently re-implemented the same border-color resolution
# and the same 1px-highlight tk.Frame construction. Centralising it keeps the
# two popup families visually consistent and removes the duplicated fallback
# chains ("border_subtle" → "trough" → magic hex) that had drifted apart.


def popup_border_color() -> str:
    """Resolve the border colour for popup (toast/tooltip) frames.

    Falls back gracefully through border_subtle → trough → a neutral grey,
    so a toast still renders even if a future palette drops a key.
    """
    colors = ThemeManager.COLORS
    return colors.get("border_subtle", colors.get("trough", "#cbd5e1"))


def make_popup_frame(parent: tk.Misc, bg: str, *, pad_x: int, pad_y: int) -> tk.Frame:
    """Build the standard popup inner frame with a 1px themed border.

    tk widgets (not ttk) are used because ttk.Frame does not reliably
    honour ``highlightthickness`` across themes — so the popup families
    share this constructor to keep the border treatment identical.
    """
    border = popup_border_color()
    return tk.Frame(
        parent,
        bg=bg,
        padx=pad_x,
        pady=pad_y,
        highlightthickness=1,
        highlightbackground=border,
        highlightcolor=border,
    )


__all__ = ["ThemeManager"]
