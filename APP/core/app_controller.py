import concurrent.futures
import logging
import threading
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable, cast

from core.infra import DiscoveryService
from core.shared.path_scrub import scrub_path
from core.app.file_processor import (
    check_master_lock,
    run_engine,
)
from core.app.performance import resolve_max_workers
from core.app.curator_paths import (
    build_drive_letters_fn,
    filter_employees_for_curator,
    get_curator_config,
    get_enabled_curator_employee_keys,
    get_network_drive_letters,
    is_report_writable,
    resolve_report_path,
)
from core.app.refresh_status import run_refresh_status as run_employee_status_refresh
from core.app.message_formatting import (
    build_empty_data_message,
    build_issue_preview,
    build_success_message,
    format_file_error_note,
    normalize_consolidation_dates,
)
from core.infra.reconciliation import build_combined_reconciliation_report
from core.infra.rsch import build_rsch_report
from core.services.rsch_service import RschService
from core.services.reconciliation_service import ReconciliationService
from core.infra.config_controller import ConfigController
from core.domain.interfaces import (
    IDataSource,
    IPersistence,
    IValidator,
    ILogicService,
    IExporter,
)
# Cancellation primitives live in a UI-free module (core.app.cancellation) so
# this controller no longer imports core.ui, and the services can import them
# without creating a services -> app_controller cycle. Re-exported under their
# historical underscore names so existing call sites stay unchanged.
from core.app.cancellation import cancel_message as _cancel_message
from core.app.cancellation import is_cancelled as _is_cancelled


class ConsolidationRunError(RuntimeError):
    def __init__(self, message: str, code: str = "failed") -> None:
        super().__init__(message)
        self.code = code


