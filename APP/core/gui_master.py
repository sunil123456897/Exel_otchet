import os
import logging
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import List, Dict, Any, Optional

from core.ui_sidebar import Sidebar
from core.ui_employee_table import EmployeeTable
from core.ui_stats_panel import StatsPanel
from core.ui_log_panel import LogPanel
from core.ui_dialogs import show_attach_file_dialog, ask_employee_name
from core.theme import ThemeManager
from core.app_controller import AppController
from core.config_controller import ConfigController
from core.utils_helpers import open_path
from ingestion_service_logging import setup_gui_logging

class GuiMaster:
    def __init__(self, root: tk.Tk, config_controller: ConfigController, app_controller: AppController):
        self.root, self.config_controller, self.app_controller = root, config_controller, app_controller
        self.root.title("🚀 Master-Report v5.5 | Financial Consolidator")
        self.root.geometry("1200x900")
        self.root.configure(bg='#f0f2f5')
        self.all_employee_data, self._cached_employees = [], {}
        ThemeManager.apply_styles()
        self.setup_ui()
        setup_gui_logging(self.log_panel.get_widget())
        self.root.after(100, self.refresh_status)

    def setup_ui(self):
        self.sidebar = Sidebar(self.root, self); self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.main_area = ttk.Frame(self.root, padding="15", style='Main.TFrame'); self.main_area.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.stats_panel = StatsPanel(self.sidebar, self); self.stats_panel.pack(fill=tk.X, pady=(0, 10))
        self.log_panel = LogPanel(self.sidebar, self); self.log_panel.pack(fill=tk.BOTH, expand=True)
        self.employee_table = EmployeeTable(self.main_area, self); self.employee_table.pack(fill=tk.BOTH, expand=True)

    def refresh_status(self):
        date = self.sidebar.get_date(); self.sidebar.set_refresh_state('disabled')
        self.employee_table.clear_tree(); self.stats_panel.set_progress(0)
        def on_prog(p): self.root.after(0, lambda: self.stats_panel.set_progress(p))
        def on_comp(data, emps, ren):
            def fin():
                self.all_employee_data, self._cached_employees = data, emps; self.filter_tree()
                self.stats_panel.update_stats(sum(1 for d in data if "🟢 ГОТОВО" in d[1]), len(data))
                self.stats_panel.set_progress(100); self.sidebar.set_refresh_state('normal')
                if ren: logging.info("Пути обновлены"); self.config_controller.save_config()
            self.root.after(0, fin)
        self.app_controller.refresh_status(date, on_prog, on_comp)

    def run_consolidation(self):
        missing = [n for n, s, p, t in self.all_employee_data if "🟢 ГОТОВО" not in s]
        if missing and not messagebox.askyesno("Предупреждение", f"Не сдано отчетов: {len(missing)}. Продолжить?"): return
        self.sidebar.set_consolidate_state('disabled')
        def on_prog(p): self.root.after(0, lambda: self.stats_panel.set_progress(p))
        def on_comp(ok, msg, path):
            def fin():
                self.sidebar.set_consolidate_state('normal'); self.stats_panel.set_progress(100)
                if ok: (logging.info("Успешно!"), open_path(str(path)) if messagebox.askyesno("Успех", "Открыть файл?") else None)
                else: logging.error(f"Ошибка: {msg}"); messagebox.showerror("Ошибка", msg)
            self.root.after(0, fin)
        self.app_controller.run_consolidation(self.sidebar.get_date(), on_prog, on_comp)

    def run_consolidation_all_dates(self):
        self.sidebar.set_consolidate_all_state('disabled')
        def on_prog(p): self.root.after(0, lambda: self.stats_panel.set_progress(p))
        def on_comp(ok, msg, path):
            def fin():
                self.sidebar.set_consolidate_all_state('normal'); self.stats_panel.set_progress(100)
                if ok: (logging.info("Готово!"), open_path(str(path)) if messagebox.askyesno("Успех", "Открыть файл?") else None)
                else: logging.error(f"Ошибка: {msg}"); messagebox.showerror("Ошибка", msg)
            self.root.after(0, fin)
        self.app_controller.run_consolidation_all_dates(on_prog, on_comp)

    def add_employee_dialog(self):
        name = ask_employee_name()
        if name: self.config_controller.add_employee(name); self.refresh_status()

    def attach_file_dialog(self):
        def on_attach(name, paths, app): self.config_controller.attach_files(name, paths, app); self.refresh_status()
        show_attach_file_dialog(self.root, self.config_controller.get_employees(), on_attach)

    def open_master_folder(self):
        p = Path(self.config_controller.get_paths().get('master_file', 'Master_Report.xlsx'))
        if not p.is_absolute(): p = Path(self.config_controller.config_path).parent / p
        if p.parent.exists(): open_path(str(p.parent))

    def copy_missing_to_clipboard(self):
        missing = [n for n, s, p, t in self.all_employee_data if "🟢 ГОТОВО" not in s]
        if missing:
            self.root.clipboard_clear(); self.root.clipboard_append(f"Должники за {self.sidebar.get_date().strftime('%d.%m')}:\n" + "\n".join([f"- {m}" for m in missing]))
            messagebox.showinfo("Успех", "Скопировано")

    def filter_tree(self):
        q = self.employee_table.get_search_query()
        self.root.after(0, lambda: (self.employee_table.clear_tree(), [self.employee_table.insert_row((n, s, p), t) for n, s, p, t in self.all_employee_data if any(q in x.lower() for x in (n, s, p))]))

    def _get_sel_path(self):
        name = self.employee_table.get_selected_employee()
        if not name: return None
        metas = self._cached_employees.get(name, [])
        return metas[0]['path'] if metas and isinstance(metas[0], dict) else metas[0] if metas else None

    def open_employee_folder(self):
        p = self._get_sel_path()
        if p: open_path(str(Path(p).parent))

    def open_employee_file(self):
        p = self._get_sel_path()
        if p: open_path(p)

    def delete_employee(self):
        name = self.employee_table.get_selected_employee()
        if name and messagebox.askyesno("Удалить", f"Удалить '{name}'?"): self.config_controller.delete_employee(name); self.refresh_status()

