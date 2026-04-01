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
            discovered_files.extend(self.ingestion.scan_directory(r))
            
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
            
            if target_name in custom_paths:
                p_val = custom_paths[target_name]
                p_list = p_val if isinstance(p_val, list) else [p_val]
                updated_paths = []
                for entry in p_list:
                    path_str = entry['path'] if isinstance(entry, dict) else entry
                    file_id = entry.get('id') if isinstance(entry, dict) else None
                    file_hash = entry.get('fp') if isinstance(entry, dict) else None
                    p_abs = Path(path_str)
                    if not p_abs.is_absolute():
                        p_base = Path(self.config_controller.config_path).parent
                        p_abs = (p_base / p_abs).absolute()
                    
                    if not p_abs.exists():
                        found_meta = None
                        for df in discovered_files:
                            if (file_id and df.get('id') == file_id) or (file_hash and df.get('fp') == file_hash):
                                found_meta = df; break
                        if found_meta:
                            p_abs = Path(found_meta['path'])
                            self.rename_detected = True
                            updated_paths.append(found_meta)
                    else:
                        try:
                            stat = os.stat(p_abs)
                            with open(p_abs, 'rb') as f: fp = hashlib.md5(f.read(8192)).hexdigest()
                            updated_paths.append({"path": str(p_abs), "id": stat.st_ino, "fp": fp})
                        except: updated_paths.append({"path": str(p_abs)})

                for meta in updated_paths:
                    p, fid, fp = str(meta.get('path')), meta.get('id'), meta.get('fp')
                    if p not in seen_paths and (not fid or fid not in seen_ids) and (not fp or fp not in seen_fps):
                        paths_for_emp.append(meta)
                        seen_paths.add(p)
                        if fid: seen_ids.add(fid)
                        if fp: seen_fps.add(fp)
                config.setdefault('employee_paths', {})[target_name] = updated_paths

            t_lower = target_name.lower()
            for d_name, files in discovered_map.items():
                if t_lower == d_name.lower():
                    for f in files:
                        p, fid, fp = str(f['path']), f.get('id'), f.get('fp')
                        if p not in seen_paths and (not fid or fid not in seen_ids) and (not fp or fp not in seen_fps):
                            paths_for_emp.append(f); seen_paths.add(p)
                            if fid: seen_ids.add(fid); 
                            if fp: seen_fps.add(fp)
            result[target_name] = paths_for_emp
        return result

