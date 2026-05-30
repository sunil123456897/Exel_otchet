import hashlib
import logging
import time
import concurrent.futures
from pathlib import Path
from typing import List, Dict, Any, Optional

from core.infra.config_controller import ConfigController
from core.infra.ingestion_engine import IngestionEngine
from core.infra.path_resolver import resolve_employee_path
from core.infra.utils_logging import scrub_path


class DiscoveryService:
    _DEFAULT_CURATOR_ROOTS = (
        "Отчет кураторов 1",
        "Отчет кураторов 2",
        "Отчет кураторов 3",
    )

    def __init__(
        self,
        config_controller: ConfigController,
        ingestion: IngestionEngine,
        persistence: Optional[Any] = None,
    ) -> None:
        self.config_controller = config_controller
        self.ingestion = ingestion
        self.persistence = persistence
        self.rename_detected = False
        self.last_discovered_count = 0

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
                    ", ".join(scrub_path(str(r)) for r in roots_to_scan),
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
                ", ".join(scrub_path(str(r)) for r in roots_to_scan),
            )
        return roots_to_scan

    @staticmethod
    def _roots_key(roots_to_scan: List[Path]) -> List[str]:
        return [str(root) for root in roots_to_scan]

    @staticmethod
    def _discovery_cache_ttl(config: Dict[str, Any]) -> float:
        network_cfg = config.get("network", {}) if hasattr(config, "get") else {}
        raw_ttl = network_cfg.get("discovery_cache_ttl_seconds", 12 * 60 * 60)
        try:
            return max(0.0, float(raw_ttl))
        except (TypeError, ValueError):
            return 12 * 60 * 60

    def _load_discovery_cache(
        self, config: Dict[str, Any], roots_to_scan: List[Path]
    ) -> List[Dict[str, Any]] | None:
        roots_key = hashlib.md5(
            str(self._roots_key(roots_to_scan)).encode()
        ).hexdigest()
        
        # Try SQLite cache first
        if self.persistence is not None:
            try:
                cached = self.persistence.get_discovery_cache(roots_key)
                if cached is not None:
                    return cached
            except Exception as e:
                logging.debug(f"SQLite discovery cache miss: {e}")
        
        # Fall back to YAML cache
        cache = config.get("discovery_cache") if hasattr(config, "get") else None
        if not isinstance(cache, dict):
            return None
        if cache.get("roots_key") != self._roots_key(roots_to_scan):
            return None

        scanned_at = cache.get("scanned_at")
        try:
            age = time.time() - float(scanned_at)
        except (TypeError, ValueError):
            return None
        if age > self._discovery_cache_ttl(config):
            return None

        files = cache.get("files")
        if not isinstance(files, list):
            return None
        return [dict(item) for item in files if isinstance(item, dict)]

    def _save_discovery_cache(
        self,
        config: Dict[str, Any],
        roots_to_scan: List[Path],
        discovered_files: List[Dict[str, Any]],
    ) -> None:
        roots_key = hashlib.md5(
            str(self._roots_key(roots_to_scan)).encode()
        ).hexdigest()
        
        # Save to SQLite if available
        if self.persistence is not None:
            try:
                self.persistence.save_discovery_cache(roots_key, discovered_files)
                logging.info("[CACHE] Discovery cache saved to SQLite")
            except Exception as e:
                logging.warning(f"Failed to save discovery cache to SQLite: {e}")
        
        # Also save to YAML for backward compatibility
        config["discovery_cache"] = {
            "roots_key": self._roots_key(roots_to_scan),
            "scanned_at": time.time(),
            "files": [dict(item) for item in discovered_files],
        }
        save_config = getattr(self.config_controller, "save_config", None)
        if callable(save_config):
            save_config()

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

    @staticmethod
    def _path_parts(path_str: str) -> List[str]:
        return [
            part.lower()
            for part in path_str.replace("\\", "/").split("/")
            if part not in ("", ".", "..")
        ]

    @classmethod
    def _matching_roots_for_path(
        cls, path_str: str, roots_to_scan: List[Path]
    ) -> List[Path]:
        normalized_path = path_str.replace("\\", "/").lower()
        path_parts = cls._path_parts(path_str)
        matches: List[Path] = []
        for root in roots_to_scan:
            normalized_root = str(root).replace("\\", "/").lower().rstrip("/")
            if normalized_path.startswith(normalized_root + "/"):
                matches.append(root)
                continue
            if root.name.lower() in path_parts:
                matches.append(root)
        return matches

    def _roots_requiring_scan(
        self,
        config_list: List[str],
        custom_paths: Dict[str, Any],
        roots_to_scan: List[Path],
        *,
        allow_network_scan: bool = True,
    ) -> List[Path]:
        if not allow_network_scan:
            return []
        if not config_list:
            return roots_to_scan
        if not roots_to_scan:
            return []
        if not all(name in custom_paths for name in config_list):
            return roots_to_scan

        missing_roots: List[Path] = []
        seen = set()
        for name in config_list:
            p_val = custom_paths[name]
            p_list = p_val if isinstance(p_val, list) else [p_val]
            for entry in p_list:
                path_str = entry["path"] if isinstance(entry, dict) else entry
                file_id = entry.get("id") if isinstance(entry, dict) else None
                file_hash = entry.get("fp") if isinstance(entry, dict) else None
                resolved, _, _ = resolve_employee_path(
                    path_str,
                    file_id=file_id,
                    file_hash=file_hash,
                    discovered_files=[],
                    config_controller=self.config_controller,
                )
                p_abs = Path(resolved)
                if p_abs.is_absolute() and p_abs.exists():
                    continue
                if file_id or file_hash:
                    return roots_to_scan

                matching_roots = self._matching_roots_for_path(
                    str(path_str), roots_to_scan
                )
                if not matching_roots:
                    return roots_to_scan
                for root in matching_roots:
                    key = str(root)
                    if key not in seen:
                        missing_roots.append(root)
                        seen.add(key)
        return missing_roots

    def _scan_discovered_files(
        self, roots_to_scan: List[Path], all_have_custom: bool
    ) -> List[Dict[str, Any]]:
        discovered_files: List[Dict[str, Any]] = []
        if not roots_to_scan:
            return discovered_files
        if all_have_custom:
            logging.info(
                "[NET] Все сотрудники привязаны, пропускаю полное сканирование сети."
            )
            return discovered_files

        def scan_root(root: Path) -> List[Dict[str, Any]]:
            try:
                logging.info("[NET] Сканирую сетевой путь: %s", scrub_path(str(root)))
                files = self.ingestion.scan_directory(root)
                logging.info("[NET] Найдено файлов в %s: %s", root.name, len(files))
                return files
            except Exception as e:
                logging.error("[NET] Ошибка доступа к %s: %s", scrub_path(str(root)), e)
                return []

        if len(roots_to_scan) == 1:
            return scan_root(roots_to_scan[0])

        max_workers = min(16, len(roots_to_scan))
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            for files in executor.map(scan_root, roots_to_scan):
                discovered_files.extend(files)
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

    def get_employees_map(
        self, *, allow_network_scan: bool = True
    ) -> Dict[str, List[Dict[str, Any]]]:
        config = self.config_controller.config
        custom_paths = self.config_controller.employees
        config_list = sorted(custom_paths.keys())

        roots_to_scan = self._resolve_roots_to_scan(config)
        roots_requiring_scan = self._roots_requiring_scan(
            config_list,
            custom_paths,
            roots_to_scan,
            allow_network_scan=allow_network_scan,
        )
        all_have_custom = not roots_requiring_scan
        discovered_files = (
            None
            if roots_requiring_scan
            else []
        )
        if roots_requiring_scan:
            discovered_files = self._load_discovery_cache(config, roots_requiring_scan)
        if discovered_files is None:
            discovered_files = self._scan_discovered_files(
                roots_requiring_scan, all_have_custom
            )
            if roots_requiring_scan:
                self._save_discovery_cache(
                    config, roots_requiring_scan, discovered_files
                )
        self.last_discovered_count = len(discovered_files or [])

        self.rename_detected = False

        result = {}
        for target_name in config_list:
            result[target_name] = self._resolve_custom_paths_for_employee(
                target_name, custom_paths, discovered_files
            )

        return result
