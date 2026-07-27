import logging
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable, TypeVar, cast

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
from core.ui.theme import ThemeManager, color as _c, status_tint

_T = TypeVar("_T")


class DashboardTabs:
    def __init__(
        self, notebook: ttk.Notebook, controller: Any, config_controller: Any
    ) -> None:
        self.notebook = notebook
        self.controller = controller
        self.config_controller = config_controller
        self.app_root = Path(getattr(config_controller, "config_path", "APP/config.yaml")).parent
        self.repo_root = self.app_root.parent
        sp = ThemeManager.SPACING
        self._tab_pad = sp["md"]        # notebook tab outer padding
        self._section_pad = sp["sm"]    # LabelFrame / section inner padding
        self._btn_gap = (0, sp["sm"])   # gap between sibling action buttons
        self.runtime_state_path = self.app_root / "runtime_state.json"
        self._last_results: list[RuntimeResult] = load_runtime_results(
            self.runtime_state_path
        )

        self.home_tab = ttk.Frame(notebook, padding=self._tab_pad, style="Main.TFrame")
        self.employees_tab = ttk.Frame(notebook, padding=self._tab_pad, style="Main.TFrame")
        self.reports_tab = ttk.Frame(notebook, padding=self._tab_pad, style="Main.TFrame")
        self.diagnostics_tab = ttk.Frame(notebook, padding=self._tab_pad, style="Main.TFrame")
        self.logs_tab = ttk.Frame(notebook, padding=self._tab_pad, style="Main.TFrame")
        self.aliases_tab = ttk.Frame(notebook, padding=self._tab_pad, style="Main.TFrame")
        self.history_tab = ttk.Frame(notebook, padding=self._tab_pad, style="Main.TFrame")  # UX-008

        notebook.add(self.employees_tab, text="Сотрудники")
        notebook.add(self.home_tab, text="Панель")
        notebook.add(self.reports_tab, text="Отчеты")
        notebook.add(self.history_tab, text="📜 История")  # UX-008
        notebook.add(self.diagnostics_tab, text="Диагностика")
        notebook.add(self.logs_tab, text="Логи")
        notebook.add(self.aliases_tab, text="🔗 Алиасы сверки")
        notebook.select(self.employees_tab)  # type: ignore[no-untyped-call]

        self._setup_home()
        self._setup_reports()
        self._setup_history()  # UX-008
        self._setup_diagnostics()
        self._setup_logs()
        self._setup_aliases()

    def _setup_home(self) -> None:
        summary_frame = ttk.LabelFrame(self.home_tab, text="Состояние", padding=self._section_pad, style="Main.TLabelframe")
        summary_frame.pack(fill=tk.X, pady=self._btn_gap)
        self.state_label = ttk.Label(summary_frame, text="", justify=tk.LEFT, wraplength=600)
        self.state_label.pack(fill=tk.X)
        # Adaptive wraplength: the 600px default is a placeholder that is
        # replaced on the first <Configure> and every subsequent resize so
        # the multi-line state summary wraps to the actual tab width instead
        # of overflowing on narrow windows or staying pinched on wide ones.
        def _reflow_state_label(event: tk.Event) -> None:
            try:
                # Available text width = tab width minus outer tab padding
                # (both sides) minus the LabelFrame's own inner padding.
                usable = event.width - 2 * self._tab_pad - 2 * self._section_pad
                # Clamp to a sane range so the label never collapses to a
                # single-word column or runs wider than the tab.
                self.state_label.configure(wraplength=max(200, min(usable, 1200)))
            except (tk.TclError, AttributeError):
                pass

        self.home_tab.bind("<Configure>", _reflow_state_label, add="+")

        quick_frame = ttk.LabelFrame(self.home_tab, text="Быстрые действия", padding=self._section_pad, style="Main.TLabelframe")
        quick_frame.pack(fill=tk.X, pady=self._btn_gap)
        ttk.Button(
            quick_frame,
            text="Открыть последний Master",
            command=lambda: self._open_report_by_label("Master_Report.xlsx"),
        ).pack(side=tk.LEFT, padx=(0, self._section_pad))
        ttk.Button(
            quick_frame,
            text="Открыть последнюю сверку",
            command=lambda: self._open_report_by_label("Последняя сверка"),
        ).pack(side=tk.LEFT, padx=(0, self._section_pad))
        ttk.Button(
            quick_frame,
            text="Открыть backup",
            command=self._open_backup_folder,
        ).pack(side=tk.LEFT, padx=(0, self._section_pad))
        ttk.Button(
            quick_frame,
            text="Открыть логи",
            command=lambda: self._open_path(self.repo_root),
        ).pack(side=tk.LEFT)

        last_frame = ttk.LabelFrame(self.home_tab, text="Последние результаты", padding=self._section_pad, style="Main.TLabelframe")
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
            "empty", foreground=_c("text_muted")
        )
        # Status tags so "✅ успех" / "❌ ошибка" rows are colour-coded
        # for at-a-glance scanning — same treatment as EmployeeTable.
        self._configure_results_tags()
        self.results_tree.pack(fill=tk.BOTH, expand=True)
        self.results_tree.bind("<Double-1>", lambda _event: self._open_selected_result())
        # Row-hover highlight — consistent with EmployeeTable so every
        # data tree feels identical under the pointer.
        from core.ui.theme import attach_treeview_hover
        attach_treeview_hover(self.results_tree)
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
        action_frame.pack(fill=tk.X, pady=self._btn_gap)
        ttk.Button(action_frame, text="Обновить", command=self.refresh).pack(side=tk.LEFT)
        ttk.Button(action_frame, text="Открыть", command=self._open_selected_report).pack(
            side=tk.LEFT, padx=(self._section_pad, 0)
        )
        ttk.Button(
            action_frame,
            text="Открыть папку",
            command=self._open_selected_report_folder,
        ).pack(side=tk.LEFT, padx=(self._section_pad, 0))
        ttk.Button(action_frame, text="Backup", command=self._open_backup_folder).pack(
            side=tk.LEFT, padx=(self._section_pad, 0)
        )

        self.reports_tree = ttk.Treeview(
            self.reports_tab,
            columns=("name", "status", "mtime", "size", "path"),
            show="headings",
            # Path-heavy tree: file names, sizes, mtimes, full paths —
            # render in tabular-mono so paths are scannable and the
            # size column aligns on the decimal.
            style="Mono.Treeview",
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
        from core.ui.theme import attach_treeview_hover
        attach_treeview_hover(self.reports_tree)

    # ── UX-008: History tab ──────────────────────────────────────

    def _setup_history(self) -> None:
        """Build the operation history tab showing recent sessions."""
        action_frame = ttk.Frame(self.history_tab, style="Main.TFrame")
        action_frame.pack(fill=tk.X, pady=self._btn_gap)
        ttk.Button(
            action_frame, text="🔄 Обновить", command=self._refresh_history
        ).pack(side=tk.LEFT)
        ttk.Label(
            action_frame,
            text="Последние операции (из БД):",
            style="Main.TLabel",
        ).pack(side=tk.LEFT, padx=(self._section_pad, 0))

        self.history_tree = ttk.Treeview(
            self.history_tab,
            columns=("Date", "Type", "Status", "Files", "Target"),
            show="headings",
        )
        self.history_tree.heading("Date", text="Дата/Время")
        self.history_tree.heading("Type", text="Тип")
        self.history_tree.heading("Status", text="Статус")
        self.history_tree.heading("Files", text="Файлов")
        self.history_tree.heading("Target", text="Дата сбора")
        self.history_tree.column("Date", width=140, anchor=tk.W)
        self.history_tree.column("Type", width=120, anchor=tk.W)
        self.history_tree.column("Status", width=100, anchor=tk.W)
        self.history_tree.column("Files", width=60, anchor=tk.W)
        # Target stretches to fill remaining width — consistent with the
        # results/reports/diagnostics trees which each give one text
        # column stretch=True so the table fills the tab without a gap
        # on wide windows or an unnecessary scrollbar on narrow ones.
        self.history_tree.column("Target", width=100, anchor=tk.W, stretch=True)

        # Status colours
        self.history_tree.tag_configure(
            "completed", foreground=_c("success")
        )
        self.history_tree.tag_configure(
            "failed", foreground=_c("danger")
        )
        self.history_tree.tag_configure(
            "cancelled", foreground=_c("warning")
        )

        self.history_tree.pack(fill=tk.BOTH, expand=True)
        from core.ui.theme import attach_treeview_hover
        attach_treeview_hover(self.history_tree)
        # Load on init (best-effort — DB may not have sessions yet)
        try:
            self._refresh_history()
        except Exception:
            pass

    def _refresh_history(self) -> None:
        """Reload sessions from the DB into the history tree."""
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        # Get persistence from the controller
        persistence = getattr(self.controller, "persistence", None)
        if persistence is None:
            # Try app_controller → persistence
            app_ctl = getattr(self.controller, "app_controller", None)
            if app_ctl is not None:
                persistence = getattr(app_ctl, "persistence", None)
        if persistence is None:
            self.history_tree.insert(
                "", tk.END,
                values=("", "", "БД недоступна", "", ""),
            )
            return
        list_sessions = getattr(persistence, "list_recent_sessions", None)
        if not callable(list_sessions):
            self.history_tree.insert(
                "", tk.END,
                values=("", "", "list_recent_sessions недоступен", "", ""),
            )
            return
        try:
            sessions = list_sessions(limit=50)
        except Exception as e:
            self.history_tree.insert(
                "", tk.END,
                values=("", "", f"Ошибка: {e}", "", ""),
            )
            return
        if not sessions:
            self.history_tree.insert(
                "", tk.END,
                values=("Нет данных", "", "", "", ""),
                tags=("empty",),
            )
            return
        type_labels = {
            "daily": "Сборка за день",
            "all_dates": "Сборка все даты",
            "monthly": "Сборка за период",
            "rsch": "РСЧ",
            "rsch_month": "РСЧ за период",
            "reconciliation": "Сверка",
        }
        for s in sessions:
            status = s.get("status", "")
            created = str(s.get("created_at", ""))
            stype = type_labels.get(s.get("session_type", ""), s.get("session_type", ""))
            files = s.get("file_count", 0)
            target = s.get("target_date") or s.get("start_date", "")
            if s.get("end_date"):
                target = f"{target}..{s['end_date']}"
            self.history_tree.insert(
                "", tk.END,
                values=(created, stype, status, files, target),
                tags=(status,) if status in ("completed", "failed", "cancelled") else (),
            )

    def _setup_diagnostics(self) -> None:
        action_frame = ttk.Frame(self.diagnostics_tab, style="Main.TFrame")
        action_frame.pack(fill=tk.X, pady=self._btn_gap)
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
        ).pack(side=tk.LEFT, padx=(self._section_pad, 0))

        self.diagnostics_tree = ttk.Treeview(
            self.diagnostics_tab,
            columns=("check", "status", "detail", "path"),
            show="headings",
            # Path-heavy tree: diagnostic check paths render in tabular-
            # mono for scannability.
            style="Mono.Treeview",
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
        from core.ui.theme import attach_treeview_hover
        attach_treeview_hover(self.diagnostics_tree)

    def _setup_logs(self) -> None:
        action_frame = ttk.Frame(self.logs_tab, style="Main.TFrame")
        action_frame.pack(fill=tk.X, pady=self._btn_gap)
        
        ttk.Button(
            action_frame,
            text="Обновить",
            command=self._refresh_logs,
        ).pack(side=tk.LEFT)
        
        ttk.Button(
            action_frame,
            text="Открыть лог работы (Python)",
            command=lambda: self._open_path(self.app_root / "startup_log.txt"),
        ).pack(side=tk.LEFT, padx=(self._section_pad, 0))
        
        ttk.Button(
            action_frame,
            text="Открыть лог запуска (Батник)",
            command=lambda: self._open_path(self.repo_root / "startup_log.txt"),
        ).pack(side=tk.LEFT, padx=(self._section_pad, 0))
        
        ttk.Button(
            action_frame,
            text="Открыть gui_error_log.txt",
            command=lambda: self._open_path(self.repo_root / "gui_error_log.txt"),
        ).pack(side=tk.LEFT, padx=(self._section_pad, 0))
        
        ttk.Button(
            action_frame,
            text="Открыть папку логов",
            command=lambda: self._open_path(self.repo_root / "logs"),
        ).pack(side=tk.LEFT, padx=(self._section_pad, 0))

        ttk.Label(self.logs_tab, text="Последние события лога:").pack(anchor=tk.W)
        
        self.log_errors = tk.Text(
            self.logs_tab,
            state="disabled",
            wrap=tk.WORD,
        )
        ThemeManager.register(self.log_errors, bg_key="bg_panel", fg_key="text")
        self.log_errors.configure(
            insertbackground=ThemeManager.COLORS["text"],
            selectbackground=ThemeManager.COLORS["primary"],
            selectforeground=ThemeManager.COLORS["text_inverse"],
            highlightthickness=0,
            borderwidth=0,
        )

        scroll_y = ttk.Scrollbar(self.logs_tab, orient=tk.VERTICAL, command=self.log_errors.yview)
        scroll_x = ttk.Scrollbar(self.logs_tab, orient=tk.HORIZONTAL, command=self.log_errors.xview)

        self.log_errors.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.log_errors.pack(fill=tk.BOTH, expand=True)

    def _setup_aliases(self) -> None:
        from core.ui.ui_aliases import AliasesTab
        app_ctl = getattr(self.controller, "app_controller", self.controller)
        self._aliases_tab = AliasesTab(self.aliases_tab, app_ctl)

    def refresh(self) -> None:
        # _refresh_reports and _refresh_home each previously called
        # collect_report_paths() (a network-walking path.exists/stat/glob
        # pass) on its own daemon thread. On slow network drives that
        # doubled the network probes after every operation completion.
        # Here we fetch the shared data once and feed both renderers.
        for item in self.reports_tree.get_children():
            self.reports_tree.delete(item)
        self.reports_tree.insert("", tk.END, values=("проверка...", "", "", "", ""))
        self.state_label.config(text="проверка...")

        def work() -> Any:
            reports = collect_report_paths(self.config_controller, self.app_root)
            diagnostics = run_light_diagnostics(self.config_controller, self.app_root)
            return reports, diagnostics

        def done(payload: Any) -> None:
            if payload is None:
                self._refresh_logs()
                return
            reports, diagnostics = payload
            self._render_reports(reports)
            self._render_home(diagnostics, reports)
            self._refresh_logs()

        self._run_in_background(work, done)

    def _render_reports(self, reports: Any) -> None:
        for item in self.reports_tree.get_children():
            self.reports_tree.delete(item)
        for item in reports:
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

    def _render_home(self, diagnostics: Any, reports: Any) -> None:
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
                tags=("success" if result.ok else "error",),
            )

    def _configure_results_tags(self) -> None:
        """Colour-code success/error rows in the results tree.

        Mirrors EmployeeTable's status treatment: bold semantic-colour
        foreground so "✅ успех"/"❌ ошибка" reads as a label, with a
        faint row-wash tint derived from the semantic palette.
        """
        bold = ThemeManager.FONTS["body_bold"]

        self.results_tree.tag_configure(
            "success", foreground=_c("success"), background=status_tint("success"), font=bold
        )
        self.results_tree.tag_configure(
            "error", foreground=_c("danger"), background=status_tint("danger"), font=bold
        )

    def refresh_theme(self) -> None:
        """Re-apply theme-dependent tag colours after a palette switch."""
        self.results_tree.tag_configure(
            "empty", foreground=_c("text_muted")
        )
        self._configure_results_tags()

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
        self.refresh()

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
                    # work() may fail → result is None; on_done handles the
                    # falsy payload. cast keeps the _T contract for mypy.
                    on_done(cast(Any, result))
                except tk.TclError:
                    pass

            try:
                self.notebook.after(0, safe_done)
            except tk.TclError:
                pass

        threading.Thread(target=runner, daemon=True).start()

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
        errors: list[str] = read_recent_log_errors(
            [self.repo_root / "startup_log.txt", self.repo_root / "gui_error_log.txt"]
        )
        return errors

    def _open_path(self, path: Path | None) -> None:
        safe_open_existing_path(path, open_path, self._show_missing)

    def _show_missing(self, message: str) -> None:
        messagebox.showwarning("Путь не найден", message)
