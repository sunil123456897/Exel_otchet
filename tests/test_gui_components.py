import pytest
import tkinter as tk
from tkinter import ttk
from unittest.mock import MagicMock, patch
from APP.core.ui_sidebar import Sidebar
from APP.core.ui_stats_panel import StatsPanel
from APP.core.ui_log_panel import LogPanel
from APP.core.ui_employee_table import EmployeeTable
from APP.core.ui_dialogs import show_attach_file_dialog, ask_employee_name

@pytest.fixture
def root():
    r = tk.Tk()
    r.withdraw()
    yield r
    r.destroy()

@pytest.fixture
def mock_controller():
    return MagicMock()

def test_sidebar(root, mock_controller):
    with patch('APP.core.ui_sidebar.DateEntry'):
        sidebar = Sidebar(root, mock_controller)
        sidebar.pack()
        assert sidebar.refresh_btn is not None
        sidebar.set_refresh_state('disabled')
        assert str(sidebar.refresh_btn['state']) == 'disabled'
        sidebar.get_date()
        sidebar.set_consolidate_state('disabled')
        sidebar.set_consolidate_all_state('disabled')

def test_stats_panel(root, mock_controller):
    stats = StatsPanel(root, mock_controller)
    stats.pack()
    stats.set_progress(50)
    assert stats.get_progress() == 50
    stats.update_stats(5, 10, 1000, 500, 1)
    assert "5/10" in stats.stats_label['text']
    assert "1,000.00" in stats.stats_label['text']

def test_log_panel(root, mock_controller):
    log = LogPanel(root, mock_controller)
    log.pack()
    log.append_log("test message")
    assert "test message" in log.log_area.get('1.0', tk.END)
    log.clear_logs()
    assert log.log_area.get('1.0', tk.END).strip() == ""
    assert log.get_widget() == log.log_area

def test_employee_table(root, mock_controller):
    table = EmployeeTable(root, mock_controller)
    table.pack()
    table.insert_row(("Alice", "🟢 ГОТОВО", "alice.xlsx"), "ready")
    assert len(table.tree.get_children()) == 1
    assert table.get_selected_employee() is None
    
    # Select the row
    child_id = table.tree.get_children()[0]
    table.tree.selection_set(child_id)
    assert table.get_selected_employee() == "Alice"
    
    assert table.get_search_query() == ""
    table.search_var.set("test")
    assert table.get_search_query() == "test"
    
    table.clear_tree()
    assert len(table.tree.get_children()) == 0

def test_dialogs(root, mocker):
    on_attach = MagicMock()
    mocker.patch('tkinter.filedialog.askopenfilenames', return_value=['file1.xlsx'])
    
    with patch('tkinter.Toplevel'):
        show_attach_file_dialog(root, ["Alice"], on_attach)

def test_ask_employee_name(mocker):
    mocker.patch('tkinter.simpledialog.askstring', return_value="Bob")
    assert ask_employee_name() == "Bob"
