import os
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Tuple

class DiscoveryService:
    def __init__(self, config_controller, ingestion):
        self.config_controller = config_controller
        self.ingestion = ingestion
        self.rename_detected = False

    def get_employees_map(self) -> Dict[str, List[Dict[str, Any]]]:
        config = self.config_controller.config
        config_list = config.get('employees', [])
        custom_paths = config.get('employee_paths', {})
        
        paths_config = config.get('paths', {})
        sr_val = paths_config.get('source_roots') or paths_config.get('source_root')
        roots_to_scan = [Path(r) for r in sr_val] if isinstance(sr_val, list) else [Path(sr_val)] if sr_val else []
        root_strings = [str(r) for r in roots_to_scan]

        discovered_files = []
        for r in roots_to_scan:
            try:
                logging.info(f"📡 Сканирую сетевой путь: {r}")
                files = self.ingestion.scan_directory(r)
                discovered_files.extend(files)
                logging.info(f"✅ Найдено файлов в {r.name}: {len(files)}")
            except Exception as e:
                logging.error(f"❌ Ошибка доступа к {r}: {e}")
            
        discovered_map = {}
        for f in discovered_files:
            p = Path(f['path'])
            # If the file is directly in the root folder, use the file name without extension. 
            # Otherwise, assume the parent folder name is the employee's name.
            name = p.stem if str(p.parent) in root_strings else p.parent.name
            discovered_map.setdefault(name, []).append(f)

        result = {}
        target_names = config_list if config_list else sorted(list(set(list(discovered_map.keys()) + list(custom_paths.keys()))))
        self.rename_detected = False

        for target_name in target_names:
            paths_for_emp, seen_paths, seen_ids, seen_fps = [], set(), set(), set()
            has_custom = False
            
            if target_name in custom_paths:
                p_val = custom_paths[target_name]
                p_list = p_val if isinstance(p_val, list) else [p_val]
                updated_paths = []
                for entry in p_list:
                    path_str = entry['path'] if isinstance(entry, dict) else entry
                    file_id = entry.get('id') if isinstance(entry, dict) else None
                    file_hash = entry.get('fp') if isinstance(entry, dict) else None
                    
                    p_abs = Path(path_str)
                    # Resolve relative to Q: or other roots if not absolute OR if missing
                    if not p_abs.is_absolute() or not p_abs.exists():
                        found_meta = None
                        # Try suffix match (e.g. "Отчет кураторов 1/Иван/отчет.xlsx")
                        norm_path = path_str.replace('\\', '/').lower()
                        for df in discovered_files:
                            df_norm = df['path'].replace('\\', '/').lower()
                            if df_norm.endswith(norm_path):
                                found_meta = df; break
                        
                        if not found_meta and (file_id or file_hash):
                            for df in discovered_files:
                                if (file_id and df.get('id') == file_id) or (file_hash and df.get('fp') and df.get('fp') == file_hash):
                                    found_meta = df; break
                        
                        if found_meta:
                            p_abs = Path(found_meta['path'])
                            self.rename_detected = True
                            updated_paths.append(found_meta)
                        elif p_abs.exists():
                            # It was absolute and it exists
                            updated_paths.append(entry if isinstance(entry, dict) else {"path": str(p_abs)})
                    else:
                        updated_paths.append(entry if isinstance(entry, dict) else {"path": str(p_abs)})

                for meta in updated_paths:
                    p = str(meta.get('path'))
                    if p not in seen_paths:
                        paths_for_emp.append(meta); seen_paths.add(p)
                
                config.setdefault('employee_paths', {})[target_name] = updated_paths
                if paths_for_emp: has_custom = True

            # Only auto-discover if no custom paths were successfully bound
            if not has_custom:
                t_lower = target_name.lower()
                for d_name, files in discovered_map.items():
                    if t_lower == d_name.lower():
                        for f in files:
                            p = str(f['path'])
                            if p not in seen_paths:
                                paths_for_emp.append(f); seen_paths.add(p)
            
            result[target_name] = paths_for_emp
        return result
