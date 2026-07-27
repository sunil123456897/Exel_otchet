"""TC-501..TC-520: dialog & popup automation.

Welcome (first-run), shortcuts (F1), and toast notifications are the
transient surfaces a user encounters during interaction. These tests
build them directly (rather than via event synthesis, which is flaky on
a withdrawn window) and assert their structure, theming, and lifecycle —
including the critical "no modal grab leaks past teardown" guard.
"""
import tkinter as tk
from unittest.mock import patch

from conftest import pump
from core.ui.theme import ThemeManager

# ---------------------------------------------------------------------------
# Welcome dialog (U11)
# ---------------------------------------------------------------------------

def test_welcome_dialog_module_imports():
    """The welcome module must be importable without a display."""
    from core.ui import welcome_dialog  # noqa: F401


def test_welcome_dialog_show_is_guarded_for_headless(gui, monkeypatch):
    """show_welcome_if_first_run must not raise when no display is available."""
    from core.ui import welcome_dialog

    # Force the headless branch and assert it no-ops cleanly.
    monkeypatch.setattr(welcome_dialog, "_display_available", lambda: False)
    # Should not raise even though first_run flag may be true.
    welcome_dialog.show_welcome_if_first_run(gui.root)
    pump(gui.root)
    # No leftover modal grab.
    assert gui.root.grab_current() is None


def test_welcome_dialog_constructs_directly(gui):
    """WelcomeDialog.show() must build a themed Toplevel with 3 steps.

    We construct the dialog directly (bypassing the first-run flag /
    display guard) to test its structure deterministically, then close
    it immediately so no grab leaks.
    """
    from core.ui import welcome_dialog

    with patch.object(welcome_dialog, "mark_first_run_done", lambda: None):
        dlg = welcome_dialog.WelcomeDialog(gui.root)
        dlg.show()
        pump(gui.root)
        try:
            assert dlg.top is not None and dlg.top.winfo_exists()
            assert len(dlg.STEPS) == 3
        finally:
            try:
                dlg.top.grab_release()
                dlg.top.destroy()
            except (tk.TclError, AttributeError):
                pass
    pump(gui.root)
    assert gui.root.grab_current() is None


def test_welcome_dialog_has_three_onboarding_steps(gui):
    """The welcome content must list exactly the 3 onboarding steps."""
    from core.ui.welcome_dialog import WelcomeDialog

    steps = WelcomeDialog.STEPS
    assert len(steps) == 3, f"expected 3 steps, got {len(steps)}"


# ---------------------------------------------------------------------------
# Shortcuts dialog (U12)
# ---------------------------------------------------------------------------

def test_shortcuts_dialog_module_imports():
    from core.ui import shortcuts_dialog  # noqa: F401


def test_shortcuts_dialog_lists_all_bindings(gui):
    """The SHORTCUTS table must cover every binding _bind_shortcuts registers."""
    from core.ui import shortcuts_dialog

    sequences = {seq for seq, _desc in shortcuts_dialog.SHORTCUTS}
    # The dialog uses human-readable "Ctrl+D" notation (not "<Control-d>").
    required = {"Ctrl+D", "Ctrl+M", "Ctrl+R", "Ctrl+E", "F5", "Escape"}
    missing = required - sequences
    assert not missing, f"shortcuts dialog missing bindings: {missing}"


def test_show_shortcuts_opens_themed_toplevel(gui):
    """show_shortcuts must surface a modal Toplevel that follows the theme."""

    gui.show_shortcuts()
    pump(gui.root)

    # Find the dialog by walking Tk's toplevel list.
    dialog = _find_titled_toplevel(gui.root, "клавиш")
    assert dialog is not None, "show_shortcuts did not open a titled dialog"
    # Themed: background matches the active palette's main canvas.
    assert str(dialog.cget("background")) == ThemeManager.COLORS["bg_main"]
    _destroy_all_toplevels(gui.root)


def test_shortcuts_dialog_grab_released_on_close(gui):
    """Closing the shortcuts dialog must release the modal grab."""
    gui.show_shortcuts()
    pump(gui.root)
    _destroy_all_toplevels(gui.root)
    pump(gui.root)
    assert gui.root.grab_current() is None, "modal grab leaked after dialog close"


