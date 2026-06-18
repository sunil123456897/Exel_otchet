import tkinter as tk
from tkinter import ttk

from core.ui.debounce import Debouncer
from core.ui.theme import ThemeManager


def _c(key, fallback):
    """Safe theme-color lookup with fallback for keys POLISH-1 may add."""
    return ThemeManager.COLORS.get(key, fallback)


class EmployeeTable(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, style='Main.TFrame')
        self.controller = controller
        self._search_debouncer = Debouncer(
            self, self.controller.filter_tree, delay_ms=300
        )
        # Row index for alternating stripes (reset on clear_tree); and
        # the current hovered item id for hover-row highlight.
        self._row_index = 0
        self._hover_row = None
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
        self.search_var.trace_add("write", lambda *args: self._search_debouncer())
        
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
        
        self.tree.column("Employee", width=220, stretch=False)
        self.tree.column("Status", width=150, stretch=False)
        self.tree.column("Path", width=400, stretch=True)
        
        # Alternating row stripes + hover highlight (POLISH-3).
        # Status tags ("ready"/"missing"/"partial") get a coloured
        # foreground so the user can scan readiness at a glance.
        self.tree.tag_configure(
            "odd", background=_c("bg_panel", "#f3f4f6")
        )
        self.tree.tag_configure(
            "even", background=_c("bg_sidebar", "#ffffff")
        )
        self.tree.tag_configure(
            "hover", background=_c("border_subtle", _c("trough", "#e5e7eb"))
        )
        self.tree.tag_configure(
            "ready", foreground=_c("success", "#28a745")
        )
        self.tree.tag_configure(
            "missing", foreground=_c("danger", "#dc3545")
        )
        self.tree.bind("<Motion>", self._on_tree_motion, add="+")
        self.tree.bind("<Leave>", self._on_tree_leave, add="+")
        
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
        self.bind("<Destroy>", self._on_destroy, add="+")

    def _on_destroy(self, _event):
        self._search_debouncer.cancel()

    def _show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item: 
            self.tree.selection_set(item)
            self.menu.post(event.x_root, event.y_root)

    def get_search_query(self):
        return self.search_var.get().lower()

    def clear_tree(self):
        self._row_index = 0
        self._hover_row = None
        for item in self.tree.get_children():
            self.tree.delete(item)

    def insert_row(self, values, tag):
        # Alternate stripe tag (odd/even) is merged with the caller's
        # status tag so both the row background AND the status text
        # colour apply — tags are additive in ttk.Treeview.
        stripe = "odd" if self._row_index % 2 else "even"
        self._row_index += 1
        tags = [stripe]
        if tag:
            tags.append(tag)
        self.tree.insert('', tk.END, values=values, tags=tuple(tags))

    def _on_tree_motion(self, event):
        """Highlight the row under the cursor for visual scanning."""
        row = self.tree.identify_row(event.y)
        if row == self._hover_row:
            return
        if self._hover_row:
            self._strip_hover_tag(self._hover_row)
        if row:
            tags = [t for t in self.tree.item(row, "tags") if t != "hover"]
            tags.append("hover")
            self.tree.item(row, tags=tags)
        self._hover_row = row or None

    def _on_tree_leave(self, _event):
        if self._hover_row:
            self._strip_hover_tag(self._hover_row)
            self._hover_row = None

    def _strip_hover_tag(self, item):
        existing = [t for t in self.tree.item(item, "tags") if t != "hover"]
        self.tree.item(item, tags=existing)

    def get_selected_employee(self):
        sel = self.tree.selection()
        if not sel:
            return None
        return self.tree.item(sel[0])['values'][0]

