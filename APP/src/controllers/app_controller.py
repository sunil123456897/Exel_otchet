import os
import logging
import threading
import uuid
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

class AppController:
    def __init__(self, config_controller, ingestion, persistence, validator, logic_service, writer):
        self.config_controller = config_controller
        self.ingestion = ingestion
        self.persistence = persistence
        self.validator = validator
        self.logic_service = logic_service
        self.writer = writer
        
        self.rename_detected = False
        self._cached_employees = {}

    def _get_employees_map(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Logic: Prioritizes explicit manual mappings from config.yaml.
        Uses 'Smart Tracking' (File ID + Fuzzy Prefix) to follow renamed/replaced files.
        """
        config = self.config_controller.config
        config_list = config.get('employees', [])
        custom_paths = config.get('employee_paths', {})
        
        # Scan directory for discovery
        source_root = config.get('paths', {}).get('source_root')
        discovered_files = []
        if source_root:
            discovered_files = self.ingestion.scan_directory(Path(source_root))
        
        # Group discovered files by parent directory or filename
        discovered_map = {}
        for f in discovered_files:
            p = Path(f['path'])
            # Use parent directory name as employee name if it's not the root
            name = p.parent.name if str(p.parent) != source_root else p.stem
            if name not in discovered_map:
                discovered_map[name] = []
            discovered_map[name].append(f)

        result = {}
        target_names = config_list if config_list else sorted(list(set(list(discovered_map.keys()) + list(custom_paths.keys()))))
        
        self.rename_detected = False

        for target_name in target_names:
            paths_for_emp = []
            seen_paths = set()
            seen_ids = set()
            seen_fps = set()
            
            # 1. Check custom paths from config
            if target_name in custom_paths:
                p_val = custom_paths[target_name]
                p_list = p_val if isinstance(p_val, list) else [p_val]
                
                updated_paths = []
                for entry in p_list:
                    path_str = entry['path'] if isinstance(entry, dict) else entry
                    file_id = entry.get('id') if isinstance(entry, dict) else None
                    file_hash = entry.get('fp') if isinstance(entry, dict) else None
                    
                    # Convert to absolute path
                    p_abs = Path(path_str)
                    if not p_abs.is_absolute():
                        # Use parent of config file as base for relative paths
                        p_base = Path(self.config_controller.config_path).parent
                        p_abs = (p_base / p_abs).absolute()
                    
                    # SMART RECOVERY
                    if not p_abs.exists():
                        found_meta = None
                        # Try to find in discovered files by ID or Hash
                        for df in discovered_files:
                            if file_id and df.get('id') == file_id:
                                found_meta = df
                                logging.info(f"[Smart] File '{p_abs.name}' was renamed to '{Path(df['path']).name}' (ID match)")
                                break
                            if file_hash and df.get('fp') == file_hash:
                                found_meta = df
                                logging.info(f"[Smart] File '{p_abs.name}' found by fingerprint: '{Path(df['path']).name}'")
                                break
                        
                        if found_meta:
                            p_abs = Path(found_meta['path'])
                            self.rename_detected = True
                            updated_paths.append(found_meta)
                        else:
                            # Still missing
                            pass
                    else:
                        # File exists, update metadata
                        try:
                            p_abs = p_abs.resolve()
                            stat = os.stat(p_abs)
                            # Fast MD5
                            with open(p_abs, 'rb') as f:
                                fp = hashlib.md5(f.read(8192)).hexdigest()
                            
                            meta = {"path": str(p_abs), "id": stat.st_ino, "fp": fp}
                            updated_paths.append(meta)
                        except Exception:
                            updated_paths.append({"path": str(p_abs)})

                for meta in updated_paths:
                    p = str(meta['path']) if isinstance(meta, dict) else str(meta)
                    fid = meta.get('id') if isinstance(meta, dict) else None
                    fp = meta.get('fp') if isinstance(meta, dict) else None
                    
                    is_new = True
                    if p in seen_paths: is_new = False
                    if fid and fid in seen_ids: is_new = False
                    if fp and fp in seen_fps: is_new = False
                    
                    if is_new:
                        paths_for_emp.append(meta)
                        seen_paths.add(p)
                        if fid: seen_ids.add(fid)
                        if fp: seen_fps.add(fp)
                
                # Update in-memory config
                config.setdefault('employee_paths', {})[target_name] = updated_paths

            # 2. Fallback: Folder-based discovery
            t_lower = target_name.lower()
            for d_name, files in discovered_map.items():
                if t_lower == d_name.lower():
                    for f in files:
                        p = str(f['path'])
                        fid = f.get('id')
                        fp = f.get('fp')
                        
                        is_new = True
                        if p in seen_paths: is_new = False
                        if fid and fid in seen_ids: is_new = False
                        if fp and fp in seen_fps: is_new = False
                        
                        if is_new:
                            paths_for_emp.append(f)
                            seen_paths.add(p)
                            if fid: seen_ids.add(fid)
                            if fp: seen_fps.add(fp)
            
            result[target_name] = paths_for_emp
            
        return result

    def refresh_status(self, selected_date, on_progress: Callable[[float], None], on_complete: Callable[[List[tuple], Dict, bool], None]):
        """Refreshes the status of all employees for the selected date."""
        def task():
            try:
                employees_map = self._get_employees_map()
                unique_names = sorted(employees_map.keys())

                if not unique_names:
                    on_complete([], {}, False)
                    return

                ready_count = 0
                local_data = []
                total_count = len(unique_names)
                
                for i, name in enumerate(unique_names):
                    progress = ((i + 1) / total_count) * 100
                    on_progress(progress)
                    
                    metas = employees_map.get(name, [])
                    paths = [m['path'] if isinstance(m, dict) else m for m in metas]
                    paths = [p for p in paths if os.path.exists(p)]
                    
                    if not paths:
                        status, tag, path_str = "🔴 НЕТ ФАЙЛА", 'missing', "---"
                    else:
                        path_str = os.path.basename(paths[0]) if len(paths) == 1 else f"[{len(paths)} файлов]"
                        status, tag = "🟠 НЕТ ДАТЫ", 'partial'
                        try:
                            for p in paths:
                                available_dates = self.ingestion.get_available_dates(Path(p))
                                if selected_date.strftime("%d.%m.%Y") in available_dates:
                                    status, tag = "🟢 ГОТОВО", 'ready'
                                    ready_count += 1
                                    break
                        except Exception as e:
                            logging.error(f"Ошибка проверки даты для {name}: {e}")
                            status, tag = "❌ ОШИБКА", 'missing'
                    
                    local_data.append((name, status, path_str, tag))
                
                self._cached_employees = employees_map
                on_complete(local_data, employees_map, self.rename_detected)
                
            except Exception as e:
                logging.error(f"Ошибка при обновлении статуса: {e}")
        
        threading.Thread(target=task, daemon=True).start()

    def run_consolidation(self, selected_date, on_progress: Callable[[float], None], on_complete: Callable[[bool, str, Optional[Path]], None]):
        """Runs the consolidation process for a specific date."""
        def task():
            session_id = str(uuid.uuid4())
            try:
                logging.info(f"--- Сборка за {selected_date.strftime('%d.%m')} (Session: {session_id}) ---")
                
                # 1. Initialize Session
                self.persistence.save_session(session_id, {"date": selected_date.strftime("%d.%m.%Y"), "type": "daily"})
                
                # 2. Ingest Data
                employees_map = self._cached_employees
                total_files = sum(len(paths) for paths in employees_map.values())
                processed_files = 0
                
                if total_files == 0:
                    on_complete(False, "Нет файлов для обработки", None)
                    return

                for emp_name, metas in employees_map.items():
                    for meta in metas:
                        path_str = meta['path'] if isinstance(meta, dict) else meta
                        if not os.path.exists(path_str): continue
                        
                        # Save file metadata
                        file_ids = self.persistence.save_file_metadata(session_id, [meta])
                        file_id = file_ids[0]
                        
                        # Read file
                        logging.info(f"Reading {emp_name}: {os.path.basename(path_str)}")
                        rows = self.ingestion.read_file(Path(path_str))
                        
                        # Filter by date and validate
                        target_date_str = selected_date.strftime("%d.%m.%Y")
                        valid_rows = []
                        for row in rows:
                            if row.get('date') == target_date_str:
                                if self.validator.validate_row(row):
                                    row['employee_name'] = emp_name
                                    valid_rows.append(row)
                        
                        # Save to staging
                        if valid_rows:
                            self.persistence.save_staging_data(file_id, valid_rows)
                        
                        processed_files += 1
                        progress = (processed_files / total_files) * 50
                        on_progress(progress)

                # 3. Consolidate
                logging.info("Consolidating data...")
                consolidated_data = self.logic_service.consolidate(session_id)
                on_progress(75)
                
                if not consolidated_data:
                    on_complete(False, "Нет данных за выбранную дату.", None)
                    return
                
                # 4. Export
                logging.info("Exporting report...")
                master_path = Path(self.config_controller.config.get('paths', {}).get('master_file', 'Master_Report.xlsx'))
                if not master_path.is_absolute():
                    master_path = Path(self.config_controller.config_path).parent / master_path
                
                success = self.writer.write_report(consolidated_data, master_path)
                on_progress(100)
                
                if success:
                    on_complete(True, "Успешно!", master_path)
                else:
                    on_complete(False, "Ошибка при записи отчета.", None)

            except Exception as e:
                logging.error(f"Ошибка: {e}", exc_info=True)
                on_complete(False, str(e), None)

        threading.Thread(target=task, daemon=True).start()

    def run_consolidation_all_dates(self, on_progress: Callable[[float], None], on_complete: Callable[[bool, str, Optional[Path]], None]):
        """Runs the consolidation process for all available dates."""
        def task():
            session_id = str(uuid.uuid4())
            try:
                logging.info(f"--- Глобальная сборка (Session: {session_id}) ---")
                
                employees_map = self._get_employees_map()
                self._cached_employees = employees_map
                
                # Find all available dates
                all_dates = set()
                for metas in employees_map.values():
                    for meta in metas:
                        path_str = meta['path'] if isinstance(meta, dict) else meta
                        if os.path.exists(path_str):
                            dates = self.ingestion.get_available_dates(Path(path_str))
                            all_dates.update(dates)
                
                if not all_dates:
                    on_complete(False, "Даты не найдены.", None)
                    return
                
                logging.info(f"Найдено дат: {len(all_dates)}")
                
                # Initialize Session
                self.persistence.save_session(session_id, {"type": "all_dates", "date_count": len(all_dates)})
                
                # Ingest Data
                total_files = sum(len(paths) for paths in employees_map.values())
                processed_files = 0
                
                for emp_name, metas in employees_map.items():
                    for meta in metas:
                        path_str = meta['path'] if isinstance(meta, dict) else meta
                        if not os.path.exists(path_str): continue
                        
                        file_ids = self.persistence.save_file_metadata(session_id, [meta])
                        file_id = file_ids[0]
                        
                        logging.info(f"Reading {emp_name}: {os.path.basename(path_str)}")
                        rows = self.ingestion.read_file(Path(path_str))
                        
                        valid_rows = []
                        for row in rows:
                            if self.validator.validate_row(row):
                                row['employee_name'] = emp_name
                                valid_rows.append(row)
                        
                        if valid_rows:
                            self.persistence.save_staging_data(file_id, valid_rows)
                        
                        processed_files += 1
                        progress = (processed_files / total_files) * 50
                        on_progress(progress)

                # Consolidate
                logging.info("Consolidating data...")
                consolidated_data = self.logic_service.consolidate(session_id)
                template_errors = self.persistence.get_template_errors(session_id)
                on_progress(75)
                
                if not consolidated_data:
                    on_complete(False, "Нет данных для консолидации.", None)
                    return
                
                # Export
                logging.info("Exporting report...")
                master_path = Path(self.config_controller.config.get('paths', {}).get('master_file', 'Master_Report.xlsx'))
                if not master_path.is_absolute():
                    master_path = Path(self.config_controller.config_path).parent / master_path
                
                success = self.writer.write_report(consolidated_data, master_path, template_errors=template_errors)
                on_progress(100)
                
                if success:
                    on_complete(True, "Глобальная сборка завершена!", master_path)
                else:
                    on_complete(False, "Ошибка при записи отчета.", None)
            except Exception as e:
                logging.error(f"Ошибка: {e}", exc_info=True)
                on_complete(False, str(e), None)
        
        threading.Thread(target=task, daemon=True).start()
