import os
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Any

from core.infra.config_controller import ConfigController
from core.infra.ingestion_engine import IngestionEngine
from core.infra.path_resolver import resolve_employee_path


class DiscoveryService:
    _DEFAULT_CURATOR_ROOTS = (
        "Отчет кураторов 1",
        "Отчет кураторов 2",
        "Отчет кураторов 3",
    )

    def __init__(
        self, config_controller: ConfigController, ingestion: IngestionEngine
    ) -> None:
        self.config_controller = config_controller
        self.ingestion = ingestion
        self.rename_detected = False

    @staticmethod
    def _copy_config_entry(entry):
        return dict(entry) if isinstance(entry, dict) else entry

    @staticmethod
    def _append_unique(entries, entry, seen):
        path_value = entry["path"] if isinstance(entry, dict) else str(entry)
        if path_value not in seen:
            entries.append(entry)
            seen.add(path_value)

    def _detect_default_roots(self, config: Dict[str, Any]) -> List[Path]:
        network_cfg = config.get("network", {}) if hasattr(config, "get") else {}
        drive_letters = network_cfg.get("drive_letters", ["Q"])
        if not isinstance(drive_letters, list) or not drive_letters:
            drive_letters = ["Q"]

        roots: List[Path] = []
        for drive_letter in drive_letters:
            drive = str(drive_letter).strip().upper().rstrip(":\\/")
            if not drive:
                continue
            for folder_name in self._DEFAULT_CURATOR_ROOTS:
                candidate = Path(f"{drive}:/") / folder_name
                if candidate.exists():
                    roots.append(candidate)

        # dedupe while preserving order
        deduped: List[Path] = []
        seen = set()
        for root in roots:
            key = str(root)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(root)
        return deduped

    def _resolve_roots_to_scan(self, config: Dict[str, Any]) -> List[Path]:
        paths_config = config.get("paths", {}) if hasattr(config, "get") else {}
        if hasattr(paths_config, "get"):
            sr_val = paths_config.get("source_roots") or paths_config.get("source_root")
        else:
            sr_val = None
        roots_to_scan = (
            [Path(r) for r in sr_val]
            if isinstance(sr_val, list)
            else [Path(sr_val)]
            if sr_val
            else []
        )

        if not roots_to_scan:
            auto_roots = self._detect_default_roots(config)
            if auto_roots:
                roots_to_scan = auto_roots
                logging.info(
                    "[NET] source_roots не заданы, использую автодетект: %s",
                    ", ".join(str(r) for r in roots_to_scan),
                )
            return roots_to_scan

        is_legacy_reports = isinstance(sr_val, str) and sr_val.strip().upper().endswith(
            "REPORTS"
        )
        if not is_legacy_reports:
            return roots_to_scan

        unresolved_root = roots_to_scan[0]
        if unresolved_root.exists():
            return roots_to_scan

        auto_roots = self._detect_default_roots(config)
        if auto_roots:
            roots_to_scan = auto_roots
            logging.info(
                "[NET] Локальный source_root недоступен, переключаюсь на: %s",
                ", ".join(str(r) for r in roots_to_scan),
            )
        return roots_to_scan

    def _all_custom_paths_available(
        self, config_list: List[str], custom_paths: Dict[str, Any]
    ) -> bool:
        if not config_list or not all(name in custom_paths for name in config_list):
            return False

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
                    return False
        return True

    def _scan_discovered_files(
        self, roots_to_scan: List[Path], all_have_custom: bool
    ) -> List[Dict[str, Any]]:
        discovered_files: List[Dict[str, Any]] = []
        if all_have_custom:
            logging.info(
                "[NET] Все сотрудники привязаны, пропускаю полное сканирование сети."
            )
            return discovered_files

        for root in roots_to_scan:
            try:
                logging.info(f"[NET] Сканирую сетевой путь: {root}")
                files = self.ingestion.scan_directory(root)
                discovered_files.extend(files)
                logging.info(f"[NET] Найдено файлов в {root.name}: {len(files)}")
            except Exception as e:
                logging.error(f"[NET] Ошибка доступа к {root}: {e}")
        return discovered_files

    def _resolve_custom_paths_for_employee(
        self, target_name: str, custom_paths: Dict[str, Any], discovered_files: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        if target_name not in custom_paths:
            return []

        paths_for_emp: List[Dict[str, Any]] = []
        seen_result_paths = set()

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
                updated_paths.append(meta if meta else {"path": resolved})
            elif meta:
                updated_paths.append(self._copy_config_entry(entry))
            else:
                p_abs = Path(resolved)
                if p_abs.exists():
                    entry_meta = {"path": str(p_abs)}
                    if file_id is not None:
                        entry_meta["id"] = file_id
                    if file_hash is not None:
                        entry_meta["fp"] = file_hash
                    updated_paths.append(self._copy_config_entry(entry))
                    meta = entry_meta

            if meta:
                self._append_unique(paths_for_emp, meta, seen_result_paths)

        deduped_paths = []
        seen_config_paths = set()
        for meta in updated_paths:
            self._append_unique(deduped_paths, meta, seen_config_paths)

        if config_changed and deduped_paths != self.config_controller.employees.get(
            target_name, []
        ):
            self.config_controller.employees[target_name] = deduped_paths
            self.config_controller._save_employees()

        return paths_for_emp

    def get_employees_map(self) -> Dict[str, List[Dict[str, Any]]]:
        config = self.config_controller.config
        custom_paths = self.config_controller.employees
        config_list = sorted(custom_paths.keys())

        roots_to_scan = self._resolve_roots_to_scan(config)
        all_have_custom = self._all_custom_paths_available(config_list, custom_paths)
        discovered_files = self._scan_discovered_files(roots_to_scan, all_have_custom)

        self.rename_detected = False

        result = {}
        for target_name in config_list:
            result[target_name] = self._resolve_custom_paths_for_employee(
                target_name, custom_paths, discovered_files
            )

        return result
