import os
import threading
import sys
import logging
from datetime import datetime
from decimal import Decimal
from ruamel.yaml import YAML
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog, filedialog
from tkcalendar import DateEntry

# Ensure we can import from the parent 'src' package
try:
    from .consolidator import Consolidator, Config
    from .writer import MasterWriter
except (ImportError, ValueError):
    from consolidator import Consolidator, Config
    from writer import MasterWriter

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

def get_base_path():
    """Returns the base path for the application, handling PyInstaller bundles."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle
        return os.path.dirname(sys.executable)
    else:
        # Running as normal Python script (src/gui_master.py)
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class GuiMaster:
    def __init__(self, root, config_path=None):
        self.root = root
        self.root.title("🚀 Master-Report v5.3 | Financial Consolidator")
        self.root.geometry("1200x900")
        self.root.configure(bg='#f0f2f5')
        
        # Initialize YAML
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        self.yaml.indent(mapping=2, sequence=4, offset=2)
        
        # Colors & Styles
        self.colors = {
            'primary': '#1f4e79',    # Deep Blue
            'success': '#28a745',    # Green
            'danger': '#dc3545',     # Red
            'warning': '#ffc107',    # Yellow/Orange
            'info': '#17a2b8',       # Teal
            'bg_light': '#f8f9fa',
            'sidebar': '#ffffff',
            'text': '#212529'
        }
        
        # Robust path resolution for config.yaml
        if config_path:
            self.config_path = config_path
        else:
            base_path = get_base_path()
            self.config_path = os.path.join(base_path, 'config.yaml')
        
        if not os.path.exists(self.config_path):
            messagebox.showerror("Ошибка", f"Файл конфигурации 'config.yaml' не найден по пути:\n{self.config_path}")
            self.root.destroy()
            return
            
        self.consolidator = Consolidator(self.config_path)
        self.writer = MasterWriter(self.consolidator.config)
        self.config = self.consolidator.config
        
        # State
        self.all_employee_data = [] # Cache for filtering
        
        self._apply_styles()
        self.setup_ui()
        self.setup_logging()
        
        # Initial status refresh
        self.root.after(100, self.refresh_status)

    def _apply_styles(self):
        """Defines modern ttk styles for the application."""
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('Main.TFrame', background='#f0f2f5')
        style.configure('Sidebar.TFrame', background=self.colors['sidebar'], relief='flat')
        style.configure('TLabel', background='#f0f2f5', foreground=self.colors['text'], font=('Segoe UI', 10))
        style.configure('Sidebar.TLabel', background=self.colors['sidebar'], font=('Segoe UI', 10))
        style.configure('Header.TLabel', font=('Segoe UI', 12, 'bold'), foreground=self.colors['primary'])
        style.configure('TButton', font=('Segoe UI', 10), padding=5)
        style.configure('Action.TButton', background=self.colors['primary'], foreground='white')
        style.map('Action.TButton', background=[('active', '#153654')])
        style.configure('Success.TButton', background=self.colors['success'], foreground='white')
        style.map('Success.TButton', background=[('active', '#218838')])
        style.configure('Audit.TButton', background=self.colors['info'], foreground='white')
        style.map('Audit.TButton', background=[('active', '#138496')])
        style.configure('TLabelframe', background=self.colors['sidebar'], relief='groove', borderwidth=1)
        style.configure('TLabelframe.Label', background=self.colors['sidebar'], foreground=self.colors['primary'], font=('Segoe UI', 9, 'bold'))
        style.configure('Treeview', font=('Segoe UI', 10), rowheight=30)
        style.configure('Treeview.Heading', font=('Segoe UI', 10, 'bold'), background='#e9ecef')
        style.map('Treeview', background=[('selected', self.colors['primary'])], foreground=[('selected', 'white')])
        style.configure('TProgressbar', thickness=15, troughcolor='#e9ecef', background=self.colors['primary'])

    def setup_ui(self):
        """Sets up the main user interface with improved layout."""
        self.sidebar = ttk.Frame(self.root, width=320, padding="15", style='Sidebar.TFrame')
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar.pack_propagate(False)
        
        self.main_area = ttk.Frame(self.root, padding="15", style='Main.TFrame')
        self.main_area.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # --- SIDEBAR CONTENT ---
        ttk.Label(self.sidebar, text="📊 ПАНЕЛЬ УПРАВЛЕНИЯ", style='Header.TLabel', background=self.colors['sidebar']).pack(pady=(0, 20), anchor=tk.W)
        
        # Group 1: Calendar
        date_frame = ttk.LabelFrame(self.sidebar, text="📅 ВЫБОР ДАТЫ", padding=10)
        date_frame.pack(fill=tk.X, pady=(0, 10))
        self.date_entry = DateEntry(date_frame, width=12, background=self.colors['primary'],
                                    foreground='white', borderwidth=2, date_pattern='dd.mm.yyyy')
        self.date_entry.pack(pady=(0, 10), fill=tk.X)
        self.date_entry.bind("<<DateEntrySelected>>", lambda e: self.refresh_status())
        self.refresh_btn = ttk.Button(date_frame, text="🔄 Обновить статус", command=self.refresh_status)
        self.refresh_btn.pack(fill=tk.X)
        
        # Group 2: Employee Management
        emp_frame = ttk.LabelFrame(self.sidebar, text="👤 СОТРУДНИКИ", padding=10)
        emp_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Button(emp_frame, text="➕ Добавить", command=self.add_employee_dialog).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(emp_frame, text="📎 Привязать", command=self.attach_file_dialog).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Group 3: Consolidation Actions
        action_frame = ttk.LabelFrame(self.sidebar, text="🚀 СБОРКА", padding=10)
        action_frame.pack(fill=tk.X, pady=(0, 10))
        self.consolidate_btn = ttk.Button(action_frame, text="⚡ СОБРАТЬ ДЕНЬ", style='Action.TButton', command=self.run_consolidation)
        self.consolidate_btn.pack(fill=tk.X, pady=(0, 5))
        self.consolidate_all_btn = ttk.Button(action_frame, text="🌍 СОБРАТЬ ВСЕ ДАТЫ", command=self.run_consolidation_all_dates)
        self.consolidate_all_btn.pack(fill=tk.X)
        
        # Group 4: Progress & Stats
        stats_frame = ttk.LabelFrame(self.sidebar, text="📈 СТАТИСТИКА ДНЯ", padding=10)
        stats_frame.pack(fill=tk.X, pady=(0, 10))
        self.stats_label = ttk.Label(stats_frame, text="Сотрудников: 0\nОтчетов готово: 0\nОшибок: 0", justify=tk.LEFT, background=self.colors['sidebar'])
        self.stats_label.pack(fill=tk.X)
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(stats_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill=tk.X, pady=(10, 0))
        
        # Log Area
        log_label_frame = ttk.Frame(self.sidebar, style='Sidebar.TFrame')
        log_label_frame.pack(fill=tk.X, pady=(10, 2))
        ttk.Label(log_label_frame, text="📝 Логи:", font=('Segoe UI', 9), background=self.colors['sidebar']).pack(side=tk.LEFT)
        ttk.Button(log_label_frame, text="🧹", width=3, command=self.clear_logs).pack(side=tk.RIGHT)
        self.log_area = scrolledtext.ScrolledText(self.sidebar, height=12, state='disabled', font=('Consolas', 8), borderwidth=1, relief='solid')
        self.log_area.pack(fill=tk.BOTH, expand=True)

        # --- MAIN AREA ---
        header_frame = ttk.Frame(self.main_area, style='Main.TFrame')
        header_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header_frame, text="📋 СТАТУС ГОТОВНОСТИ ОТЧЕТОВ", style='Header.TLabel').pack(side=tk.LEFT)
        btn_frame = ttk.Frame(header_frame, style='Main.TFrame')
        btn_frame.pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="📂 Папка Master", command=self.open_master_folder).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📋 Копировать должников", command=self.copy_missing_to_clipboard).pack(side=tk.LEFT)
        
        # Search & Treeview
        search_frame = ttk.Frame(self.main_area, style='Main.TFrame')
        search_frame.pack(fill=tk.X, pady=(0, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.filter_tree())
        ttk.Entry(search_frame, textvariable=self.search_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.tree_frame = ttk.Frame(self.main_area)
        self.tree_frame.pack(fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(self.tree_frame, columns=("Employee", "Status", "Path"), show='headings', selectmode='browse')
        self.tree.heading("Employee", text="Сотрудник"); self.tree.heading("Status", text="Статус"); self.tree.heading("Path", text="Файл отчета")
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Context menu
        self.menu = tk.Menu(self.tree, tearoff=0)
        self.menu.add_command(label="📁 Открыть папку", command=self.open_employee_folder)
        self.menu.add_command(label="📊 Открыть файл", command=self.open_employee_file)
        self.menu.add_separator()
        self.menu.add_command(label="❌ Удалить сотрудника", command=self.delete_employee)
        self.tree.bind("<Button-3>", self.show_context_menu)
        self.tree.bind("<Double-1>", lambda e: self.open_employee_file())

    def setup_logging(self):
        self.text_handler = TextHandler(self.log_area)
        self.text_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S'))
        root_logger = logging.getLogger()
        root_logger.addHandler(self.text_handler)
        root_logger.setLevel(logging.INFO)

    def clear_logs(self):
        self.log_area.configure(state='normal'); self.log_area.delete('1.0', tk.END); self.log_area.configure(state='disabled')

    def open_master_folder(self):
        try:
            path = os.path.dirname(self.writer.master_path)
            if os.path.exists(path): os.startfile(path)
        except Exception as e: logging.error(f"Ошибка: {e}")

    def open_employee_folder(self):
        sel = self.tree.selection()
        if not sel: return
        name = self.tree.item(sel[0])['values'][0]
        paths = self.consolidator.get_employees().get(name, [])
        if paths: os.startfile(os.path.dirname(paths[0]))

    def open_employee_file(self):
        sel = self.tree.selection()
        if not sel: return
        name = self.tree.item(sel[0])['values'][0]
        paths = self.consolidator.get_employees().get(name, [])
        if paths: os.startfile(paths[0])

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item: 
            self.tree.selection_set(item)
            self.menu.post(event.x_root, event.y_root)

    def delete_employee(self):
        sel = self.tree.selection()
        if sel:
            name = self.tree.item(sel[0], 'values')[0]
            if messagebox.askyesno("Удалить", f"Удалить '{name}'?"):
                curr = self.config.get('employees', [])
                if name in curr:
                    curr.remove(name)
                    self.config.data['employees'] = curr
                
                # ALSO remove from employee_paths to avoid leaks in config.yaml
                custom_paths = self.config.get('employee_paths', {})
                if name in custom_paths:
                    del custom_paths[name]
                    self.config.data['employee_paths'] = custom_paths
                    
                self.save_config()
                self.refresh_status()

    def filter_tree(self):
        query = self.search_var.get().lower()
        for item in self.tree.get_children(): self.tree.delete(item)
        for n, s, p, t in self.all_employee_data:
            if query in n.lower() or query in s.lower() or query in p.lower():
                self.tree.insert('', tk.END, values=(n, s, p), tags=(t,))

    def update_stats(self, ready_count, total_count, total_income, total_expense, error_count=0):
        text = f"Готово: {ready_count}/{total_count}\nПриход: {total_income:,.2f}\nРасход: {total_expense:,.2f}\nОшибки: {error_count}"
        self.stats_label.config(text=text)

    def refresh_status(self):
        """Refreshes the status of all employees for the selected date."""
        selected_date = self.date_entry.get_date()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.progress_var.set(0)
            
        def task():
            try:
                self.refresh_btn.config(state='disabled')
                
                # Get aggregated mapping once to avoid redundant disk I/O
                employees_map = self.consolidator.get_employees()
                
                # Get unique sorted list of employees from config
                config_employees = self.config.get('employees', [])
                if config_employees:
                    # Use set to ensure uniqueness if config has duplicates
                    unique_names = sorted(list(set(config_employees)))
                else:
                    # Fallback to discovered employees if config is empty
                    unique_names = sorted(employees_map.keys())

                if not unique_names:
                    self.root.after(0, lambda: [self.update_stats(0, 0, Decimal('0'), Decimal('0')), self.progress_var.set(100)])
                    return

                ready_count = 0
                local_data = [] # Use local list to prevent race conditions and duplicates
                total_count = len(unique_names)
                
                for i, name in enumerate(unique_names):
                    # Update progress bar in UI thread
                    progress = ((i + 1) / total_count) * 100
                    self.root.after(0, lambda v=progress: self.progress_var.set(v))
                    
                    paths = employees_map.get(name, [])
                    
                    if not paths:
                        status, tag, path_str = "🔴 НЕТ ФАЙЛА", 'missing', "---"
                    else:
                        # Aggregated status logic: check if any file has the selected date
                        path_str = os.path.basename(paths[0]) if len(paths) == 1 else f"[{len(paths)} файлов]"
                        status, tag = "🟠 НЕТ ДАТЫ", 'partial'
                        try:
                            for p in paths:
                                if self.consolidator.check_date_exists(p, selected_date):
                                    status, tag = "🟢 ГОТОВО", 'ready'
                                    ready_count += 1
                                    break
                        except Exception as e:
                            logging.error(f"Ошибка проверки даты для {name}: {e}")
                            status, tag = "❌ ОШИБКА", 'missing'
                    
                    local_data.append((name, status, path_str, tag))
                
                # Final UI update on main thread
                def finalize():
                    self.all_employee_data = local_data
                    self.filter_tree()
                    self.update_stats(ready_count, total_count, Decimal('0'), Decimal('0'))
                    self.progress_var.set(100)
                
                self.root.after(0, finalize)
                
            except Exception as e:
                logging.error(f"Ошибка при обновлении статуса: {e}")
            finally:
                self.root.after(0, lambda: self.refresh_btn.config(state='normal'))
        
        threading.Thread(target=task, daemon=True).start()

    def attach_file_dialog(self):
        employees = self.config.get('employees', [])
        dialog = tk.Toplevel(self.root)
        dialog.title("Привязать файлы (без копирования)")
        dialog.geometry("450x400")
        
        ttk.Label(dialog, text="Выберите сотрудника для привязки файлов:", padding=10).pack()
        
        lb = tk.Listbox(dialog)
        for e in employees:
            lb.insert(tk.END, e)
        lb.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.append_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(dialog, text="Добавить к существующим (не удалять старые)", variable=self.append_var).pack(pady=5)
        
        def pick():
            sel = lb.curselection()
            if not sel:
                messagebox.showwarning("Внимание", "Сначала выберите сотрудника из списка")
                return
            
            emp_name = lb.get(sel[0])
            file_paths = filedialog.askopenfilenames(
                title=f"Выберите файлы отчетов для {emp_name}",
                filetypes=[("Excel files", "*.xlsx")]
            )
            
            if file_paths:
                # Convert tuple to list of absolute paths
                abs_paths = [os.path.abspath(fp) for fp in file_paths]
                
                # Get current paths and handle legacy string format
                current_paths = self.config.data.get('employee_paths', {}).get(emp_name, [])
                if isinstance(current_paths, str):
                    current_paths = [current_paths]
                
                # Combine based on checkbox
                if self.append_var.get():
                    combined = current_paths + abs_paths
                else:
                    combined = abs_paths
                
                # Remove duplicates while preserving order
                final_paths = list(dict.fromkeys(combined))
                
                # Store absolute paths in config
                if 'employee_paths' not in self.config.data:
                    self.config.data['employee_paths'] = {}
                
                self.config.data['employee_paths'][emp_name] = final_paths
                self.save_config()
                
                logging.info(f"Сотруднику {emp_name} привязано файлов: {len(final_paths)} (новых: {len(abs_paths)})")
                messagebox.showinfo("Успех", f"Файлы для {emp_name} успешно привязаны ({len(final_paths)} шт.)!")
                dialog.destroy()
                self.refresh_status()
        
        btn_frame = ttk.Frame(dialog, padding=10)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="Выбрать файл", command=pick).pack(side=tk.RIGHT)
        ttk.Button(btn_frame, text="Отмена", command=dialog.destroy).pack(side=tk.RIGHT, padx=5)

    def copy_missing_to_clipboard(self):
        missing = [n for n, s, p, t in self.all_employee_data if "🟢 ГОТОВО" not in s]
        if missing:
            text = f"Должники за {self.date_entry.get_date().strftime('%d.%m')}:\n" + "\n".join([f"- {m}" for m in missing])
            self.root.clipboard_clear(); self.root.clipboard_append(text); messagebox.showinfo("Успех", "Скопировано")

    def add_employee_dialog(self):
        name = simpledialog.askstring("Добавить", "Имя сотрудника:")
        if name:
            curr = self.config.get('employees', [])
            if name.strip() not in curr: curr.append(name.strip()); self.config.data['employees'] = sorted(curr); self.save_config(); self.refresh_status()

    def save_config(self):
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f: config_to_save = self.yaml.load(f)
            config_to_save['employees'] = self.config.data.get('employees', [])
            config_to_save['employee_paths'] = self.config.data.get('employee_paths', {})
            with open(self.config_path, 'w', encoding='utf-8') as f: self.yaml.dump(config_to_save, f)
        except Exception as e: logging.error(f"Ошибка сохранения: {e}")

    def run_consolidation_all_dates(self):
        def task():
            try:
                self.consolidate_all_btn.config(state='disabled')
                logging.info("Поиск всех доступных дат в файлах...")
                all_dates = self.consolidator.get_all_available_dates()
                if not all_dates:
                    logging.warning("Даты не найдены.")
                    return
                
                if not messagebox.askyesno("Найдено дат: " + str(len(all_dates)), 
                                         f"Найдено {len(all_dates)} дат. Начать полную сборку отчетов кураторов?"):
                    return

                results_by_date = self.consolidator.consolidate_multiple(all_dates)
                if not results_by_date: return

                self.writer.write_all_days(results_by_date)
                logging.info("Глобальная сборка завершена!")
                if messagebox.askyesno("Успех", "Сборка завершена! Открыть файл?"):
                    os.startfile(self.writer.master_path)
            except Exception as e:
                logging.error(f"Ошибка: {e}")
            finally:
                self.root.after(0, lambda: self.consolidate_all_btn.config(state='normal'))
        threading.Thread(target=task, daemon=True).start()

    def run_consolidation(self):
        selected_date = self.date_entry.get_date()
        missing = [n for n, s, p, t in self.all_employee_data if "🟢 ГОТОВО" not in s]
        if missing:
            if not messagebox.askyesno("Предупреждение", f"Не сдано отчетов: {len(missing)}. Продолжить?"): return

        def task():
            try:
                self.consolidate_btn.config(state='disabled')
                logging.info(f"--- Сборка за {selected_date.strftime('%d.%m')} ---")
                self.progress_var.set(20)
                
                # 1. Consolidate employee data
                results = self.consolidator.consolidate_multiple([selected_date])
                all_data = results.get(selected_date.strftime("%d.%m.%Y"), [])
                if not all_data:
                    logging.warning("Нет данных за выбранную дату."); return
                
                # 2. Write data to Excel
                self.progress_var.set(60)
                self.writer.write_daily_data(selected_date, all_data)
                
                self.progress_var.set(100)
                logging.info("Успешно!")
                if messagebox.askyesno("Успех", f"Консолидация завершена!\n\nОткрыть файл?"): os.startfile(self.writer.master_path)
            except Exception as e:
                logging.error(f"Ошибка: {e}")
                self.root.after(0, lambda: messagebox.showerror("Ошибка", f"Произошла ошибка:\n{e}"))
            finally: self.root.after(0, lambda: self.consolidate_btn.config(state='normal'))

        threading.Thread(target=task, daemon=True).start()

if __name__ == "__main__":
    root = tk.Tk()
    app = GuiMaster(root)
    root.mainloop()
