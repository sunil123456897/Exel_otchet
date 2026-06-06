"""Consolidation commands (day / all dates / month).

The three methods share the same skeleton: validate, confirm, ask
the state machine for a slot, then hand off to the ViewModel. Kept
as a small module so the build-vs-filter distinction is obvious to
anyone reading the package.
"""
from __future__ import annotations

from tkinter import messagebox

from core.ui.operation_state import OperationType
from core.ui.gui_commands._base import CommandContext


class ConsolidationCommandsMixin:
    """Mixin providing the three consolidation entry points.

    Combines with :class:`GuiCommands` which supplies ``self.ctx``.
    """

    ctx: CommandContext

    def run_consolidation(self) -> None:
        missing_names = self.ctx.employee_vm.get_missing_names()
        if missing_names:
            msg = f"Не сдано отчетов: {len(missing_names)}. Продолжить?"
            if not messagebox.askyesno("Предупреждение", msg):
                return

        if not messagebox.askyesno(
            "Подтверждение сборки", "Собрать основной отчет?"
        ):
            return

        if not self.ctx.operation_state.begin(OperationType.CONSOLIDATION_DAY):
            return

        curator = self.ctx.sidebar.get_curator()
        self.ctx.consolidation_vm.run_consolidation(
            self.ctx.app_controller,
            self.ctx.sidebar.get_date(),
            curator=curator,
        )

    def run_consolidation_all_dates(self) -> None:
        if not messagebox.askyesno(
            "Подтверждение сборки", "Собрать основной отчет (все даты)?"
        ):
            return

        if not self.ctx.operation_state.begin(OperationType.CONSOLIDATION_ALL):
            return

        curator = self.ctx.sidebar.get_curator()
        self.ctx.consolidation_vm.run_consolidation_all_dates(
            self.ctx.app_controller,
            curator=curator,
        )

    def run_consolidation_month(self) -> None:
        start_date, end_date = self.ctx.sidebar.get_month_range()
        if start_date > end_date:
            messagebox.showerror(
                "Ошибка", "Дата начала должна быть раньше даты окончания"
            )
            return

        if not messagebox.askyesno(
            "Подтверждение сборки", "Собрать основной отчет?"
        ):
            return

        if not self.ctx.operation_state.begin(OperationType.CONSOLIDATION_MONTH):
            return

        curator = self.ctx.sidebar.get_curator()
        self.ctx.consolidation_vm.run_consolidation_month(
            self.ctx.app_controller,
            start_date,
            end_date,
            curator=curator,
        )
