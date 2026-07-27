"""Automated UI tests for the top-level window chrome.

Implements check-list TC-101 ... TC-115 from
``docs/superdoc/04_TEST_PLAN.md``. Each test exercises the observable,
user-visible contract of :class:`GuiMaster` — window title, icon,
geometry / minsize, notebook tabs, the nine global hotkeys, the F1
shortcuts dialog, theme background, and the existence of the core
collaborators (operation_state, toasts, commands) — through the public
``gui`` fixture, never by reaching into GuiMaster internals.

The tests are black-box: they only call public Tk widgets and
attributes that a user or platform window manager would also touch.
"""
import re
import tkinter as tk
from pathlib import Path

import pytest
from conftest import find_widget, pump
from core.ui.theme import ThemeManager

# Repo-relative path to the brand icon asset. Resolved once at import
# time so a missing asset fails the relevant tests loudly (rather than
# each test re-computing the path).
REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ICO = REPO_ROOT / "APP" / "assets" / "icons" / "app.ico"

# Canonical list of the nine shortcuts GuiMaster._bind_shortcuts must
# register on the root window (UX-006). Listed here rather than scraped
# from the source so this file is the spec — a regression that drops a
# binding fails with a readable diff.
EXPECTED_SHORTCUTS = (
    "<Control-d>",
    "<Control-D>",
    "<Control-m>",
    "<Control-r>",
    "<Control-R>",
    "<Control-e>",
    "<F5>",
    "<Escape>",
    "<F1>",
)

# ``geometry()`` returns "WxH+X+Y" (or "WxH-X-Y" for negative coords on
# multi-monitor setups). Capture once so the parsing stays consistent
# across the geometry / minsize tests.
_GEOMETRY_RE = re.compile(r"^(\d+)x(\d+)([+-]-?\d+)([+-]-?\d+)$")


# ---------------------------------------------------------------------------
# TC-101 — window title
# ---------------------------------------------------------------------------


def test_window_title_has_no_emoji(gui):
    """The window title must not carry a decorative rocket emoji."""
    title = gui.root.title()
    assert "🚀" not in title, f"title unexpectedly contains emoji: {title!r}"


def test_window_title_contains_version_prefix(gui):
    """The window title must advertise the app name and version."""
    title = gui.root.title()
    assert "Master-Report v" in title, f"title missing brand prefix: {title!r}"


# ---------------------------------------------------------------------------
# TC-102 — window icon
# ---------------------------------------------------------------------------


def test_apply_window_icon_method_exists(gui):
    """GuiMaster must expose the icon-application seam (U10 brand identity)."""
    assert callable(getattr(gui, "_apply_window_icon", None))


def test_window_icon_asset_is_present():
    """The brand ``app.ico`` asset must ship with the app."""
    assert APP_ICO.exists(), f"missing icon asset: {APP_ICO}"


def test_window_icon_asset_is_valid_multires():
    """``app.ico`` must contain 16x16 and 256x256 sub-images (taskbar + alt-tab)."""
    try:
        from PIL import Image
    except ImportError:
        pytest.skip("Pillow not installed; cannot introspect .ico")
    if not APP_ICO.exists():
        pytest.skip("app.ico missing; covered by test_window_icon_asset_is_present")
    with Image.open(APP_ICO) as im:
        sizes = set(im.ico.sizes())
    assert (16, 16) in sizes, f"16x16 entry missing from {sizes}"
    assert (256, 256) in sizes, f"256x256 entry missing from {sizes}"


def test_window_icon_is_applied(gui):
    """The icon must actually be set on the root (iconbitmap on Windows).

    iconbitmap on Windows sets the icon via Win32 directly and does NOT
    register a Tk image (so the image-registry check is unreliable). The
    stable signal is that ``root.iconbitmap`` was actually called during
    construction with a real .ico path — verified here by re-running the
    method with a spy on ``root.iconbitmap``.
    """
    from unittest.mock import patch

    with patch.object(gui.root, "iconbitmap") as spy:
        gui._apply_window_icon()
    # iconbitmap must have been called with the .ico path (first arg).
    assert spy.called, "iconbitmap was never called — icon step is a no-op"
    args, _ = spy.call_args
    assert str(args[0]).endswith("app.ico"), f"unexpected icon path: {args[0]}"


# ---------------------------------------------------------------------------
# TC-103 / TC-104 — geometry and minsize
# ---------------------------------------------------------------------------


def test_geometry_string_is_well_formed(gui):
    """``geometry()`` must return the canonical WxH+X+Y form."""
    geom = gui.root.geometry()
    assert _GEOMETRY_RE.match(geom) is not None, f"malformed geometry: {geom!r}"


def test_geometry_meets_minimum_window_size(gui):
    """The realized window must be at least 640x420 (readability floor)."""
    geom = gui.root.geometry()
    m = _GEOMETRY_RE.match(geom)
    assert m is not None, f"malformed geometry: {geom!r}"
    width, height = int(m.group(1)), int(m.group(2))
    assert width >= 640, f"window too narrow: {width}"
    assert height >= 420, f"window too short: {height}"


def test_minsize_meets_floor(gui):
    """``minsize()`` must not let the user shrink below 640x420."""
    min_w, min_h = gui.root.minsize()
    assert min_w >= 640, f"minsize width below floor: {min_w}"
    assert min_h >= 420, f"minsize height below floor: {min_h}"


