import os
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from core.infra.discovery_service import DiscoveryService

import concurrent.futures

class AppController:
    def __init__(self, config_controller, ingestion, persistence, validator, logic_service, writer):
        self.config_controller = config_controller
        self.ingestion = ingestion
        self.persistence = persistence
        self.validator = validator
        self.logic_service = logic_service
        self.writer = writer
        
        self.discovery = DiscoveryService(config_controller, ingestion)
        self._cached_employees = {}

    @property
    def rename_detected(self):
        return self.discovery.rename_detected

    def _get_employees_map(self) -> Dict[str, List[Dict[str, Any]]]:
        return self.discovery.get_employees_map()

    def _check_master_lock(self) -> bool:
        """Check if master file is accessible for writing."""
        master_path = Path(self.config_controller.config.get('paths', {}).get('master_file', 'Master_Report.xlsx'))
        if not master_path.is_absolute():
            master_path = Path(self.config_controller.config_path).parent / master_path
        
        if master_path.exists():
            try:
                with open(master_path, 'a'): pass
                return True
            except (IOError, PermissionError):
                return False
        return True

    def refresh_status(self, selected_date, on_progress: Callable[[float], None], on_complete: Callable[[List[tuple], Dict, bool], None]):
        if not self._check_master_lock():
            on_complete([], {}, False)
            logging.error("Master file is locked. Please close it in Excel.")
            return

        def task():
            try:
                logging.info("📡 Начинаю поиск файлов в сети...")
                employees_map = self._get_employees_map()
                unique_names = sorted(employees_map.keys())
                if not unique_names:
                    on_complete([], {}, False); return

                local_data, total_count = [], len(unique_names)
                target_date = selected_date.strftime("%d.%m.%Y")
                
                def check_employee(name):
                    metas = employees_map.get(name, [])
                    paths = [m['path'] if isinstance(m, dict) else m for m in metas]
                    paths = [p for p in paths if os.path.exists(p)]
                    
                    if not paths: return (name, "🔴 НЕТ ФАЙЛА", "---", 'missing')
                    
                    path_str = os.path.basename(paths[0]) if len(paths) == 1 else f"[{len(paths)} файлов]"
                    status, tag = "🟠 НЕТ ДАТЫ", 'partial'
                    try:
                        for p in paths:
                            p_path = Path(p)
                            stat = os.stat(p_path)
                            cache = self.persistence.get_file_cache(str(p_path))
                            
                            if cache and cache['mtime'] == stat.st_mtime and cache['size'] == stat.st_size:
                                available = cache['dates']
                            else:
                                available = self.ingestion.get_available_dates(p_path)
                                self.persistence.save_file_cache(str(p_path), stat.st_mtime, stat.st_size, available)
                            
                            if target_date in available:
                                status, tag = "🟢 ГОТОВО", 'ready'
                                break
                    except Exception as e:
                        logging.error(f"Error {name}: {e}"); status, tag = "❌ ОШИБКА", 'missing'
                    return (name, status, path_str, tag)

                # Use ThreadPoolExecutor for parallel network scanning
                with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                    futures = {executor.submit(check_employee, name): name for name in unique_names}
                    for i, future in enumerate(concurrent.futures.as_completed(futures)):
                        local_data.append(future.result())
                        on_progress(((i + 1) / total_count) * 100)
                
                # Restore original order
                local_data.sort(key=lambda x: x[0])
                self._cached_employees = employees_map
                on_complete(local_data, employees_map, self.rename_detected)
            except Exception as e: 
                logging.error(f"Refresh error: {e}")
                on_complete([], {}, False)
        threading.Thread(target=task, daemon=True).start()

    def _run_engine(self, session_id, employees_map, target_date_str, on_progress, start_date_str=None, end_date_str=None):
        total_files = sum(len(paths) for paths in employees_map.values())
        if total_files == 0: return False

        def process_file_task(emp_name, meta):
            path_str = meta['path'] if isinstance(meta, dict) else meta
            if not os.path.exists(path_str):
                return 0

            logging.info(f"Processing file {path_str}")
            file_ids = self.persistence.save_file_metadata(session_id, [meta])
            file_id = file_ids[0]

            rows = self.ingestion.read_file(Path(path_str))
            valid_rows = []
            for row in rows:
                row_date = row.get('date')
                if not row_date:
                    continue
                # Date filtering: single date, range, or all
                if target_date_str:
                    date_match = (row_date == target_date_str)
                elif start_date_str and end_date_str:
                    try:
                        rd = datetime.strptime(row_date, "%d.%m.%Y")
                        sd = datetime.strptime(start_date_str, "%d.%m.%Y")
                        ed = datetime.strptime(end_date_str, "%d.%m.%Y")
                        date_match = (sd <= rd <= ed)
                    except ValueError:
                        date_match = False
                else:
                    date_match = True  # all dates

                if date_match and self.validator.validate_row(row):
                    row['employee_name'] = emp_name
                    valid_rows.append(row)

            if valid_rows:
                self.persistence.save_staging_data(file_id, valid_rows)
            return len(valid_rows)

        processed_files = 0
        total_rows_processed = 0
        
        # Parallel file processing
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(32, (os.cpu_count() or 4) * 2)) as executor:
            future_to_file = {}
            for emp_name, metas in employees_map.items():
                for meta in metas:
                    future = executor.submit(process_file_task, emp_name, meta)
                    future_to_file[future] = meta
            
            for future in concurrent.futures.as_completed(future_to_file):
                try:
                    total_rows_processed += future.result()
                except Exception as e:
                    logging.error(f"Failed to process file: {e}")
                
                processed_files += 1
                on_progress((processed_files / total_files) * 50)

        # Ensure all queued DB writes are completed
        self.persistence.wait_for_writes()
        logging.info(f"Ingestion complete. Total valid rows processed: {total_rows_processed}")
        return True

    def run_consolidation(self, selected_date, on_progress: Callable[[float], None], on_complete: Callable[[bool, str, Optional[Path]], None]):
        if not self._check_master_lock():
            on_complete(False, "Мастер-файл занят в Excel! Закройте его и повторите.", None)
            return
        def task():
            session_id = str(uuid.uuid4())
            try:
                date_str = selected_date.strftime("%d.%m.%Y")
                self.persistence.save_session(session_id, {"date": date_str, "type": "daily"})
                if not self._run_engine(session_id, self._cached_employees, date_str, on_progress):
                    on_complete(False, "Нет файлов", None); return

                consolidated_data = self.logic_service.consolidate(session_id)
                on_progress(75)
                if not consolidated_data:
                    on_complete(False, "Нет данных за дату", None); return
                
                master_path = Path(self.config_controller.config.get('paths', {}).get('master_file', 'Master_Report.xlsx'))
                if not master_path.is_absolute(): master_path = Path(self.config_controller.config_path).parent / master_path
                
                if self.writer.write_report(consolidated_data, master_path): on_complete(True, "Успешно!", master_path)
                else: on_complete(False, "Ошибка записи", None)
            except Exception as e: logging.error(f"Error: {e}"); on_complete(False, str(e), None)
        threading.Thread(target=task, daemon=True).start()

    def run_consolidation_all_dates(self, on_progress: Callable[[float], None], on_complete: Callable[[bool, str, Optional[Path]], None]):
        if not self._check_master_lock():
            on_complete(False, "Мастер-файл занят в Excel! Закройте его и повторите.", None)
            return
        def task():
            session_id = str(uuid.uuid4())
            try:
                employees_map = self._get_employees_map()
                self._cached_employees = employees_map
                self.persistence.save_session(session_id, {"type": "all_dates"})
                if not self._run_engine(session_id, employees_map, None, on_progress):
                    on_complete(False, "Нет файлов", None); return

                consolidated_data = self.logic_service.consolidate(session_id)
                errors = self.persistence.get_template_errors(session_id)
                on_progress(75)
                if not consolidated_data:
                    on_complete(False, "Нет данных", None); return
                
                master_path = Path(self.config_controller.config.get('paths', {}).get('master_file', 'Master_Report.xlsx'))
                if not master_path.is_absolute(): master_path = Path(self.config_controller.config_path).parent / master_path
                
                if self.writer.write_report(consolidated_data, master_path, template_errors=errors):
                    on_complete(True, "Готово!", master_path)
                else: on_complete(False, "Ошибка записи", None)
            except Exception as e: logging.error(f"Error: {e}"); on_complete(False, str(e), None)
        threading.Thread(target=task, daemon=True).start()

    def run_consolidation_month(self, start_date, end_date, on_progress: Callable[[float], None], on_complete: Callable[[bool, str, Optional[Path]], None]):
        """Консолидация за диапазон дат (например, месяц)."""
        if not self._check_master_lock():
            on_complete(False, "Мастер-файл занят в Excel! Закройте его и повторите.", None)
            return
        def task():
            session_id = str(uuid.uuid4())
            try:
                start_str = start_date.strftime("%d.%m.%Y")
                end_str = end_date.strftime("%d.%m.%Y")
                self.persistence.save_session(session_id, {"start_date": start_str, "end_date": end_str, "type": "monthly"})

                employees_map = self._cached_employees or self._get_employees_map()
                if not employees_map:
                    on_complete(False, "Нет файлов", None); return

                if not self._run_engine(session_id, employees_map, None, on_progress, start_date_str=start_str, end_date_str=end_str):
                    on_complete(False, "Нет файлов", None); return

                consolidated_data = self.logic_service.consolidate(session_id)
                on_progress(75)
                if not consolidated_data:
                    on_complete(False, f"Нет данных за период {start_str} — {end_str}", None); return

                master_path = Path(self.config_controller.config.get('paths', {}).get('master_file', 'Master_Report.xlsx'))
                if not master_path.is_absolute(): master_path = Path(self.config_controller.config_path).parent / master_path

                if self.writer.write_report(consolidated_data, master_path):
                    on_complete(True, f"Готово! ({start_str} — {end_str})", master_path)
                else:
                    on_complete(False, "Ошибка записи", None)
            except Exception as e:
                logging.error(f"Error: {e}")
                on_complete(False, str(e), None)
        threading.Thread(target=task, daemon=True).start()
