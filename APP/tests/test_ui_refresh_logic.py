import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime
from decimal import Decimal

# Add APP and APP/src to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
sys.path.append(os.path.join(BASE_DIR, 'src'))

# We don't want to actually import GuiMaster if it starts a Tkinter app, 
# but we need to test its logic.
# Since we are testing the logic inside GuiMaster, we can either import it and mock root,
# or we can copy the logic if it's too tied to UI.
# Let's try to import it and mock the UI components.

from gui_master import GuiMaster

class TestUiRefreshLogic(unittest.TestCase):
    def setUp(self):
        # Mock the root and other UI components to avoid actual Tkinter windows
        self.root = MagicMock()
        # Mock DateEntry and other widgets
        with patch('gui_master.DateEntry'), \
             patch('gui_master.ttk.Treeview'), \
             patch('gui_master.tk.Menu'), \
             patch('gui_master.scrolledtext.ScrolledText'), \
             patch('gui_master.Consolidator'), \
             patch('gui_master.MasterWriter'), \
             patch('gui_master.Config'), \
             patch('gui_master.os.path.exists', return_value=True), \
             patch('gui_master.YAML'):
            
            # We need to mock the config file reading
            self.app = GuiMaster(self.root, config_path="mock_config.yaml")
            
            # Mock UI elements that are created in setup_ui
            self.app.tree = MagicMock()
            self.app.date_entry = MagicMock()
            self.app.refresh_btn = MagicMock()
            self.app.progress_var = MagicMock()
            self.app.stats_label = MagicMock()

    @patch('gui_master.threading.Thread')
    def test_refresh_status_deduplication_and_aggregated_status(self, mock_thread):
        """
        Verify that refresh_status:
        1. Deduplicates employees from config.
        2. Correctly aggregates status for multi-file employees.
        """
        # 1. Setup Mock Data
        # Duplicate "Adam" in config
        self.app.config.get.side_effect = lambda key, default=None: {
            'employees': ["Adam", "Adam", "Boris"]
        }.get(key, default)
        
        # Mock employees_map from consolidator
        # Adam has 2 files, Boris has 1
        employees_map = {
            "Adam": ["path/to/adam1.xlsx", "path/to/adam2.xlsx"],
            "Boris": ["path/to/boris1.xlsx"]
        }
        self.app.consolidator.get_employees.return_value = employees_map
        
        selected_date = datetime(2026, 3, 23)
        self.app.date_entry.get_date.return_value = selected_date
        
        # Mock check_date_exists
        # Adam: first file NO date, second file HAS date -> Status should be 🟢 ГОТОВО
        # Boris: first file NO date -> Status should be 🟠 НЕТ ДАТЫ
        def mock_check_date(path, date):
            if path == "path/to/adam2.xlsx":
                return True
            return False
        
        self.app.consolidator.check_date_exists.side_effect = mock_check_date
        
        # 2. Capture the task function passed to threading.Thread
        self.app.refresh_status()
        
        # Get the task function
        task_func = mock_thread.call_args[1]['target']
        
        # 3. Run the task logic
        # We need to mock self.root.after to execute the callbacks immediately or just capture them
        callbacks = []
        def mock_after(ms, func):
            callbacks.append(func)
        self.app.root.after.side_effect = mock_after
        
        task_func()
        
        # Execute all captured callbacks (like finalize)
        for cb in callbacks:
            if callable(cb):
                cb()
        
        # 4. Assertions
        
        # Check all_employee_data
        # It should have exactly 2 entries: Adam and Boris
        self.assertEqual(len(self.app.all_employee_data), 2, "Should only have 2 unique employees")
        
        names = [d[0] for d in self.app.all_employee_data]
        self.assertIn("Adam", names)
        self.assertIn("Boris", names)
        
        # Check Adam's status (should be 🟢 ГОТОВО because adam2.xlsx has the date)
        adam_data = next(d for d in self.app.all_employee_data if d[0] == "Adam")
        self.assertEqual(adam_data[1], "🟢 ГОТОВО")
        self.assertEqual(adam_data[3], "ready")
        self.assertEqual(adam_data[2], "[2 файлов]")
        
        # Check Boris's status (should be 🟠 НЕТ ДАТЫ)
        boris_data = next(d for d in self.app.all_employee_data if d[0] == "Boris")
        self.assertEqual(boris_data[1], "🟠 НЕТ ДАТЫ")
        self.assertEqual(boris_data[3], 'partial')

    @patch('gui_master.threading.Thread')
    def test_refresh_status_no_files(self, mock_thread):
        """Verify status when an employee has no files."""
        self.app.config.get.side_effect = lambda key, default=None: {
            'employees': ["Charlie"]
        }.get(key, default)
        
        self.app.consolidator.get_employees.return_value = {} # No files for Charlie
        
        self.app.refresh_status()
        task_func = mock_thread.call_args[1]['target']
        
        callbacks = []
        self.app.root.after.side_effect = lambda ms, func: callbacks.append(func)
        
        task_func()
        for cb in callbacks:
            if callable(cb): cb()
            
        charlie_data = next(d for d in self.app.all_employee_data if d[0] == "Charlie")
        self.assertEqual(charlie_data[1], "🔴 НЕТ ФАЙЛА")
        self.assertEqual(charlie_data[3], 'missing')

if __name__ == "__main__":
    unittest.main()
