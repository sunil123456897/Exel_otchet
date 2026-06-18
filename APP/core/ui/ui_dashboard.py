import logging
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, TypeVar

from core.infra import open_path
from core.ui.dashboard_state import (
    RuntimeResult,
    build_diagnostic_summary,
    collect_report_paths,
    load_runtime_results,
    read_recent_log_errors,
    read_recent_logs,
    run_light_diagnostics,
    safe_open_existing_path,
    save_runtime_results,
    status_text,
)
from core.ui.theme import ThemeManager

_T = TypeVar("_T")


def _c(key, fallback):
    """Safe theme-color lookup with fallback for keys POLISH-1 may add."""
    return ThemeManager.COLORS.get(key, fallback)


class DashboardTabs:
    def __init__(self, notebook: ttk.Notebook, controller, config_controller) -> None:
        self.notebook = notebook
        self.controller = controller
        self.config_controller = config_controller
        self.app_root = Path(getattr(config_controller, "config_path", "APP/config.yaml")).parent
        self.repo_root = self.app_root.parent
        self.runtime_state_path = self.app_root / "runtime_state.json"
        self._last_results: list[RuntimeResult] = load_runtime_results(
            self.runtime_state_path
        )

        self.home_tab = ttk.Frame(notebook, padding=10, style="Main.TFrame")
        self.employees_tab = ttk.Frame(notebook, padding=10, style="Main.TFrame")
        self.reports_tab = ttk.Frame(notebook, padding=10, style="Main.TFrame")
        self.diagnostics_tab = ttk.Frame(notebook, padding=10, style="Main.TFrame")
        self.logs_tab = ttk.Frame(notebook, padding=10, style="Main.TFrame")
        self.settings_tab = ttk.Frame(notebook, padding=10, style="Main.TFrame")
        self.aliases_tab = ttk.Frame(notebook, padding=10, style="Main.TFrame")

        notebook.add(self.employees_tab, text="Сотрудники")
        notebook.add(self.home_tab, text="Панель")
        notebook.add(self.reports_tab, text="Отчеты")
        notebook.add(self.diagnostics_tab, text="Диагностика")
        notebook.add(self.logs_tab, text="Логи")
        notebook.add(self.aliases_tab, text="🔗 Алиасы сверки")
        notebook.add(self.settings_tab, text="Настройки")
        notebook.select(self.employees_tab)

        self._setup_home()
        self._setup_reports()
        self._setup_diagnostics()
        self._setup_logs()
        self._setup_settings()
        self._setup_aliases()

    def _setup_home(self) -> None:
        summary_frame = ttk.LabelFrame(self.home_tab, text="Состояние", padding=8)
        summary_frame.pack(fill=tk.X, pady=(0, 8))
        self.state_label = ttk.Label(summary_frame, text="", justify=tk.LEFT, wraplength=600)
        self.state_label.pack(fill=tk.X)

        quick_frame = ttk.LabelFrame(self.home_tab, text="Быстрые действия", padding=8)
        quick_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(
            quick_frame,
            text="Открыть последний Master",
            command=lambda: self._open_report_by_label("Master_Report.xlsx"),
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            quick_frame,
            text="Открыть последнюю сверку",
            command=lambda: self._open_report_by_label("Последняя сверка"),
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            quick_frame,
            text="Открыть backup",
            command=self._open_backup_folder,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            quick_frame,
            text="Открыть логи",
            command=lambda: self._open_path(self.repo_root),
        ).pack(side=tk.LEFT)

        last_frame = ttk.LabelFrame(self.home_tab, text="Последние результаты", padding=8)
        last_frame.pack(fill=tk.BOTH, expand=True)
        self.results_tree = ttk.Treeview(
            last_frame,
            columns=("type", "status", "time", "path", "message"),
            show="headings",
        )
        for column, text, width in (
            ("type", "Тип", 120),
            ("status", "Статус", 90),
            ("time", "Время", 140),
            ("path", "Путь", 260),
            ("message", "Сообщение", 360),
        ):
            self.results_tree.heading(column, text=text)
            self.results_tree.column(column, width=width, anchor=tk.W, stretch=(column == "message"))
        # Empty-state placeholder: when no results have been recorded
        # yet, show a muted hint instead of a blank tree.
        self.results_tree.tag_configure(
            "empty", foreground=_c("text_muted", _c("text", "#6c757d"))
        )
        self.results_tree.pack(fill=tk.BOTH, expand=True)
        self.results_tree.bind("<Double-1>", lambda _event: self._open_selected_result())
        # Initial empty-state hint so the tree isn't a blank grid on
        # first launch — replaced by real rows once ``_refresh_home``
        # completes (or re-inserted if there are no results yet).
        self.results_tree.insert(
            "",
            tk.END,
            values=("Нет данных", "", "", "", "Запустите сборку отчета"),
            tags=("empty",),
        )

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
            self.reports_tree.column(column, width=width, anchor=tk.W, stretch=(column == "path"))
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
        ttk.Button(
            action_frame,
            text="Скопировать диагностику",
            command=self.copy_diagnostics,
        ).pack(side=tk.LEFT, padx=(6, 0))

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
            self.diagnostics_tree.column(column, width=width, anchor=tk.W, stretch=(column in ("detail", "path")))
        self.diagnostics_tree.pack(fill=tk.BOTH, expand=True)

    def _setup_logs(self) -> None:
        action_frame = ttk.Frame(self.logs_tab, style="Main.TFrame")
        action_frame.pack(fill=tk.X, pady=(0, 8))
        
        ttk.Button(
            action_frame,
            text="Обновить",
            command=self._refresh_logs,
        ).pack(side=tk.LEFT)
        
        ttk.Button(
            action_frame,
            text="Открыть лог работы (Python)",
            command=lambda: self._open_path(self.app_root / "startup_log.txt"),
        ).pack(side=tk.LEFT, padx=(6, 0))
        
        ttk.Button(
            action_frame,
            text="Открыть лог запуска (Батник)",
            command=lambda: self._open_path(self.repo_root / "startup_log.txt"),
        ).pack(side=tk.LEFT, padx=(6, 0))
        
        ttk.Button(
            action_frame,
            text="Открыть gui_error_log.txt",
            command=lambda: self._open_path(self.repo_root / "gui_error_log.txt"),
        ).pack(side=tk.LEFT, padx=(6, 0))
        
        ttk.Button(
            action_frame,
            text="Открыть папку логов",
            command=lambda: self._open_path(self.repo_root / "logs"),
        ).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(self.logs_tab, text="Последние события лога:").pack(anchor=tk.W)
        
        self.log_errors = tk.Text(
            self.logs_tab,
            state="disabled",
            wrap=tk.WORD,
        )
        
        scroll_y = ttk.Scrollbar(self.logs_tab, orient=tk.VERTICAL, command=self.log_errors.yview)
        scroll_x = ttk.Scrollbar(self.logs_tab, orient=tk.HORIZONTAL, command=self.log_errors.xview)
        
        self.log_errors.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.log_errors.pack(fill=tk.BOTH, expand=True)
        ThemeManager.register(self.log_errors, bg_key="bg_panel", fg_key="text")

    def _setup_settings(self) -> None:
        self.settings_mode = "visual"  # "visual" или "yaml"
        
        # Переменные для формы настроек
        self.master_file_var = tk.StringVar()
        self.archive_dir_var = tk.StringVar()
        self.drive_letters_var = tk.StringVar()
        self.excel_keep_var = tk.IntVar(value=10)
        
        # Общий action_frame
        action_frame = ttk.Frame(self.settings_tab, style="Main.TFrame")
        action_frame.pack(fill=tk.X, pady=(0, 8))
        
        self.save_btn = ttk.Button(
            action_frame,
            text="Сохранить",
            command=self._save_settings,
        )
        self.save_btn.pack(side=tk.LEFT)
        
        self.reset_btn = ttk.Button(
            action_frame,
            text="Сбросить",
            command=self._refresh_settings,
        )
        self.reset_btn.pack(side=tk.LEFT, padx=(6, 0))
        
        self.mode_btn = ttk.Button(
            action_frame,
            text="Режим YAML-кода",
            command=self._toggle_settings_mode,
        )
        self.mode_btn.pack(side=tk.LEFT, padx=(6, 0))
        
        self.external_btn = ttk.Button(
            action_frame,
            text="Открыть в Блокноте",
            command=lambda: self._open_path(Path(self.config_controller.config_path)),
        )
        self.external_btn.pack(side=tk.LEFT, padx=(6, 0))

        # Контейнер для двух режимов
        self.settings_container = ttk.Frame(self.settings_tab, style="Main.TFrame")
        self.settings_container.pack(fill=tk.BOTH, expand=True)

        # 1. Фрейм визуального режима
        self.settings_visual_frame = ttk.Frame(self.settings_container, style="Main.TFrame")
        
        # Поле Master-отчета
        master_frame = ttk.LabelFrame(self.settings_visual_frame, text="Основной сводный отчет (Master_Report.xlsx)", padding=8)
        master_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Entry(master_frame, textvariable=self.master_file_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Button(master_frame, text="Обзор...", command=self._browse_master_file).pack(side=tk.RIGHT)
        
        # Поле папки бэкапов
        backup_frame = ttk.LabelFrame(self.settings_visual_frame, text="Папка для резервных копий (archive_dir)", padding=8)
        backup_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Entry(backup_frame, textvariable=self.archive_dir_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Button(backup_frame, text="Обзор...", command=self._browse_archive_dir).pack(side=tk.RIGHT)
        
        # Список папок-источников (кураторов)
        sources_frame = ttk.LabelFrame(self.settings_visual_frame, text="Папки с отчетами кураторов (source_roots)", padding=8)
        sources_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        
        list_container = ttk.Frame(sources_frame)
        list_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 8))
        
        self.sources_listbox = tk.Listbox(list_container)
        ThemeManager.register(self.sources_listbox, bg_key="bg_panel", fg_key="text")
        
        scroll_y_lb = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.sources_listbox.yview)
        self.sources_listbox.configure(yscrollcommand=scroll_y_lb.set)
        
        self.sources_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y_lb.pack(side=tk.RIGHT, fill=tk.Y)
        
        btn_container = ttk.Frame(sources_frame)
        btn_container.pack(side=tk.RIGHT, fill=tk.Y)
        ttk.Button(btn_container, text="Добавить...", command=self._add_source_root).pack(fill=tk.X, pady=(0, 4))
        ttk.Button(btn_container, text="Удалить", command=self._remove_source_root).pack(fill=tk.X)
        
        # Дополнительные настройки (сетевые диски и число бэкапов)
        misc_frame = ttk.LabelFrame(self.settings_visual_frame, text="Дополнительно", padding=8)
        misc_frame.pack(fill=tk.X)
        misc_frame.grid_columnconfigure(1, weight=1)
        
        # Сетевые диски
        ttk.Label(misc_frame, text="Сетевые диски (буквы через запятую):").grid(row=0, column=0, sticky=tk.W, pady=4, padx=(0, 8))
        ttk.Entry(misc_frame, textvariable=self.drive_letters_var).grid(row=0, column=1, sticky="ew", pady=4)
        
        # Хранение бэкапов
        ttk.Label(misc_frame, text="Количество хранимых бэкапов Excel:").grid(row=1, column=0, sticky=tk.W, pady=4, padx=(0, 8))
        ttk.Entry(misc_frame, textvariable=self.excel_keep_var).grid(row=1, column=1, sticky="ew", pady=4)

        # 2. Фрейм YAML-режима
        self.settings_yaml_frame = ttk.Frame(self.settings_container, style="Main.TFrame")
        
        self.settings_text = tk.Text(
            self.settings_yaml_frame,
            undo=True,
            wrap=tk.NONE,
        )
        scroll_y = ttk.Scrollbar(self.settings_yaml_frame, orient=tk.VERTICAL, command=self.settings_text.yview)
        scroll_x = ttk.Scrollbar(self.settings_yaml_frame, orient=tk.HORIZONTAL, command=self.settings_text.xview)
        self.settings_text.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.settings_text.pack(fill=tk.BOTH, expand=True)
        ThemeManager.register(self.settings_text, bg_key="bg_panel", fg_key="text")
        
        self.settings_visual_frame.pack(fill=tk.BOTH, expand=True)

    def _setup_aliases(self) -> None:
        from core.ui.ui_aliases import AliasesTab
        app_ctl = getattr(self.controller, "app_controller", self.controller)
        self._aliases_tab = AliasesTab(self.aliases_tab, app_ctl)

    def refresh(self) -> None:
        self._refresh_reports()
        self._refresh_home()
        self._refresh_logs()
        self._refresh_settings()

    def refresh_theme(self) -> None:
        """Re-apply theme-dependent tag colours after a palette switch."""
        self.results_tree.tag_configure(
            "empty", foreground=_c("text_muted", _c("text", "#6c757d"))
        )

    def run_diagnostics(self) -> None:
        for item in self.diagnostics_tree.get_children():
            self.diagnostics_tree.delete(item)
        for item in run_light_diagnostics(self.config_controller, self.app_root):
            self.diagnostics_tree.insert(
                "",
                tk.END,
                values=(
                    item.label,
                    status_text(item.status),
                    item.detail,
                    str(item.path) if item.path else "",
                ),
            )
        self._refresh_home()

    def copy_diagnostics(self) -> None:
        diagnostics = run_light_diagnostics(
            self.config_controller,
            self.app_root,
            include_network=False,
        )
        log_errors = self._recent_log_errors()
        summary = build_diagnostic_summary(
            diagnostics,
            self._last_results,
            log_errors,
        )
        self.notebook.clipboard_clear()
        self.notebook.clipboard_append(summary)
        messagebox.showinfo("Диагностика", "Диагностика скопирована в буфер обмена")

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
        save_runtime_results(self.runtime_state_path, self._last_results)
        self.refresh()

    def _run_in_background(
        self, work: Callable[[], _T], on_done: Callable[[_T], None]
    ) -> None:
        """Run ``work`` on a daemon thread, then call ``on_done`` on the
        GUI thread via ``root.after(0, ...)``.

        Used to keep ``path.exists()`` / network-drive probes off the
        Tk event loop so consolidations do not freeze the UI.
        """

        def runner() -> None:
            try:
                result = work()
            except Exception:
                logging.exception("Background dashboard task failed")
                result = None

            def safe_done() -> None:
                try:
                    on_done(result)
                except tk.TclError:
                    pass

            try:
                self.notebook.after(0, safe_done)
            except tk.TclError:
                pass

        threading.Thread(target=runner, daemon=True).start()

    def _refresh_reports(self) -> None:
        for item in self.reports_tree.get_children():
            self.reports_tree.delete(item)
        self.reports_tree.insert("", tk.END, values=("проверка...", "", "", "", ""))

        def work():
            return collect_report_paths(self.config_controller, self.app_root)

        def done(payload):
            if payload is None:
                return
            for item in self.reports_tree.get_children():
                self.reports_tree.delete(item)
            for item in payload:
                status = "найден" if item.exists else "не найден"
                self.reports_tree.insert(
                    "",
                    tk.END,
                    values=(
                        item.label,
                        f"✅ {status}" if item.exists else f"⚠️ {status}",
                        item.mtime,
                        item.size,
                        str(item.path) if item.path else "",
                    ),
                )

        self._run_in_background(work, done)

    def _refresh_home(self) -> None:
        self.state_label.config(text="проверка...")

        def work():
            diagnostics = run_light_diagnostics(self.config_controller, self.app_root)
            reports = collect_report_paths(self.config_controller, self.app_root)
            return diagnostics, reports

        def done(payload):
            if payload is None:
                return
            diagnostics, reports = payload
            errors = sum(1 for item in diagnostics if item.status == "error")
            warnings = sum(1 for item in diagnostics if item.status == "warning")
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
            if not self._last_results:
                # Empty-state hint so the tree isn't a blank grid on
                # first launch (before any consolidation has run).
                self.results_tree.insert(
                    "",
                    tk.END,
                    values=(
                        "Нет данных",
                        "",
                        "",
                        "",
                        "Запустите сборку отчета",
                    ),
                    tags=("empty",),
                )
                return
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
                        "✅ успех" if result.ok else "❌ ошибка",
                        time_text,
                        str(result.path) if result.path else "",
                        message,
                    ),
                )

        self._run_in_background(work, done)

    def _refresh_logs(self) -> None:
        logs = read_recent_logs(
            [self.app_root / "startup_log.txt", self.repo_root / "gui_error_log.txt"],
            limit=150
        )
        self.log_errors.configure(state="normal")
        self.log_errors.delete("1.0", tk.END)
        if logs:
            self.log_errors.insert(tk.END, "\n".join(logs))
            self.log_errors.see(tk.END)
        else:
            self.log_errors.insert(tk.END, "Событий в логах не найдено.")
        self.log_errors.configure(state="disabled")

    def _refresh_settings(self) -> None:
        # 1. Загрузка в YAML-редактор
        self.settings_text.configure(state="normal")
        self.settings_text.delete("1.0", tk.END)
        config_path = Path(self.config_controller.config_path)
        if config_path.exists():
            try:
                text = config_path.read_text(encoding="utf-8")
                self.settings_text.insert(tk.END, text)
            except Exception as e:
                self.settings_text.insert(tk.END, f"# Ошибка чтения файла настроек: {e}")
        else:
            self.settings_text.insert(tk.END, "# Файл config.yaml не найден.")
        
        # 2. Загрузка в визуальную форму
        cfg = self.config_controller.config
        paths_cfg = cfg.get("paths", {})
        
        self.master_file_var.set(paths_cfg.get("master_file", ""))
        self.archive_dir_var.set(paths_cfg.get("archive_dir", ""))
        
        # Загрузка списка источников
        self.sources_listbox.delete(0, tk.END)
        source_roots = paths_cfg.get("source_roots", [])
        if isinstance(source_roots, list):
            for root in source_roots:
                self.sources_listbox.insert(tk.END, str(root))
                
        # Сетевые диски
        network_cfg = cfg.get("network", {})
        drive_letters = network_cfg.get("drive_letters", [])
        if isinstance(drive_letters, list):
            self.drive_letters_var.set(", ".join(str(d) for d in drive_letters))
        else:
            self.drive_letters_var.set(str(drive_letters))
            
        # Число бэкапов
        backup_cfg = cfg.get("backup", {})
        self.excel_keep_var.set(backup_cfg.get("excel_keep", 10))

    def _save_settings(self) -> None:
        config_path = Path(self.config_controller.config_path)
        from ruamel.yaml import YAML
        yaml = YAML()
        
        if self.settings_mode == "yaml":
            # Сохранение в режиме YAML-кода
            text = self.settings_text.get("1.0", tk.END)
            try:
                parsed = yaml.load(text)
                if not isinstance(parsed, dict):
                    raise ValueError("Корневой элемент конфигурации должен быть объектом (словарем)")
            except Exception as e:
                messagebox.showerror("Ошибка сохранения", f"Некорректный синтаксис YAML:\n{e}")
                return
                
            try:
                config_path.write_text(text, encoding="utf-8")
                self.config_controller.config = parsed
                messagebox.showinfo("Успех", "Настройки успешно сохранены!")
            except Exception as e:
                messagebox.showerror("Ошибка сохранения", f"Не удалось записать файл config.yaml:\n{e}")
        else:
            # Сохранение из визуальной формы
            cfg = self.config_controller.config
            
            if "paths" not in cfg:
                cfg["paths"] = {}
            if "network" not in cfg:
                cfg["network"] = {}
            if "backup" not in cfg:
                cfg["backup"] = {}
                
            cfg["paths"]["master_file"] = self.master_file_var.get()
            cfg["paths"]["archive_dir"] = self.archive_dir_var.get()
            
            roots = list(self.sources_listbox.get(0, tk.END))
            cfg["paths"]["source_roots"] = roots
            
            drives_str = self.drive_letters_var.get()
            drives = [d.strip().upper() for d in drives_str.split(",") if d.strip()]
            cfg["network"]["drive_letters"] = drives
            
            try:
                keep = int(self.excel_keep_var.get())
                cfg["backup"]["excel_keep"] = keep
            except (ValueError, tk.TclError):
                messagebox.showerror("Ошибка сохранения", "Количество бэкапов должно быть целым числом!")
                return
                
            try:
                self.config_controller.save_config()
                self._refresh_settings()
                messagebox.showinfo("Успех", "Настройки успешно сохранены!")
            except Exception as e:
                messagebox.showerror("Ошибка сохранения", f"Не удалось сохранить настройки:\n{e}")

    def _toggle_settings_mode(self) -> None:
        if self.settings_mode == "visual":
            self.settings_mode = "yaml"
            self.mode_btn.configure(text="Визуальный режим")
            self.settings_visual_frame.pack_forget()
            self._refresh_settings()
            self.settings_yaml_frame.pack(fill=tk.BOTH, expand=True)
        else:
            self.settings_mode = "visual"
            self.mode_btn.configure(text="Режим YAML-кода")
            self.settings_yaml_frame.pack_forget()
            self._refresh_settings()
            self.settings_visual_frame.pack(fill=tk.BOTH, expand=True)

    def _browse_master_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Выберите основной сводный отчет",
            filetypes=[("Excel Files", "*.xlsx;*.xlsb"), ("All Files", "*.*")]
        )
        if path:
            try:
                rel_path = Path(path).relative_to(self.repo_root)
                self.master_file_var.set(str(Path("..") / rel_path))
            except ValueError:
                self.master_file_var.set(path)

    def _browse_archive_dir(self) -> None:
        path = filedialog.askdirectory(title="Выберите папку для резервных копий")
        if path:
            try:
                rel_path = Path(path).relative_to(self.repo_root)
                self.archive_dir_var.set(str(Path("..") / rel_path))
            except ValueError:
                self.archive_dir_var.set(path)

    def _add_source_root(self) -> None:
        path = filedialog.askdirectory(title="Выберите папку с отчетами кураторов")
        if path:
            self.sources_listbox.insert(tk.END, path)

    def _remove_source_root(self) -> None:
        selected = self.sources_listbox.curselection()
        if selected:
            self.sources_listbox.delete(selected[0])

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

    def _open_report_by_label(self, label: str) -> None:
        for item in collect_report_paths(self.config_controller, self.app_root):
            if item.label == label:
                self._open_path(item.path)
                return
        self._show_missing(f"Путь не найден: {label}")

    def _recent_log_errors(self) -> list[str]:
        return read_recent_log_errors(
            [self.repo_root / "startup_log.txt", self.repo_root / "gui_error_log.txt"]
        )

    def _open_path(self, path: Path | None) -> None:
        safe_open_existing_path(path, open_path, self._show_missing)

    def _show_missing(self, message: str) -> None:
        messagebox.showwarning("Путь не найден", message)
