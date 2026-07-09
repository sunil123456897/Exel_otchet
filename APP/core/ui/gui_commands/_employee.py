"""Refresh, employee-table sync, and one-off employee actions.

Everything the user can do *to the employee list* — add, attach, open
folder, delete, refresh — lives here. The consolidation / RSCH /
reconciliation commands are bigger and get their own modules.
"""
from __future__ import annotations

from tkinter import messagebox
from pathlib import Path
from typing import List

from core.infra import open_path
from core.ui.operation_state import OperationType
from core.ui.gui_commands._base import CommandContext


class EmployeeCommandsMixin:
    """Mixin providing refresh + employee table actions.

    The mixin is meant to be combined with :class:`GuiCommands`, which
    supplies the ``ctx`` and ``_record_dashboard_result`` methods
    referenced below. Splitting along this seam keeps the file size
    manageable: the employee list interactions change together, and
    the build-report commands change together.
    """

    ctx: CommandContext

    # --- refresh / status sync -----------------------------------------

    def refresh_status(self) -> None:
        """Trigger a full employee re-scan and update the table."""
        if not self.ctx.operation_state.begin(OperationType.REFRESH):
            return
        self.ctx.employee_table.clear_tree()
        self.ctx.stats_panel.set_readiness(0)
        self.ctx.stats_panel.set_operation(0)

        def on_refresh_complete() -> None:
            self.ctx.operation_state.end()

        def on_refresh_error(message: str) -> None:
            def show() -> None:
                if self.ctx.toasts:
                    self.ctx.toasts.error(
                        "Ошибка обновления", message, duration_ms=6000
                    )
                else:
                    messagebox.showerror("Ошибка", message)
            self.ctx.root.after(0, show)

        self.ctx.employee_vm.refresh(
            self.ctx.app_controller,
            self.ctx.sidebar.get_date(),
            self._on_consolidation_progress,
            on_complete=on_refresh_complete,
            on_error=on_refresh_error,
        )

    def _on_consolidation_progress(self, progress: float) -> None:
        self.ctx.post(lambda: self.ctx.stats_panel.set_operation(progress))

    def _sync_employee_ui(self) -> None:
        self.ctx.employee_table.clear_tree()
        employees = self.ctx.employee_vm.get_filtered_employees()
        if not employees:
            # U11: show a friendly empty state instead of a bare table on
            # a fresh install (or when every row is filtered out). Uses
            # the existing EmployeeTable.show_empty_state so the styling
            # (placeholder tag, disabled selection) stays consistent.
            self.ctx.employee_table.show_empty_state(
                "Добавьте сотрудников, чтобы начать"
            )
        for emp in employees:
            self.ctx.employee_table.insert_row(
                (emp.name, emp.status_text, emp.path_text), emp.tag
            )
        self.ctx.stats_panel.update_stats(
            self.ctx.employee_vm.get_ready_count(),
            self.ctx.employee_vm.get_total_count(),
        )
        self.ctx.stats_panel.set_readiness(
            self.ctx.employee_vm.get_progress_percent()
        )
        self.ctx.sidebar.set_refresh_state("normal")
        self._refresh_dashboard()

    def _refresh_dashboard(self) -> None:
        if self.ctx.dashboard_tabs is not None:
            self.ctx.dashboard_tabs.refresh()

    # --- add / attach / open / delete -----------------------------------

    def add_employee_dialog(self) -> None:
        from core.ui.ui_dialogs import ask_employee_name

        existing = list(self.ctx.employee_vm.get_all_names())
        name = ask_employee_name(existing_names=existing)
        if name:
            self.ctx.employee_vm.add_employee(self.ctx.config_controller, name)
            self.refresh_status()

    def attach_file_dialog(self) -> None:
        from core.ui.ui_dialogs import show_attach_file_dialog

        def on_attach(name, paths, append) -> None:
            self.ctx.employee_vm.attach_files(
                self.ctx.config_controller, name, paths, append=append
            )
            self.refresh_status()

        show_attach_file_dialog(
            self.ctx.root,
            self.ctx.employee_vm.get_all_names() or self.ctx.config_controller.get_employees(),
            on_attach,
        )

    def attach_files_to_employee(self, name: str, paths: List[str]) -> None:
        """UX-010: Attach dropped files to an employee (drag-and-drop)."""
        self.ctx.employee_vm.attach_files(
            self.ctx.config_controller, name, paths, append=True
        )
        self.refresh_status()
        if self.ctx.toasts:
            self.ctx.toasts.success(
                "Файл привязан",
                f"{'.'.join(Path(p).name for p in paths)} → {name}",
                duration_ms=2500,
            )

    def open_master_folder(self) -> None:
        p = self.ctx.employee_vm.get_master_path(self.ctx.config_controller)
        if p and p.parent.exists():
            open_path(str(p.parent))

    def copy_missing_to_clipboard(self) -> None:
        missing = self.ctx.employee_vm.get_missing_names()
        if missing:
            date_str = self.ctx.sidebar.get_date().strftime("%d.%m")
            text = "Должники за " + date_str + ":\n" + "\n".join(
                f"- {m}" for m in missing
            )
            self.ctx.root.clipboard_clear()
            self.ctx.root.clipboard_append(text)
            if self.ctx.toasts:
                self.ctx.toasts.info(
                    "Должники",
                    "Список скопирован в буфер обмена",
                    duration_ms=2500,
                )
            else:
                messagebox.showinfo(
                    "Успех", "Список должников скопирован в буфер обмена"
                )

    def filter_tree(self) -> None:
        # Forward BOTH the text search and the status dropdown filter to
        # the viewmodel so get_filtered_employees applies them together.
        # Previously only search_query was passed, leaving the status
        # dropdown (Все/Готово/Нет файла/Должники) as a dead control.
        self.ctx.employee_vm.search_query = self.ctx.employee_table.get_search_query()
        self.ctx.employee_vm.status_filter = self.ctx.employee_table.get_status_filter()
        self._sync_employee_ui()

    def open_employee_folder(self) -> None:
        name = self.ctx.employee_table.get_selected_employee()
        paths = self.ctx.employee_vm.get_selected_employee_paths(name)
        if not paths:
            return

        unique_parents: List[str] = []
        seen: set = set()
        for raw_path in paths:
            parent = str(Path(raw_path).parent)
            if parent in seen:
                continue
            seen.add(parent)
            unique_parents.append(parent)

        for parent in unique_parents:
            open_path(parent)

    def open_employee_file(self) -> None:
        name = self.ctx.employee_table.get_selected_employee()
        paths = self.ctx.employee_vm.get_selected_employee_paths(name)
        if not paths:
            return
        if len(paths) == 1:
            open_path(paths[0])
            return

        action = messagebox.askyesnocancel(
            "Несколько файлов",
            (
                f"У сотрудника '{name}' найдено {len(paths)} файлов.\n\n"
                "Да - открыть все файлы\n"
                "Нет - открыть папки с файлами\n"
                "Отмена - ничего не делать"
            ),
        )
        if action is None:
            return
        if action:
            for path in paths:
                open_path(path)
            return

        self.open_employee_folder()

    def delete_employee(self) -> None:
        # UX-015: support batch deletion of multiple selected employees.
        names = self.ctx.employee_table.get_selected_employees()
        if not names:
            # Fallback to single selection for backward compat
            name = self.ctx.employee_table.get_selected_employee()
            if not name:
                return
            names = [name]
        count = len(names)
        if count == 1:
            msg = f"Удалить сотрудника '{names[0]}'?"
        else:
            msg = f"Удалить {count} сотрудников?\n\n" + "\n".join(f"• {n}" for n in names[:10])
            if count > 10:
                msg += f"\n... и ещё {count - 10}"
        if not messagebox.askyesno("Удалить", msg):
            return
        for name in names:
            self.ctx.employee_vm.delete_employee(self.ctx.config_controller, name)
        self.refresh_status()
