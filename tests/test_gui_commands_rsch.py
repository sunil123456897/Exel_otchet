from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.ui.gui_commands import GuiCommands


@pytest.fixture
def commands_fixture():
    root = MagicMock()
    root.after.side_effect = lambda _ms, fn: fn()

    sidebar = MagicMock()
    sidebar.get_date.return_value = datetime(2026, 4, 13)

    cmd = GuiCommands(
        root=root,
        config_controller=MagicMock(),
        app_controller=MagicMock(),
        employee_vm=MagicMock(),
        consolidation_vm=MagicMock(),
        sidebar=sidebar,
        employee_table=MagicMock(),
        stats_panel=MagicMock(),
    )
    return cmd, root, sidebar


def test_run_rsch_report_happy_path(commands_fixture):
    cmd, _root, sidebar = commands_fixture

    with (
        patch(
            "core.ui.gui_commands.filedialog.askopenfilename", return_value="C:/in.xlsx"
        ),
        patch(
            "core.ui.gui_commands.filedialog.asksaveasfilename",
            return_value="C:/out.xlsx",
        ),
    ):
        cmd.run_rsch_report()

    sidebar.set_rsch_state.assert_called_once_with("disabled")
    cmd.app_controller.run_rsch_report.assert_called_once()

    args = cmd.app_controller.run_rsch_report.call_args[0]
    assert args[0] == Path("C:/in.xlsx")
    assert args[1] == Path("C:/out.xlsx")
    assert args[2] == datetime(2026, 4, 13)
    assert callable(args[3])


def test_run_rsch_report_cancel_on_source(commands_fixture):
    cmd, _root, sidebar = commands_fixture

    with patch("core.ui.gui_commands.filedialog.askopenfilename", return_value=""):
        cmd.run_rsch_report()

    sidebar.set_rsch_state.assert_not_called()
    cmd.app_controller.run_rsch_report.assert_not_called()


def test_run_rsch_report_cancel_on_output(commands_fixture):
    cmd, _root, sidebar = commands_fixture

    with (
        patch(
            "core.ui.gui_commands.filedialog.askopenfilename", return_value="C:/in.xlsx"
        ),
        patch("core.ui.gui_commands.filedialog.asksaveasfilename", return_value=""),
    ):
        cmd.run_rsch_report()

    sidebar.set_rsch_state.assert_not_called()
    cmd.app_controller.run_rsch_report.assert_not_called()


def test_on_rsch_complete_success(commands_fixture):
    cmd, _root, sidebar = commands_fixture

    with (
        patch("core.ui.gui_commands.messagebox.askyesno", return_value=True),
        patch("core.ui.gui_commands.open_path") as open_path,
    ):
        cmd._on_rsch_complete(True, "ok", Path("C:/out.xlsx"))

    sidebar.set_rsch_state.assert_called_once_with("normal")
    open_path.assert_called_once()
    assert open_path.call_args[0][0].endswith("out.xlsx")


def test_on_rsch_complete_error(commands_fixture):
    cmd, _root, sidebar = commands_fixture

    with patch("core.ui.gui_commands.messagebox.showerror") as showerror:
        cmd._on_rsch_complete(False, "fail", None)

    sidebar.set_rsch_state.assert_called_once_with("normal")
    showerror.assert_called_once_with("Ошибка", "fail")
