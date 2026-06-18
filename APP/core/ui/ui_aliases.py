"""UI tab for customer aliases — reconciliation name mappings.

Позволяет бухгалтерам вручную указывать соответствия между заказчиками
со стороны кураторов (master) и заказчиками со стороны РСЧ. Эти алиасы
используются сверкой: при точном совпадении суммы + исполнителя + имени
заказчика (или алиаса) строка получает статус "сверено".
"""

import tkinter as tk
from tkinter import ttk, messagebox
import logging

logger = logging.getLogger(__name__)


class AliasesTab:
    """Tab widget for managing customer aliases.

    Shows a sortable table of all aliases with add/edit/delete buttons.
    Double-click a row to edit. Changes take effect immediately on the
    next reconciliation run.
    """

    def __init__(self, parent: ttk.Frame, app_controller) -> None:
        self.parent = parent
        self.app = app_controller
        self._editing: dict | None = None
        self._setup_ui()
        self.refresh()

    def _setup_ui(self) -> None:
        # Header
        header = ttk.Frame(self.parent, style="Main.TFrame")
        header.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(
            header,
            text="🔗 Соответствия заказчиков для сверки",
            style="Header.TLabel",
        ).pack(side=tk.LEFT)
        ttk.Label(
            header,
            text="Бухгалтеры указывают, какой заказчик куратора = какой заказчик РСЧ",
            style="Muted.TLabel",
        ).pack(side=tk.LEFT, padx=(12, 0))

        # Toolbar
        toolbar = ttk.Frame(self.parent, style="Main.TFrame")
        toolbar.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(toolbar, text="➕ Добавить", command=self._on_add).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(toolbar, text="✏️ Изменить", command=self._on_edit).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="🗑️ Удалить", command=self._on_delete).pack(side=tk.LEFT, padx=4)
        ttk.Button(toolbar, text="🔄 Обновить", command=self.refresh).pack(side=tk.LEFT, padx=4)
        ttk.Label(
            toolbar,
            text="Двойной клик по строке — изменить",
            style="Muted.TLabel",
        ).pack(side=tk.RIGHT)

        # Treeview
        tree_frame = ttk.Frame(self.parent, style="Main.TFrame")
        tree_frame.pack(fill=tk.BOTH, expand=True)
        columns = ("id", "master", "rsch", "notes", "updated")
        self.tree = ttk.Treeview(
            tree_frame,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("id", text="ID")
        self.tree.heading("master", text="Заказчик (куратор)")
        self.tree.heading("rsch", text="Заказчик (РСЧ)")
        self.tree.heading("notes", text="Заметки")
        self.tree.heading("updated", text="Обновлено")
        self.tree.column("id", width=50, stretch=False)
        self.tree.column("master", width=300, stretch=True)
        self.tree.column("rsch", width=300, stretch=True)
        self.tree.column("notes", width=200, stretch=True)
        self.tree.column("updated", width=140, stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        hsb.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", lambda e: self._on_edit())

        # Footer hint
        ttk.Label(
            self.parent,
            text="ℹ️ Сверено = точное совпадение суммы + исполнителя + заказчика (или алиаса). "
                 "Строки с частичным совпадением попадают в «Проверить» — добавьте алиас, чтобы "
                 "в следующий раз они сверялись автоматически.",
            style="Muted.TLabel",
            wraplength=900,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(8, 0))

    def refresh(self) -> None:
        """Reload aliases from DB into the treeview."""
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            aliases = self.app.get_customer_aliases()
        except Exception as e:
            logger.error("Failed to load aliases: %s", e)
            messagebox.showerror("Ошибка", f"Не удалось загрузить алиасы: {e}", parent=self.parent)
            return
        for a in aliases:
            updated = (a.updated_at or "")[:19]
            self.tree.insert(
                "",
                tk.END,
                values=(a.id, a.master_customer, a.rsch_customer, a.notes, updated),
            )

    def _selected_id(self) -> int | None:
        sel = self.tree.selection()
        if not sel:
            return None
        values = self.tree.item(sel[0], "values")
        return int(values[0]) if values else None

    def _on_add(self) -> None:
        self._open_dialog(mode="add")

    def _on_edit(self) -> None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Изменение", "Выберите строку для изменения", parent=self.parent)
            return
        values = self.tree.item(sel[0], "values")
        self._open_dialog(
            mode="edit",
            alias_id=int(values[0]),
            master=str(values[1]),
            rsch=str(values[2]),
            notes=str(values[3]) if values[3] else "",
        )

    def _on_delete(self) -> None:
        alias_id = self._selected_id()
        if alias_id is None:
            messagebox.showinfo("Удаление", "Выберите строку для удаления", parent=self.parent)
            return
        if messagebox.askyesno(
            "Удаление алиаса",
            "Удалить выбранный алиас?",
            parent=self.parent,
        ):
            try:
                self.app.delete_customer_alias(alias_id)
                self.refresh()
            except Exception as e:
                messagebox.showerror("Ошибка", str(e), parent=self.parent)

    def _open_dialog(
        self,
        mode: str,
        alias_id: int | None = None,
        master: str = "",
        rsch: str = "",
        notes: str = "",
    ) -> None:
        dlg = tk.Toplevel(self.parent)
        dlg.title("Добавить алиас" if mode == "add" else "Изменить алиас")
        dlg.geometry("520x230")
        dlg.transient(self.parent)
        dlg.grab_set()

        ttk.Label(dlg, text="Заказчик со стороны куратора:").grid(row=0, column=0, sticky="w", padx=8, pady=(12, 4))
        master_entry = ttk.Entry(dlg, width=60)
        master_entry.grid(row=0, column=1, padx=8, pady=(12, 4))
        master_entry.insert(0, master)

        ttk.Label(dlg, text="Заказчик со стороны РСЧ:").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        rsch_entry = ttk.Entry(dlg, width=60)
        rsch_entry.grid(row=1, column=1, padx=8, pady=4)
        rsch_entry.insert(0, rsch)

        ttk.Label(dlg, text="Заметки:").grid(row=2, column=0, sticky="nw", padx=8, pady=4)
        notes_entry = tk.Text(dlg, width=60, height=3, wrap=tk.WORD)
        notes_entry.grid(row=2, column=1, padx=8, pady=4)
        notes_entry.insert("1.0", notes)

        btn_frame = ttk.Frame(dlg)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=(12, 8))

        def save():
            m = master_entry.get().strip()
            r = rsch_entry.get().strip()
            n = notes_entry.get("1.0", tk.END).strip()
            if not m or not r:
                messagebox.showerror("Ошибка", "Заполните оба поля заказчиков", parent=dlg)
                return
            try:
                if mode == "add":
                    self.app.add_customer_alias(m, r, n)
                else:
                    self.app.update_customer_alias(alias_id, m, r, n)
                self.refresh()
                dlg.destroy()
            except ValueError as e:
                messagebox.showerror("Ошибка", str(e), parent=dlg)
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось сохранить: {e}", parent=dlg)

        ttk.Button(btn_frame, text="Сохранить", command=save).pack(side=tk.LEFT, padx=4)
        ttk.Button(btn_frame, text="Отмена", command=dlg.destroy).pack(side=tk.LEFT, padx=4)

        dlg.update_idletasks()
        dlg.geometry(f"+{self.parent.winfo_rootx() + 100}+{self.parent.winfo_rooty() + 100}")
        master_entry.focus_set()
