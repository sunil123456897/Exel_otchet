import tkinter as tk
from tkinter import ttk
from typing import Any

from core.ui.debounce import Debouncer
from core.ui.theme import ThemeManager, color as _c, status_tint

# UX-010: Optional drag-and-drop support via tkinterdnd2.
# If the package is not installed, drag-drop is silently disabled
# and the user attaches files via the "Привязать" button as before.
try:
    import tkinterdnd2
    _DND_AVAILABLE = True
except ImportError:
    tkinterdnd2 = None
    _DND_AVAILABLE = False


_COLUMN_WEIGHTS = {
    "Employee": 35,
    "Status": 20,
    "Path": 45,
}


class EmployeeTable(ttk.Frame):
    def __init__(self, parent: tk.Misc, controller: Any) -> None:
        super().__init__(parent, style="Main.TFrame")
        self.controller = controller
        self._search_debouncer = Debouncer(self, self.controller.filter_tree, delay_ms=300)
        # Row index for alternating stripes (reset on clear_tree); and
        # the current hovered item id for hover-row highlight.
        self._row_index = 0
        self._hover_row: str | None = None
        # UX-012: sort state — (column, reverse). None = no sort.
        self._sort_column: str | None = None
        self._sort_reverse: bool = False
        # UX-013: status filter — None = show all.
        self._status_filter: str | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        # Header with actions
        header_frame = ttk.Frame(self, style="Main.TFrame")
        header_frame.pack(fill=tk.X, pady=(0, ThemeManager.SPACING["sm"]))

        ttk.Label(header_frame, text="📋 СТАТУС ГОТОВНОСТИ ОТЧЕТОВ", style="Header.TLabel").pack(
            side=tk.LEFT
        )

        btn_frame = ttk.Frame(header_frame, style="Main.TFrame")
        btn_frame.pack(side=tk.RIGHT)

        ttk.Button(
            btn_frame, text="📂 Папка Master", command=self.controller.open_master_folder
        ).pack(side=tk.LEFT, padx=ThemeManager.SPACING["xs"])

        ttk.Button(
            btn_frame, text="📋 Должники", command=self.controller.copy_missing_to_clipboard
        ).pack(side=tk.LEFT)

        # Search + status filter (UX-013)
        search_frame = ttk.Frame(self, style="Main.TFrame")
        search_frame.pack(fill=tk.X, pady=(0, ThemeManager.SPACING["xs"]))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._search_debouncer())

        ttk.Entry(search_frame, textvariable=self.search_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

        # UX-013: status filter dropdown
        self._status_filter_var = tk.StringVar(value="Все")
        filter_cb = ttk.Combobox(
            search_frame,
            textvariable=self._status_filter_var,
            values=["Все", "Готово", "Нет файла", "Должники"],
            state="readonly",
            width=12,
        )
        filter_cb.pack(side=tk.RIGHT, padx=(4, 0))
        filter_cb.bind("<<ComboboxSelected>>", lambda e: self._on_status_filter_change())

        # Treeview
        self.tree_frame = ttk.Frame(self)
        self.tree_frame.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(
            self.tree_frame,
            columns=("Employee", "Status", "Path"),
            show="headings",
            # UX-015: extended selectmode allows multi-select (Ctrl+click,
            # Shift+click) for batch operations (delete multiple, etc.).
            selectmode="extended",
        )
        # UX-012: clickable headings for sort. Clicking toggles asc/desc.
        self.tree.heading("Employee", text="Сотрудник ▲▼",
                          command=lambda: self._sort_by("Employee"))
        self.tree.heading("Status", text="Статус ▲▼",
                          command=lambda: self._sort_by("Status"))
        self.tree.heading("Path", text="Файл отчета ▲▼",
                          command=lambda: self._sort_by("Path"))

        # All columns stretch proportionally to window width
        self.tree.column("Employee", width=180, stretch=True)
        self.tree.column("Status", width=120, stretch=True)
        self.tree.column("Path", width=250, stretch=True)

        # Bind to frame resize for proportional column distribution
        self.tree_frame.bind("<Configure>", self._resize_columns, add="+")

        # Alternating row stripes + hover highlight (POLISH-3).
        # Status tags ("ready"/"missing"/"partial") get a coloured
        # foreground so the user can scan readiness at a glance.
        self._configure_tags()
        self.tree.bind("<Motion>", self._on_tree_motion, add="+")
        self.tree.bind("<Leave>", self._on_tree_leave, add="+")

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Scrollbar
        scrollbar = ttk.Scrollbar(self.tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Context Menu
        self.menu = tk.Menu(
            self.tree,
            tearoff=0,
            bg=_c("bg_sidebar"),
            fg=_c("text"),
            activebackground=_c("primary"),
            activeforeground=_c("text_inverse"),
            borderwidth=0,
        )
        # tk.Menu does not honour ttk styles, so register it for
        # re-theming on light↔dark switches — otherwise the right-click
        # menu lingers in the palette that was active at creation.
        ThemeManager.register_menu(self.menu)
        self.menu.add_command(
            label="📁 Открыть папку", command=self.controller.open_employee_folder
        )
        self.menu.add_command(label="📊 Открыть файл", command=self.controller.open_employee_file)
        self.menu.add_separator()
        # UX-015: batch delete — label changes based on selection count
        self.menu.add_command(
            label="❌ Удалить сотрудника", command=self.controller.delete_employee
        )

        self.tree.bind("<Button-3>", self._show_context_menu)
        self.tree.bind("<Double-1>", lambda e: self.controller.open_employee_file())
        self.bind("<Destroy>", self._on_destroy, add="+")

        # UX-010: drag-and-drop file attachment. If tkinterdnd2 is
        # available, register the tree as a drop target — dropping an
        # .xlsx file onto a row attaches it to that employee.
        if _DND_AVAILABLE:
            try:
                # tkinterdnd2 monkey-patches these methods onto the widget
                # at runtime; the ttk stubs don't know about them.
                self.tree.drop_target_register(tkinterdnd2.DND_FILES)  # type: ignore[attr-defined]
                self.tree.dnd_bind("<<Drop>>", self._on_file_drop)  # type: ignore[attr-defined]
            except (tk.TclError, AttributeError):
                pass  # DnD not supported on this platform/config

    def _on_file_drop(self, event: Any) -> None:
        """UX-010: Handle a dropped file — attach to the selected employee."""
        # event.data contains the dropped file path(s), possibly wrapped in {}.
        raw = event.data.strip()
        # Parse: Tk DnD may give "{C:/path/to/file.xlsx}" or "C:/path/to/file.xlsx"
        paths = []
        for token in raw.split():
            token = token.strip("{}")
            if token:
                paths.append(token)
        if not paths:
            return
        # Find which employee row the drop landed on
        row = self.tree.identify_row(event.y)
        if not row:
            return
        values = self.tree.item(row, "values")
        if not values:
            return
        employee_name = str(values[0])
        # Only accept .xlsx files
        xlsx_paths = [p for p in paths if p.lower().endswith((".xlsx", ".xls"))]
        if not xlsx_paths:
            return
        # Delegate to the controller's attach logic
        attach = getattr(self.controller, "attach_files_to_employee", None)
        if callable(attach):
            attach(employee_name, xlsx_paths)

    def _configure_tags(self) -> None:
        """Apply current theme colours to Treeview row tags.

        Called at init and again on every ``refresh_theme()`` so the
        stripes/status colours follow light↔dark switches.

        Status tags (ready/missing/partial) carry BOTH a coloured
        foreground AND a faint row-wash tint so readiness is scannable
        at a glance without reading the status text. The tint is a
        very-light wash derived from the semantic colour — light enough
        that the odd/even stripe is still perceptible through it but
        saturated enough to mark the row. Status text is set in the
        Semibold font so it reads as a deliberate label, not body copy.
        """
        # Row stripes + hover (no status semantics).
        self.tree.tag_configure("odd", background=_c("bg_panel"))
        self.tree.tag_configure("even", background=_c("bg_sidebar"))
        self.tree.tag_configure("hover", background=_c("border_subtle"))

        bold = ThemeManager.FONTS["body_bold"]

        # ready — success: green tint + bold green text.
        self.tree.tag_configure(
            "ready",
            foreground=_c("success"),
            background=status_tint("success"),
            font=bold,
        )
        # missing — danger: red tint + bold red text.
        self.tree.tag_configure(
            "missing",
            foreground=_c("danger"),
            background=status_tint("danger"),
            font=bold,
        )
        # partial — warning: amber tint + bold amber text.
        # Previously UNREGISTERED: rows with tag "partial" ("🟠 НЕТ ДАТЫ")
        # were generated by app_controller but rendered in the default
        # body colour, so the "no data yet" state was nearly invisible
        # against normal rows — the primary complaint from the screen
        # review. Registering it here gives it the same scannable
        # treatment as ready/missing.
        self.tree.tag_configure(
            "partial",
            foreground=_c("warning"),
            background=status_tint("warning"),
            font=bold,
        )
        # UX-021: empty-state placeholder — italic, muted colour
        self.tree.tag_configure("empty_state", foreground=_c("text_secondary"))

    def refresh_theme(self) -> None:
        """Re-apply theme-dependent tag colours after a palette switch."""
        self._configure_tags()

    def reflow_columns(self) -> None:
        """Recalculate column widths proportionally (called on scale change)."""
        self._resize_columns()

    def _resize_columns(self, event: object = None) -> None:
        """Distribute treeview width proportionally across columns.

        Uses the ``_COLUMN_WEIGHTS`` dict (percentages). The scrollbar
        width is subtracted so the distribution matches the visible area.
        """
        try:
            total = self.tree_frame.winfo_width()
            if total < 50:
                return
            # Subtract ~20 px for the scrollbar
            available = total - 20
            for col, weight in _COLUMN_WEIGHTS.items():
                w = max(60, int(available * weight / 100))
                self.tree.column(col, width=w, minwidth=60)
        except (tk.TclError, AttributeError):
            pass

    def _on_destroy(self, _event: object) -> None:
        self._search_debouncer.cancel()

    def _show_context_menu(self, event: Any) -> None:
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.menu.post(event.x_root, event.y_root)

    def get_search_query(self) -> str:
        return self.search_var.get().lower()

    def clear_tree(self) -> None:
        self._row_index = 0
        self._hover_row = None
        for item in self.tree.get_children():
            self.tree.delete(item)

    def insert_row(self, values: Any, tag: str | None) -> None:
        # Remove empty-state placeholder if present
        children = self.tree.get_children()
        if children and self.tree.item(children[0], "tags") == ("empty_state",):
            self.tree.delete(children[0])
        # Alternate stripe tag (odd/even) is merged with the caller's
        # status tag so both the row background AND the status text
        # colour apply — tags are additive in ttk.Treeview.
        stripe = "odd" if self._row_index % 2 else "even"
        self._row_index += 1
        tags = [stripe]
        if tag:
            tags.append(tag)
        self.tree.insert("", tk.END, values=values, tags=tuple(tags))

    def show_empty_state(self, message: str = "Добавьте сотрудников, чтобы начать") -> None:
        """UX-021: Show a placeholder row when the table has no data."""
        self.clear_tree()
        self.tree.insert(
            "", tk.END,
            values=(message, "", ""),
            tags=("empty_state",),
        )

    def _on_tree_motion(self, event: Any) -> None:
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

    def _on_tree_leave(self, _event: object) -> None:
        if self._hover_row:
            self._strip_hover_tag(self._hover_row)
            self._hover_row = None

    def _strip_hover_tag(self, item: str) -> None:
        existing = [t for t in self.tree.item(item, "tags") if t != "hover"]
        self.tree.item(item, tags=existing)

    def get_selected_employee(self) -> Any:
        sel = self.tree.selection()
        if not sel:
            return None
        return self.tree.item(sel[0])["values"][0]

    def get_selected_employees(self) -> list[str]:
        """UX-015: Return all selected employee names (multi-select)."""
        sel = self.tree.selection()
        if not sel:
            return []
        names = []
        for item in sel:
            values = self.tree.item(item)["values"]
            if values:
                names.append(str(values[0]))
        return names

    # ── UX-012: column sorting ──────────────────────────────────

    def _sort_by(self, column: str) -> None:
        """Sort the tree by ``column``. Toggle ascending/descending."""
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = False
        self._apply_sort()

    def _apply_sort(self) -> None:
        """Re-sort the existing tree items by the current sort column."""
        if self._sort_column is None:
            return
        items = list(self.tree.get_children(""))
        col_idx = {"Employee": 0, "Status": 1, "Path": 2}.get(self._sort_column, 0)
        try:
            items.sort(
                key=lambda iid: str(self.tree.item(iid)["values"][col_idx]).lower(),
                reverse=self._sort_reverse,
            )
        except (IndexError, tk.TclError):
            return
        for i, iid in enumerate(items):
            self.tree.move(iid, "", i)

    # ── UX-013: status filter ────────────────────────────────────

    # Map the dropdown's Russian labels to the EmployeeStatus tag values
    # the viewmodel filters on. "Должники" (debtors) is a compound view:
    # everyone who is NOT ready (missing + partial).
    _STATUS_FILTER_MAP = {
        "Готово": "ready",
        "Нет файла": "missing",
        "Должники": "debtors",
    }

    def _on_status_filter_change(self) -> None:
        """Apply the selected status filter by re-running filter_tree."""
        value = self._status_filter_var.get()
        self._status_filter = self._STATUS_FILTER_MAP.get(value)
        # Trigger a re-filter via the controller
        if hasattr(self.controller, "filter_tree"):
            self.controller.filter_tree()

    def get_status_filter(self) -> str | None:
        """Return the active status filter tag, or None for 'show all'.

        Returns one of: None, 'ready', 'missing', 'debtors'.
        """
        return self._status_filter
