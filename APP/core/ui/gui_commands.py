import logging
import re
from collections import Counter
from tkinter import filedialog, messagebox
from pathlib import Path
from typing import Optional, List

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
        self._apply_saved_rsch_mode()

    def refresh_status(self):
        self.sidebar.set_refresh_state("disabled")
        self.employee_table.clear_tree()
        self.stats_panel.set_progress(0)

        def on_refresh_error(message: str) -> None:
            self.root.after(0, lambda: messagebox.showerror("Ошибка", message))

        self.employee_vm.refresh(
            self.app_controller,
            self.sidebar.get_date(),
            self._on_consolidation_progress,
            on_error=on_refresh_error,
        )

    def run_consolidation(self):

        missing_names = self.employee_vm.get_missing_names()
        if missing_names:
            msg = f"Не сдано отчетов: {len(missing_names)}. Продолжить?"
            if not messagebox.askyesno("Предупреждение", msg):
                return

        if not messagebox.askyesno("Подтверждение сборки", "Собрать основной отчет?"):
            return

        curator = self.sidebar.get_curator()
        self.sidebar.set_consolidate_state("disabled")
        self.consolidation_vm.run_consolidation(
            self.app_controller,
            self.sidebar.get_date(),
            curator=curator,
        )

    def run_consolidation_all_dates(self):
        if not messagebox.askyesno(
            "Подтверждение сборки", "Собрать основной отчет (все даты)?"
        ):
            return

        curator = self.sidebar.get_curator()
        self.sidebar.set_consolidate_all_state("disabled")
        self.consolidation_vm.run_consolidation_all_dates(
            self.app_controller,
            curator=curator,
        )

    def run_consolidation_month(self):
        start_date, end_date = self.sidebar.get_month_range()
        if start_date > end_date:
            messagebox.showerror(
                "Ошибка", "Дата начала должна быть раньше даты окончания"
            )
            return

        if not messagebox.askyesno("Подтверждение сборки", "Собрать основной отчет?"):
            return

        curator = self.sidebar.get_curator()
        self.sidebar.set_consolidate_month_state("disabled")
        self.consolidation_vm.run_consolidation_month(
            self.app_controller,
            start_date,
            end_date,
            curator=curator,
        )

    def run_rsch_report(self):
        mode = self.sidebar.get_rsch_mode()
        source_paths: List[Path] = []
        saved_sources = self._get_saved_rsch_sources()
        if saved_sources:
            existing_saved = [p for p in saved_sources if p.exists()]
            use_saved = messagebox.askyesnocancel(
                "РСЧ файлы",
                "Использовать сохраненный набор файлов РСЧ?",
            )
            if use_saved is None:
                return
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
            if not source_paths:
                return

        selected_date = self.sidebar.get_date()
        date_suffix = selected_date.strftime("%d.%m.%Y")
        default_name = f"РСЧ_отчет_{date_suffix}.xlsx"
        output_initial_dir = self._suggest_rsch_output_dir(source_paths)
        if mode == "per_file":
            output_dir = filedialog.askdirectory(
                title="Выберите папку для сохранения ШО отчетов",
                initialdir=output_initial_dir,
                mustexist=True,
            )
            if not output_dir:
                return

            output_dir_path = Path(output_dir)
            duplicate_stems = self._get_duplicate_source_stems(source_paths)
            output_paths = [
                output_dir_path
                / self._build_per_file_output_name(
                    src_path,
                    selected_date,
                    idx,
                    duplicate_stems,
                )
                for idx, src_path in enumerate(source_paths, start=1)
            ]

            self._save_rsch_preferences(source_paths, output_paths[0], mode)
            self.sidebar.set_rsch_state("disabled")
            self.app_controller.run_rsch_report_batch(
                source_paths,
                output_paths,
                selected_date,
                self._on_rsch_complete_batch,
            )
            return

        output = filedialog.asksaveasfilename(
            title="Сохранить ШО отчет",
            defaultextension=".xlsx",
            initialfile=default_name,
            initialdir=output_initial_dir,
            filetypes=[("Excel files", "*.xlsx")],
        )
        if not output:
            return

        self._save_rsch_preferences(source_paths, Path(output), mode)

        self.sidebar.set_rsch_state("disabled")
        self.app_controller.run_rsch_report(
            source_paths,
            Path(output),
            selected_date,
            self._on_rsch_complete,
        )

    def run_rsch_report_month(self):
        start_date, end_date = self.sidebar.get_month_range()
        if start_date > end_date:
            messagebox.showerror(
                "Ошибка", "Дата начала должна быть раньше даты окончания"
            )
            return

        source_paths: List[Path] = []
        saved_sources = self._get_saved_rsch_sources()
        if saved_sources:
            existing_saved = [p for p in saved_sources if p.exists()]
            use_saved = messagebox.askyesnocancel(
                "РСЧ файлы",
                "Использовать сохраненный набор файлов РСЧ?",
            )
            if use_saved is None:
                return
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
            if not source_paths:
                return

        start_suffix = start_date.strftime("%d.%m.%Y")
        end_suffix = end_date.strftime("%d.%m.%Y")
        mode = self.sidebar.get_rsch_mode()
        if mode == "per_file":
            output_dir = filedialog.askdirectory(
                title="Выберите папку для сохранения ШО отчетов за период",
                initialdir=self._suggest_rsch_output_dir(source_paths),
                mustexist=True,
            )
            if not output_dir:
                return

            output_dir_path = Path(output_dir)
            self._save_rsch_preferences(
                source_paths,
                output_dir_path / f"РСЧ_отчет_{start_suffix}-{end_suffix}.xlsx",
                mode,
            )
            self.sidebar.set_rsch_state("disabled")
            self.app_controller.run_rsch_report_period_batch(
                source_paths,
                output_dir_path,
                start_date,
                end_date,
                self._on_rsch_complete_batch,
            )
            return

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

        self._save_rsch_preferences(source_paths, Path(output), "combined")
        self.sidebar.set_rsch_state("disabled")
        self.app_controller.run_rsch_report_period(
            source_paths,
            Path(output),
            start_date,
            end_date,
            self._on_rsch_complete,
        )

    def _get_rsch_config(self) -> dict:
        cfg = getattr(self.config_controller, "config", None)
        if not isinstance(cfg, dict):
            cfg = {}
            try:
                self.config_controller.config = cfg
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
        seen = set()
        for raw in raw_sources:
            if not raw:
                continue
            path = Path(str(raw))
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(path)
        return normalized

    def _select_rsch_sources(self, saved_sources: List[Path]) -> List[Path]:
        selected_paths: List[Path] = []
        while True:
            initial_dir = self._suggest_rsch_source_dir(saved_sources + selected_paths)
            selected = filedialog.askopenfilenames(
                title="Выберите ШР файлы РСЧ",
                filetypes=[
                    ("Excel files", "*.xlsx *.xlsm *.xlsb"),
                    ("All files", "*.*"),
                ],
                initialdir=initial_dir,
            )

            if selected:
                selected_paths = self._merge_unique_paths(
                    selected_paths,
                    [Path(p) for p in selected],
                )

            if not selected_paths:
                if not selected:
                    return []
                continue

            more = messagebox.askyesno(
                "РСЧ файлы",
                f"Сейчас выбрано {len(selected_paths)} файлов. Добавить еще из другой папки?",
            )
            if not more:
                return selected_paths

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

    def _build_per_file_output_name(
        self,
        source_path: Path,
        selected_date,
        index: int,
        duplicate_stems: Optional[set[str]] = None,
    ) -> str:
        date_suffix = selected_date.strftime("%d.%m.%Y")
        stem = source_path.stem.strip() or f"file_{index}"
        safe_stem = re.sub(r"[\\/:*?\"<>|]", "_", stem)
        if duplicate_stems and safe_stem in duplicate_stems:
            parent_name = source_path.parent.name.strip() or f"folder_{index}"
            safe_parent = re.sub(r"[\\/:*?\"<>|]", "_", parent_name)
            safe_stem = f"{safe_parent}_{safe_stem}_{index}"
        return f"РСЧ_отчет_{date_suffix}_{safe_stem}.xlsx"

    def _get_duplicate_source_stems(self, source_paths: List[Path]) -> set[str]:
        stem_counts = Counter(
            re.sub(r"[\\/:*?\"<>|]", "_", path.stem.strip() or "")
            for path in source_paths
        )
        return {
            stem
            for stem, count in stem_counts.items()
            if stem and count > 1
        }

    def _suggest_rsch_source_dir(self, saved_sources: List[Path]) -> str:
        for path in saved_sources:
            parent = path.parent
            if parent.exists():
                return str(parent)
        rsch_cfg = self._get_rsch_config()
        last_output_dir = rsch_cfg.get("last_output_dir")
        if last_output_dir:
            parent = Path(str(last_output_dir))
            if parent.exists():
                return str(parent)
        return ""

    def _suggest_rsch_output_dir(self, source_paths: List[Path]) -> str:
        rsch_cfg = self._get_rsch_config()
        last_output_dir = rsch_cfg.get("last_output_dir")
        if last_output_dir:
            parent = Path(str(last_output_dir))
            if parent.exists():
                return str(parent)
        if source_paths:
            first_parent = source_paths[0].parent
            if first_parent.exists():
                return str(first_parent)
        return ""

    def _save_rsch_preferences(
        self, source_paths: List[Path], output_path: Path, mode: str
    ) -> None:
        rsch_cfg = self._get_rsch_config()
        rsch_cfg["recent_sources"] = [str(p) for p in source_paths]
        rsch_cfg["last_output_dir"] = str(output_path.parent)
        rsch_cfg["mode"] = mode
        save_config = getattr(self.config_controller, "save_config", None)
        if callable(save_config):
            save_config()

    def _apply_saved_rsch_mode(self) -> None:
        rsch_cfg = self._get_rsch_config()
        mode = rsch_cfg.get("mode", "combined")
        self.sidebar.set_rsch_mode(mode)

    def add_employee_dialog(self):
        from core.ui.ui_dialogs import ask_employee_name

        name = ask_employee_name()
        if name:
            self.employee_vm.add_employee(self.config_controller, name)
            self.refresh_status()

    def attach_file_dialog(self):
        from core.ui.ui_dialogs import show_attach_file_dialog

        def on_attach(name, paths, append):
            self.employee_vm.attach_files(
                self.config_controller, name, paths, append=append
            )
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
        paths = self.employee_vm.get_selected_employee_paths(name)
        if not paths:
            return

        unique_parents = []
        seen = set()
        for raw_path in paths:
            parent = str(Path(raw_path).parent)
            if parent in seen:
                continue
            seen.add(parent)
            unique_parents.append(parent)

        for parent in unique_parents:
            open_path(parent)

    def open_employee_file(self):
        name = self.employee_table.get_selected_employee()
        paths = self.employee_vm.get_selected_employee_paths(name)
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

    def _on_rsch_complete(self, ok: bool, msg: str, path: Optional[Path]):
        def fin():
            self.sidebar.set_rsch_state("normal")
            if ok:
                logging.info(f"Успешно: {msg}")
                if path and messagebox.askyesno(
                    "Успех", "РСЧ отчет собран. Открыть файл?"
                ):
                    open_path(str(path))
            else:
                logging.error(f"Ошибка: {msg}")
                messagebox.showerror("Ошибка", msg)

        self.root.after(0, fin)

    def _on_rsch_complete_batch(
        self,
        ok: bool,
        msg: str,
        output_dir: Optional[Path],
    ):
        def fin():
            self.sidebar.set_rsch_state("normal")
            if ok:
                logging.info(f"Успешно: {msg}")
                if output_dir and messagebox.askyesno(
                    "Успех", "РСЧ отчеты собраны. Открыть папку?"
                ):
                    open_path(str(output_dir))
            else:
                logging.error(f"Ошибка: {msg}")
                messagebox.showerror("Ошибка", msg)

        self.root.after(0, fin)
