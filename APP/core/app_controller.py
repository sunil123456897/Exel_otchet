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


class AppController:
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

    @property
    def rename_detected(self):
        return self.discovery.rename_detected

    def _get_employees_map(self, curator=None) -> Dict[str, List[Dict[str, Any]]]:
        return self.discovery.get_employees_map(curator=curator)

    def _get_curator_config(self, curator=None) -> Optional[Dict[str, Any]]:
        if not curator:
            return None
        return self.config_controller.config.get("curators", {}).get(curator)

    def _resolve_master_path(self, curator=None, curator_config=None) -> Path:
        if curator and curator_config:
            out = curator_config.get("output_path")
            if out:
                return self.config_controller.resolve_path(out)
        return get_master_path(self.config_controller)

    def refresh_status(
        self,
        selected_date,
        on_progress: Callable[[float], None],
        on_complete: Callable[[List[tuple], Dict, bool], None],
        curator=None,
    ):
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

                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
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

        threading.Thread(target=task, daemon=True).start()

    def run_consolidation(
        self,
        selected_date,
        on_progress: Callable[[float], None],
        on_complete: Callable[[bool, str, Optional[Path]], None],
        curator=None,
    ):
        if not check_master_lock(self.config_controller):
            on_complete(
                False, "Мастер-файл занят в Excel! Закройте его и повторите.", None
            )
            return

        def task():
            session_id = str(uuid.uuid4())
            try:
                date_str = selected_date.strftime("%d.%m.%Y")
                self.persistence.save_session(
                    session_id, {"date": date_str, "type": "daily"}
                )
                with self._lock:
                    cached = dict(self._cached_employees)
                if not run_engine(
                    self.persistence,
                    self.ingestion,
                    self.validator,
                    cached,
                    session_id,
                    date_str,
                    on_progress,
                ):
                    on_complete(False, "Нет файлов", None)
                    return

                curator_config = self._get_curator_config(curator)
                consolidated_data = self.logic_service.consolidate(
                    session_id, curator=curator, curator_config=curator_config
                )
                on_progress(75)
                if not consolidated_data:
                    on_complete(False, "Нет данных за дату", None)
                    return

                master_path = self._resolve_master_path(curator, curator_config)

                if self.writer.write_report(
                    consolidated_data,
                    master_path,
                    curator=curator,
                    curator_config=curator_config,
                ):
                    on_complete(True, "Успешно!", master_path)
                else:
                    on_complete(False, "Ошибка записи", None)
            except Exception as e:
                logging.error(f"Error: {e}")
                on_complete(False, str(e), None)

        threading.Thread(target=task, daemon=True).start()

    def run_consolidation_all_dates(
        self,
        on_progress: Callable[[float], None],
        on_complete: Callable[[bool, str, Optional[Path]], None],
        curator=None,
    ):
        if not check_master_lock(self.config_controller):
            on_complete(
                False, "Мастер-файл занят в Excel! Закройте его и повторите.", None
            )
            return

        def task():
            session_id = str(uuid.uuid4())
            try:
                employees_map = self._get_employees_map(curator=curator)
                with self._lock:
                    self._cached_employees = employees_map
                self.persistence.save_session(session_id, {"type": "all_dates"})
                if not run_engine(
                    self.persistence,
                    self.ingestion,
                    self.validator,
                    employees_map,
                    session_id,
                    None,
                    on_progress,
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
                    on_complete(False, "Нет данных", None)
                    return

                master_path = self._resolve_master_path(curator, curator_config)

                if self.writer.write_report(
                    consolidated_data,
                    master_path,
                    template_errors=errors,
                    curator=curator,
                    curator_config=curator_config,
                ):
                    on_complete(True, "Готово!", master_path)
                else:
                    on_complete(False, "Ошибка записи", None)
            except Exception as e:
                logging.error(f"Error: {e}")
                on_complete(False, str(e), None)

        threading.Thread(target=task, daemon=True).start()

    def run_consolidation_month(
        self,
        start_date,
        end_date,
        on_progress: Callable[[float], None],
        on_complete: Callable[[bool, str, Optional[Path]], None],
        curator=None,
    ):
        if not check_master_lock(self.config_controller):
            on_complete(
                False, "Мастер-файл занят в Excel! Закройте его и повторите.", None
            )
            return

        def task():
            session_id = str(uuid.uuid4())
            try:
                start_str = start_date.strftime("%d.%m.%Y")
                end_str = end_date.strftime("%d.%m.%Y")
                self.persistence.save_session(
                    session_id,
                    {"start_date": start_str, "end_date": end_str, "type": "monthly"},
                )

                with self._lock:
                    employees_map = dict(self._cached_employees) if self._cached_employees else None
                if not employees_map:
                    employees_map = self._get_employees_map(curator=curator)
                if not employees_map:
                    on_complete(False, "Нет файлов", None)
                    return

                if not run_engine(
                    self.persistence,
                    self.ingestion,
                    self.validator,
                    employees_map,
                    session_id,
                    None,
                    on_progress,
                    start_date_str=start_str,
                    end_date_str=end_str,
                ):
                    on_complete(False, "Нет файлов", None)
                    return

                curator_config = self._get_curator_config(curator)
                consolidated_data = self.logic_service.consolidate(
                    session_id, curator=curator, curator_config=curator_config
                )
                on_progress(75)
                if not consolidated_data:
                    on_complete(
                        False, f"Нет данных за период {start_str} — {end_str}", None
                    )
                    return

                master_path = self._resolve_master_path(curator, curator_config)

                if self.writer.write_report(
                    consolidated_data,
                    master_path,
                    curator=curator,
                    curator_config=curator_config,
                ):
                    on_complete(True, f"Готово! ({start_str} — {end_str})", master_path)
                else:
                    on_complete(False, "Ошибка записи", None)
            except Exception as e:
                logging.error(f"Error: {e}")
                on_complete(False, str(e), None)

        threading.Thread(target=task, daemon=True).start()

    def shutdown(self):
        logging.info("[APP] Завершение: ожидаю завершения записей в БД...")
        self.persistence.wait_for_writes()
        self.persistence.close()
        logging.info("[APP] Завершение: БД закрыта.")