# ---------------------------------------------------------------------------
# TC-105 / TC-106 — notebook tabs
# ---------------------------------------------------------------------------


def test_notebook_has_seven_tabs(gui):
    """DashboardTabs must register exactly seven tabs."""
    tabs = gui.notebook.tabs()
    assert len(tabs) == 7, f"expected 7 tabs, got {len(tabs)}"


def test_first_tab_is_employees(gui):
    """The leftmost tab must be the Сотрудники (employees) tab."""
    first = gui.notebook.tabs()[0]
    text = gui.notebook.tab(first, "text")
    assert "Сотрудник" in text, f"first tab text was {text!r}"


def test_first_tab_is_selected_by_default(gui):
    """On startup the employees tab must be the active tab."""
    assert gui.notebook.select() == gui.notebook.tabs()[0]


# ---------------------------------------------------------------------------
# TC-107 — global hotkeys
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sequence", EXPECTED_SHORTCUTS)
def test_global_shortcut_is_bound(gui, sequence):
    """Each documented hotkey must carry a bound command on the root."""
    bound = gui.root.bind(sequence)
    assert bound, f"no command bound to {sequence!r} on root"


def test_all_expected_shortcuts_are_bound(gui):
    """All nine hotkeys are present in one shot (regression summary)."""
    missing = [s for s in EXPECTED_SHORTCUTS if not gui.root.bind(s)]
    assert not missing, f"unbound shortcuts: {missing}"


# ---------------------------------------------------------------------------
# TC-108 — F1 opens the shortcuts dialog
# ---------------------------------------------------------------------------


def test_f1_opens_shortcuts_dialog(gui):
    """show_shortcuts() must surface the modal reference Toplevel.

    We call ``gui.show_shortcuts()`` directly rather than synthesising an
    F1 key event: event_generate on a withdrawn window is unreliable
    (focus may be on an Entry, triggering the _guard), and the transient
    Toplevel that shortcuts_dialog creates isn't always reachable via
    winfo_children. Calling the method directly is the deterministic
    contract — the F1 binding is verified separately in
    test_global_shortcut_is_bound.
    """
    gui.show_shortcuts()
    pump(gui.root)

    # The dialog is a transient Toplevel — search all of Tk's toplevel
    # windows (including transient ones) for one whose title matches.
    found = None
    try:
        for w in gui.root.tk.call("winfo", "children", ".") or []:
            try:
                title = gui.root.tk.call("wm", "title", w)
            except tk.TclError:
                title = ""
            if "клавиш" in str(title).lower() or "shortcut" in str(title).lower():
                found = w
                break
    except tk.TclError:
        pass
    assert found is not None, "show_shortcuts() did not open a titled dialog"

    # Always tear down: grab_release + destroy, never let it leak.
    _destroy_all_dialogs(gui.root)
    pump(gui.root)


def _destroy_all_dialogs(root):
    """Destroy every transient Toplevel that isn't the root itself.

    Prevents modal grabs from leaking across tests when a dialog test
    opens a Toplevel that grabs the pointer.
    """
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


# ---------------------------------------------------------------------------
# TC-109 — theme background
# ---------------------------------------------------------------------------


def test_root_background_matches_theme(gui):
    """The root window background must match the active theme palette."""
    expected = ThemeManager.COLORS["bg_main"]
    assert gui.root.cget("bg") == expected, (
        f"root bg {gui.root.cget('bg')!r} != theme bg_main {expected!r}"
    )


# ---------------------------------------------------------------------------
# TC-110 — operation_state
# ---------------------------------------------------------------------------


def test_operation_state_exists_and_not_busy(gui):
    """After construction the app must not report a running operation."""
    assert gui.operation_state is not None
    assert gui.operation_state.is_busy is False


# ---------------------------------------------------------------------------
# TC-111 / TC-112 — toasts and commands
# ---------------------------------------------------------------------------


def test_toast_manager_exists(gui):
    """The toast notifier must be wired up (success/error popups)."""
    assert gui.toasts is not None


def test_commands_object_exists(gui):
    """The GuiCommands facade must be constructed and reachable."""
    assert gui.commands is not None


# ---------------------------------------------------------------------------
# TC-113 — welcome dialog must not block startup
# ---------------------------------------------------------------------------


def test_no_modal_grab_held_after_construction(gui):
    """Startup must not leave a modal grab pinned on the root."""
    # Welcome/shortcuts dialogs call grab_set; if one leaked past
    # construction it would freeze every later interaction. The harness
    # flushes the construction-time after() callbacks, so by now any
    # modal Toplevel that was supposed to appear has either shown up
    # (and grabbed) or been suppressed by the display heuristic.
    pump(gui.root)
    assert gui.root.grab_current() is None, (
        "a modal grab is held after construction — welcome/shortcuts "
        "dialog may be blocking the UI"
    )


# ---------------------------------------------------------------------------
# TC-114 / TC-115 — icon file validity (covered by the asset tests above;
# kept here as an explicit TC anchor so the test-plan trace is readable)
# ---------------------------------------------------------------------------


def test_find_widget_helper_sees_notebook(gui):
    """Sanity-check the harness: the notebook is discoverable via winfo_class."""
    nb = find_widget(gui.root, "TNotebook")
    assert nb is not None, "harness could not locate the ttk.Notebook by class"
    assert nb is gui.notebook