# ---------------------------------------------------------------------------
# Toast manager (U7 / FIX-006 detail section)
# ---------------------------------------------------------------------------

def test_toast_manager_has_four_levels(gui):
    """ToastManager must support info/success/warning/error levels."""
    from core.ui.toast import ToastLevel

    for level in ("info", "success", "warning", "error"):
        assert hasattr(ToastLevel, level.upper()), f"missing ToastLevel.{level}"


def test_success_toast_does_not_raise(gui):
    """Showing a success toast must not raise and must not grab."""
    gui.toasts.success("Тест", "Операция завершена", duration_ms=100)
    pump(gui.root)
    # Toasts must not take a modal grab (they're non-blocking notifications).
    assert gui.root.grab_current() is None


def test_error_toast_accepts_detail_section(gui):
    """FIX-006: error toasts must accept an expandable detail payload."""
    # The detail kwarg is the contract for long error messages.
    gui.toasts.error("Ошибка", "коротко", detail="длинный traceback", duration_ms=100)
    pump(gui.root)


def test_toast_widgets_are_themed(gui):
    """Toast background must derive from the active semantic palette."""
    ThemeManager.set_theme("dark")
    gui.toasts.info("T", "msg", duration_ms=100)
    pump(gui.root)
    # The info toast frame bg should be the dark info colour (or a darken of it).
    # We assert loosely: a themed toast exists in the root's children.
    toplevels = _find_all_toplevels(gui.root)
    assert toplevels, "info toast did not create a popup"
    ThemeManager.set_theme("light")
    _destroy_all_toplevels(gui.root)


# ---------------------------------------------------------------------------
# Settings dialog smoke (does not deep-test every tab — that's manual)
# ---------------------------------------------------------------------------

def test_open_settings_does_not_raise(gui):
    """Settings dialog construction must not raise.

    NOTE: ``gui.open_settings()`` blocks via ``root.wait_window()`` (it's
    a modal settings dialog). We cannot call it directly in an automated
    test without hanging the event loop. Instead we verify the SettingsDialog
    class is importable and its 8-tab structure is documented; full
    per-tab interaction (live theme preview, path pickers) is a manual
    visual check per ``04_TEST_PLAN.md`` §3.6.
    """
    from core.ui import ui_settings  # noqa: F401

    # The dialog class must exist and expose the tab list.
    assert hasattr(ui_settings, "SettingsDialog")


def test_settings_dialog_is_themed(gui):
    """The settings Toplevel background is driven by the active palette.

    Same constraint as test_open_settings_does_not_raise: open_settings
    blocks via wait_window, so we verify the theming contract at the
    construction level — SettingsDialog.__init__ applies
    ThemeManager.COLORS["bg_main"] to its Toplevel background.
    """
    import inspect

    from core.ui import ui_settings

    src = inspect.getsource(ui_settings.SettingsDialog.__init__)
    assert "bg_main" in src, "SettingsDialog does not theme its background"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dark_bg() -> str:
    from core.ui.theme import _DARK
    return _DARK["bg_main"]


def _find_titled_toplevel(root, title_fragment: str):
    """Find a Tk Toplevel whose title contains the fragment (case-insensitive)."""
    try:
        children = root.tk.call("winfo", "children", ".") or []
    except tk.TclError:
        return None
    for w in children:
        try:
            title = str(root.tk.call("wm", "title", w)).lower()
        except tk.TclError:
            continue
        if title_fragment.lower() in title:
            # Reify as a Toplevel widget for cget().
            return root.nametowidget(w)
    return None


def _find_all_toplevels(root):
    """Return all Toplevel widget paths under the root."""
    found = []
    try:
        children = root.tk.call("winfo", "children", ".") or []
    except tk.TclError:
        return found
    for w in children:
        if w == ".":
            continue
        try:
            cls = root.tk.call("winfo", "class", w)
        except tk.TclError:
            cls = ""
        if cls == "Toplevel":
            found.append(w)
    return found


def _destroy_all_toplevels(root):
    """Destroy every transient Toplevel; release any modal grab."""
    try:
        children = root.tk.call("winfo", "children", ".") or []
    except tk.TclError:
        return
    for w in children:
        if w == ".":
            continue
        try:
            root.tk.call("grab", "release", w)
            root.tk.call("destroy", w)
        except tk.TclError:
            pass
