"""UI automation for the Sidebar widget — TC-201…TC-232.

These tests drive the *real* Sidebar (built inside the full GuiMaster by the
`gui` fixture) and assert on public behaviour: widget existence, theming,
collapsible panel state, period-range validation, and the global operation
lock that disables every action button while a long-running task is in
flight.

We never run actual consolidation/RSCH/reconciliation — the mock controller
absorbs the command. What we verify is that the button's `invoke()` does not
blow up Tk and that state propagates to the right widgets.
"""
from __future__ import annotations

import datetime

import pytest
from conftest import pump
from core.ui.operation_state import OperationState, OperationType
from core.ui.theme import ThemeManager

# ---------------------------------------------------------------------------
# Tiny helpers
# ---------------------------------------------------------------------------

def _is_disabled(btn) -> bool:
    """ttk buttons report state via `.state()`, not `cget('state')`.

    `.cget('state')` on a ttk widget returns the *style spec*, not the live
    widget state, so it lies about whether the button is clickable. We read
    the live state flags instead.
    """
    return "disabled" in btn.state()


# Every action button that the global operation lock must disable together
# with the per-button state-setter helpers. Mirrors Sidebar's
# ``_OPERATION_BUTTONS_ATTRS``.
_ACTION_BUTTONS = (
    "consolidate_btn",
    "consolidate_all_btn",
    "rsch_btn",
    "reconciliation_btn",
    "auto_reconciliation_btn",
    "consolidate_month_btn",
    "rsch_month_btn",
    "add_employee_btn",
    "attach_btn",
)


# ---------------------------------------------------------------------------
# TC-201..TC-203: network indicator
# ---------------------------------------------------------------------------

def test_network_indicator_exists_and_shows_network_label(gui):
    """TC-201: the sidebar renders a network-drive status indicator."""
    indicator = gui.sidebar._net_indicator
    assert indicator is not None
    text = str(indicator.cget("text"))
    assert "Сеть" in text, f"indicator text should mention 'Сеть', got {text!r}"


# ---------------------------------------------------------------------------
# TC-204..TC-206: date entry
# ---------------------------------------------------------------------------

def test_date_entry_exists_and_is_interactive(gui):
    """TC-204: the main DateEntry exists and is not disabled."""
    entry = gui.sidebar.date_entry
    assert entry is not None
    assert str(entry.cget("state")) != "disabled"


def test_date_entry_has_primary_accent_color(gui):
    """TC-204: the calendar header background is themed to `primary`.

    tkcalendar freezes accent colours at creation, so this proves the
    sidebar built the picker with the active palette rather than a
    hard-coded colour.
    """
    primary = ThemeManager.COLORS["primary"]
    assert str(gui.sidebar.date_entry.cget("background")) == primary
    assert str(gui.sidebar.date_entry.cget("headersbackground")) == primary
    assert str(gui.sidebar.date_entry.cget("selectbackground")) == primary


def test_weekday_tooltip_helper_returns_formatted_string(gui):
    """TC-206: the date-entry tooltip resolves a weekday string."""
    text = gui.sidebar._weekday_tooltip_text()
    assert text, "weekday tooltip should be non-empty for a valid date"
    assert "—" in text, f"expected 'dd.mm.yyyy — weekday', got {text!r}"


# ---------------------------------------------------------------------------
# TC-208: refresh button
# ---------------------------------------------------------------------------

def test_refresh_button_exists(gui):
    """TC-208: the refresh (🔄) button is present."""
    assert gui.sidebar.refresh_btn is not None


def test_refresh_button_invoke_does_not_raise(gui):
    """TC-208: clicking 🔄 forwards to the command without error.

    The button is bound to ``self.controller.refresh_status`` where
    ``self.controller`` is the GuiMaster itself. GuiMaster.refresh_status
    delegates to ``self.commands.refresh_status()``, which calls
    ``employee_vm.refresh(...)`` on a background thread. We only assert
    that invoke() does not raise on the GUI thread — the (mock)
    app_controller absorbs the actual command. The previous assertion
    ``gui.controller.refresh_status.assert_called()`` was wrong:
    GuiMaster has no ``controller`` attribute (it IS the sidebar's
    controller), and even if it did the GuiCommands instance is a real
    object, not a mock.
    """
    try:
        gui.sidebar.refresh_btn.invoke()
    except Exception as exc:  # pragma: no cover - defensive
        pytest.fail(f"refresh_btn.invoke() raised: {exc!r}")
    pump(gui.root)


# ---------------------------------------------------------------------------
# TC-210..TC-211: employee buttons
# ---------------------------------------------------------------------------

