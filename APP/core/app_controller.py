import concurrent.futures
import logging
import os
import threading
import uuid
from datetime import datetime
from collections.abc import Sequence
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

from core.infra import DiscoveryService
from core.app.file_processor import (
    check_master_lock,
    run_engine,
    date_matches_target,
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
                fallback,
            )
            if Path(paths_cfg.get("master_file", "")) != fallback:
                paths_cfg["master_file"] = str(fallback)
                save_config = getattr(self.config_controller, "save_config", None)
                if callable(save_config):
                    save_config()
            return fallback

    def _start_thread(self, target: Callable) -> None:
        """Start a task thread and track it for graceful shutdown."""
        t = threading.Thread(target=target, daemon=True)
        with self._lock:
            self._active_threads = [th for th in self._active_threads if th.is_alive()]
            self._active_threads.append(t)
        t.start()

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
            try:
                logging.info("[NET] Начинаю поиск файлов в сети...")
                employees_map = self._get_employees_map()
                unique_names = sorted(employees_map.keys())
                if not unique_names:
                    on_complete([], {}, False)
                    return

                local_data, total_count = [], len(unique_names)
                target_date_obj = (
                    selected_date
                    if isinstance(selected_date, datetime)
                    else datetime.combine(selected_date, datetime.min.time())
                )
                today = datetime.now()

                def _has_target_date(available_dates: List[Any]) -> bool:
                    if target_date_obj.date() > today.date():
                        return False
                    for available_date in available_dates or []:
                        if date_matches_target(available_date, target_date_obj):
                            return True
                    return False

                def check_employee(name):
                    metas = employees_map.get(name, [])
                    paths = [m["path"] if isinstance(m, dict) else m for m in metas]
                    paths = [p for p in paths if os.path.exists(p)]

                    if not paths:
                        return (name, "🔴 НЕТ ФАЙЛА", "---", "missing")

                    path_str = (
                        os.path.basename(paths[0])
                        if len(paths) == 1
                        else f"[{len(paths)} файлов]"
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
                            needs_cache_migration = cache_hit and cache_version < 2

                            if cache_hit:
                                available = cache.get("dates", [])
                                if _has_target_date(available) and not needs_cache_migration:
                                    status, tag = "🟢 ГОТОВО", "ready"
                                    break
                                # Safety net: if cache says no date, force one re-parse once.
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

                            if _has_target_date(available):
                                status, tag = "🟢 ГОТОВО", "ready"
                                break
                    except Exception as e:
                        logging.error(f"Error {name}: {e}")
                        status, tag = "[ERR] ОШИБКА", "missing"
                    return (name, status, path_str, tag)

                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=_ADAPTIVE_WORKERS
                ) as executor:
                    futures = {
                        executor.submit(check_employee, name): name
                        for name in unique_names
                    }
                    for i, future in enumerate(
                        concurrent.futures.as_completed(futures)
                    ):
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
        if not check_master_lock(self.config_controller):
            on_complete(
                False, "Мастер-файл занят в Excel! Закройте его и повторите.", None
            )
            return

        def task():
            session_id = str(uuid.uuid4())
            try:
                today = datetime.now().date()
                range_note: Optional[str] = None
                effective_target_date = target_date_str
                effective_start_date = start_date_str
                effective_end_date = end_date_str

                if target_date_str:
                    td = datetime.strptime(target_date_str, "%d.%m.%Y").date()
                    if td > today:
                        on_complete(
                            False,
                            (
                                f"Дата {target_date_str} в будущем. "
                                "Будущие даты исключаются из сборки."
                            ),
                            None,
                        )
                        return

                if start_date_str and end_date_str:
                    sd = datetime.strptime(start_date_str, "%d.%m.%Y").date()
                    ed = datetime.strptime(end_date_str, "%d.%m.%Y").date()
                    if sd > today:
                        on_complete(
                            False,
                            (
                                f"Период {start_date_str} — {end_date_str} полностью в будущем. "
                                "Будущие даты исключаются из сборки."
                            ),
                            None,
                        )
                        return
                    if ed > today:
                        effective_end_date = today.strftime("%d.%m.%Y")
                        range_note = (
                            f"Даты после {effective_end_date} исключены "
                            "(будущие даты не учитываются)."
                        )

                # Build session metadata
                meta: Dict[str, Any] = {"type": session_type}
                if effective_target_date:
                    meta["date"] = effective_target_date
                if effective_start_date and effective_end_date:
                    meta["start_date"] = effective_start_date
                    meta["end_date"] = effective_end_date
                self.persistence.save_session(session_id, meta)

                # Discover employees
                if use_fresh_employees:
                    employees_map = self._get_employees_map()
                    with self._lock:
                        self._cached_employees = employees_map
                else:
                    with self._lock:
                        employees_map = (
                            dict(self._cached_employees)
                            if self._cached_employees
                            else None
                        )
                    if not employees_map:
                        employees_map = self._get_employees_map()
                        with self._lock:
                            if not self._cached_employees:
                                self._cached_employees = employees_map

                if not employees_map:
                    self.persistence.update_session_status(session_id, "failed")
                    on_complete(False, "Нет файлов", None)
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
                    on_complete(False, "Нет файлов", None)
                    return

                consolidated_data = self.logic_service.consolidate(session_id)
                errors = self.persistence.get_template_errors(session_id)

                file_error_note = None
                if file_errors:
                    sample = ", ".join(
                        os.path.basename(err.get("path", ""))
                        for err in file_errors[:3]
                        if err.get("path")
                    )
                    suffix = "" if len(file_errors) <= 3 else " ..."
                    if sample:
                        file_error_note = (
                            f"Не удалось обработать {len(file_errors)} файл(ов): "
                            f"{sample}{suffix}."
                        )
                    else:
                        file_error_note = (
                            f"Не удалось обработать {len(file_errors)} файл(ов)."
                        )

                if not consolidated_data:
                    self.persistence.update_session_status(session_id, "failed")
                    if effective_start_date and effective_end_date:
                        msg = (
                            f"Нет данных за период {effective_start_date} — "
                            f"{effective_end_date}"
                        )
                    elif effective_target_date:
                        msg = "Нет данных за дату"
                    else:
                        msg = "Нет данных"

                    notes = [note for note in (range_note, file_error_note) if note]
                    if notes:
                        msg = f"{msg}. {' '.join(notes)}"
                    on_complete(False, msg, None)
                    return

                master_path = self._resolve_master_path()
                write_kwargs: Dict[str, Any] = {}
                if errors:
                    write_kwargs["template_errors"] = errors
                has_actionable_warnings = any(
                    error.get("error_type") not in {"soft_structure"}
                    for error in errors
                )

                if not self.writer.write_report(
                    consolidated_data, master_path, **write_kwargs
                ):
                    self.persistence.update_session_status(session_id, "failed")
                    on_complete(False, "Ошибка записи основного отчёта", None)
                    return

                logging.info("[MAIN] Основной отчёт собран: %s", master_path)
                on_progress(100)
                has_runtime_warnings = bool(range_note or file_error_note)
                self.persistence.update_session_status(
                    session_id,
                    "completed_with_warnings"
                    if has_actionable_warnings or has_runtime_warnings
                    else "completed",
                )

                if effective_start_date and effective_end_date:
                    msg = f"Готово! ({effective_start_date} — {effective_end_date})"
                elif session_type == "all_dates":
                    msg = "Готово!"
                else:
                    msg = "Успешно!"

                notes = [note for note in (range_note, file_error_note) if note]
                if notes:
                    msg = f"{msg} {' '.join(notes)}"
                on_complete(True, msg, master_path)
            except Exception as e:
                logging.error(f"Error: {e}")
                self.persistence.update_session_status(session_id, "failed")
                on_complete(False, str(e), None)

        self._start_thread(task)

    def run_consolidation(
        self,
        selected_date,
        on_progress: Callable[[float], None],
        on_complete: Callable[[bool, str, Optional[Path]], None],
    ):
        """Run consolidation for a single selected date."""
        self._run_consolidation_core(
            on_progress,
            on_complete,
            target_date_str=selected_date.strftime("%d.%m.%Y"),
            session_type="daily",
        )

    def run_consolidation_all_dates(
        self,
        on_progress: Callable[[float], None],
        on_complete: Callable[[bool, str, Optional[Path]], None],
    ):
        """Run consolidation for all available dates."""
        self._run_consolidation_core(
            on_progress,
            on_complete,
            session_type="all_dates",
            use_fresh_employees=True,
        )

    def run_consolidation_month(
        self,
        start_date,
        end_date,
        on_progress: Callable[[float], None],
        on_complete: Callable[[bool, str, Optional[Path]], None],
    ):
        """Run consolidation for a date range (monthly)."""
        self._run_consolidation_core(
            on_progress,
            on_complete,
            start_date_str=start_date.strftime("%d.%m.%Y"),
            end_date_str=end_date.strftime("%d.%m.%Y"),
            session_type="monthly",
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
                    unique_issues = []
                    seen = set()
                    for issue in issues:
                        if issue in seen:
                            continue
                        seen.add(issue)
                        unique_issues.append(issue)

                    preview = "; ".join(unique_issues[:3])
                    if len(unique_issues) > 3:
                        preview += f"; и еще {len(unique_issues) - 3}"
                    msg = (
                        f"РСЧ отчет собран: {written_rows} строк из {len(normalized_sources)} файлов. "
                        f"Есть проблемы с листами: {preview}"
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
                    unique_issues = []
                    seen = set()
                    for issue in issues:
                        if issue in seen:
                            continue
                        seen.add(issue)
                        unique_issues.append(issue)

                    preview = "; ".join(unique_issues[:3])
                    if len(unique_issues) > 3:
                        preview += f"; и еще {len(unique_issues) - 3}"
                    msg = (
                        f"РСЧ отчеты собраны: {len(normalized_outputs)} файлов, {total_rows} строк. "
                        f"Есть проблемы с листами: {preview}"
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
