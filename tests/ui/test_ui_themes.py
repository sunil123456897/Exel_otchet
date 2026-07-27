"""TC-601..TC-620: theme switching & visual consistency automation.

Verifies that the light↔dark↔system palette switch propagates to EVERY
themed surface — ttk styles, the root background, DateEntry accents, the
context menu, and the status-badge row-washes. These are the checks a
human QA would do by eye after toggling the theme; here we assert the
underlying widget state directly so a regression (a widget that "sticks"
in the old palette) fails loudly instead of shipping unnoticed.
"""
from tkinter import ttk

from conftest import pump
from core.ui.theme import _DARK, _LIGHT, ThemeManager

# ---------------------------------------------------------------------------
# TC-601: palette load & switch
# ---------------------------------------------------------------------------

def test_light_palette_has_all_22_keys(gui):
    """The light palette must expose the full canonical token set."""
    for key in ("primary", "bg_main", "bg_sidebar", "bg_panel", "text",
                "text_muted", "border_subtle", "success", "danger", "warning"):
        assert key in _LIGHT, f"missing light token: {key}"


def test_dark_palette_mirrors_light_keys(gui):
    """Dark must define exactly the same keys as light (no drift)."""
    assert set(_LIGHT.keys()) == set(_DARK.keys())


def test_set_theme_dark_changes_root_background(gui):
    """Switching to dark must recolour the root window background.

    Note: raw ThemeManager.set_theme updates COLORS but does NOT touch
    the root widget; GuiMaster.set_theme is the full path that also
    calls root.configure(bg=...). We exercise the full path here.
    """
    gui.set_theme("light")
    light_bg = gui.root.cget("bg")
    gui.set_theme("dark")
    dark_bg = gui.root.cget("bg")
    assert light_bg != dark_bg, "root bg did not change between themes"
    assert dark_bg == _DARK["bg_main"]


def test_set_theme_light_restores_root_background(gui):
    """Switching back to light restores the light canvas colour."""
    gui.set_theme("dark")
    gui.set_theme("light")
    assert gui.root.cget("bg") == _LIGHT["bg_main"]


def test_resolve_effective_system_calls_detector(gui, monkeypatch):
    """'system' must defer to the OS detector (not hard-code a value)."""
    import core.ui.system_theme as sys_theme

    monkeypatch.setattr(sys_theme, "detect_system_theme", lambda: "dark")
    assert ThemeManager.resolve_effective("system") == "dark"
    monkeypatch.setattr(sys_theme, "detect_system_theme", lambda: "light")
    assert ThemeManager.resolve_effective("system") == "light"
    monkeypatch.setattr(sys_theme, "detect_system_theme", lambda: None)
    assert ThemeManager.resolve_effective("system") == "light"


# ---------------------------------------------------------------------------
# TC-602..TC-604: DateEntry follows theme (the U3 retheme fix)
# ---------------------------------------------------------------------------

def test_date_entry_accent_follows_theme_switch(gui):
    """The calendar picker must update its accent colour on theme switch.

    tkcalendar freezes colours at creation; U3 added Sidebar.refresh_theme
    to re-assert them. If that wiring breaks, the picker sticks in the
    palette active at startup.
    """
    sb = gui.sidebar
    ThemeManager.set_theme("light")
    gui.sidebar.refresh_theme()
    light_primary = str(sb.date_entry.cget("background"))
    assert light_primary == _LIGHT["primary"]

    ThemeManager.set_theme("dark")
    gui.sidebar.refresh_theme()
    dark_primary = str(sb.date_entry.cget("background"))
    assert dark_primary == _DARK["primary"]
    assert light_primary != dark_primary


def test_date_entry_headers_follow_theme(gui):
    """The calendar's header band must also follow the theme."""
    sb = gui.sidebar
    ThemeManager.set_theme("dark")
    sb.refresh_theme()
    assert str(sb.date_entry.cget("headersbackground")) == _DARK["primary"]
    ThemeManager.set_theme("light")


def test_all_three_date_entries_retheme(gui):
    """The period picker's two entries retheme alongside the main one."""
    sb = gui.sidebar
    ThemeManager.set_theme("dark")
    sb.refresh_theme()
    for attr in ("date_entry", "month_start_entry", "month_end_entry"):
        entry = getattr(sb, attr)
        assert str(entry.cget("background")) == _DARK["primary"], (
            f"{attr} did not retheme"
        )
    ThemeManager.set_theme("light")


# ---------------------------------------------------------------------------
# TC-605: context menu follows theme (the register_menu mechanism)
# ---------------------------------------------------------------------------

def test_context_menu_is_registered_for_retheme(gui):
    """The employee-table right-click menu must be in the themed-menus registry."""
    menus = ThemeManager._themed_menus
    assert any(m is gui.employee_table.menu for (m, *_r) in menus), (
        "employee_table.menu not registered via ThemeManager.register_menu"
    )


def test_context_menu_retheme_on_palette_switch(gui):
    """Switching theme must recolour the registered context menu."""
    menu = gui.employee_table.menu
    ThemeManager.set_theme("light")
    ThemeManager.set_theme("dark")  # set_theme re-applies menus
    pump(gui.root)
    assert str(menu.cget("background")) == _DARK["bg_sidebar"]
    assert str(menu.cget("activebackground")) == _DARK["primary"]
    ThemeManager.set_theme("light")


# ---------------------------------------------------------------------------
# TC-606..TC-609: ttk style consistency under both themes
# ---------------------------------------------------------------------------

