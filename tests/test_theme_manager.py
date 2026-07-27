"""Tests for the dark/light theme manager and the system-theme resolver.

The theme manager is intentionally pure (no Tk) so we can drive most
of it from a normal test. The only Tk-bound surface is ``apply_styles``,
which we exercise through a withdrawn Tk root.
"""
import tkinter as tk
from unittest.mock import patch

import pytest
from core.ui.theme import ThemeManager


@pytest.fixture
def fresh_theme():
    """Reset the theme between tests so we never see leakage."""
    yield
    ThemeManager.set_theme("light")


def test_default_theme_is_light(fresh_theme):
    assert ThemeManager.current_theme() == "light"
    # Reference the palette's own value rather than a hard-coded hex so
    # the test survives deliberate palette redesigns (see
    # workspace/sources/design_system.json) while still verifying that
    # the light palette's bg_main is actually loaded into COLORS.
    from core.ui.theme import _LIGHT

    assert ThemeManager.COLORS["bg_main"] == _LIGHT["bg_main"]


def test_set_theme_dark_changes_palette(fresh_theme):
    ThemeManager.set_theme("dark")
    assert ThemeManager.current_theme() == "dark"
    from core.ui.theme import _DARK

    assert ThemeManager.COLORS["bg_main"] == _DARK["bg_main"]
    # And it must differ from light — otherwise the switch is a no-op.
    from core.ui.theme import _LIGHT

    assert _DARK["bg_main"] != _LIGHT["bg_main"]


def test_set_theme_unknown_raises(fresh_theme):
    with pytest.raises(ValueError):
        ThemeManager.set_theme("neon-pink")


def test_palette_returns_fresh_copy(fresh_theme):
    a = ThemeManager.palette()
    a["bg_main"] = "#000000"
    b = ThemeManager.palette()
    assert b["bg_main"] != "#000000"


def test_resolve_effective_passthrough(fresh_theme):
    assert ThemeManager.resolve_effective("light") == "light"
    assert ThemeManager.resolve_effective("dark") == "dark"


def test_resolve_effective_system_calls_detector(fresh_theme):
    with patch("core.ui.system_theme.detect_system_theme", return_value="dark") as d:
        assert ThemeManager.resolve_effective("system") == "dark"
        d.assert_called_once()


def test_resolve_effective_system_fallback_when_detector_returns_none(fresh_theme):
    with patch("core.ui.system_theme.detect_system_theme", return_value=None):
        assert ThemeManager.resolve_effective("system") == "light"


def test_apply_styles_writes_ttk_options(fresh_theme):
    try:
        root = tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"Tk not available: {e}")
    root.withdraw()
    try:
        ThemeManager.set_theme("dark")
        from tkinter import ttk
        style = ttk.Style()
        assert style.lookup("TLabel", "background") == ThemeManager.COLORS["bg_main"]
        ThemeManager.set_theme("light")
        # ttk style must follow whichever palette is active — reference
        # the palette rather than a hard-coded hex so the assertion
        # holds across palette redesigns.
        from core.ui.theme import _LIGHT

        assert style.lookup("TLabel", "background") == _LIGHT["bg_main"]
    finally:
        root.destroy()
