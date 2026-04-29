import concurrent.futures
import logging
import os
import threading
import uuid
from datetime import datetime, timedelta
from collections.abc import Sequence
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

from core.infra import DiscoveryService, is_file_writable
from core.infra.utils_logging import scrub_path
from core.app.file_processor import (
    check_master_lock,
    run_engine,
    date_matches_target,
)
from core.app.controller_messages import (
    build_empty_data_message as build_controller_empty_data_message,
    build_issue_preview,
    build_success_message as build_controller_success_message,
    format_file_error_note as format_controller_file_error_note,
    normalize_consolidation_dates as normalize_controller_consolidation_dates,
)
from core.infra.rsch_report import build_rsch_report

_ADAPTIVE_WORKERS = min(32, (os.cpu_count() or 4) * 2)


class AppController:
    """Main orchestrator — coordinates file discovery, ingestion, and export."""

    def __init__(
        self,
        config_controller,
        ingestion,
        persistence,
        validator,
        logic_service,
        writer,
    ):
        self.config_controller = config_controller
        self.ingestion = ingestion
        self.persistence = persistence
        self.validator = validator
        self.logic_service = logic_service
        self.writer = writer

        self.discovery = DiscoveryService(config_controller, ingestion)
        self._lock = threading.Lock()
        self._cached_employees = {}
        self._active_threads: List[threading.Thread] = []

    @property
    def rename_detected(self):
        return self.discovery.rename_detected

    def _get_employees_map(self) -> Dict[str, List[Dict[str, Any]]]:
        """Discover and return employee-to-file mapping."""
        return self.discovery.get_employees_map()

    def _resolve_master_path(self) -> Path:
        """Resolve the output master report path."""
        fallback = Path(self.config_controller.config_path).parent / "Master_Report.xlsx"
        paths_cfg = self.config_controller.config.setdefault("paths", {})
        master_cfg = paths_cfg.get("master_file")
        if master_cfg:
            master_path = self.config_controller.resolve_path(str(master_cfg))
        else:
            master_path = fallback
            paths_cfg["master_file"] = str(fallback)
            save_config = getattr(self.config_controller, "save_config", None)
            if callable(save_config):
                save_config()
        try:
            master_path.parent.mkdir(parents=True, exist_ok=True)
            return master_path
        except OSError as e:
            logging.warning(
                "Master path unavailable (%s). Using fallback: %s",
                e,
                scrub_path(str(fallback)),
            )
            if Path(paths_cfg.get("master_file", "")) != fallback:
                paths_cfg["master_file"] = str(fallback)
                save_config = getattr(self.config_controller, "save_config", None)
                if callable(save_config):
                    save_config()
            return fallback

    def _get_curator_config(self, curator: Optional[str]) -> Optional[Dict[str, Any]]:
        if not curator:
            return None
        curators = self.config_controller.config.get("curators", {})
        if not isinstance(curators, dict):
            return None
        cfg = curators.get(curator)
        if not isinstance(cfg, dict) or not cfg.get("enabled", True):
            return None
        return cfg

    def _resolve_report_path(self, curator_config: Optional[Dict[str, Any]]) -> Path:
        if curator_config and curator_config.get("output_path"):
            return self.config_controller.resolve_path(str(curator_config["output_path"]))
        return self._resolve_master_path()

    def _is_report_writable(self, curator_config: Optional[Dict[str, Any]]) -> bool:
        if not curator_config:
            return check_master_lock(self.config_controller)
        path = self._resolve_report_path(curator_config)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False
        return is_file_writable(str(path))

    def _get_enabled_curator_employee_keys(self) -> set[str]:
        curators = self.config_controller.config.get("curators", {})
        if not isinstance(curators, dict):
            return set()

        keys = set()
        for cfg in curators.values():
            if not isinstance(cfg, dict) or not cfg.get("enabled", True):
                continue
            key = str(cfg.get("employees_key") or "").strip().lower()
            if key:
                keys.add(key)
        return keys

    @staticmethod
    def _employee_name_matches_any_key(name: str, keys: set[str]) -> bool:
        lowered_name = str(name).lower()
        return any(key in lowered_name for key in keys)

    @staticmethod
    def _filter_employees_for_curator(
        employees_map: Dict[str, List[Dict[str, Any]]],
        curator_config: Optional[Dict[str, Any]],
        general_excluded_keys: Optional[set[str]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        if not curator_config:
            excluded_keys = general_excluded_keys or set()
            if not excluded_keys:
                return employees_map
            return {
                name: metas
                for name, metas in employees_map.items()
                if not AppController._employee_name_matches_any_key(name, excluded_keys)
            }

        key = str(curator_config.get("employees_key") or "").strip().lower()
        if not key:
            return employees_map

        included_keys = {key}

        return {
            name: metas
            for name, metas in employees_map.items()
            if AppController._employee_name_matches_any_key(name, included_keys)
        }

    def _start_thread(self, target: Callable) -> None:
        """Start a task thread and track it for graceful shutdown."""
        t = threading.Thread(target=target, daemon=True)
        with self._lock:
            self._active_threads = [th for th in self._active_threads if th.is_alive()]
            self._active_threads.append(t)
        t.start()

    @staticmethod
    def _normalize_selected_datetime(selected_date) -> datetime:
        if isinstance(selected_date, datetime):
            return selected_date
        return datetime.combine(selected_date, datetime.min.time())

    @staticmethod
    def _has_target_date(
        available_dates: List[Any], target_date_obj: datetime, today: datetime
    ) -> bool:
        if target_date_obj.date() > today.date():
            return False
        for available_date in available_dates or []:
            if date_matches_target(available_date, target_date_obj):
                return True
        return False

    def _check_employee_refresh_status(
        self,
        name: str,
        employees_map: Dict[str, List[Dict[str, Any]]],
        target_date_obj: datetime,
        today: datetime,
    ) -> tuple[str, str, str, str]:
        metas = employees_map.get(name, [])
        paths = [m["path"] if isinstance(m, dict) else m for m in metas]
        paths = [p for p in paths if os.path.exists(p)]

        if not paths:
            return (name, "🔴 НЕТ ФАЙЛА", "---", "missing")

        path_str = (
            os.path.basename(paths[0]) if len(paths) == 1 else f"[{len(paths)} файлов]"
        )
        status, tag = "🟠 НЕТ ДАТЫ", "partial"

        try:
            forced_refresh_tokens = set()
            for p in paths:
                p_path = Path(p)
                stat = os.stat(p_path)
                stat_mtime = stat.st_mtime
                stat_size = stat.st_size
                cache = self.persistence.get_file_cache(str(p_path))

                cache_hit = (
                    cache
                    and cache["mtime"] == stat_mtime
                    and cache["size"] == stat_size
                )
                cache_version = int(cache.get("cache_version", 1)) if cache else 1
                needs_cache_migration = cache_hit and cache_version < 3

                if cache_hit:
                    available = cache.get("dates", [])
                    if self._has_target_date(available, target_date_obj, today) and not needs_cache_migration:
                        status, tag = "🟢 ГОТОВО", "ready"
                        break

                    force_token = (
                        str(p_path),
                        target_date_obj.strftime("%d.%m.%Y"),
                        stat_mtime,
                        stat_size,
                    )
                    if force_token not in forced_refresh_tokens:
                        forced_refresh_tokens.add(force_token)
                        available = self.ingestion.get_available_dates(
                            p_path,
                            remote_mtime=stat_mtime,
                            remote_size=stat_size,
                        )
                        self.persistence.save_file_cache(
                            str(p_path), stat_mtime, stat_size, available
                        )
                else:
                    available = self.ingestion.get_available_dates(
                        p_path,
                        remote_mtime=stat_mtime,
                        remote_size=stat_size,
                    )
                    self.persistence.save_file_cache(
                        str(p_path), stat_mtime, stat_size, available
                    )

                if self._has_target_date(available, target_date_obj, today):
                    status, tag = "🟢 ГОТОВО", "ready"
                    break
        except Exception as e:
            logging.error(f"Error {name}: {e}")
            status, tag = "[ERR] ОШИБКА", "missing"

        return (name, status, path_str, tag)

    def _run_refresh_status(
        self,
        selected_date,
        on_progress: Callable[[float], None],
        on_complete: Callable[[List[tuple], Dict, bool], None],
        on_error: Optional[Callable[[str], None]] = None,
    ) -> None:
        try:
            logging.info("[NET] Начинаю поиск файлов в сети...")
            employees_map = self._get_employees_map()
            unique_names = sorted(employees_map.keys())
            if not unique_names:
                on_complete([], {}, False)
                return

            target_date_obj = self._normalize_selected_datetime(selected_date)
            today = datetime.now()
            total_count = len(unique_names)
            local_data: List[tuple] = []

            with concurrent.futures.ThreadPoolExecutor(max_workers=_ADAPTIVE_WORKERS) as executor:
                futures = {
                    executor.submit(
                        self._check_employee_refresh_status,
                        name,
                        employees_map,
                        target_date_obj,
                        today,
                    ): name
                    for name in unique_names
                }
                for i, future in enumerate(concurrent.futures.as_completed(futures)):
                    local_data.append(future.result())
                    on_progress(((i + 1) / total_count) * 100)

            local_data.sort(key=lambda x: x[0])
            with self._lock:
                self._cached_employees = employees_map
            on_complete(local_data, employees_map, self.rename_detected)
        except Exception as e:
            logging.error(f"Refresh error: {e}")
            on_complete([], {}, False)
            if callable(on_error):
                on_error(f"Ошибка обновления статусов: {e}")

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

    def _resolve_employees_for_run(self, use_fresh_employees: bool) -> Dict[str, List[Dict[str, Any]]]:
        if use_fresh_employees:
            employees_map = self._get_employees_map()
            with self._lock:
                self._cached_employees = employees_map
            return employees_map

        with self._lock:
            employees_map = dict(self._cached_employees) if self._cached_employees else None
        if employees_map:
            return employees_map

        employees_map = self._get_employees_map()
        with self._lock:
            if not self._cached_employees:
                self._cached_employees = employees_map
        return employees_map

    @staticmethod
    def _format_file_error_note(file_errors: List[Dict[str, str]]) -> Optional[str]:
        return format_controller_file_error_note(file_errors)

    @staticmethod
    def _build_empty_data_message(
        target_date_str: Optional[str],
        start_date_str: Optional[str],
        end_date_str: Optional[str],
        range_note: Optional[str],
        file_error_note: Optional[str],
    ) -> str:
        return build_controller_empty_data_message(
            target_date_str,
            start_date_str,
            end_date_str,
            range_note,
            file_error_note,
        )

    def _build_no_files_message(self) -> str:
        raw_count = getattr(self.discovery, "last_discovered_count", 0)
        discovered_count = raw_count if isinstance(raw_count, int) else 0
        if discovered_count:
            return (
                f"Найдено {discovered_count} файл(ов), но 0 привязано к сотрудникам. "
                "Проверьте employees.yaml или привязки файлов."
            )
        return "Нет файлов"

    @staticmethod
    def _build_success_message(
        session_type: str,
        start_date_str: Optional[str],
        end_date_str: Optional[str],
        range_note: Optional[str],
        file_error_note: Optional[str],
    ) -> str:
        return build_controller_success_message(
            session_type,
            start_date_str,
            end_date_str,
            range_note,
            file_error_note,
        )

    @staticmethod
    def _normalize_consolidation_dates(
        target_date_str: Optional[str],
        start_date_str: Optional[str],
        end_date_str: Optional[str],
    ) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
        return normalize_controller_consolidation_dates(
            target_date_str,
            start_date_str,
            end_date_str,
        )

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
    ) -> None:
        session_id = str(uuid.uuid4())
        try:
            curator_config = self._get_curator_config(curator)
            effective_target_date, effective_start_date, effective_end_date, date_error, range_note = (
                self._normalize_consolidation_dates(
                    target_date_str,
                    start_date_str,
                    end_date_str,
                )
            )
            if date_error:
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
            employees_map = self._filter_employees_for_curator(
                employees_map,
                curator_config,
                self._get_enabled_curator_employee_keys(),
            )
            if not employees_map:
                self.persistence.update_session_status(session_id, "failed")
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
            ):
                self.persistence.update_session_status(session_id, "failed")
                on_complete(False, self._build_no_files_message(), None)
                return

            consolidated_data = self.logic_service.consolidate(
                session_id,
                curator=curator,
                curator_config=curator_config,
            )
            errors = self.persistence.get_template_errors(session_id)
            file_error_note = self._format_file_error_note(file_errors)

            if not consolidated_data:
                self.persistence.update_session_status(session_id, "failed")
                on_complete(
                    False,
                    self._build_empty_data_message(
                        effective_target_date,
                        effective_start_date,
                        effective_end_date,
                        range_note,
                        file_error_note,
                    ),
                    None,
                )
                return

            master_path = self._resolve_report_path(curator_config)
            write_kwargs: Dict[str, Any] = {}
            if errors:
                write_kwargs["template_errors"] = errors
            if curator_config:
                write_kwargs["curator"] = curator
                write_kwargs["curator_config"] = curator_config

            if not self.writer.write_report(consolidated_data, master_path, **write_kwargs):
                self.persistence.update_session_status(session_id, "failed")
                on_complete(False, "Ошибка записи основного отчёта", None)
                return

            logging.info("[MAIN] Основной отчёт собран: %s", scrub_path(str(master_path)))
            on_progress(100)
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
                self._build_success_message(
                    session_type,
                    effective_start_date,
                    effective_end_date,
                    range_note,
                    file_error_note,
                ),
                master_path,
            )
        except Exception as e:
            logging.error(f"Error: {e}")
            self.persistence.update_session_status(session_id, "failed")
            on_complete(False, str(e), None)

    def refresh_status(
        self,
        selected_date,
        on_progress: Callable[[float], None],
        on_complete: Callable[[List[tuple], Dict, bool], None],
        curator=None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        """Refresh employee file status for the selected date."""
        if not check_master_lock(self.config_controller):
            on_complete([], {}, False)
            msg = "Мастер-файл занят в Excel. Закройте его и повторите."
            logging.error("Master file is locked. Please close it in Excel.")
            if callable(on_error):
                on_error(msg)
            return

        def task():
            self._run_refresh_status(
                selected_date,
                on_progress,
                on_complete,
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
    ):
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
        """
        curator_config = self._get_curator_config(curator)
        if not self._is_report_writable(curator_config):
            on_complete(
                False, "Файл отчёта занят в Excel! Закройте его и повторите.", None
            )
            return

        def task():
            self._execute_consolidation(
                on_progress,
                on_complete,
                target_date_str,
                start_date_str,
                end_date_str,
                session_type,
                use_fresh_employees,
                curator,
            )

        self._start_thread(task)

    def run_consolidation(
        self,
        selected_date,
        on_progress: Callable[[float], None],
        on_complete: Callable[[bool, str, Optional[Path]], None],
        curator: Optional[str] = None,
    ):
        """Run consolidation for a single selected date."""
        self._run_consolidation_core(
            on_progress,
            on_complete,
            target_date_str=selected_date.strftime("%d.%m.%Y"),
            session_type="daily",
            curator=curator,
        )

    def run_consolidation_all_dates(
        self,
        on_progress: Callable[[float], None],
        on_complete: Callable[[bool, str, Optional[Path]], None],
        curator: Optional[str] = None,
    ):
        """Run consolidation for all available dates."""
        self._run_consolidation_core(
            on_progress,
            on_complete,
            session_type="all_dates",
            use_fresh_employees=True,
            curator=curator,
        )

    def run_consolidation_month(
        self,
        start_date,
        end_date,
        on_progress: Callable[[float], None],
        on_complete: Callable[[bool, str, Optional[Path]], None],
        curator: Optional[str] = None,
    ):
        """Run consolidation for a date range (monthly)."""
        self._run_consolidation_core(
            on_progress,
            on_complete,
            start_date_str=start_date.strftime("%d.%m.%Y"),
            end_date_str=end_date.strftime("%d.%m.%Y"),
            session_type="monthly",
            curator=curator,
        )

    def run_rsch_report(
        self,
        source_paths: Path | Sequence[Path],
        output_path: Path,
        selected_date,
        on_complete: Callable[[bool, str, Optional[Path]], None],
    ) -> None:
        """Build an RSC control report from selected workbooks."""

        def task() -> None:
            try:
                target_date = selected_date
                if hasattr(selected_date, "date"):
                    target_date = selected_date.date()

                if isinstance(source_paths, (str, Path)):
                    normalized_sources = [Path(source_paths)]
                else:
                    normalized_sources = [Path(p) for p in source_paths]

                issues: List[str] = []

                written_rows = build_rsch_report(
                    normalized_sources,
                    output_path,
                    target_date=target_date,
                    issues_sink=issues,
                )

                if issues:
                    msg = (
                        f"РСЧ отчет собран: {written_rows} строк из {len(normalized_sources)} файлов. "
                        f"Есть проблемы с листами: {build_issue_preview(issues)}"
                    )
                else:
                    msg = (
                        f"РСЧ отчет собран: {written_rows} строк из {len(normalized_sources)} файлов"
                    )

                on_complete(
                    True,
                    msg,
                    output_path,
                )
            except Exception as e:
                logging.error("RSC build error: %s", e)
                on_complete(False, f"Ошибка сборки РСЧ: {e}", None)

        self._start_thread(task)

    def run_rsch_report_period(
        self,
        source_paths: Path | Sequence[Path],
        output_path: Path,
        start_date,
        end_date,
        on_complete: Callable[[bool, str, Optional[Path]], None],
    ) -> None:
        """Build one RSC control workbook with one sheet per row date in range."""

        def task() -> None:
            try:
                start = start_date.date() if hasattr(start_date, "date") else start_date
                end = end_date.date() if hasattr(end_date, "date") else end_date

                if isinstance(source_paths, (str, Path)):
                    normalized_sources = [Path(source_paths)]
                else:
                    normalized_sources = [Path(p) for p in source_paths]

                issues: List[str] = []
                written_rows = build_rsch_report(
                    normalized_sources,
                    output_path,
                    start_date=start,
                    end_date=end,
                    issues_sink=issues,
                )

                if issues:
                    msg = (
                        f"РСЧ отчет за период собран: {written_rows} строк из {len(normalized_sources)} файлов. "
                        f"Есть проблемы с листами: {build_issue_preview(issues)}"
                    )
                else:
                    msg = (
                        f"РСЧ отчет за период собран: {written_rows} строк из "
                        f"{len(normalized_sources)} файлов"
                    )

                on_complete(True, msg, output_path)
            except Exception as e:
                logging.error("RSC period build error: %s", e)
                on_complete(False, f"Ошибка сборки РСЧ за период: {e}", None)

        self._start_thread(task)

    def run_rsch_report_period_batch(
        self,
        source_paths: Path | Sequence[Path],
        output_dir: Path,
        start_date,
        end_date,
        on_complete: Callable[[bool, str, Optional[Path]], None],
    ) -> None:
        """Build separate RSC workbooks for each date in the selected range."""

        def task() -> None:
            try:
                start = start_date.date() if hasattr(start_date, "date") else start_date
                end = end_date.date() if hasattr(end_date, "date") else end_date

                if isinstance(source_paths, (str, Path)):
                    normalized_sources = [Path(source_paths)]
                else:
                    normalized_sources = [Path(p) for p in source_paths]

                output_dir_path = Path(output_dir)
                output_dir_path.mkdir(parents=True, exist_ok=True)

                current = start
                total_rows = 0
                files_written = 0
                issues: List[str] = []
                while current <= end:
                    output_path = output_dir_path / f"РСЧ_отчет_{current.strftime('%d.%m.%Y')}.xlsx"
                    written_rows = build_rsch_report(
                        normalized_sources,
                        output_path,
                        target_date=current,
                        issues_sink=issues,
                    )
                    if written_rows:
                        total_rows += written_rows
                        files_written += 1
                    elif output_path.exists():
                        output_path.unlink()
                    current += timedelta(days=1)

                if issues:
                    msg = (
                        f"РСЧ отчеты за период собраны: {files_written} файлов, {total_rows} строк. "
                        f"Есть проблемы с листами: {build_issue_preview(issues)}"
                    )
                else:
                    msg = (
                        f"РСЧ отчеты за период собраны: {files_written} файлов, "
                        f"{total_rows} строк"
                    )

                on_complete(True, msg, output_dir_path)
            except Exception as e:
                logging.error("RSC period batch build error: %s", e)
                on_complete(False, f"Ошибка пакетной сборки РСЧ за период: {e}", None)

        self._start_thread(task)

    def run_rsch_report_batch(
        self,
        source_paths: Sequence[Path],
        output_paths: Sequence[Path],
        selected_date,
        on_complete: Callable[[bool, str, Optional[Path]], None],
    ) -> None:
        """Build separate RSC reports per source workbook."""

        def task() -> None:
            try:
                target_date = selected_date
                if hasattr(selected_date, "date"):
                    target_date = selected_date.date()

                normalized_sources = [Path(p) for p in source_paths]
                normalized_outputs = [Path(p) for p in output_paths]
                if len(normalized_sources) != len(normalized_outputs):
                    raise ValueError("Sources and outputs count mismatch")
                if len({str(path) for path in normalized_outputs}) != len(
                    normalized_outputs
                ):
                    raise ValueError("Duplicate output paths")

                total_rows = 0
                issues: List[str] = []
                for src, out in zip(normalized_sources, normalized_outputs):
                    total_rows += build_rsch_report(
                        src,
                        out,
                        target_date=target_date,
                        issues_sink=issues,
                    )

                output_dir = (
                    normalized_outputs[0].parent if normalized_outputs else None
                )

                if issues:
                    msg = (
                        f"РСЧ отчеты собраны: {len(normalized_outputs)} файлов, {total_rows} строк. "
                        f"Есть проблемы с листами: {build_issue_preview(issues)}"
                    )
                else:
                    msg = (
                        f"РСЧ отчеты собраны: {len(normalized_outputs)} файлов, "
                        f"{total_rows} строк"
                    )

                on_complete(
                    True,
                    msg,
                    output_dir,
                )
            except Exception as e:
                logging.error("RSC batch build error: %s", e)
                on_complete(False, f"Ошибка пакетной сборки РСЧ: {e}", None)

        self._start_thread(task)

    def shutdown(self):
        """Gracefully shut down: wait for threads and close DB."""
        logging.info("[APP] Завершение: ожидаю завершения записей в БД...")
        self.persistence.wait_for_writes()

        # Wait for active task threads to finish (with timeout)
        with self._lock:
            threads = list(self._active_threads)
        for t in threads:
            t.join(timeout=10)

        self.persistence.close()
        logging.info("[APP] Завершение: БД закрыта.")
