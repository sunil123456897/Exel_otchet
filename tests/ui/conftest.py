"""Test harness for Tkinter UI automation.

Builds a REAL GuiMaster (full window with sidebar, notebook, all 7 tabs,
toasts, shortcuts, theme system) driven by MOCK controllers — so the
tests exercise actual widget rendering, event handling, and introspection
without needing a database, network drives, or Excel files.

The root window is created and withdrawn (never shown on screen) but all
Tk calls work: widget construction, event_generate, cget, winfo_*,
ttk.Style lookups, update()/update_idletasks() to flush the event queue.

Skip policy: if this environment cannot create a Tk root (headless CI
without a display server), the whole module is skipped via the `gui`
fixture rather than failing — matching the project's existing pattern in
test_theme_manager.py / test_operation_status_bar.py.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from core.ui.theme import ThemeManager

# ---------------------------------------------------------------------------
# Mock controllers
# ---------------------------------------------------------------------------


def _make_mock_config_controller(tmp_path: Path) -> MagicMock:
    """A ConfigController stand-in that returns safe defaults.

    GuiMaster only reads UI preferences + a couple of path keys at
    construction; it never writes through the mock. Returning a real
    UIPreferences object keeps SettingsStore happy without a YAML file.
    """
    from core.infra.settings_store import UIPreferences

    cfg = MagicMock(name="ConfigController")
    cfg.config_path = str(tmp_path / "config.yaml")
    # SettingsStore calls config_controller.resolve_path / get on a few
    # keys; the mock returns the tmp dir so nothing touches the real FS.
    cfg.resolve_path = MagicMock(return_value=tmp_path)
    cfg.get = MagicMock(return_value=None)
    cfg.get_ui_preferences = MagicMock(return_value=UIPreferences())
    cfg.set_ui_preferences = MagicMock()
    return cfg


def _make_mock_app_controller() -> MagicMock:
    """An AppController stand-in. GuiMaster binds callbacks to it but the
    heavy operations (consolidation/RSCH/reconciliation) are never
    actually invoked in UI tests — we test that the BUTTONS exist, are
    bound, and report the right state, not that the finance engine runs.
    """
    app = MagicMock(name="AppController")
    # ConsolidationViewModel stores a ref to app_controller and may call
    # .consolidate / .shutdown on shutdown(); the mock accepts anything.
    app.shutdown = MagicMock()
    return app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tk_root():
    """A module-scoped withdrawn Tk root.

    Re-creating Tk per-test is slow and leaks window handles on Windows;
    a single root per module is the established pattern (see
    test_operation_status_bar.py). Tests that mutate global Tk state
    (e.g. ThemeManager) must restore it via the `fresh_theme` fixture.
    """
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # no display server
        pytest.skip(f"Tk not available: {exc}")
    root.withdraw()
    # Force a deterministic geometry so tests asserting on window size
    # aren't dependent on the host monitor.
    root.geometry("1100x840+0+0")
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


@pytest.fixture
def fresh_theme():
    """Reset ThemeManager to light between tests to prevent leakage.

    GuiMaster's constructor calls _load_theme_early which can switch the
    global palette; this fixture guarantees each test starts from a known
    baseline and restores it on teardown.
    """
    ThemeManager.set_theme("light")
    yield
    ThemeManager.set_theme("light")


@pytest.fixture
def gui(tk_root, fresh_theme, tmp_path):
    """Build a full GuiMaster with mock controllers.

    Yields the GuiMaster instance with every widget already constructed:
    sidebar, notebook (7 tabs), employee_table, stats_panel, toasts,
    operation_state, shortcuts bound. Use ``gui.root.update()`` to flush
    pending events after programmatic interactions.

    The slow FS/network calls that GuiMaster/DashboardTabs trigger on a
    background thread (collect_report_paths, run_light_diagnostics) are
    patched to return empty results — this keeps the daemon thread from
    touching the real filesystem and from outliving the test session.
    """
    # Patch the heavy background work BEFORE GuiMaster construction so
    # DashboardTabs.refresh()'s daemon thread returns instantly. These
    # functions walk network drives / read log files; in UI tests we
    # only care about widget rendering, not their output.
    #
    # Additionally, stub DashboardTabs._run_in_background so it runs
    # `work` synchronously on the main thread and calls `done` directly
    # — avoiding a daemon thread that outlives the root window and
    # raises "main thread is not in main loop" on teardown.
    def _sync_run_in_background(self_dash, work, on_done, *_a, **_kw):
        try:
            result = work()
        except Exception:
            result = None
        try:
            on_done(result)
        except Exception:
            pass

    with patch("core.ui.ui_dashboard.collect_report_paths",
               return_value=[]), \
         patch("core.ui.ui_dashboard.run_light_diagnostics",
               return_value=[]), \
         patch("core.ui.ui_dashboard.load_runtime_results",
               return_value=[]), \
         patch("core.ui.ui_dashboard.DashboardTabs._run_in_background",
               _sync_run_in_background), \
         patch("core.ui.welcome_dialog.show_welcome_if_first_run",
               lambda *a, **kw: None):
        from core.ui.gui_master import GuiMaster

        cfg = _make_mock_config_controller(tmp_path)
        app = _make_mock_app_controller()
        master = GuiMaster(tk_root, cfg, app)
        # Flush the construction-time after() callbacks (title poll,
        # theme poll, the refresh_status scheduled at +100ms) so they
        # don't fire mid-test. The welcome dialog is patched out above
        # so no modal grab is taken.
        pump(tk_root)
        _cancel_after_callbacks(tk_root)
        # refresh_status (scheduled at +100ms) begins a REFRESH
        # operation that the mock controller never ends — reset to a
        # clean idle baseline so tests asserting is_busy==False pass.
        # Also re-apply the idle snapshot to the sidebar so its action
        # buttons (disabled by the REFRESH begin) are re-enabled: the
        # operation-state listener doesn't fire on a bare end() call.
        try:
            master.operation_state.end()
            master.sidebar.apply(master.operation_state.snapshot())
        except Exception:
            pass
        yield master
        # Teardown: invalidate the icon cache AND clear the registered-
        # widget list so PhotoImages built for this GuiMaster instance
        # don't linger (they reference the module-scoped root and would
        # cause "image doesn't exist" errors when the next module
        # rebuilds GuiMaster). Without clearing _registered, a theme
        # switch in the next test tries to re-apply icons to destroyed
        # widgets from this test.
        try:
            from core.ui.icons import IconManager
            IconManager._cache.clear()
            IconManager._registered.clear()
        except Exception:
            pass
        # Destroy the GuiMaster-owned widgets so the module-scoped root
        # is clean for the next test.
        try:
            master.sidebar.destroy()
        except (tk.TclError, AttributeError):
            pass
        try:
            master.main_area.destroy()
        except (tk.TclError, AttributeError):
            pass
        # Release any leftover modal grab and destroy stray Toplevels.
        _destroy_all_toplevels(tk_root)
    # Teardown: cancel recurring after() polls so the module-scoped root
    # stays clean for the next test.
    _cancel_after_callbacks(tk_root)
    ThemeManager.set_theme("light")


# ---------------------------------------------------------------------------
# Helpers (importable by test modules via `from conftest import ...`)
# ---------------------------------------------------------------------------


def _cancel_after_callbacks(root: tk.Tk) -> None:
    """Best-effort cancellation of pending root.after() callbacks.

    Tk doesn't expose a list of pending after-ids, so we rely on
    dooming the scheduler: each recurring poll checks for TclError on
    root.after and dies quietly. Cancelling isn't strictly necessary
    (the root is withdrawn) but reduces noise in -v output.
    """
    try:
        root.after_cancel("all")  # Tk 8.6 supports "all" sentinel
    except tk.TclError:
        pass


def _destroy_all_toplevels(root: tk.Tk) -> None:
    """Destroy every transient Toplevel under the root.

    Welcome/shortcuts/settings dialogs create transient Toplevels that
    call grab_set; if one leaks past a test it freezes subsequent
    interactions. This walks the toplevel widget list and tears down
    anything that isn't the root itself.
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