def test_add_employee_button_invoke_does_not_raise(gui, monkeypatch):
    """TC-210: ➕ Добавить forwards through the command without error.

    ``add_employee_dialog`` opens a modal ``ask_employee_name`` dialog
    that calls ``wait_window()`` and would block the test forever — so
    we patch the dialog function to return "" (user cancelled), which
    makes ``add_employee_dialog`` return immediately without touching
    the viewmodel. The mock controller absorbs the cancellation.
    """
    from core.ui import ui_dialogs

    monkeypatch.setattr(ui_dialogs, "ask_employee_name", lambda **_kw: "")
    try:
        gui.sidebar.add_employee_btn.invoke()
    except Exception as exc:  # pragma: no cover - defensive
        pytest.fail(f"add_employee_btn.invoke() raised: {exc!r}")
    pump(gui.root)


def test_attach_button_invoke_does_not_raise(gui, monkeypatch):
    """TC-211: 📎 Привязать forwards through the command without error.

    ``attach_file_dialog`` opens a ``show_attach_file_dialog`` Toplevel
    with ``grab_set``; it does not call ``wait_window`` but the grab
    would outlive the test and freeze later interactions. We patch the
    dialog opener to a no-op so the command returns immediately.
    """
    from core.ui import ui_dialogs

    monkeypatch.setattr(ui_dialogs, "show_attach_file_dialog", lambda *a, **kw: None)
    try:
        gui.sidebar.attach_btn.invoke()
    except Exception as exc:  # pragma: no cover - defensive
        pytest.fail(f"attach_btn.invoke() raised: {exc!r}")
    pump(gui.root)


# ---------------------------------------------------------------------------
# TC-212: action buttons + curator combobox
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("attr", _ACTION_BUTTONS)
def test_action_buttons_exist(gui, attr):
    """TC-214..TC-220: every action button is built and is a real widget."""
    assert hasattr(gui.sidebar, attr), f"sidebar is missing {attr}"
    btn = getattr(gui.sidebar, attr)
    assert btn is not None
    # winfo_class confirms it is actually a ttk Button, not a stray None.
    assert btn.winfo_class() == "TButton"


def test_curator_combobox_has_three_curator_options(gui):
    """TC-212: the curator combobox lists Общий / Борис / Иван and is readonly."""
    combo = gui.sidebar.curator_combo
    values = tuple(combo.cget("values"))
    assert len(values) == 3
    joined = " ".join(values)
    assert "Общий" in joined and "Борис" in joined and "Иван" in joined
    assert str(combo.cget("state")) == "readonly"


def test_get_curator_maps_labels_to_codes(gui):
    """TC-213: get_curator translates the combo selection to internal codes."""
    gui.sidebar.curator_var.set("Куратор Борис")
    assert gui.sidebar.get_curator() == "boris"
    gui.sidebar.curator_var.set("Куратор Иван")
    assert gui.sidebar.get_curator() == "ivan"
    gui.sidebar.curator_var.set("Общий отчет")
    assert gui.sidebar.get_curator() is None


# ---------------------------------------------------------------------------
# Date / period public API
# ---------------------------------------------------------------------------

def test_get_date_returns_a_date_instance(gui):
    """Sidebar.get_date surfaces the picker value as a datetime.date."""
    d = gui.sidebar.get_date()
    assert isinstance(d, datetime.date)


def test_get_month_range_returns_two_dates(gui):
    """get_month_range returns a (start, end) pair of dates."""
    start, end = gui.sidebar.get_month_range()
    assert isinstance(start, datetime.date)
    assert isinstance(end, datetime.date)
    assert start <= end


# ---------------------------------------------------------------------------
# TC-223..TC-228: collapsible period panel + range validation
# ---------------------------------------------------------------------------

def test_period_panel_starts_collapsed_and_can_be_expanded(gui):
    """TC-223: the ЗА ПЕРИОД panel is collapsed initially and toggles open."""
    assert gui.sidebar._period_expanded is False
    gui.sidebar._toggle_period_section()
    pump(gui.root)
    assert gui.sidebar._period_expanded is True
    assert "Свернуть" in str(gui.sidebar._per_toggle.cget("text"))


def test_period_panel_toggling_twice_restores_initial_state(gui):
    """TC-223: two toggles return the panel to the collapsed state."""
    initial = gui.sidebar._period_expanded
    gui.sidebar._toggle_period_section()
    gui.sidebar._toggle_period_section()
    pump(gui.root)
    assert gui.sidebar._period_expanded is initial


