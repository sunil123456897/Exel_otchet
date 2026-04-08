import logging
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Optional

from core.ui.ui_sidebar import Sidebar
from core.ui.ui_employee_table import EmployeeTable
from core.ui.ui_stats_panel import StatsPanel
from core.ui.ui_log_panel import LogPanel
from core.ui.ui_dialogs import show_attach_file_dialog, ask_employee_name
from core.ui.theme import ThemeManager
from core.app_controller import AppController
from core.infra.config_controller import ConfigController
from core.domain.utils_helpers import open_path
from core.infra.utils_logging import setup_gui_logging

# MVVM Imports
from core.view_models.employee_list_viewmodel import EmployeeListViewModel
from core.view_models.consolidation_viewmodel import ConsolidationViewModel


class GuiMaster:
    def __init__(
        self,
        root: tk.Tk,
        config_controller: ConfigController,
        app_controller: AppController,
    ):
        self.root, self.config_controller, self.app_controller = (
            root,
            config_controller,
            app_controller,
        )
        self.root.title("🚀 Master-Report v5.5 | Financial Consolidator")
        self.root.geometry("1200x900")
        self.root.configure(bg="#f0f2f5")

        # Initialize ViewModels
        self.employee_vm = EmployeeListViewModel()
        self.consolidation_vm = ConsolidationViewModel(app_controller)

        # Subscribe to updates
        self.employee_vm.set_update_callback(self.on_employee_vm_update)
        self.consolidation_vm.set_callbacks(
            self.on_consolidation_progress, self.on_consolidation_complete
        )

        ThemeManager.apply_styles()
        self.setup_ui()
        setup_gui_logging(self.log_panel.get_widget())

        # Initial status refresh
        self.root.after(100, self.refresh_status)

    def setup_ui(self):
        self.sidebar = Sidebar(self.root, self)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)

        self.main_area = ttk.Frame(self.root, padding="15", style="Main.TFrame")
        self.main_area.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.stats_panel = StatsPanel(self.sidebar, self)
        self.stats_panel.pack(fill=tk.X, pady=(0, 10))

        self.log_panel = LogPanel(self.sidebar, self)
        self.log_panel.pack(fill=tk.BOTH, expand=True)

        self.employee_table = EmployeeTable(self.main_area, self)
        self.employee_table.pack(fill=tk.BOTH, expand=True)

    # --- ViewModel Subscriptions ---

    def on_employee_vm_update(self):
        """Callback for EmployeeListViewModel updates."""
        self.root.after(0, self._sync_employee_ui)

    def _sync_employee_ui(self):
        """Synchronize UI with current EmployeeListViewModel state."""
        self.employee_table.clear_tree()
        for emp in self.employee_vm.get_filtered_employees():
            self.employee_table.insert_row(
                (emp.name, emp.status_text, emp.path_text), emp.tag
            )

        self.stats_panel.update_stats(
            self.employee_vm.get_ready_count(), self.employee_vm.get_total_count()
        )
        self.stats_panel.set_progress(self.employee_vm.get_progress_percent())
        self.sidebar.set_refresh_state("normal")

    def on_consolidation_progress(self, progress: float):
        """Callback for progress updates from both ViewModels."""
        self.root.after(0, lambda: self.stats_panel.set_progress(progress))

    def on_consolidation_complete(self, ok: bool, msg: str, path: Optional[Path]):
        """Callback for consolidation completion."""

        def fin():
            state = self.consolidation_vm.get_button_state()
            self.sidebar.set_consolidate_state(state)
            self.sidebar.set_consolidate_all_state(state)
            self.sidebar.set_consolidate_month_state(state)
            self.stats_panel.set_progress(100 if ok else self.consolidation_vm.progress)

            if ok:
                logging.info(f"Успешно: {msg}")
                if path and messagebox.askyesno(
                    "Успех", "Консолидация завершена. Открыть файл?"
                ):
                    open_path(str(path))
            else:
                logging.error(f"Ошибка: {msg}")
                messagebox.showerror("Ошибка", msg)

        self.root.after(0, fin)

    # --- UI Commands (called by Sidebar, EmployeeTable, etc.) ---

    def refresh_status(self):
        """Refresh employee statuses for the selected date."""
        self.sidebar.set_refresh_state("disabled")
        self.employee_table.clear_tree()
        self.stats_panel.set_progress(0)
        self.employee_vm.refresh(
            self.app_controller, self.sidebar.get_date(), self.on_consolidation_progress
        )

    def run_consolidation(self):
        """Consolidate reports for a single date."""
        missing_names = self.employee_vm.get_missing_names()
        if missing_names:
            msg = f"Не сдано отчетов: {len(missing_names)}. Продолжить?"
            if not messagebox.askyesno("Предупреждение", msg):
                return

        self.sidebar.set_consolidate_state("disabled")
        self.consolidation_vm.run_consolidation(
            self.app_controller, self.sidebar.get_date()
        )

    def run_consolidation_all_dates(self):
        """Consolidate all available reports across all dates."""
        self.sidebar.set_consolidate_all_state("disabled")
        self.consolidation_vm.run_consolidation_all_dates(self.app_controller)

    def run_consolidation_month(self):
        """Consolidate reports for a specific date range."""
        start_date, end_date = self.sidebar.get_month_range()
        if start_date > end_date:
            messagebox.showerror(
                "Ошибка", "Дата начала должна быть раньше даты окончания"
            )
            return

        self.sidebar.set_consolidate_month_state("disabled")
        self.consolidation_vm.run_consolidation_month(
            self.app_controller, start_date, end_date
        )

    def add_employee_dialog(self):
        """Open dialog to add a new employee."""
        name = ask_employee_name()
        if name:
            self.employee_vm.add_employee(self.config_controller, name)
            self.refresh_status()

    def attach_file_dialog(self):
        """Open dialog to attach files to an employee."""

        def on_attach(name, paths, append):
            self.employee_vm.attach_files(self.config_controller, name, paths)
            self.refresh_status()

        show_attach_file_dialog(
            self.root, self.config_controller.get_employees(), on_attach
        )

    def open_master_folder(self):
        """Open the directory containing the master report file."""
        p = self.employee_vm.get_master_path(self.config_controller)
        if p and p.parent.exists():
            open_path(str(p.parent))

    def copy_missing_to_clipboard(self):
        """Copy list of employees who haven't submitted reports to clipboard."""
        missing = self.employee_vm.get_missing_names()
        if missing:
            date_str = self.sidebar.get_date().strftime("%d.%m")
            text = f"Должники за {date_str}:\n" + "\n".join([f"- {m}" for m in missing])
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            messagebox.showinfo("Успех", "Список должников скопирован в буфер обмена")

    def filter_tree(self):
        """Filter the employee table based on search query."""
        self.employee_vm.search_query = self.employee_table.get_search_query()
        self._sync_employee_ui()

    def open_employee_folder(self):
        """Open the folder containing the selected employee's report."""
        name = self.employee_table.get_selected_employee()
        path = self.employee_vm.get_selected_employee_path(name)
        if path:
            open_path(str(Path(path).parent))

    def open_employee_file(self):
        """Open the selected employee's report file."""
        name = self.employee_table.get_selected_employee()
        path = self.employee_vm.get_selected_employee_path(name)
        if path:
            open_path(path)

    def delete_employee(self):
        """Delete the selected employee from configuration."""
        name = self.employee_table.get_selected_employee()
        if name and messagebox.askyesno("Удалить", f"Удалить сотрудника '{name}'?"):
            self.employee_vm.delete_employee(self.config_controller, name)
            self.refresh_status()
