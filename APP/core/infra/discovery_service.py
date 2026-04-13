import os
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Any

from core.infra.config_controller import ConfigController
from core.infra.ingestion_engine import IngestionEngine
from core.infra.path_resolver import resolve_employee_path


class DiscoveryService:
    def __init__(
        self, config_controller: ConfigController, ingestion: IngestionEngine
    ) -> None:
        self.config_controller = config_controller
        self.ingestion = ingestion
        self.rename_detected = False

    def get_employees_map(self) -> Dict[str, List[Dict[str, Any]]]:
        config = self.config_controller.config
        custom_paths = self.config_controller.employees
        config_list = sorted(custom_paths.keys())

        paths_config = config.get("paths", {})
        sr_val = paths_config.get("source_roots") or paths_config.get("source_root")
        roots_to_scan = (
            [Path(r) for r in sr_val]
            if isinstance(sr_val, list)
            else [Path(sr_val)]
            if sr_val
            else []
        )
        root_strings = [str(r) for r in roots_to_scan]

        all_have_custom = False
        if config_list and all(name in custom_paths for name in config_list):
            all_paths_ok = True
            for name in config_list:
                p_val = custom_paths[name]
                p_list = p_val if isinstance(p_val, list) else [p_val]
                for entry in p_list:
                    path_str = entry["path"] if isinstance(entry, dict) else entry
                    resolved, _, _ = resolve_employee_path(
                        path_str,
                        file_id=entry.get("id") if isinstance(entry, dict) else None,
                        file_hash=entry.get("fp") if isinstance(entry, dict) else None,
                        discovered_files=[],
                        config_controller=self.config_controller,
                    )
                    p_abs = Path(resolved)
                    if not p_abs.is_absolute() or not p_abs.exists():
                        all_paths_ok = False
                        break
                if not all_paths_ok:
                    break
            all_have_custom = all_paths_ok

        discovered_files = []
        if not all_have_custom:
            for r in roots_to_scan:
                try:
                    logging.info(f"[NET] Сканирую сетевой путь: {r}")
                    files = self.ingestion.scan_directory(r)
                    discovered_files.extend(files)
                    logging.info(f"[NET] Найдено файлов в {r.name}: {len(files)}")
                except Exception as e:
                    logging.error(f"[NET] Ошибка доступа к {r}: {e}")
        else:
            logging.info(
                "[NET] Все сотрудники привязаны, пропускаю полное сканирование сети."
            )

        discovered_map = {}
        for f in discovered_files:
            p = Path(f["path"])
            name = p.stem if str(p.parent) in root_strings else p.parent.name
            discovered_map.setdefault(name, []).append(f)

        result = {}
        target_names = (
            config_list
            if config_list
            else sorted(
                list(set(list(discovered_map.keys()) + list(custom_paths.keys())))
            )
        )
        self.rename_detected = False

        for target_name in target_names:
            paths_for_emp, seen_paths = [], set()
            has_custom = False

            if target_name in custom_paths:
                p_val = custom_paths[target_name]
                p_list = p_val if isinstance(p_val, list) else [p_val]
                updated_paths = []
                config_changed = False

                for entry in p_list:
                    path_str = entry["path"] if isinstance(entry, dict) else entry
                    file_id = entry.get("id") if isinstance(entry, dict) else None
                    file_hash = entry.get("fp") if isinstance(entry, dict) else None

                    resolved, meta, renamed = resolve_employee_path(
                        path_str,
                        file_id=file_id,
                        file_hash=file_hash,
                        discovered_files=discovered_files,
                        config_controller=self.config_controller,
                    )

                    if renamed:
                        self.rename_detected = True
                        config_changed = True
                        stored_entry = meta if meta else {"path": resolved}
                        updated_paths.append(stored_entry)
                    elif meta:
                        stored_entry = dict(entry) if isinstance(entry, dict) else entry
                        updated_paths.append(stored_entry)
                    else:
                        p_abs = Path(resolved)
                        if p_abs.exists():
                            entry_meta = {"path": str(p_abs)}
                            if file_id is not None:
                                entry_meta["id"] = file_id
                            if file_hash is not None:
                                entry_meta["fp"] = file_hash
                            stored_entry = dict(entry) if isinstance(entry, dict) else entry
                            updated_paths.append(stored_entry)
                            meta = entry_meta

                    if meta:
                        p = str(meta.get("path"))
                        if p not in seen_paths:
                            paths_for_emp.append(meta)
                            seen_paths.add(p)
                            has_custom = True

                deduped_paths = []
                seen_stored_paths = set()
                for meta in updated_paths:
                    p = meta["path"] if isinstance(meta, dict) else str(meta)
                    if p not in seen_stored_paths:
                        deduped_paths.append(meta)
                        seen_stored_paths.add(p)

                if config_changed and deduped_paths != self.config_controller.employees.get(
                    target_name, []
                ):
                    self.config_controller.employees[target_name] = deduped_paths
                    self.config_controller._save_employees()

            if not has_custom:
                t_lower = target_name.lower()
                for d_name, files in discovered_map.items():
                    if t_lower == d_name.lower():
                        for f in files:
                            p = str(f["path"])
                            if p not in seen_paths:
                                paths_for_emp.append(f)
                                seen_paths.add(p)

            result[target_name] = paths_for_emp

        return result