def test_invalid_period_range_flags_and_disables_period_buttons(gui):
    """TC-227: end < start flips _range_invalid and greys-out period buttons."""
    sb = gui.sidebar
    later = datetime.date.today() + datetime.timedelta(days=30)
    earlier = datetime.date.today()
    sb.month_start_entry.set_date(later)
    sb.month_end_entry.set_date(earlier)
    sb._validate_period_range()
    # NOTE: no pump() — see test_apply_busy_snapshot_disables_all_action_buttons
    # for why the operation-state listener would override the disabled flag.
    assert sb._range_invalid is True
    assert _is_disabled(sb.consolidate_month_btn)
    assert _is_disabled(sb.rsch_month_btn)


def test_restoring_valid_range_clears_invalid_flag(gui):
    """TC-228: a corrected range re-enables the period buttons."""
    sb = gui.sidebar
    today = datetime.date.today()
    sb.month_start_entry.set_date(today.replace(day=1))
    sb.month_end_entry.set_date(today)
    sb._validate_period_range()
    assert sb._range_invalid is False
    assert not _is_disabled(sb.consolidate_month_btn)
    assert not _is_disabled(sb.rsch_month_btn)


# ---------------------------------------------------------------------------
# TC-229..TC-232: theme switching
# ---------------------------------------------------------------------------

def test_theme_var_defaults_to_light(gui):
    """The theme radio group starts on the light palette."""
    assert gui.sidebar.theme_var.get() in ("light", "dark", "system")
    assert gui.sidebar.theme_var.get() == "light"


def test_theme_var_set_dark_propagates_to_global_palette(gui):
    """TC-230: choosing Тёмная re-themes the whole app via the controller.

    Setting the var then firing the radio callback routes through
    ``GuiMaster.set_theme``, which flips ``ThemeManager`` and calls
    ``sidebar.refresh_theme()``.
    """
    gui.sidebar.theme_var.set("dark")
    gui.sidebar._on_theme_changed()
    pump(gui.root)
    assert ThemeManager.current_theme() == "dark"


def test_theme_switch_updates_date_entry_accent(gui):
    """TC-232: switching theme re-applies the accent colour on DateEntry.

    The picker freezes colours at creation; only ``refresh_theme`` repaints
    it. After a dark switch the background must track the dark palette's
    ``primary`` token, not the light one captured at build time.
    """
    gui.sidebar.theme_var.set("dark")
    gui.sidebar._on_theme_changed()
    pump(gui.root)
    dark_primary = ThemeManager.COLORS["primary"]
    assert str(gui.sidebar.date_entry.cget("background")) == dark_primary
    # restore the baseline so the next test starts from light
    gui.sidebar.theme_var.set("light")
    gui.sidebar._on_theme_changed()
    pump(gui.root)


def test_refresh_theme_keeps_date_entry_in_sync_with_palette(gui):
    """refresh_theme re-asserts all four accent options of the picker."""
    ThemeManager.set_theme("dark")
    gui.sidebar.refresh_theme()
    pump(gui.root)
    primary = ThemeManager.COLORS["primary"]
    entry = gui.sidebar.date_entry
    assert str(entry.cget("background")) == primary
    assert str(entry.cget("headersbackground")) == primary
    assert str(entry.cget("selectbackground")) == primary
    ThemeManager.set_theme("light")


# ---------------------------------------------------------------------------
# TC-221: global operation lock
# ---------------------------------------------------------------------------

def test_apply_busy_snapshot_disables_all_action_buttons(gui):
    """TC-221: while an operation runs, every action button goes disabled."""
    op = OperationState()
    op.begin(OperationType.CONSOLIDATION_DAY)
    gui.sidebar.apply(op.snapshot())
    # NOTE: do NOT call pump() here — GuiMaster registers an
    # _on_operation_state listener on gui.operation_state (which is
    # idle), and pumping would let a pending idle-snapshot callback
    # re-enable the buttons and mask the disabled state we just set.
    # We test the sidebar's apply() contract directly.
    for attr in _ACTION_BUTTONS:
        btn = getattr(gui.sidebar, attr)
        assert _is_disabled(btn), f"{attr} should be disabled while busy"


def test_apply_idle_snapshot_reenables_all_action_buttons(gui):
    """When the operation ends, every action button is re-enabled."""
    op = OperationState()
    op.begin(OperationType.CONSOLIDATION_DAY)
    gui.sidebar.apply(op.snapshot())
    op.end()
    gui.sidebar.apply(op.snapshot())
    for attr in _ACTION_BUTTONS:
        btn = getattr(gui.sidebar, attr)
        assert not _is_disabled(btn), f"{attr} should be enabled when idle"
