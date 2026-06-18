"""RSCH (day / month) commands and their persistence helpers.

The RSCH build flow is the most stateful of the three: the user
selects source workbooks (optionally remembered from a previous run),
picks an output path, and the build runs in a background thread. All
the persistence helpers (saved sources, suggested dirs, safe file
names) live here too because nothing else needs them.
"""
from __future__ import annotations

from pathlib import Path
from tkinter import filedialog, messagebox
from typing import List, Optional

from core.ui.operation_state import OperationType
from core.ui.gui_commands._base import CommandContext, finish


class RschCommandsMixin:
    """Mixin providing RSCH commands and the related completion handler."""

    ctx: CommandContext

    # --- command entry points ------------------------------------------

    def run_rsch_report(self) -> None:
        source_paths = self._resolve_rsch_sources()
        if not source_paths:
            return

        selected_date = self.ctx.sidebar.get_date()
        date_suffix = selected_date.strftime("%d.%m.%Y")
        default_name = f"РСЧ_отчет_{date_suffix}.xlsx"
        output = filedialog.asksaveasfilename(
            title="Сохранить ШО отчет",
            defaultextension=".xlsx",
            initialfile=default_name,
            initialdir=self._suggest_rsch_output_dir(source_paths),
            filetypes=[("Excel files", "*.xlsx")],
        )
        if not output:
            return

        self._save_rsch_preferences(source_paths, Path(output))

        if not self.ctx.operation_state.begin(OperationType.RSCH_DAY):
            return
        self.ctx.app_controller.run_rsch_report(
            source_paths,
            Path(output),
            selected_date,
            self._on_rsch_complete,
            cancel_event=self.ctx.operation_state.cancel_event,
        )

    def run_rsch_report_month(self) -> None:
        start_date, end_date = self.ctx.sidebar.get_month_range()
        if start_date > end_date:
            messagebox.showerror(
                "Ошибка", "Дата начала должна быть раньше даты окончания"
            )
            return

        source_paths = self._resolve_rsch_sources()
        if not source_paths:
            return

        start_suffix = start_date.strftime("%d.%m.%Y")
        end_suffix = end_date.strftime("%d.%m.%Y")
        default_name = f"РСЧ_отчет_{start_suffix}-{end_suffix}.xlsx"
        output = filedialog.asksaveasfilename(
            title="Сохранить ШО отчет за период",
            defaultextension=".xlsx",
            initialfile=default_name,
            initialdir=self._suggest_rsch_output_dir(source_paths),
            filetypes=[("Excel files", "*.xlsx")],
        )
        if not output:
            return

        self._save_rsch_preferences(source_paths, Path(output))
        if not self.ctx.operation_state.begin(OperationType.RSCH_MONTH):
            return
        self.ctx.app_controller.run_rsch_report_period(
            source_paths,
            Path(output),
            start_date,
            end_date,
            self._on_rsch_complete,
            cancel_event=self.ctx.operation_state.cancel_event,
        )

    def _on_rsch_complete(self, ok: bool, msg: str, path: Optional[Path]) -> None:
        def fin() -> None:
            finish(
                self.ctx,
                ok=ok,
                msg=msg,
                path=path,
                label="РСЧ",
                ask_open_text=(
                    "РСЧ отчет собран. Открыть файл?" if ok else None
                ),
                record_result=self._record_dashboard_result,
            )
        self.ctx.post(fin)

    # --- source-file resolution (saved vs. fresh selection) ------------

    def _resolve_rsch_sources(self) -> List[Path]:
        """Apply the saved-or-pick dialog flow, returning the chosen paths.

        Returns an empty list when the user cancelled any of the
        dialogs; the caller treats that as 'abort the command'.
        """
        source_paths: List[Path] = []
        saved_sources = self._get_saved_rsch_sources()
        if saved_sources:
            existing_saved = [p for p in saved_sources if p.exists()]
            use_saved = messagebox.askyesnocancel(
                "РСЧ файлы",
                "Использовать сохраненный набор файлов РСЧ?",
            )
            if use_saved is None:
                return []
            if use_saved:
                if existing_saved:
                    source_paths = existing_saved
                else:
                    messagebox.showwarning(
                        "РСЧ файлы",
                        "Сохраненные пути не найдены. Выберите файлы заново.",
                    )

        if not source_paths:
            source_paths = self._select_rsch_sources(saved_sources)
        return source_paths

    def _select_rsch_sources(self, saved_sources: List[Path]) -> List[Path]:
        from core.ui.ui_dialogs import show_multi_file_select_dialog

        # Pre-populate the dialog with any paths that still exist on
        # disk so the user can re-open a session without losing work.
        seed = [str(p) for p in saved_sources if p.exists()]
        selected = show_multi_file_select_dialog(
            self.ctx.root,
            initial_paths=seed,
            title="Выберите ШР файлы РСЧ",
            filetypes=[
                ("Excel files", "*.xlsx *.xlsm *.xlsb"),
                ("All files", "*.*"),
            ],
        )
        return [Path(p) for p in selected]

    def _merge_unique_paths(
        self, current: List[Path], new_items: List[Path]
    ) -> List[Path]:
        merged = list(current)
        seen = {str(p) for p in current}
        for item in new_items:
            key = str(item)
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

    # --- config persistence --------------------------------------------

    def _get_rsch_config(self) -> dict:
        cfg = getattr(self.ctx.config_controller, "config", None)
        if not isinstance(cfg, dict):
            cfg = {}
            try:
                self.ctx.config_controller.config = cfg
            except Exception:
                return {}

        rsch_cfg = cfg.get("rsch")
        if not isinstance(rsch_cfg, dict):
            rsch_cfg = {}
            cfg["rsch"] = rsch_cfg
        return rsch_cfg

    def _get_saved_rsch_sources(self) -> List[Path]:
        rsch_cfg = self._get_rsch_config()
        raw_sources = rsch_cfg.get("recent_sources", [])
        if isinstance(raw_sources, str):
            raw_sources = [raw_sources]

        normalized: List[Path] = []
        seen: set = set()
        for raw in raw_sources:
            if not raw:
                continue
            path = Path(str(raw))
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(self._resolve_config_path(path))
        return normalized

    def _resolve_config_path(self, path: Path) -> Path:
        if path.is_absolute():
            return path
        resolve_path = getattr(self.ctx.config_controller, "resolve_path", None)
        if callable(resolve_path):
            return Path(resolve_path(str(path)))
        return path

    def _save_rsch_preferences(
        self, source_paths: List[Path], output_path: Path
    ) -> None:
        rsch_cfg = self._get_rsch_config()
        rsch_cfg["recent_sources"] = [str(p) for p in source_paths]
        rsch_cfg["last_output_dir"] = str(output_path.parent)
        rsch_cfg["mode"] = "combined"
        save_config = getattr(self.ctx.config_controller, "save_config", None)
        if callable(save_config):
            save_config()

    def _apply_saved_rsch_mode(self) -> None:
        rsch_cfg = self._get_rsch_config()
        if rsch_cfg.get("mode") != "combined":
            rsch_cfg["mode"] = "combined"

    # --- output naming -------------------------------------------------

    def _suggest_rsch_output_dir(self, source_paths: List[Path]) -> str:
        rsch_cfg = self._get_rsch_config()
        last_output_dir = rsch_cfg.get("last_output_dir")
        if last_output_dir:
            parent = self._resolve_config_path(Path(str(last_output_dir)))
            if parent.exists():
                return str(parent)
        if source_paths:
            first_parent = source_paths[0].parent
            if first_parent.exists():
                return str(first_parent)
        return ""
