import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from core.infra import open_path
from core.ui.dashboard_state import (
    RuntimeResult,
    collect_report_paths,
    collect_settings_lines,
    read_recent_log_errors,
    run_light_diagnostics,
    safe_open_existing_path,
)


class DashboardTabs:
    def __init__(self, notebook: ttk.Notebook, controller, config_controller) -> None:
        self.notebook = notebook
        self.controller = controller
        self.config_controller = config_controller
        self.app_root = Path(getattr(config_controller, "config_path", "APP/config.yaml")).parent
        self.repo_root = self.app_root.parent
        self._last_results: list[RuntimeResult] = []

        self.home_tab = ttk.Frame(notebook, padding=10, style="Main.TFrame")
        self.employees_tab = ttk.Frame(notebook, padding=10, style="Main.TFrame")
        self.reports_tab = ttk.Frame(notebook, padding=10, style="Main.TFrame")
        self.diagnostics_tab = ttk.Frame(notebook, padding=10, style="Main.TFrame")
        self.logs_tab = ttk.Frame(notebook, padding=10, style="Main.TFrame")
        self.settings_tab = ttk.Frame(notebook, padding=10, style="Main.TFrame")

        notebook.add(self.home_tab, text="Главная")
        notebook.add(self.employees_tab, text="Сотрудники")
        notebook.add(self.reports_tab, text="Отчеты")
        notebook.add(self.diagnostics_tab, text="Диагностика")
        notebook.add(self.logs_tab, text="Логи")
        notebook.add(self.settings_tab, text="Настройки")

        self._setup_home()
        self._setup_reports()
        self._setup_diagnostics()
        self._setup_logs()
        self._setup_settings()

    def _setup_home(self) -> None:
        summary_frame = ttk.LabelFrame(self.home_tab, text="Состояние", padding=8)
        summary_frame.pack(fill=tk.X, pady=(0, 8))
        self.state_label = ttk.Label(summary_frame, text="", justify=tk.LEFT)
        self.state_label.pack(fill=tk.X)

        last_frame = ttk.LabelFrame(self.home_tab, text="Последние результаты", padding=8)
        last_frame.pack(fill=tk.BOTH, expand=True)
        self.results_tree = ttk.Treeview(
            last_frame,
            columns=("type", "status", "time", "path", "message"),
            show="headings",
            height=8,
        )
        for column, text, width in (
            ("type", "Тип", 120),
            ("status", "Статус", 90),
            ("time", "Время", 120),
            ("path", "Путь", 260),
            ("message", "Сообщение", 360),
        ):
            self.results_tree.heading(column, text=text)
            self.results_tree.column(column, width=width, anchor=tk.W)
        self.results_tree.pack(fill=tk.BOTH, expand=True)
        self.results_tree.bind("<Double-1>", lambda _event: self._open_selected_result())

    def _setup_reports(self) -> None:
        action_frame = ttk.Frame(self.reports_tab, style="Main.TFrame")
        action_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(action_frame, text="Обновить", command=self.refresh).pack(side=tk.LEFT)
        ttk.Button(action_frame, text="Открыть", command=self._open_selected_report).pack(
            side=tk.LEFT, padx=(6, 0)
        )
        ttk.Button(
            action_frame,
            text="Открыть папку",
            command=self._open_selected_report_folder,
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(action_frame, text="Backup", command=self._open_backup_folder).pack(
            side=tk.LEFT, padx=(6, 0)
        )

        self.reports_tree = ttk.Treeview(
            self.reports_tab,
            columns=("name", "status", "mtime", "size", "path"),
            show="headings",
        )
        for column, text, width in (
            ("name", "Файл", 160),
            ("status", "Статус", 90),
            ("mtime", "Изменен", 130),
            ("size", "Размер", 80),
            ("path", "Путь", 520),
        ):
            self.reports_tree.heading(column, text=text)
            self.reports_tree.column(column, width=width, anchor=tk.W)
        self.reports_tree.pack(fill=tk.BOTH, expand=True)
        self.reports_tree.bind("<Double-1>", lambda _event: self._open_selected_report())

    def _setup_diagnostics(self) -> None:
        action_frame = ttk.Frame(self.diagnostics_tab, style="Main.TFrame")
        action_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(
            action_frame,
            text="Проверить систему",
            command=self.run_diagnostics,
            style="Action.TButton",
        ).pack(side=tk.LEFT)

        self.diagnostics_tree = ttk.Treeview(
            self.diagnostics_tab,
            columns=("check", "status", "detail", "path"),
            show="headings",
        )
        for column, text, width in (
            ("check", "Проверка", 170),
            ("status", "Статус", 90),
            ("detail", "Детали", 260),
            ("path", "Путь", 520),
        ):
            self.diagnostics_tree.heading(column, text=text)
            self.diagnostics_tree.column(column, width=width, anchor=tk.W)
        self.diagnostics_tree.pack(fill=tk.BOTH, expand=True)

    def _setup_logs(self) -> None:
        action_frame = ttk.Frame(self.logs_tab, style="Main.TFrame")
        action_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(
            action_frame,
            text="Открыть startup_log.txt",
            command=lambda: self._open_path(self.repo_root / "startup_log.txt"),
        ).pack(side=tk.LEFT)
        ttk.Button(
            action_frame,
            text="Открыть gui_error_log.txt",
            command=lambda: self._open_path(self.repo_root / "gui_error_log.txt"),
        ).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(
            action_frame,
            text="Открыть папку логов",
            command=lambda: self._open_path(self.repo_root),
        ).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(self.logs_tab, text="Последние ошибки:").pack(anchor=tk.W)
        self.log_errors = tk.Text(self.logs_tab, height=12, state="disabled", wrap=tk.WORD)
        self.log_errors.pack(fill=tk.BOTH, expand=True)

    def _setup_settings(self) -> None:
        action_frame = ttk.Frame(self.settings_tab, style="Main.TFrame")
        action_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(
            action_frame,
            text="Открыть config.yaml",
            command=lambda: self._open_path(Path(self.config_controller.config_path)),
        ).pack(side=tk.LEFT)

        self.settings_text = tk.Text(
            self.settings_tab,
            height=12,
            state="disabled",
            wrap=tk.WORD,
        )
        self.settings_text.pack(fill=tk.BOTH, expand=True)

    def refresh(self) -> None:
        self._refresh_reports()
        self._refresh_home()
        self._refresh_logs()
        self._refresh_settings()

    def run_diagnostics(self) -> None:
        for item in self.diagnostics_tree.get_children():
            self.diagnostics_tree.delete(item)
        for item in run_light_diagnostics(self.config_controller, self.app_root):
            self.diagnostics_tree.insert(
                "",
                tk.END,
                values=(
                    item.label,
                    self._status_text(item.status),
                    item.detail,
                    str(item.path) if item.path else "",
                ),
            )
        self._refresh_home()

    def record_result(
        self,
        label: str,
        ok: bool,
        message: str,
        path: Path | None = None,
        rows: int | None = None,
    ) -> None:
        self._last_results.insert(
            0,
            RuntimeResult(label, ok, message, path, rows, datetime.now()),
        )
        self._last_results = self._last_results[:10]
        self.refresh()

    def _refresh_reports(self) -> None:
        for item in self.reports_tree.get_children():
            self.reports_tree.delete(item)
        for item in collect_report_paths(self.config_controller, self.app_root):
            status = "найден" if item.exists else "не найден"
            self.reports_tree.insert(
                "",
                tk.END,
                values=(
                    item.label,
                    status,
                    item.mtime,
                    item.size,
                    str(item.path) if item.path else "",
                ),
            )

    def _refresh_home(self) -> None:
        diagnostics = run_light_diagnostics(self.config_controller, self.app_root)
        errors = sum(1 for item in diagnostics if item.status == "error")
        warnings = sum(1 for item in diagnostics if item.status == "warning")
        reports = collect_report_paths(self.config_controller, self.app_root)
        existing_reports = sum(1 for item in reports if item.exists)
        self.state_label.config(
            text=(
                f"Готовность: {'можно работать' if errors == 0 else 'есть ошибки'}\n"
                f"Диагностика: ошибок {errors}, предупреждений {warnings}\n"
                f"Найдено результатов: {existing_reports}/{len(reports)}"
            )
        )

        for item in self.results_tree.get_children():
            self.results_tree.delete(item)
        for result in self._last_results:
            time_text = result.created_at.strftime("%d.%m.%Y %H:%M") if result.created_at else "-"
            message = result.message
            if result.rows is not None:
                message = f"{message} | строк: {result.rows}"
            self.results_tree.insert(
                "",
                tk.END,
                values=(
                    result.label,
                    "успех" if result.ok else "ошибка",
                    time_text,
                    str(result.path) if result.path else "",
                    message,
                ),
            )

    def _refresh_logs(self) -> None:
        errors = read_recent_log_errors(
            [self.repo_root / "startup_log.txt", self.repo_root / "gui_error_log.txt"]
        )
        self.log_errors.configure(state="normal")
        self.log_errors.delete("1.0", tk.END)
        if errors:
            self.log_errors.insert(tk.END, "\n".join(errors))
        else:
            self.log_errors.insert(tk.END, "Ошибок в последних логах не найдено.")
        self.log_errors.configure(state="disabled")

    def _refresh_settings(self) -> None:
        self.settings_text.configure(state="normal")
        self.settings_text.delete("1.0", tk.END)
        self.settings_text.insert(
            tk.END,
            "\n".join(collect_settings_lines(self.config_controller)),
        )
        self.settings_text.configure(state="disabled")

    def _selected_report_path(self) -> Path | None:
        selected = self.reports_tree.selection()
        if not selected:
            return None
        values = self.reports_tree.item(selected[0])["values"]
        if len(values) < 5 or not values[4]:
            return None
        return Path(str(values[4]))

    def _selected_result_path(self) -> Path | None:
        selected = self.results_tree.selection()
        if not selected:
            return None
        values = self.results_tree.item(selected[0])["values"]
        if len(values) < 4 or not values[3]:
            return None
        return Path(str(values[3]))

    def _open_selected_report(self) -> None:
        self._open_path(self._selected_report_path())

    def _open_selected_report_folder(self) -> None:
        path = self._selected_report_path()
        if path and path.is_file():
            path = path.parent
        self._open_path(path)

    def _open_selected_result(self) -> None:
        self._open_path(self._selected_result_path())

    def _open_backup_folder(self) -> None:
        for item in collect_report_paths(self.config_controller, self.app_root):
            if item.label == "Backup":
                self._open_path(item.path)
                return
        self._show_missing("Backup-папка не настроена")

    def _open_path(self, path: Path | None) -> None:
        safe_open_existing_path(path, open_path, self._show_missing)

    def _show_missing(self, message: str) -> None:
        messagebox.showwarning("Путь не найден", message)

    @staticmethod
    def _status_text(status: str) -> str:
        if status == "ok":
            return "OK"
        if status == "warning":
            return "Внимание"
        return "Ошибка"
