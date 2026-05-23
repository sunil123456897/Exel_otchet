import logging
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Optional

from core.ui.ui_sidebar import Sidebar
from core.ui.ui_employee_table import EmployeeTable
from core.ui.ui_stats_panel import StatsPanel
from core.ui.ui_log_panel import LogPanel
from core.ui.ui_dashboard import DashboardTabs
from core.ui.theme import ThemeManager
from core.infra import ConfigController, setup_gui_logging, open_path
from core.app_controller import AppController

from core.view_models.employee_list_viewmodel import EmployeeListViewModel
from core.view_models.consolidation_viewmodel import ConsolidationViewModel
from core.ui.gui_commands import GuiCommands


def _fit_window_geometry(
    preferred_width: int,
    preferred_height: int,
    screen_width: int,
    screen_height: int,
) -> str:
    max_width = max(800, int(screen_width * 0.82))
    max_height = max(560, int(screen_height * 0.88))
    width = min(preferred_width, max_width)
    height = min(preferred_height, max_height)
    x = max(0, (screen_width - width) // 2)
    y = max(0, (screen_height - height) // 2)
    return f"{width}x{height}+{x}+{y}"


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
        self.root.geometry(
            _fit_window_geometry(
                1100,
                840,
                self.root.winfo_screenwidth(),
                self.root.winfo_screenheight(),
            )
        )
        self.root.configure(bg="#f0f2f5")

        self.employee_vm = EmployeeListViewModel()
        self.consolidation_vm = ConsolidationViewModel(app_controller)

        self.employee_vm.set_update_callback(self._on_employee_vm_update)
        self.consolidation_vm.set_callbacks(
            self._on_consolidation_progress, self._on_consolidation_complete
        )

        ThemeManager.apply_styles()
        self.setup_ui()
        setup_gui_logging(self.log_panel.get_widget())

        self.commands = GuiCommands(
            self.root,
            config_controller,
            app_controller,
            self.employee_vm,
            self.consolidation_vm,
            self.sidebar,
            self.employee_table,
            self.stats_panel,
            self.dashboard_tabs,
        )

        self.root.after(100, self.commands.refresh_status)

    def setup_ui(self):
        self.sidebar = Sidebar(self.root, self)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)

        self.main_area = ttk.Frame(self.root, padding="15", style="Main.TFrame")
        self.main_area.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.stats_panel = StatsPanel(self.sidebar, self)
        self.stats_panel.pack(fill=tk.X, pady=(0, 10))

        self.log_panel = LogPanel(self.sidebar, self)
        self.log_panel.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(self.main_area)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.dashboard_tabs = DashboardTabs(
            self.notebook,
            self,
            self.config_controller,
        )

        self.employee_table = EmployeeTable(self.dashboard_tabs.employees_tab, self)
        self.employee_table.pack(fill=tk.BOTH, expand=True)
        self.dashboard_tabs.refresh()

    def _on_employee_vm_update(self):
        self.root.after(0, self.commands._sync_employee_ui)

    def _on_consolidation_progress(self, progress: float):
        self.root.after(0, lambda: self.stats_panel.set_progress(progress))

    def _on_consolidation_complete(self, ok: bool, msg: str, path: Optional[Path]):
        def fin():
            state = self.consolidation_vm.get_button_state()
            self.sidebar.set_consolidate_state(state)
            self.sidebar.set_consolidate_all_state(state)
            self.sidebar.set_consolidate_month_state(state)
            self.sidebar.set_rsch_state(state)
            self.stats_panel.set_progress(100 if ok else self.consolidation_vm.progress)

            if ok:
                logging.info(f"Успешно: {msg}")
                self.dashboard_tabs.record_result("Master", ok, msg, path)
                if path and messagebox.askyesno(
                    "Успех", "Консолидация завершена. Открыть файл?"
                ):
                    open_path(str(path))
            else:
                logging.error(f"Ошибка: {msg}")
                self.dashboard_tabs.record_result("Master", ok, msg, path)
                messagebox.showerror("Ошибка", msg)

        self.root.after(0, fin)

    def refresh_status(self):
        self.commands.refresh_status()

    def run_consolidation(self):
        self.commands.run_consolidation()

    def run_consolidation_all_dates(self):
        self.commands.run_consolidation_all_dates()

    def run_consolidation_month(self):
        self.commands.run_consolidation_month()

    def run_rsch_report(self):
        self.commands.run_rsch_report()

    def run_rsch_report_month(self):
        self.commands.run_rsch_report_month()

    def run_reconciliation_report(self):
        self.commands.run_reconciliation_report()

    def run_auto_reconciliation_day(self):
        self.commands.run_auto_reconciliation_day()

    def add_employee_dialog(self):
        self.commands.add_employee_dialog()

    def attach_file_dialog(self):
        self.commands.attach_file_dialog()

    def open_master_folder(self):
        self.commands.open_master_folder()

    def copy_missing_to_clipboard(self):
        self.commands.copy_missing_to_clipboard()

    def filter_tree(self):
        self.commands.filter_tree()

    def open_employee_folder(self):
        self.commands.open_employee_folder()

    def open_employee_file(self):
        self.commands.open_employee_file()

    def delete_employee(self):
        self.commands.delete_employee()
