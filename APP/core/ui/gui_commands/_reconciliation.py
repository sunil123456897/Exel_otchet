"""Reconciliation commands and their completion handlers.

Two operations here: the manual reconciliation (the user picks
already-built reports) and the automatic one (the controller
rebuilds the master reports itself before comparing them to the
РСЧ). Both share the source-file resolution flow with RSCH but
diverge in the file-picker UX.
"""
from __future__ import annotations

from pathlib import Path
from tkinter import filedialog
from typing import Any, Optional

from core.ui.operation_state import OperationType
from core.ui.gui_commands._base import CommandContext, finish
from core.ui.gui_commands._rsch import RschCommandsMixin


class ReconciliationCommandsMixin(RschCommandsMixin):  # type: ignore[misc]  # dual APP./core. identity → base seen as Any
    """Mixin providing the two reconciliation entry points.

    Inherits the RSCH source-resolution helpers because the auto
    reconciliation needs the same file-picker flow.
    """

    ctx: CommandContext

    def run_reconciliation_report(self) -> None:
        default_master_path = self.ctx.employee_vm.get_master_path(
            self.ctx.config_controller
        )
        filetypes = [("Excel files", "*.xlsx *.xlsm"), ("All files", "*.*")]
        master_dialog_kwargs: dict[str, Any] = {"filetypes": filetypes}
        if default_master_path:
            master_dialog_kwargs["initialdir"] = str(
                Path(default_master_path).parent
            )

        master_paths: dict[str, Any] = {}
        for label, title in (
            ("Общий", "Выберите общий мастер-отчет"),
            ("Борис", "Выберите отчет Бориса"),
            ("Иван", "Выберите отчет Ивана"),
        ):
            selected = filedialog.askopenfilename(
                title=title, **master_dialog_kwargs
            )
            if not selected:
                return
            master_paths[label] = Path(selected)
            master_dialog_kwargs["initialdir"] = str(Path(selected).parent)

        selected_date = self.ctx.sidebar.get_date()
        rsch_path = filedialog.askopenfilename(
            title="Выберите готовый РСЧ отчет",
            filetypes=filetypes,
            initialdir=self._suggest_rsch_output_dir([]),
        )
        if not rsch_path:
            return

        date_suffix = selected_date.strftime("%d.%m.%Y")
        output = filedialog.asksaveasfilename(
            title="Сохранить отчет расхождений",
            defaultextension=".xlsx",
            initialfile=f"Отчет_расхождений_{date_suffix}.xlsx",
            initialdir=str(Path(rsch_path).parent),
            filetypes=[("Excel files", "*.xlsx")],
        )
        if not output:
            return

        if not self.ctx.operation_state.begin(OperationType.RECONCILIATION):
            return
        self.ctx.app_controller.run_reconciliation_report(
            master_paths,
            Path(rsch_path),
            Path(output),
            selected_date,
            self._on_reconciliation_complete,
            cancel_event=self.ctx.operation_state.cancel_event,
        )

    def run_auto_reconciliation_day(self) -> None:
        source_paths = self._resolve_rsch_sources()
        if not source_paths:
            return

        selected_date = self.ctx.sidebar.get_date()
        date_suffix = selected_date.strftime("%d.%m.%Y")
        output = filedialog.asksaveasfilename(
            title="Сохранить автоматический отчет расхождений",
            defaultextension=".xlsx",
            initialfile=f"Отчет_расхождений_{date_suffix}.xlsx",
            initialdir=self._suggest_rsch_output_dir(source_paths),
            filetypes=[("Excel files", "*.xlsx")],
        )
        if not output:
            return

        self._save_rsch_preferences(source_paths, Path(output))
        if not self.ctx.operation_state.begin(OperationType.AUTO_RECONCILIATION):
            return
        self.ctx.app_controller.run_auto_reconciliation_day(
            source_paths,
            Path(output),
            selected_date,
            self._on_auto_reconciliation_complete,
            cancel_event=self.ctx.operation_state.cancel_event,
        )

    # --- completion handlers -------------------------------------------

    def _on_reconciliation_complete(
        self, ok: bool, msg: str, path: Optional[Path]
    ) -> None:
        def fin() -> None:
            finish(
                self.ctx,
                ok=ok,
                msg=msg,
                path=path,
                label="Сверка",
                ask_open_text=(
                    "Отчет расхождений собран. Открыть файл?" if ok else None
                ),
                record_result=self._record_dashboard_result,
            )
        self.ctx.post(fin)

    def _on_auto_reconciliation_complete(
        self, ok: bool, msg: str, path: Optional[Path]
    ) -> None:
        def fin() -> None:
            finish(
                self.ctx,
                ok=ok,
                msg=msg,
                path=path,
                label="Автосверка",
                ask_open_text=(
                    "Автоматический отчет расхождений собран. Открыть файл?"
                    if ok
                    else None
                ),
                record_result=self._record_dashboard_result,
            )
        self.ctx.post(fin)
