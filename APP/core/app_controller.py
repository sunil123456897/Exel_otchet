import concurrent.futures
import logging
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

from core.infra import DiscoveryService
from core.app.file_processor import check_master_lock, run_engine, get_master_path

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
        self._curator = None
        self._active_threads: List[threading.Thread] = []

    @property
    def rename_detected(self):
        return self.discovery.rename_detected

    def _get_employees_map(self, curator=None) -> Dict[str, List[Dict[str, Any]]]:
        """Discover and return employee-to-file mapping."""
        return self.discovery.get_employees_map(curator=curator)

    def _get_curator_config(self, curator=None) -> Optional[Dict[str, Any]]:
        """Return curator-specific config section, or None."""
        if not curator:
            return None
        return self.config_controller.config.get("curators", {}).get(curator)

    def _resolve_master_path(self, curator=None, curator_config=None) -> Path:
        """Resolve the output master report path."""
        if curator and curator_config:
            out = curator_config.get("output_path")
            if out:
                return self.config_controller.resolve_path(out)
        return get_master_path(self.config_controller)

    def _start_thread(self, target: Callable) -> None:
        """Start a task thread and track it for graceful shutdown."""
        t = threading.Thread(target=target, daemon=True)
        with self._lock:
            self._active_threads = [
                th for th in self._active_threads if th.is_alive()
            ]
            self._active_threads.append(t)
        t.start()

    def refresh_status(
        self,
        selected_date,
        on_progress: Callable[[float], None],
        on_complete: Callable[[List[tuple], Dict, bool], None],
        curator=None,
    ):
        """Refresh employee file status for the selected date."""
        if not check_master_lock(self.config_controller):
            on_complete([], {}, False)
            logging.error("Master file is locked. Please close it in Excel.")
            return

        with self._lock:
            self._curator = curator

        def task():
            try:
                logging.info("[NET] Начинаю поиск файлов в сети...")
                employees_map = self._get_employees_map(curator=curator)
                unique_names = sorted(employees_map.keys())
                if not unique_names:
                    on_complete([], {}, False)
                    return

                local_data, total_count = [], len(unique_names)
                target_date = selected_date.strftime("%d.%m.%Y")

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
                        for p in paths:
                            p_path = Path(p)
                            stat = os.stat(p_path)
                            cache = self.persistence.get_file_cache(str(p_path))

                            if (
                                cache
                                and cache["mtime"] == stat.st_mtime
                                and cache["size"] == stat.st_size
                            ):
                                available = cache["dates"]
                            else:
                                available = self.ingestion.get_available_dates(p_path)
                                self.persistence.save_file_cache(
                                    str(p_path), stat.st_mtime, stat.st_size, available
                                )

                            if target_date in available:
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

        self._start_thread(task)

    # ── Unified consolidation core (Item 6) ──────────────────────

    def _run_consolidation_core(
        self,
        on_progress: Callable[[float], None],
        on_complete: Callable[[bool, str, Optional[Path]], None],
        curator: Optional[str] = None,
        target_date_str: Optional[str] = None,
        start_date_str: Optional[str] = None,
        end_date_str: Optional[str] = None,
        session_type: str = "daily",
        use_fresh_employees: bool = False,
    ):
        """Core consolidation logic shared by all consolidation entry points.

        Args:
            on_progress: Progress callback (0-100).
            on_complete: Completion callback (ok, message, path).
            curator: Optional curator name.
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
                # Build session metadata
                meta: Dict[str, Any] = {"type": session_type}
                if target_date_str:
                    meta["date"] = target_date_str
                if start_date_str and end_date_str:
                    meta["start_date"] = start_date_str
                    meta["end_date"] = end_date_str
                self.persistence.save_session(session_id, meta)

                # Get employees map — thread-safe
                if use_fresh_employees:
                    employees_map = self._get_employees_map(curator=curator)
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
                        employees_map = self._get_employees_map(curator=curator)
                        with self._lock:
                            if not self._cached_employees:
                                self._cached_employees = employees_map

                if not employees_map:
                    on_complete(False, "Нет файлов", None)
                    return

                if not run_engine(
                    self.persistence,
                    self.ingestion,
                    self.validator,
                    employees_map,
                    session_id,
                    target_date_str,
                    on_progress,
                    start_date_str=start_date_str,
                    end_date_str=end_date_str,
                ):
                    on_complete(False, "Нет файлов", None)
                    return

                curator_config = self._get_curator_config(curator)
                consolidated_data = self.logic_service.consolidate(
                    session_id, curator=curator, curator_config=curator_config
                )
                errors = self.persistence.get_template_errors(session_id)
                on_progress(75)
                if not consolidated_data:
                    if start_date_str and end_date_str:
                        on_complete(
                            False,
                            f"Нет данных за период {start_date_str} — {end_date_str}",
                            None,
                        )
                    elif target_date_str:
                        on_complete(False, "Нет данных за дату", None)
                    else:
                        on_complete(False, "Нет данных", None)
                    return

                master_path = self._resolve_master_path(curator, curator_config)

                write_kwargs: Dict[str, Any] = {
                    "curator": curator,
                    "curator_config": curator_config,
                }
                if errors:
                    write_kwargs["template_errors"] = errors

                if self.writer.write_report(
                    consolidated_data, master_path, **write_kwargs
                ):
                    if start_date_str and end_date_str:
                        msg = f"Готово! ({start_date_str} — {end_date_str})"
                    elif session_type == "all_dates":
                        msg = "Готово!"
                    else:
                        msg = "Успешно!"
                    on_complete(True, msg, master_path)
                else:
                    on_complete(False, "Ошибка записи", None)
            except Exception as e:
                logging.error(f"Error: {e}")
                on_complete(False, str(e), None)

        self._start_thread(task)

    def run_consolidation(
        self,
        selected_date,
        on_progress: Callable[[float], None],
        on_complete: Callable[[bool, str, Optional[Path]], None],
        curator=None,
    ):
        """Run consolidation for a single selected date."""
        self._run_consolidation_core(
            on_progress,
            on_complete,
            curator=curator,
            target_date_str=selected_date.strftime("%d.%m.%Y"),
            session_type="daily",
        )

    def run_consolidation_all_dates(
        self,
        on_progress: Callable[[float], None],
        on_complete: Callable[[bool, str, Optional[Path]], None],
        curator=None,
    ):
        """Run consolidation for all available dates."""
        self._run_consolidation_core(
            on_progress,
            on_complete,
            curator=curator,
            session_type="all_dates",
            use_fresh_employees=True,
        )

    def run_consolidation_month(
        self,
        start_date,
        end_date,
        on_progress: Callable[[float], None],
        on_complete: Callable[[bool, str, Optional[Path]], None],
        curator=None,
    ):
        """Run consolidation for a date range (monthly)."""
        self._run_consolidation_core(
            on_progress,
            on_complete,
            curator=curator,
            start_date_str=start_date.strftime("%d.%m.%Y"),
            end_date_str=end_date.strftime("%d.%m.%Y"),
            session_type="monthly",
        )

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