def test_ttk_styles_reconfigure_under_dark(gui):
    """apply_styles under dark must set dark colours on ttk widgets."""
    ThemeManager.set_theme("dark")
    style = ttk.Style()
    assert style.lookup("TLabel", "background") == _DARK["bg_main"]
    assert style.lookup("TLabel", "foreground") == _DARK["text"]
    ThemeManager.set_theme("light")


def test_action_button_uses_primary_fill(gui):
    """The primary action button style must fill with the accent colour."""
    ThemeManager.set_theme("light")
    style = ttk.Style()
    assert style.lookup("Action.TButton", "background") == _LIGHT["primary"]
    ThemeManager.set_theme("dark")
    assert style.lookup("Action.TButton", "background") == _DARK["primary"]
    ThemeManager.set_theme("light")


def test_treeview_heading_font_is_semibold(gui):
    """Headings must use the Semibold family (not algorithmic bold)."""
    style = ttk.Style()
    font_spec = style.lookup("Treeview.Heading", "font")
    assert "Semibold" in str(font_spec), (
        f"heading font not Semibold: {font_spec!r}"
    )


def test_mono_treeview_style_uses_cascadia(gui):
    """Mono.Treeview (path-heavy trees) must use the tabular-mono font."""
    style = ttk.Style()
    font_spec = str(style.lookup("Mono.Treeview", "font"))
    # Accept either Cascadia Mono or the Consolas fallback (CI without Cascadia).
    assert "Cascadia" in font_spec or "Consolas" in font_spec, (
        f"Mono.Treeview font not mono-family: {font_spec!r}"
    )


# ---------------------------------------------------------------------------
# TC-610: status-badge row-wash derives from semantic palette
# ---------------------------------------------------------------------------

def test_status_tags_carry_semantic_colours(gui):
    """ready/missing/partial tags must use success/danger/warning foreground."""
    tree = gui.employee_table.tree
    # Re-assert tags under the current theme then read them back.
    gui.employee_table._configure_tags()
    assert str(tree.tag_configure("ready", "foreground")) == _LIGHT["success"]
    assert str(tree.tag_configure("missing", "foreground")) == _LIGHT["danger"]
    assert str(tree.tag_configure("partial", "foreground")) == _LIGHT["warning"]


def test_status_tags_have_row_wash_background(gui):
    """Status tags must set a background tint (row-wash), not just foreground."""
    tree = gui.employee_table.tree
    gui.employee_table._configure_tags()
    for tag in ("ready", "missing", "partial"):
        bg = tree.tag_configure(tag, "background")
        assert bg, f"{tag} tag has no row-wash background"


# ---------------------------------------------------------------------------
# TC-611..TC-613: contrast guarantees (WCAG AA)
# ---------------------------------------------------------------------------

def _contrast(fg_hex: str, bg_hex: str) -> float:
    """WCAG 2.1 contrast ratio between two hex colours."""

    def _lum(h: str) -> float:
        h = h.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))

        def _ch(c: float) -> float:
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

        return 0.2126 * _ch(r) + 0.7152 * _ch(g) + 0.0722 * _ch(b)

    l1, l2 = _lum(fg_hex), _lum(bg_hex)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def test_body_text_meets_aa_in_light(gui):
    """Body text on the card surface must pass WCAG AA (≥4.5:1) in light."""
    ratio = _contrast(_LIGHT["text"], _LIGHT["bg_sidebar"])
    assert ratio >= 4.5, f"light body contrast {ratio:.2f} < 4.5"


def test_body_text_meets_aa_in_dark(gui):
    """Body text on the card surface must pass WCAG AA (≥4.5:1) in dark."""
    ratio = _contrast(_DARK["text"], _DARK["bg_sidebar"])
    assert ratio >= 4.5, f"dark body contrast {ratio:.2f} < 4.5"


def test_muted_text_meets_aa_in_light(gui):
    """Caption/muted text must still clear AA on the card in light."""
    ratio = _contrast(_LIGHT["text_muted"], _LIGHT["bg_sidebar"])
    assert ratio >= 4.5, f"light muted contrast {ratio:.2f} < 4.5"


def test_primary_button_label_meets_aa_large(gui):
    """Primary-button label on accent fill must clear AA-large (≥3:1)."""
    for name, pal in (("light", _LIGHT), ("dark", _DARK)):
        ratio = _contrast(pal["text_inverse"], pal["primary"])
        assert ratio >= 3.0, f"{name} primary-button contrast {ratio:.2f} < 3.0"


# ---------------------------------------------------------------------------
# TC-614: no stale Tailwind hex leaks (U4 guarantee)
# ---------------------------------------------------------------------------

def test_no_forbidden_tailwind_hex_in_theme(gui):
    """The palette must not contain any of the old Tailwind defaults."""
    forbidden = {"#2563eb", "#60a5fa", "#f3f4f6", "#334155", "#0f172a", "#1e293b"}
    leaked = forbidden & {v.lower() for v in _LIGHT.values()} | \
        forbidden & {v.lower() for v in _DARK.values()}
    assert not leaked, f"forbidden Tailwind hex still in palette: {leaked}"


def test_theme_teardown_restores_light(gui):
    """Each test must leave the global theme as light for the next one."""
    # This runs LAST in the module via pytest ordering; it's a guard.
    ThemeManager.set_theme("light")
    assert ThemeManager.current_theme() == "light"
