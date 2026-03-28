import os
import logging
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog
from pathlib import Path
from typing import List, Dict, Any, Optional

from .components.sidebar import Sidebar
from .components.employee_table import EmployeeTable
from .components.stats_panel import StatsPanel
from .components.log_panel import LogPanel
from .theme import ThemeManager
from .controllers.app_controller import AppController
from .controllers.config_controller import ConfigController
from .utils.helpers import open_path

class TextHandler(logging.Handler):
    """Custom logging handler to redirect logs to a Tkinter ScrolledText widget."""
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        def append():
            self.text_widget.configure(state='normal')
            self.text_widget.insert(tk.END, msg + '\n')
            self.text_widget.configure(state='disabled')
            self.text_widget.yview(tk.END)
        self.text_widget.after(0, append)

class GuiMaster:
    def __init__(self, root: tk.Tk, config_controller: ConfigController, app_controller: AppController):
        self.root = root
        self.config_controller = config_controller
        self.app_controller = app_controller
        
        self.root.title("🚀 Master-Report v5.5 | Financial Consolidator")
        self.root.geometry("1200x900")
        self.root.configure(bg='#f0f2f5')
        
        # State
        self.all_employee_data = [] # Cache for filtering
        self._cached_employees = {}
        
        ThemeManager.apply_styles()
        self.setup_ui()
        self.setup_logging()
        
        # Initial status refresh
        self.root.after(100, self.refresh_status)

    def setup_ui(self):
        # Sidebar
        self.sidebar = Sidebar(self.root, self)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        
        # Main Area
        self.main_area = ttk.Frame(self.root, padding="15", style='Main.TFrame')
        self.main_area.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # Stats Panel (inside Sidebar)
        self.stats_panel = StatsPanel(self.sidebar, self)
        self.stats_panel.pack(fill=tk.X, pady=(0, 10))
        
        # Log Panel (inside Sidebar)
        self.log_panel = LogPanel(self.sidebar, self)
        self.log_panel.pack(fill=tk.BOTH, expand=True)
        
        # Employee Table (inside Main Area)
        self.employee_table = EmployeeTable(self.main_area, self)
        self.employee_table.pack(fill=tk.BOTH, expand=True)

    def setup_logging(self):
        self.text_handler = TextHandler(self.log_panel.get_widget())
        self.text_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S'))
        root_logger = logging.getLogger()
        root_logger.addHandler(self.text_handler)
        root_logger.setLevel(logging.INFO)

    def refresh_status(self):
        """Refreshes the status of all employees for the selected date."""
        selected_date = self.sidebar.get_date()
        self.sidebar.set_refresh_state('disabled')
        self.employee_table.clear_tree()
        self.stats_panel.set_progress(0)
            
        def on_progress(progress):
            self.root.after(0, lambda: self.stats_panel.set_progress(progress))
            
        def on_complete(local_data, employees_map, rename_detected):
            def finalize():
                self.all_employee_data = local_data
                self._cached_employees = employees_map
                self.filter_tree()
                
                ready_count = sum(1 for d in local_data if "🟢 ГОТОВО" in d[1])
                self.stats_panel.update_stats(ready_count, len(local_data))
                self.stats_panel.set_progress(100)
                self.sidebar.set_refresh_state('normal')
                
                if rename_detected:
                    logging.info("Автоматическое сохранение новых путей (файлы были переименованы)")
                    self.config_controller.save_config()
            
            self.root.after(0, finalize)
        
        self.app_controller.refresh_status(selected_date, on_progress, on_complete)

    def run_consolidation(self):
        selected_date = self.sidebar.get_date()
        missing = [n for n, s, p, t in self.all_employee_data if "🟢 ГОТОВО" not in s]
        if missing:
            if not messagebox.askyesno("Предупреждение", f"Не сдано отчетов: {len(missing)}. Продолжить?"): 
                return

        self.sidebar.set_consolidate_state('disabled')
        
        def on_progress(progress):
            self.root.after(0, lambda: self.stats_panel.set_progress(progress))
            
        def on_complete(success, message, master_path):
            def finalize():
                self.sidebar.set_consolidate_state('normal')
                self.stats_panel.set_progress(100)
                if success:
                    logging.info("Успешно!")
                    if messagebox.askyesno("Успех", f"Консолидация завершена!\n\nОткрыть файл?"):
                        open_path(str(master_path))
                else:
                    logging.error(f"Ошибка: {message}")
                    messagebox.showerror("Ошибка", f"Произошла ошибка:\n{message}")
            
            self.root.after(0, finalize)

        self.app_controller.run_consolidation(selected_date, on_progress, on_complete)

    def run_consolidation_all_dates(self):
        self.sidebar.set_consolidate_all_state('disabled')
        
        def on_progress(progress):
            self.root.after(0, lambda: self.stats_panel.set_progress(progress))
            
        def on_complete(success, message, master_path):
            def finalize():
                self.sidebar.set_consolidate_all_state('normal')
                self.stats_panel.set_progress(100)
                if success:
                    logging.info("Глобальная сборка завершена!")
                    if messagebox.askyesno("Успех", "Сборка завершена! Открыть файл?"):
                        open_path(str(master_path))
                else:
                    logging.error(f"Ошибка: {message}")
                    messagebox.showerror("Ошибка", f"Произошла ошибка:\n{message}")
            
            self.root.after(0, finalize)

        self.app_controller.run_consolidation_all_dates(on_progress, on_complete)

    def add_employee_dialog(self):
        name = simpledialog.askstring("Добавить", "Имя сотрудника:")
        if name:
            self.config_controller.add_employee(name)
            self.refresh_status()

    def attach_file_dialog(self):
        employees = self.config_controller.get_employees()
        dialog = tk.Toplevel(self.root)
        dialog.title("Привязать файлы")
        dialog.geometry("450x400")
        
        ttk.Label(dialog, text="Выберите сотрудника:", padding=10).pack()
        lb = tk.Listbox(dialog)
        for e in employees: 
            lb.insert(tk.END, e)
        lb.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        append_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(dialog, text="Добавить к существующим", variable=append_var).pack(pady=5)
        
        def pick():
            sel = lb.curselection()
            if not sel: 
                return
            emp_name = lb.get(sel[0])
            file_paths = filedialog.askopenfilenames(title=f"Файлы для {emp_name}")
            if file_paths:
                self.config_controller.attach_files(emp_name, list(file_paths), append_var.get())
                dialog.destroy()
                self.refresh_status()
        
        btn_frame = ttk.Frame(dialog, padding=10)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Выбрать файлы", command=pick).pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="Отмена", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

    def open_master_folder(self):
        try:
            master_file = self.config_controller.get_paths().get('master_file', 'Master_Report.xlsx')
            master_path = Path(master_file)
            if not master_path.is_absolute():
                master_path = Path(self.config_controller.config_path).parent / master_path
            
            path = master_path.parent
            if path.exists(): 
                open_path(str(path))
        except Exception as e: 
            logging.error(f"Ошибка: {e}")

    def copy_missing_to_clipboard(self):
        missing = [n for n, s, p, t in self.all_employee_data if "🟢 ГОТОВО" not in s]
        if missing:
            text = f"Должники за {self.sidebar.get_date().strftime('%d.%m')}:\n" + "\n".join([f"- {m}" for m in missing])
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            messagebox.showinfo("Успех", "Скопировано")

    def filter_tree(self):
        query = self.employee_table.get_search_query()
        def _update():
            self.employee_table.clear_tree()
            for n, s, p, t in self.all_employee_data:
                if query in n.lower() or query in s.lower() or query in p.lower():
                    self.employee_table.insert_row((n, s, p), t)
        self.root.after(0, _update)

    def open_employee_folder(self):
        name = self.employee_table.get_selected_employee()
        if not name: 
            return
        metas = self._cached_employees.get(name, [])
        if metas:
            p = metas[0]['path'] if isinstance(metas[0], dict) else metas[0]
            open_path(str(Path(p).parent))

    def open_employee_file(self):
        name = self.employee_table.get_selected_employee()
        if not name: 
            return
        metas = self._cached_employees.get(name, [])
        if metas:
            p = metas[0]['path'] if isinstance(metas[0], dict) else metas[0]
            open_path(p)

    def delete_employee(self):
        name = self.employee_table.get_selected_employee()
        if name:
            if messagebox.askyesno("Удалить", f"Удалить '{name}'?"):
                self.config_controller.delete_employee(name)
                self.refresh_status()