class AppController:
    """Main orchestrator — coordinates file discovery, ingestion, and export."""

    def __init__(
        self,
        config_controller: ConfigController,
        ingestion: IDataSource,
        persistence: IPersistence,
        validator: IValidator,
        logic_service: ILogicService,
        writer: IExporter,
        alias_repo: Any = None,
    ) -> None:
        self.config_controller = config_controller
        self.ingestion = ingestion
        self.persistence = persistence
        self.validator = validator
        self.logic_service = logic_service
        self.writer = writer
        self.alias_repo = alias_repo

        self.discovery = DiscoveryService(config_controller, ingestion, persistence=persistence)
        self._max_workers = resolve_max_workers(
            getattr(config_controller, "config", None)
        )
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="hermes-worker",
        )
        self._lock = threading.Lock()
        self._cached_employees: Dict[str, List[Dict[str, Any]]] = {}
        self._active_threads: List[threading.Thread] = []
        self._rsch = RschService(
            start_thread_fn=self._start_thread,
            get_drive_letters_fn=build_drive_letters_fn(self.config_controller),
        )
        self._reconciliation = ReconciliationService(
            start_thread_fn=self._start_thread,
            get_drive_letters_fn=build_drive_letters_fn(self.config_controller),
            alias_repo=self.alias_repo,
        )

        # TD-019: purge old completed/failed/cancelled sessions on startup
        # so cache.db does not grow unboundedly across months of daily use.
        # Best-effort — never blocks startup if the purge fails.
        self._purge_old_sessions_on_startup()

    def _purge_old_sessions_on_startup(self, max_age_days: int = 30) -> None:
        """Delete sessions older than ``max_age_days`` (best-effort)."""
        try:
            purge = getattr(self.persistence, "purge_old_sessions", None)
            if callable(purge):
                purge(max_age_days)
        except Exception:
            logging.warning("Startup session purge failed (non-fatal)", exc_info=True)

    @property
    def rename_detected(self) -> bool:
        return cast(bool, self.discovery.rename_detected)

    def _get_employees_map(
        self, *, allow_network_scan: bool = True
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Discover and return employee-to-file mapping."""
        return cast(
            Dict[str, List[Dict[str, Any]]],
            self.discovery.get_employees_map(allow_network_scan=allow_network_scan),
        )

    def _start_thread(self, target: Callable[..., Any]) -> None:
        """Start a task thread and track it for graceful shutdown."""
        t = threading.Thread(target=target, daemon=True)
        with self._lock:
            self._active_threads = [th for th in self._active_threads if th.is_alive()]
            self._active_threads.append(t)
        t.start()

    @staticmethod
    def _build_session_meta(
        session_type: str,
        target_date_str: Optional[str],
        start_date_str: Optional[str],
        end_date_str: Optional[str],
    ) -> Dict[str, Any]:
        meta: Dict[str, Any] = {"type": session_type}
        if target_date_str:
            meta["date"] = target_date_str
        if start_date_str and end_date_str:
            meta["start_date"] = start_date_str
            meta["end_date"] = end_date_str
        return meta

    def _cache_employees_map(self, employees_map: Dict[str, List[Dict[str, Any]]]) -> None:
        with self._lock:
            self._cached_employees = employees_map

    def _resolve_employees_for_run(self, use_fresh_employees: bool) -> Dict[str, List[Dict[str, Any]]]:
        if use_fresh_employees:
            employees_map = self._get_employees_map()
            with self._lock:
                self._cached_employees = employees_map
            return employees_map

        with self._lock:
            employees_map = cast(
                Dict[str, List[Dict[str, Any]]],
                dict(self._cached_employees) if self._cached_employees else None,
            )
        if employees_map:
            return employees_map

        employees_map = self._get_employees_map()
        with self._lock:
            if not self._cached_employees:
                self._cached_employees = employees_map
        return employees_map

    def _build_no_files_message(self) -> str:
        raw_count = getattr(self.discovery, "last_discovered_count", 0)
        discovered_count = raw_count if isinstance(raw_count, int) else 0
        if discovered_count:
            return (
                f"Найдено {discovered_count} файл(ов), но 0 привязано к сотрудникам. "
                "Проверьте employees.yaml или привязки файлов."
            )
        return "Нет файлов"

    def _execute_consolidation(
        self,
        on_progress: Callable[[float], None],
        on_complete: Callable[[bool, str, Optional[Path]], None],
        target_date_str: Optional[str],
        start_date_str: Optional[str],
        end_date_str: Optional[str],
        session_type: str,
        use_fresh_employees: bool,
        curator: Optional[str] = None,
        on_failure_code: Optional[Callable[[str], None]] = None,
        cancel_event: Optional[threading.Event] = None,
        on_current_file: Optional[Callable[[str, int, int], None]] = None,
    ) -> None:
        import time as _time
        _t0 = _time.monotonic()
        session_id = str(uuid.uuid4())

        def _is_cancelled() -> bool:
            return cancel_event is not None and cancel_event.is_set()

        try:
            curator_config = get_curator_config(self.config_controller.config, curator)
            effective_target_date, effective_start_date, effective_end_date, date_error, range_note = (
                normalize_consolidation_dates(
                    target_date_str,
                    start_date_str,
                    end_date_str,
                )
            )
            if date_error:
                if callable(on_failure_code):
                    on_failure_code("invalid_date")
                on_complete(False, date_error, None)
                return

            meta = self._build_session_meta(
                session_type,
                effective_target_date,
                effective_start_date,
                effective_end_date,
            )
            self.persistence.save_session(session_id, meta)

            employees_map = self._resolve_employees_for_run(use_fresh_employees)
            employees_map = filter_employees_for_curator(
                employees_map,
                curator_config,
                get_enabled_curator_employee_keys(self.config_controller.config),
            )
            if not employees_map:
                self.persistence.update_session_status(session_id, "failed")
                if callable(on_failure_code):
                    on_failure_code("no_files")
                on_complete(False, self._build_no_files_message(), None)
                return

            file_errors: List[Dict[str, str]] = []

            def collect_file_errors(errors: List[Dict[str, str]]) -> None:
                file_errors.extend(errors)

            if not run_engine(
                self.persistence,
                self.ingestion,
                self.validator,
                employees_map,
                session_id,
                effective_target_date,
                on_progress,
                start_date_str=effective_start_date,
                end_date_str=effective_end_date,
                on_file_error=collect_file_errors,
                cancel_event=cancel_event,
                on_current_file=on_current_file,
            ):
                self.persistence.update_session_status(session_id, "failed")
                if callable(on_failure_code):
                    on_failure_code("no_files")
                on_complete(False, self._build_no_files_message(), None)
                return

            if _is_cancelled():
                self.persistence.update_session_status(session_id, "cancelled")
                _cancel_message(on_complete)
                return

            consolidated_data = self.logic_service.consolidate(
                session_id,
                curator=curator,
                curator_config=curator_config,
            )
            # After the SQL aggregation step, push the bar to ~70% so the
            # user can see we are in the final stretch (write_report
            # is the last heavy step before completion).
            on_progress(70)

            if _is_cancelled():
                self.persistence.update_session_status(session_id, "cancelled")
                _cancel_message(on_complete)
                return
            errors = self.persistence.get_template_errors(session_id)
            file_error_note = format_file_error_note(file_errors)

            if not consolidated_data:
                self.persistence.update_session_status(session_id, "failed")
                if callable(on_failure_code):
                    on_failure_code("empty_data")
                on_complete(
                    False,
                    build_empty_data_message(
                        effective_target_date,
                        effective_start_date,
                        effective_end_date,
                        range_note,
                        file_error_note,
                    ),
                    None,
                )
                return

            master_path = resolve_report_path(self.config_controller, curator_config)
            write_kwargs: Dict[str, Any] = {}
            if errors:
                write_kwargs["template_errors"] = errors
            if curator_config:
                write_kwargs["curator"] = curator
                write_kwargs["curator_config"] = curator_config

            if not self.writer.write_report(consolidated_data, master_path, **write_kwargs):
                self.persistence.update_session_status(session_id, "failed")
                if callable(on_failure_code):
                    on_failure_code("write_error")
                on_complete(False, "Ошибка записи основного отчёта", None)
                return

            logging.info("[MAIN] Основной отчёт собран: %s", scrub_path(str(master_path)))
            _elapsed = _time.monotonic() - _t0
            logging.info(f"[PERF] Consolidation ({session_type}): {_elapsed:.1f}s")
            on_progress(95)
            # `on_progress(100)` is intentionally left to the *completion
            # handler* — that is when the OperationState's end() resets
            # the bar to 0. Otherwise the bar reaches 100% for a single
            # frame and then immediately resets, which makes it look
            # like nothing happened.
            has_actionable_warnings = any(
                error.get("error_type") not in {"soft_structure"} for error in errors
            )
            has_runtime_warnings = bool(range_note or file_error_note)
            self.persistence.update_session_status(
                session_id,
                "completed_with_warnings"
                if has_actionable_warnings or has_runtime_warnings
                else "completed",
            )

            on_complete(
                True,
                build_success_message(
                    session_type,
                    effective_start_date,
                    effective_end_date,
                    range_note,
                    file_error_note,
                ),
                master_path,
            )
        except Exception as e:
            logging.exception("Error: %s", e)
            self.persistence.update_session_status(session_id, "failed")
            if callable(on_failure_code):
                on_failure_code("exception")
            on_complete(False, str(e), None)

    def refresh_status(
        self,
        selected_date: Any,
        on_progress: Callable[[float], None],
        on_complete: Callable[[List[tuple[Any, ...]], Dict[str, Any], bool], None],
        curator: Optional[str] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Refresh employee file status for the selected date."""
        if not check_master_lock(self.config_controller):
            on_complete([], {}, False)
            msg = "Мастер-файл занят в Excel. Закройте его и повторите."
            logging.error("Master file is locked. Please close it in Excel.")
            if callable(on_error):
                on_error(msg)
            return

        def task() -> None:
            run_employee_status_refresh(
                persistence=self.persistence,
                ingestion=self.ingestion,
                executor=self._executor,
                employees_map_provider=lambda: self._get_employees_map(
                    allow_network_scan=False
                ),
                rename_detected=lambda: self.rename_detected,
                on_employees_loaded=self._cache_employees_map,
                selected_date=selected_date,
                on_progress=on_progress,
                on_complete=on_complete,
                on_error=on_error,
            )

        self._start_thread(task)

    # ── Unified consolidation core (Item 6) ──────────────────────

    def _run_consolidation_core(
        self,
        on_progress: Callable[[float], None],
        on_complete: Callable[[bool, str, Optional[Path]], None],
        target_date_str: Optional[str] = None,
        start_date_str: Optional[str] = None,
        end_date_str: Optional[str] = None,
        session_type: str = "daily",
        use_fresh_employees: bool = False,
        curator: Optional[str] = None,
        cancel_event: Optional[threading.Event] = None,
        on_current_file: Optional[Callable[[str, int, int], None]] = None,
    ) -> None:
        """Core consolidation logic shared by all consolidation entry points.

        Builds one Master report for all employees.

        Args:
            on_progress: Progress callback (0-100).
            on_complete: Completion callback (ok, message, path).
            target_date_str: Single date filter (dd.mm.YYYY) or None.
            start_date_str: Range start (dd.mm.YYYY) or None.
            end_date_str: Range end (dd.mm.YYYY) or None.
            session_type: 'daily', 'all_dates', or 'monthly'.
            use_fresh_employees: If True, re-discover employees from disk.
            cancel_event: optional threading.Event; if set, the task stops
                at the next checkpoint and reports cancelled to the caller.
        """
        curator_config = get_curator_config(self.config_controller.config, curator)
        if not is_report_writable(self.config_controller, curator_config):
            on_complete(
                False, "Файл отчёта занят в Excel! Закройте его и повторите.", None
            )
            return

        def task() -> None:
            self._execute_consolidation(
                on_progress,
                on_complete,
                target_date_str,
                start_date_str,
                end_date_str,
                session_type,
                use_fresh_employees,
                curator,
                cancel_event=cancel_event,
                on_current_file=on_current_file,
            )

        self._start_thread(task)

    def run_consolidation(
        self,
        selected_date: Any,
        on_progress: Callable[[float], None],
        on_complete: Callable[[bool, str, Optional[Path]], None],
        curator: Optional[str] = None,
        cancel_event: Optional[threading.Event] = None,
        on_current_file: Optional[Callable[[str, int, int], None]] = None,
    ) -> None:
        """Run consolidation for a single selected date."""
        self._run_consolidation_core(
            on_progress,
            on_complete,
            target_date_str=selected_date.strftime("%d.%m.%Y"),
            session_type="daily",
            curator=curator,
            cancel_event=cancel_event,
            on_current_file=on_current_file,
        )

    def run_consolidation_all_dates(
        self,
        on_progress: Callable[[float], None],
        on_complete: Callable[[bool, str, Optional[Path]], None],
        curator: Optional[str] = None,
        cancel_event: Optional[threading.Event] = None,
        on_current_file: Optional[Callable[[str, int, int], None]] = None,
    ) -> None:
        """Run consolidation for all available dates."""
        self._run_consolidation_core(
            on_progress,
            on_complete,
            session_type="all_dates",
            use_fresh_employees=True,
            curator=curator,
            cancel_event=cancel_event,
            on_current_file=on_current_file,
        )

    def run_consolidation_month(
        self,
        start_date: Any,
        end_date: Any,
        on_progress: Callable[[float], None],
        on_complete: Callable[[bool, str, Optional[Path]], None],
        curator: Optional[str] = None,
        cancel_event: Optional[threading.Event] = None,
        on_current_file: Optional[Callable[[str, int, int], None]] = None,
    ) -> None:
        """Run consolidation for a date range (monthly)."""
        self._run_consolidation_core(
            on_progress,
            on_complete,
            start_date_str=start_date.strftime("%d.%m.%Y"),
            end_date_str=end_date.strftime("%d.%m.%Y"),
            session_type="monthly",
            curator=curator,
            cancel_event=cancel_event,
            on_current_file=on_current_file,
        )

    def _run_consolidation_blocking(
        self,
        *,
        target_date_str: Optional[str],
        start_date_str: Optional[str],
        end_date_str: Optional[str],
        session_type: str,
        curator: Optional[str],
    ) -> Path:
        curator_config = get_curator_config(self.config_controller.config, curator)
        if not is_report_writable(self.config_controller, curator_config):
            label = curator or "общий"
            raise RuntimeError(f"Файл отчета {label} занят в Excel! Закройте его и повторите.")

        result: dict[str, Any] = {}

        def on_complete(ok: bool, msg: str, path: Optional[Path]) -> None:
            result["ok"] = ok
            result["msg"] = msg
            result["path"] = path

        def on_failure_code(code: str) -> None:
            result["code"] = code

        self._execute_consolidation(
            lambda _progress: None,
            on_complete,
            target_date_str,
            start_date_str,
            end_date_str,
            session_type,
            False,
            curator,
            on_failure_code=on_failure_code,
        )

        if not result.get("ok"):
            raise ConsolidationRunError(
                str(result.get("msg") or "Не удалось собрать отчет"),
                str(result.get("code") or "failed"),
            )
        path = result.get("path")
        if path is None:
            raise RuntimeError("Отчет собран, но путь к файлу не получен")
        return Path(path)

    def _write_empty_auto_reconciliation_report(self, curator: str, target_date: Any) -> Path:
        curator_config = get_curator_config(self.config_controller.config, curator)
        if not curator_config:
            raise RuntimeError(f"Не настроен отчет куратора {curator}")
        if not is_report_writable(self.config_controller, curator_config):
            raise RuntimeError(f"Файл отчета {curator} занят в Excel! Закройте его и повторите.")

        output_path = cast(Path, resolve_report_path(self.config_controller, curator_config))
        write_empty_report = getattr(self.writer, "write_empty_daily_report", None)
        if not callable(write_empty_report):
            raise RuntimeError("Экспортер не поддерживает пустой отчет для автосверки")

        if not write_empty_report(
            output_path,
            target_date,
            curator=curator,
            curator_config=curator_config,
        ):
            raise RuntimeError(f"Ошибка записи пустого отчета куратора {curator}")
        return output_path

    def _run_auto_master_report(
        self,
        *,
        label: str,
        curator: Optional[str],
        date_suffix: str,
        target_date: Any,
    ) -> Path:
        try:
            return self._run_consolidation_blocking(
                target_date_str=date_suffix,
                start_date_str=None,
                end_date_str=None,
                session_type="daily",
                curator=curator,
            )
        except ConsolidationRunError as exc:
            if exc.code == "empty_data":
                if curator:
                    return self._write_empty_auto_reconciliation_report(curator, target_date)
                raise RuntimeError(f"{label}: Нет данных за {date_suffix}") from exc
            raise RuntimeError(f"{label}: {exc}") from exc
        except RuntimeError as exc:
            raise RuntimeError(f"{label}: {exc}") from exc

    def run_auto_reconciliation_day(
        self,
        source_paths: Path | Sequence[Path],
        output_path: Path,
        selected_date: Any,
        on_complete: Callable[[bool, str, Optional[Path]], None],
        cancel_event: Optional[threading.Event] = None,
    ) -> None:
        """Rebuild daily reports, rebuild RSC, then write one 3-sheet reconciliation."""

        def task() -> None:
            try:
                target_date = selected_date.date() if hasattr(selected_date, "date") else selected_date
                date_suffix = target_date.strftime("%d.%m.%Y")
                output_path_resolved = Path(output_path)
                rsch_output = output_path_resolved.parent / f"РСЧ_отчет_{date_suffix}.xlsx"

                if _is_cancelled(cancel_event):
                    _cancel_message(on_complete, output_path_resolved, rsch_output)
                    return

                master_paths = {
                    "Общий": self._run_auto_master_report(
                        label="Общий",
                        curator=None,
                        date_suffix=date_suffix,
                        target_date=target_date,
                    ),
                    "Борис": self._run_auto_master_report(
                        label="Борис",
                        curator="boris",
                        date_suffix=date_suffix,
                        target_date=target_date,
                    ),
                    "Иван": self._run_auto_master_report(
                        label="Иван",
                        curator="ivan",
                        date_suffix=date_suffix,
                        target_date=target_date,
                    ),
                }

                if _is_cancelled(cancel_event):
                    _cancel_message(on_complete, output_path_resolved, rsch_output)
                    return

                if isinstance(source_paths, (str, Path)):
                    normalized_sources = [Path(source_paths)]
                else:
                    normalized_sources = [Path(p) for p in source_paths]

                issues: List[str] = []
                rsch_rows = build_rsch_report(
                    normalized_sources,
                    rsch_output,
                    target_date=target_date,
                    issues_sink=issues,
                    drive_letters=get_network_drive_letters(self.config_controller.config),
                )
                if rsch_rows == 0:
                    on_complete(
                        True,
                        f"Нет данных РСЧ за {date_suffix}. Автосверка пропущена.",
                        None,
                    )
                    return

                if _is_cancelled(cancel_event):
                    _cancel_message(on_complete, output_path_resolved, rsch_output)
                    return

                try:
                    counts = build_combined_reconciliation_report(
                        master_paths,
                        rsch_output,
                        output_path_resolved,
                        target_date=target_date,
                        drive_letters=get_network_drive_letters(self.config_controller.config),
                        alias_repo=self.alias_repo,
                    )
                except ValueError as e:
                    on_complete(
                        True,
                        f"Сверка за {date_suffix}: {e}",
                        None,
                    )
                    return
                issue_note = (
                    f" Есть проблемы с листами РСЧ: {build_issue_preview(issues)}"
                    if issues
                    else ""
                )
                msg = (
                    "Автосверка собрана: "
                    f"Общий {counts.get('Общий', 0)}, "
                    f"Борис {counts.get('Борис', 0)}, "
                    f"Иван {counts.get('Иван', 0)} строк. "
                    f"РСЧ: {rsch_rows} строк."
                    f"{issue_note}"
                )
                on_complete(True, msg, output_path_resolved)
            except Exception as e:
                logging.exception("Auto reconciliation error: %s", e)
                on_complete(False, f"Ошибка автоматической сверки: {e}", None)

        self._start_thread(task)

    def run_reconciliation_report(
        self,
        master_paths: Dict[str, Path],
        rsch_path: Path,
        output_path: Path,
        selected_date: Any,
        on_complete: Callable[[bool, str, Optional[Path]], None],
        cancel_event: Optional[threading.Event] = None,
    ) -> None:
        """Build a reconciliation report from already selected report and RSC files."""
        self._reconciliation.run_reconciliation_report(
            master_paths, rsch_path, output_path, selected_date, on_complete, cancel_event
        )

    def run_rsch_report(
        self,
        source_paths: Path | Sequence[Path],
        output_path: Path,
        selected_date: Any,
        on_complete: Callable[[bool, str, Optional[Path]], None],
        cancel_event: Optional[threading.Event] = None,
        on_progress: Optional[Callable[[float], None]] = None,
        on_current_file: Optional[Callable[[str, int, int], None]] = None,
    ) -> None:
        """Build an RSC control report from selected workbooks."""
        self._rsch.run_rsch_report(
            source_paths,
            output_path,
            selected_date,
            on_complete,
            cancel_event,
            on_progress=on_progress,
            on_current_file=on_current_file,
        )

    def run_rsch_report_period(
        self,
        source_paths: Path | Sequence[Path],
        output_path: Path,
        start_date: Any,
        end_date: Any,
        on_complete: Callable[[bool, str, Optional[Path]], None],
        cancel_event: Optional[threading.Event] = None,
        on_progress: Optional[Callable[[float], None]] = None,
        on_current_file: Optional[Callable[[str, int, int], None]] = None,
    ) -> None:
        """Build one RSC control workbook with one sheet per row date in range."""
        self._rsch.run_rsch_report_period(
            source_paths,
            output_path,
            start_date,
            end_date,
            on_complete,
            cancel_event,
            on_progress=on_progress,
            on_current_file=on_current_file,
        )

    def run_rsch_report_period_batch(
        self,
        source_paths: Path | Sequence[Path],
        output_dir: Path,
        start_date: Any,
        end_date: Any,
        on_complete: Callable[[bool, str, Optional[Path]], None],
        cancel_event: Optional[threading.Event] = None,
    ) -> None:
        """Build separate RSC workbooks for each date in the selected range."""
        self._rsch.run_rsch_report_period_batch(
            source_paths, output_dir, start_date, end_date, on_complete, cancel_event
        )

    def run_rsch_report_batch(
        self,
        source_paths: Sequence[Path],
        output_paths: Sequence[Path],
        selected_date: Any,
        on_complete: Callable[[bool, str, Optional[Path]], None],
        cancel_event: Optional[threading.Event] = None,
    ) -> None:
        """Build separate RSC reports per source workbook."""
        self._rsch.run_rsch_report_batch(
            source_paths, output_paths, selected_date, on_complete, cancel_event
        )

    def shutdown(self) -> None:
        """Gracefully shut down: wait for threads and close DB."""
        logging.info("[APP] Завершение: ожидаю завершения записей в БД...")
        self.persistence.wait_for_writes()

        # Shutdown thread pool executor
        self._executor.shutdown(wait=True)
        logging.info("[APP] Завершение: пул потоков остановлен.")

        # Wait for active task threads to finish (with timeout)
        with self._lock:
            threads = list(self._active_threads)
        for t in threads:
            t.join(timeout=10)

        self.persistence.close()
        logging.info("[APP] Завершение: БД закрыта.")

    # ── Customer aliases (reconciliation mapping) ───────────

    def get_customer_aliases(self) -> List[Any]:
        """Return all customer alias entries for UI display."""
        if self.alias_repo is None:
            return []
        return cast(List[Any], self.alias_repo.get_all_aliases())

    def add_customer_alias(self, master_customer: str, rsch_customer: str, notes: str = "") -> int:
        """Add a new customer alias mapping. Returns new alias id."""
        if self.alias_repo is None:
            raise RuntimeError("Алиасы не настроены")
        return cast(int, self.alias_repo.add_alias(master_customer, rsch_customer, notes))

    def update_customer_alias(
        self, alias_id: int, master_customer: str, rsch_customer: str, notes: str = ""
    ) -> None:
        """Update an existing customer alias."""
        if self.alias_repo is None:
            raise RuntimeError("Алиасы не настроены")
        self.alias_repo.update_alias(alias_id, master_customer, rsch_customer, notes)

    def delete_customer_alias(self, alias_id: int) -> None:
        """Delete a customer alias by id."""
        if self.alias_repo is None:
            raise RuntimeError("Алиасы не настроены")
        self.alias_repo.delete_alias(alias_id)
