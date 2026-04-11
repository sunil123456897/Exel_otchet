import logging
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
from typing import Optional

from core.infra import open_path


class GuiCommands:
    def __init__(
        self,
        root,
        config_controller,
        app_controller,
        employee_vm,
        consolidation_vm,
        sidebar,
        employee_table,
        stats_panel,
    ):
        self.root = root
        self.config_controller = config_controller
        self.app_controller = app_controller
        self.employee_vm = employee_vm
        self.consolidation_vm = consolidation_vm
        self.sidebar = sidebar
        self.employee_table = employee_table
        self.stats_panel = stats_panel

    def refresh_status(self):
        self.sidebar.set_refresh_state("disabled")
        self.employee_table.clear_tree()
        self.stats_panel.set_progress(0)
        self.employee_vm.refresh(
            self.app_controller,
            self.sidebar.get_date(),
            self._on_consolidation_progress,
        )

    def _get_curator_display_names(self, curators):
        """Map curator keys to display names for UI."""
        mapping = {"boris": "Борис", "ivan": "Иван"}
        return [mapping.get(c, c) for c in curators]

    def run_consolidation(self):
        from core.view_models.consolidation_viewmodel import ConsolidationViewModel
        from core.ui.ui_dialogs import ask_employee_name

        missing_names = self.employee_vm.get_missing_names()
        if missing_names:
            msg = f"Не сдано отчетов: {len(missing_names)}. Продолжить?"
            if not messagebox.askyesno("Предупреждение", msg):
                return

        selected_curators = self.sidebar.get_selected_curators()

        # Confirmation dialog listing what will be built
        parts = ["основной отчет"]
        if selected_curators:
            names = self._get_curator_display_names(selected_curators)
            parts.append("дополнительные отчёты для: " + ", ".join(names))
        confirm_msg = "Собрать " + " и ".join(parts) + "?"
        if not messagebox.askyesno("Подтверждение сборки", confirm_msg):
            return

        self.sidebar.set_consolidate_state("disabled")
        self.consolidation_vm.run_consolidation(
            self.app_controller,
            self.sidebar.get_date(),
            selected_curators=selected_curators,
        )

    def run_consolidation_all_dates(self):
        selected_curators = self.sidebar.get_selected_curators()

        parts = ["основной отчет"]
        if selected_curators:
            names = self._get_curator_display_names(selected_curators)
            parts.append("дополнительные отчёты для: " + ", ".join(names))
        confirm_msg = "Собрать " + " и ".join(parts) + " (все даты)?"
        if not messagebox.askyesno("Подтверждение сборки", confirm_msg):
            return

        self.sidebar.set_consolidate_all_state("disabled")
        self.consolidation_vm.run_consolidation_all_dates(
            self.app_controller, selected_curators=selected_curators
        )

    def run_consolidation_month(self):
        start_date, end_date = self.sidebar.get_month_range()
        if start_date > end_date:
            messagebox.showerror(
                "Ошибка", "Дата начала должна быть раньше даты окончания"
            )
            return

        selected_curators = self.sidebar.get_selected_curators()

        parts = ["основной отчет"]
        if selected_curators:
            names = self._get_curator_display_names(selected_curators)
            parts.append("дополнительные отчёты для: " + ", ".join(names))
        confirm_msg = "Собрать " + " и ".join(parts) + "?"
        if not messagebox.askyesno("Подтверждение сборки", confirm_msg):
            return

        self.sidebar.set_consolidate_month_state("disabled")
        self.consolidation_vm.run_consolidation_month(
            self.app_controller, start_date, end_date,
            selected_curators=selected_curators,
        )

    def add_employee_dialog(self):
        from core.ui.ui_dialogs import ask_employee_name

        name = ask_employee_name()
        if name:
            self.employee_vm.add_employee(self.config_controller, name)
            self.refresh_status()

    def attach_file_dialog(self):
        from core.ui.ui_dialogs import show_attach_file_dialog

        def on_attach(name, paths, append):
            self.employee_vm.attach_files(self.config_controller, name, paths)
            self.refresh_status()

        show_attach_file_dialog(
            self.root, self.config_controller.get_employees(), on_attach
        )

    def open_master_folder(self):
        p = self.employee_vm.get_master_path(self.config_controller)
        if p and p.parent.exists():
            open_path(str(p.parent))

    def copy_missing_to_clipboard(self):
        missing = self.employee_vm.get_missing_names()
        if missing:
            date_str = self.sidebar.get_date().strftime("%d.%m")
            text = f"Должники за {date_str}:\n" + "\n".join([f"- {m}" for m in missing])
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            messagebox.showinfo("Успех", "Список должников скопирован в буфер обмена")

    def filter_tree(self):
        self.employee_vm.search_query = self.employee_table.get_search_query()
        self._sync_employee_ui()

    def open_employee_folder(self):
        name = self.employee_table.get_selected_employee()
        path = self.employee_vm.get_selected_employee_path(name)
        if path:
            open_path(str(Path(path).parent))

    def open_employee_file(self):
        name = self.employee_table.get_selected_employee()
        path = self.employee_vm.get_selected_employee_path(name)
        if path:
            open_path(path)

    def delete_employee(self):
        name = self.employee_table.get_selected_employee()
        if name and messagebox.askyesno("Удалить", f"Удалить сотрудника '{name}'?"):
            self.employee_vm.delete_employee(self.config_controller, name)
            self.refresh_status()

    def _on_consolidation_progress(self, progress: float):
        self.root.after(0, lambda: self.stats_panel.set_progress(progress))

    def _sync_employee_ui(self):
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
