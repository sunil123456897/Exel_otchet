"""DiscoveryService — поиск файлов, rename detection, привязка к сотрудникам."""

import os
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

from core.infra.config_controller import ConfigController
from core.infra.ingestion_engine import IngestionEngine


class DiscoveryService:
    """Обнаружение файлов сотрудников и определение переименований."""

    def __init__(
        self, config_controller: ConfigController, ingestion: IngestionEngine
    ) -> None:
        self.config_controller = config_controller
        self.ingestion = ingestion
        self.rename_detected = False

    def get_employees_map(self) -> Dict[str, List[Dict[str, Any]]]:
        """Получить карту сотрудник → список файлов.

        Возвращает dict где ключ — имя сотрудника, значение — список
        метаданных файлов (path, id, fp).
        """
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

        # Optimization: Skip full SMB scan only if all employees have explicit, absolute and existing paths
        all_have_custom = False
        if config_list and all(name in custom_paths for name in config_list):
            all_paths_ok = True
            for name in config_list:
                p_val = custom_paths[name]
                p_list = p_val if isinstance(p_val, list) else [p_val]
                for entry in p_list:
                    path_str = entry["path"] if isinstance(entry, dict) else entry
                    p_abs = Path(path_str)
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
            # If the file is directly in the root folder, use the file name without extension.
            # Otherwise, assume the parent folder name is the employee's name.
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
            paths_for_emp, seen_paths, seen_ids, seen_fps = [], set(), set(), set()
            has_custom = False

            if target_name in custom_paths:
                p_val = custom_paths[target_name]
                p_list = p_val if isinstance(p_val, list) else [p_val]
                updated_paths = []
                for entry in p_list:
                    path_str = entry["path"] if isinstance(entry, dict) else entry
                    file_id = entry.get("id") if isinstance(entry, dict) else None
                    file_hash = entry.get("fp") if isinstance(entry, dict) else None

                    p_abs = Path(path_str)
                    # Resolve relative to Q: or other roots if not absolute OR if missing
                    if not p_abs.is_absolute() or not p_abs.exists():
                        found_meta = None
                        # Try suffix match (e.g. "Отчет кураторов 1/Иван/отчет.xlsx")
                        norm_path = path_str.replace("\\", "/").lower()
                        for df in discovered_files:
                            df_norm = df["path"].replace("\\", "/").lower()
                            if df_norm.endswith(norm_path):
                                found_meta = df
                                break

                        if not found_meta and (file_id or file_hash):
                            for df in discovered_files:
                                if (file_id and df.get("id") == file_id) or (
                                    file_hash
                                    and df.get("fp")
                                    and df.get("fp") == file_hash
                                ):
                                    found_meta = df
                                    break

                        if found_meta:
                            p_abs = Path(found_meta["path"])
                            self.rename_detected = True
                            updated_paths.append(found_meta)
                        elif p_abs.exists() or not p_abs.is_absolute():
                            # If it doesn't exist but is relative, try resolving relative to config_path
                            if not p_abs.is_absolute() and hasattr(
                                self.config_controller, "config_path"
                            ):
                                alt_p = (
                                    Path(self.config_controller.config_path).parent
                                    / p_abs
                                ).resolve()
                                if alt_p.exists():
                                    p_abs = alt_p

                            if p_abs.exists():
                                if isinstance(entry, dict):
                                    entry["path"] = str(p_abs)
                                    if "id" not in entry:
                                        entry["id"] = (
                                            int(
                                                hashlib.md5(
                                                    str(p_abs).encode()
                                                ).hexdigest(),
                                                16,
                                            )
                                            % 10**8
                                        )
                                    if "fp" not in entry:
                                        entry["fp"] = None
                                    updated_paths.append(entry)
                                else:
                                    updated_paths.append(
                                        {
                                            "path": str(p_abs),
                                            "id": int(
                                                hashlib.md5(
                                                    str(p_abs).encode()
                                                ).hexdigest(),
                                                16,
                                            )
                                            % 10**8,
                                            "fp": None,
                                        }
                                    )
                    else:
                        if isinstance(entry, dict):
                            if "id" not in entry:
                                entry["id"] = (
                                    int(
                                        hashlib.md5(str(p_abs).encode()).hexdigest(), 16
                                    )
                                    % 10**8
                                )
                            if "fp" not in entry:
                                entry["fp"] = None
                            updated_paths.append(entry)
                        else:
                            updated_paths.append(
                                {
                                    "path": str(p_abs),
                                    "id": int(
                                        hashlib.md5(str(p_abs).encode()).hexdigest(), 16
                                    )
                                    % 10**8,
                                    "fp": None,
                                }
                            )

                for meta in updated_paths:
                    p = str(meta.get("path"))
                    if p not in seen_paths:
                        paths_for_emp.append(meta)
                        seen_paths.add(p)

                self.config_controller.employees[target_name] = updated_paths
                self.config_controller._save_employees()
                if paths_for_emp:
                    has_custom = True

            # Only auto-discover if no custom paths were successfully bound
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
