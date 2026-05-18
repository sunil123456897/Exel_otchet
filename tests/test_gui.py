import pytest
import tkinter as tk
from unittest.mock import MagicMock, patch
from core.ui.gui_master import GuiMaster, _fit_window_geometry
from core.view_models.employee_list_viewmodel import EmployeeStatus


@pytest.fixture
def mock_controllers():
    return MagicMock(), MagicMock()


@pytest.fixture
def gui_app(mock_controllers):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk is not available in this environment: {exc}")
    root.withdraw()
    config_controller, app_controller = mock_controllers

    with (
        patch("core.ui.gui_master.ThemeManager.apply_styles"),
        patch("core.ui.gui_master.setup_gui_logging"),
        patch("core.ui.gui_master.Sidebar"),
        patch("core.ui.gui_master.StatsPanel"),
        patch("core.ui.gui_master.LogPanel"),
        patch("core.ui.gui_master.EmployeeTable"),
    ):
        gui = GuiMaster(root, config_controller, app_controller)
        yield gui
        root.destroy()


def test_gui_init(gui_app):
    assert "Master-Report" in gui_app.root.title()
    assert gui_app.employee_vm is not None
    assert gui_app.consolidation_vm is not None


def test_fit_window_geometry_caps_size_to_screen():
    assert _fit_window_geometry(1100, 840, 1366, 768) == "1100x675+133+46"


def test_fit_window_geometry_centers_default_on_large_screen():
    assert _fit_window_geometry(1100, 840, 1920, 1080) == "1100x840+410+120"


def test_refresh_status(gui_app, mock_controllers):
    _, app_controller = mock_controllers
    gui_app.sidebar.get_date.return_value = MagicMock()
    gui_app.refresh_status()
    # refresh_status calls employee_vm.refresh, which calls app_controller.refresh_status
    app_controller.refresh_status.assert_called_once()


def test_run_consolidation(gui_app, mocker):
    # Set data in VM instead of gui_app
    gui_app.employee_vm._all_employees = [
        EmployeeStatus("Alice", "🟢 ГОТОВО", "alice.xlsx", "ready")
    ]
    gui_app.sidebar.get_date.return_value = MagicMock()
    mocker.patch("tkinter.messagebox.askyesno", return_value=True)
    gui_app.run_consolidation()
    gui_app.app_controller.run_consolidation.assert_called_once()


def test_run_consolidation_cancel(gui_app, mocker):
    # Set data in VM
    gui_app.employee_vm._all_employees = [
        EmployeeStatus("Alice", "🔴 НЕТ ФАЙЛА", "---", "missing")
    ]
    mocker.patch("tkinter.messagebox.askyesno", return_value=False)
    gui_app.run_consolidation()
    gui_app.app_controller.run_consolidation.assert_not_called()


def test_run_consolidation_all_dates(gui_app, mocker):
    mocker.patch("tkinter.messagebox.askyesno", return_value=True)
    gui_app.run_consolidation_all_dates()
    gui_app.app_controller.run_consolidation_all_dates.assert_called_once()


def test_add_employee_dialog(gui_app, mocker):
    mocker.patch("core.ui.ui_dialogs.ask_employee_name", return_value="Charlie")
    gui_app.add_employee_dialog()
    gui_app.config_controller.add_employee.assert_called_with("Charlie")


def test_attach_file_dialog(gui_app, mocker):
    mock_dialog = mocker.patch("core.ui.ui_dialogs.show_attach_file_dialog")
    gui_app.attach_file_dialog()

    callback = mock_dialog.call_args[0][2]
    callback("Alice", ["C:/a.xlsx"], False)

    gui_app.config_controller.attach_files.assert_called_with(
        "Alice", ["C:/a.xlsx"], append=False
    )


def test_open_master_folder(gui_app, mocker):
    gui_app.config_controller.get_paths.return_value = {"master_file": "Master.xlsx"}
    gui_app.config_controller.config_path = "C:/config.yaml"
    mocker.patch("pathlib.Path.parent", return_value=MagicMock(exists=lambda: True))
    mocker.patch("core.ui.gui_commands.open_path")
    gui_app.open_master_folder()


