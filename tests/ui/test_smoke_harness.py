"""Smoke test: verify the `gui` fixture builds a full GuiMaster."""


def test_gui_fixture_builds_full_window(gui):
    """The harness must construct GuiMaster without raising."""
    assert gui is not None
    assert gui.root is not None


def test_all_top_level_components_exist(gui):
    """Sidebar, notebook, employee_table, stats_panel, toasts present."""
    assert hasattr(gui, "sidebar") and gui.sidebar is not None
    assert hasattr(gui, "notebook") and gui.notebook is not None
    assert hasattr(gui, "employee_table") and gui.employee_table is not None
    assert hasattr(gui, "stats_panel") and gui.stats_panel is not None
    assert hasattr(gui, "toasts") and gui.toasts is not None


def test_notebook_has_seven_tabs(gui):
    """DashboardTabs creates 7 tabs (Сотрудники, Панель, Отчёты, ...)"""
    tabs = gui.notebook.tabs()
    assert len(tabs) == 7, f"expected 7 tabs, got {len(tabs)}"
