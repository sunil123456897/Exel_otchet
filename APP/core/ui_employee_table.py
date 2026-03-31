import tkinter as tk
from tkinter import ttk
from core.theme import ThemeManager

class EmployeeTable(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, style='Main.TFrame')
        self.controller = controller
        self._setup_ui()

    def _setup_ui(self):
        # Header with actions
        header_frame = ttk.Frame(self, style='Main.TFrame')
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(
            header_frame, 
            text="📋 СТАТУС ГОТОВНОСТИ ОТЧЕТОВ", 
            style='Header.TLabel'
        ).pack(side=tk.LEFT)
        
        btn_frame = ttk.Frame(header_frame, style='Main.TFrame')
        btn_frame.pack(side=tk.RIGHT)
        
        ttk.Button(
            btn_frame, 
            text="📂 Папка Master", 
            command=self.controller.open_master_folder
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame, 
            text="📋 Копировать должников", 
            command=self.controller.copy_missing_to_clipboard
        ).pack(side=tk.LEFT)

        # Search
        search_frame = ttk.Frame(self, style='Main.TFrame')
        search_frame.pack(fill=tk.X, pady=(0, 5))
        
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self.controller.filter_tree())
        
        ttk.Entry(
            search_frame, 
            textvariable=self.search_var
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Treeview
        self.tree_frame = ttk.Frame(self)
        self.tree_frame.pack(fill=tk.BOTH, expand=True)
        
        self.tree = ttk.Treeview(
            self.tree_frame, 
            columns=("Employee", "Status", "Path"), 
            show='headings', 
            selectmode='browse'
        )
        self.tree.heading("Employee", text="Сотрудник")
        self.tree.heading("Status", text="Статус")
        self.tree.heading("Path", text="Файл отчета")
        
        self.tree.column("Employee", width=200)
        self.tree.column("Status", width=150)
        self.tree.column("Path", width=400)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self.tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Context Menu
        self.menu = tk.Menu(self.tree, tearoff=0)
        self.menu.add_command(label="📁 Открыть папку", command=self.controller.open_employee_folder)
        self.menu.add_command(label="📊 Открыть файл", command=self.controller.open_employee_file)
        self.menu.add_separator()
        self.menu.add_command(label="❌ Удалить сотрудника", command=self.controller.delete_employee)
        
        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<Double-1>", lambda e: self.controller.open_employee_file())

    def _show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item: 
            self.tree.selection_set(item)
            self.menu.post(event.x_root, event.y_root)

    def get_search_query(self):
        return self.search_var.get().lower()

    def clear_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def insert_row(self, values, tag):
        self.tree.insert('', tk.END, values=values, tags=(tag,))

    def get_selected_employee(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return self.tree.item(sel[0])['values'][0]

