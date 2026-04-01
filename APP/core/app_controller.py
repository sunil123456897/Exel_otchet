import os
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
from core.infra.discovery_service import DiscoveryService

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

    def refresh_status(self, selected_date, on_progress: Callable[[float], None], on_complete: Callable[[List[tuple], Dict, bool], None]):
        def task():
            try:
                employees_map = self._get_employees_map()
                unique_names = sorted(employees_map.keys())
                if not unique_names:
                    on_complete([], {}, False); return

                local_data, total_count = [], len(unique_names)
                for i, name in enumerate(unique_names):
                    on_progress(((i + 1) / total_count) * 100)
                    metas = employees_map.get(name, [])
                    paths = [m['path'] if isinstance(m, dict) else m for m in metas]
                    paths = [p for p in paths if os.path.exists(p)]
                    
                    if not paths: status, tag, path_str = "🔴 НЕТ ФАЙЛА", 'missing', "---"
                    else:
                        path_str = os.path.basename(paths[0]) if len(paths) == 1 else f"[{len(paths)} файлов]"
                        status, tag = "🟠 НЕТ ДАТЫ", 'partial'
                        try:
                            target_date = selected_date.strftime("%d.%m.%Y")
                            for p in paths:
                                available = self.ingestion.get_available_dates(Path(p))
                                if target_date in available:
                                    status, tag = "🟢 ГОТОВО", 'ready'
                                    break
                                logging.info(f"🗓️ {os.path.basename(p)}: {available}")
                        except Exception as e:
                            logging.error(f"Error {name}: {e}"); status, tag = "❌ ОШИБКА", 'missing'
                    local_data.append((name, status, path_str, tag))
                self._cached_employees = employees_map
                on_complete(local_data, employees_map, self.rename_detected)
            except Exception as e: logging.error(f"Refresh error: {e}")
        threading.Thread(target=task, daemon=True).start()

    def _run_engine(self, session_id, employees_map, target_date_str, on_progress):
        total_files = sum(len(paths) for paths in employees_map.values())
        processed_files = 0
        if total_files == 0: return False

        for emp_name, metas in employees_map.items():
            for meta in metas:
                path_str = meta['path'] if isinstance(meta, dict) else meta
                if not os.path.exists(path_str): continue
                
                file_id = self.persistence.save_file_metadata(session_id, [meta])[0]
                rows = self.ingestion.read_file(Path(path_str))
                valid_rows = []
                for row in rows:
                    if (not target_date_str or row.get('date') == target_date_str) and self.validator.validate_row(row):
                        row['employee_name'] = emp_name
                        valid_rows.append(row)
                if valid_rows: self.persistence.save_staging_data(file_id, valid_rows)
                processed_files += 1
                on_progress((processed_files / total_files) * 50)
        return True

    def run_consolidation(self, selected_date, on_progress: Callable[[float], None], on_complete: Callable[[bool, str, Optional[Path]], None]):
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