def pump(root: tk.Misc, times: int = 3) -> None:
    """Process pending Tk events so async state propagates.

    Equivalent to letting the event loop tick a few times — needed
    after event_generate / after(0, ...) callbacks before asserting on
    widget state. Mirrors what a user sees after a brief pause.
    """
    for _ in range(times):
        try:
            root.update_idletasks()
            root.update()
        except tk.TclError:
            break


def find_widget(parent: tk.Misc, winfo_class: str) -> tk.Misc | None:
    """Recursively find the first descendant matching a winfo class.

    ``winfo_class`` examples: "TButton", "TEntry", "Treeview",
    "TNotebook", "TCombobox". Returns None if not found. Useful when a
    test needs to poke a widget it doesn't hold a direct reference to.
    """
    try:
        for child in parent.winfo_children():
            try:
                if child.winfo_class() == winfo_class:
                    return child
            except tk.TclError:
                continue
            found = find_widget(child, winfo_class)
            if found is not None:
                return found
    except tk.TclError:
        pass
    return None


def find_all(parent: tk.Misc, winfo_class: str) -> list:
    """Find ALL descendants matching a winfo class (depth-first order)."""
    results: list = []
    try:
        for child in parent.winfo_children():
            try:
                if child.winfo_class() == winfo_class:
                    results.append(child)
            except tk.TclError:
                continue
            results.extend(find_all(child, winfo_class))
    except tk.TclError:
        pass
    return results
