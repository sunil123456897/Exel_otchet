import pytest
import tkinter as tk
from unittest.mock import MagicMock, patch
from core.ui.gui_master import GuiMaster

@pytest.fixture
def mock_controllers():
    return MagicMock(), MagicMock()

@pytest.fixture
def gui_app(mock_controllers):
    root = tk.Tk()
    root.withdraw()
    config_controller, app_controller = mock_controllers
    
    with patch('core.ui.gui_master.ThemeManager.apply_styles'), \
         patch('core.ui.gui_master.setup_gui_logging'), \
         patch('core.ui.gui_master.Sidebar'), \
         patch('core.ui.gui_master.StatsPanel'), \
         patch('core.ui.gui_master.LogPanel'), \
         patch('core.ui.gui_master.EmployeeTable'):
        
        gui = GuiMaster(root, config_controller, app_controller)
        yield gui
        root.destroy()

def test_gui_init(gui_app):
    assert "Master-Report" in gui_app.root.title()

def test_refresh_status(gui_app, mock_controllers):
    _, app_controller = mock_controllers
    gui_app.sidebar.get_date.return_value = MagicMock()
    gui_app.refresh_status()
    app_controller.refresh_status.assert_called_once()

def test_run_consolidation(gui_app, mocker):
    gui_app.all_employee_data = [('Alice', '🟢 ГОТОВО', 'alice.xlsx', 'ready')]
    gui_app.sidebar.get_date.return_value = MagicMock()
    mocker.patch('tkinter.messagebox.askyesno', return_value=True)
    gui_app.run_consolidation()
    gui_app.app_controller.run_consolidation.assert_called_once()

def test_run_consolidation_cancel(gui_app, mocker):
    gui_app.all_employee_data = [('Alice', '🔴 НЕТ ФАЙЛА', '---', 'missing')]
    mocker.patch('tkinter.messagebox.askyesno', return_value=False)
    gui_app.run_consolidation()
    gui_app.app_controller.run_consolidation.assert_not_called()

def test_run_consolidation_all_dates(gui_app):
    gui_app.run_consolidation_all_dates()
    gui_app.app_controller.run_consolidation_all_dates.assert_called_once()

def test_add_employee_dialog(gui_app, mocker):
    mocker.patch('core.ui.gui_master.ask_employee_name', return_value="Charlie")
    gui_app.add_employee_dialog()
    gui_app.config_controller.add_employee.assert_called_with("Charlie")

def test_attach_file_dialog(gui_app, mocker):
    mocker.patch('core.ui.gui_master.show_attach_file_dialog')
    gui_app.attach_file_dialog()
    import core.ui.gui_master as gm
    gm.show_attach_file_dialog.assert_called_once()

def test_open_master_folder(gui_app, mocker):
    gui_app.config_controller.get_paths.return_value = {'master_file': 'Master.xlsx'}
    gui_app.config_controller.config_path = "C:/config.yaml"
    mocker.patch('pathlib.Path.parent', return_value=MagicMock(exists=lambda: True))
    mocker.patch('core.ui.gui_master.open_path')
    gui_app.open_master_folder()
    import core.ui.gui_master as gm
    gm.open_path.assert_called_once()

def test_copy_missing_to_clipboard(gui_app, mocker):
    gui_app.all_employee_data = [('Alice', '🔴 НЕТ ФАЙЛА', '---', 'missing')]
    mocker.patch('tkinter.messagebox.showinfo')
    gui_app.copy_missing_to_clipboard()
    assert "Alice" in gui_app.root.clipboard_get()

def test_filter_tree(gui_app):
    gui_app.all_employee_data = [('Alice', '🟢 ГОТОВО', 'alice.xlsx', 'ready')]
    gui_app.employee_table.get_search_query.return_value = "alice"
    gui_app.filter_tree()
    gui_app.root.update()
    gui_app.employee_table.insert_row.assert_called()

def test_delete_employee(gui_app, mocker):
    gui_app.employee_table.get_selected_employee.return_value = "Alice"
    mocker.patch('tkinter.messagebox.askyesno', return_value=True)
    gui_app.delete_employee()
    gui_app.config_controller.delete_employee.assert_called_with("Alice")

def test_open_employee_folder(gui_app, mocker):
    gui_app._cached_employees = {'Alice': [{'path': 'C:/alice.xlsx'}]}
    gui_app.employee_table.get_selected_employee.return_value = "Alice"
    mocker.patch('core.ui.gui_master.open_path')
    gui_app.open_employee_folder()
    import core.ui.gui_master as gm
    gm.open_path.assert_called_once()

def test_open_employee_file(gui_app, mocker):
    gui_app._cached_employees = {'Alice': [{'path': 'C:/alice.xlsx'}]}
    gui_app.employee_table.get_selected_employee.return_value = "Alice"
    mocker.patch('core.ui.gui_master.open_path')
    gui_app.open_employee_file()
    import core.ui.gui_master as gm
    gm.open_path.assert_called_once()