def test_copy_missing_to_clipboard(gui_app, mocker):
    # Set data in VM
    gui_app.employee_vm._all_employees = [
        EmployeeStatus("Alice", "🔴 НЕТ ФАЙЛА", "---", "missing")
    ]
    mocker.patch("tkinter.messagebox.showinfo")
    gui_app.copy_missing_to_clipboard()
    assert "Alice" in gui_app.root.clipboard_get()


def test_filter_tree(gui_app):
    # Set data in VM
    gui_app.employee_vm._all_employees = [
        EmployeeStatus("Alice", "🟢 ГОТОВО", "alice.xlsx", "ready")
    ]
    gui_app.employee_table.get_search_query.return_value = "alice"
    gui_app.filter_tree()
    # GuiMaster.filter_tree calls _sync_employee_ui which calls insert_row
    gui_app.employee_table.insert_row.assert_called()


def test_delete_employee(gui_app, mocker):
    gui_app.employee_table.get_selected_employee.return_value = "Alice"
    mocker.patch("tkinter.messagebox.askyesno", return_value=True)
    gui_app.delete_employee()
    gui_app.config_controller.delete_employee.assert_called_with("Alice")


def test_open_employee_folder(gui_app, mocker):
    gui_app.employee_vm._employees_map = {"Alice": [{"path": "C:/alice.xlsx"}]}
    gui_app.employee_table.get_selected_employee.return_value = "Alice"
    open_path = mocker.patch("core.ui.gui_commands.open_path")
    gui_app.open_employee_folder()
    open_path.assert_called_once_with("C:\\")


def test_open_employee_file(gui_app, mocker):
    gui_app.employee_vm._employees_map = {"Alice": [{"path": "C:/alice.xlsx"}]}
    gui_app.employee_table.get_selected_employee.return_value = "Alice"
    open_path = mocker.patch("core.ui.gui_commands.open_path")
    gui_app.open_employee_file()
    open_path.assert_called_once_with("C:/alice.xlsx")


def test_open_employee_file_opens_all_files_after_confirmation(gui_app, mocker):
    gui_app.employee_vm._employees_map = {
        "Alice": [
            {"path": "C:/alice-1.xlsx"},
            {"path": "D:/alice-2.xlsx"},
        ]
    }
    gui_app.employee_table.get_selected_employee.return_value = "Alice"
    askyesnocancel = mocker.patch(
        "core.ui.gui_commands.messagebox.askyesnocancel", return_value=True
    )
    open_path = mocker.patch("core.ui.gui_commands.open_path")

    gui_app.open_employee_file()

    askyesnocancel.assert_called_once()
    open_path.assert_any_call("C:/alice-1.xlsx")
    open_path.assert_any_call("D:/alice-2.xlsx")
    assert open_path.call_count == 2


def test_open_employee_folder_opens_all_unique_parent_folders(gui_app, mocker):
    gui_app.employee_vm._employees_map = {
        "Alice": [
            {"path": "C:/reports/alice-1.xlsx"},
            {"path": "D:/archive/alice-2.xlsx"},
            {"path": "D:/archive/alice-3.xlsx"},
        ]
    }
    gui_app.employee_table.get_selected_employee.return_value = "Alice"
    open_path = mocker.patch("core.ui.gui_commands.open_path")

    gui_app.open_employee_folder()

    open_path.assert_any_call("C:\\reports")
    open_path.assert_any_call("D:\\archive")
    assert open_path.call_count == 2


def test_run_rsch_report(gui_app):
    gui_app.commands.run_rsch_report = MagicMock()
    gui_app.run_rsch_report()
    gui_app.commands.run_rsch_report.assert_called_once()


def test_run_reconciliation_report(gui_app):
    gui_app.commands.run_reconciliation_report = MagicMock()
    gui_app.run_reconciliation_report()
    gui_app.commands.run_reconciliation_report.assert_called_once()
