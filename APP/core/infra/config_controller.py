import os
import logging
import hashlib
import re
import threading
from pathlib import Path
from typing import Any, Dict, List, cast
from ruamel.yaml import YAML

from core.infra.utils import atomic_save_yaml
from core.infra.utils_logging import scrub_path


class ConfigController:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        self.yaml.indent(mapping=2, sequence=4, offset=2)
        self.config = self.load_config()
        emp_path = Path(config_path).parent / "employees.yaml"
        self.employees_path = str(emp_path)
        self.employees = self._load_employees()
        self._employees_lock = threading.Lock()

    def _load_employees(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self.employees_path):
                with open(self.employees_path, "r", encoding="utf-8") as f:
                    return self.yaml.load(f) or {}
        except Exception as e:
            logging.error(f"Error loading employees: {e}")
        return {}

    def _save_employees(self) -> None:
        try:
            atomic_save_yaml(self.employees_path, self.employees, self.yaml)
            # Restrict to owner-only read/write — employees.yaml contains
            # network paths and file fingerprints that shouldn't be
            # world-readable on shared machines.
            try:
                os.chmod(self.employees_path, 0o600)
            except OSError as chmod_err:
                logging.warning(
                    "Could not restrict %s permissions: %s",
                    self.employees_path,
                    chmod_err,
                )
        except Exception as e:
            logging.error(f"Error saving employees: {e}")

    def load_config(self) -> Dict[str, Any]:
        """Loads the configuration from the YAML file."""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return self.yaml.load(f) or {}

            example_path = Path(self.config_path).with_name("config.example.yaml")
            if example_path.exists():
                logging.warning(
                    "Config file not found: %s. Creating it from %s",
                    self.config_path,
                    example_path,
                )
                config_path = Path(self.config_path)
                config_path.parent.mkdir(parents=True, exist_ok=True)
                config_path.write_text(
                    example_path.read_text(encoding="utf-8"),
                    encoding="utf-8",
                )
                # Restrict to owner-only — config.yaml may contain
                # network paths and operator-specific tuning.
                try:
                    os.chmod(config_path, 0o600)
                except OSError as chmod_err:
                    logging.warning(
                        "Could not restrict %s permissions: %s",
                        config_path,
                        chmod_err,
                    )
                with open(config_path, "r", encoding="utf-8") as f:
                    return self.yaml.load(f) or {}

            logging.warning(f"Config file not found: {self.config_path}")
            return {}
        except Exception as e:
            logging.error(
                "Error loading config: %s. Running on built-in defaults; "
                "settings will NOT be saved this session. If config.yaml or "
                "config.example.yaml is corrupt, restore it.", e,
            )
            return {}

    def save_config(self) -> None:
        """Saves the current configuration to the YAML file."""
        try:
            atomic_save_yaml(self.config_path, self.config, self.yaml)
            # Restrict to owner-only read/write — see load_config.
            try:
                os.chmod(self.config_path, 0o600)
            except OSError as chmod_err:
                logging.warning(
                    "Could not restrict %s permissions: %s",
                    self.config_path,
                    chmod_err,
                )
        except Exception as e:
            logging.error(f"Error saving config: {e}")

    def _invalidate_discovery_cache(self) -> None:
        if isinstance(self.config, dict):
            self.config.pop("discovery_cache", None)

    def add_employee(self, name: str) -> None:
        name = name.strip()
        if not name:
            return
        with self._employees_lock:
            self.employees.setdefault(name, [])
        self._invalidate_discovery_cache()
        self._save_employees()

    def delete_employee(self, name: str) -> None:
        with self._employees_lock:
            if name in self.employees:
                del self.employees[name]
        self._invalidate_discovery_cache()
        self._save_employees()

    def attach_files(self, emp_name: str, files: List[str], append: bool = True) -> None:
        """Attaches files to an employee, updating metadata for smart tracking."""
        new_metas: List[Any] = []
        for fp in files:
            p: Any = Path(fp).absolute()
            if not p.exists():
                continue
            try:
                stat = os.stat(p)
                with open(p, "rb") as f:
                    digest = hashlib.md5()
                    for chunk in iter(lambda: f.read(8192), b""):
                        digest.update(chunk)
                    h = digest.hexdigest()
                new_metas.append({"path": str(p), "id": stat.st_ino, "fp": h})
            except Exception as e:
                logging.error(f"Error generating metadata for {fp}: {e}")
                new_metas.append({"path": str(p)})

        current = self.employees.get(emp_name, [])
        if not isinstance(current, list):
            current = [current] if current else []

        combined = current + new_metas if append else new_metas

        final: List[Any] = []
        seen: set[Any] = set()
        for m in combined:
            p = m["path"] if isinstance(m, dict) else m
            if p not in seen:
                final.append(m)
                seen.add(p)

        with self._employees_lock:
            self.employees[emp_name] = final
        self._invalidate_discovery_cache()
        self._save_employees()

    def get_employees(self) -> List[str]:
        return sorted(self.employees.keys())

    def resolve_path(self, path_str: str) -> Path:
        config_dir = Path(self.config_path).parent.resolve()
        project_root = config_dir.parent.resolve()
        allow_roots = self._allowlist_roots(config_dir, project_root)
        if self._is_effectively_absolute(path_str):
            # Absolute / UNC / drive-letter paths previously bypassed the
            # traversal check entirely (returned as-is). Apply an allowlist
            # so only paths under a configured source_root, the config dir,
            # or the project root are accepted.
            try:
                resolved_abs = Path(path_str).resolve()
            except (OSError, ValueError) as exc:
                raise ValueError(
                    f"Path traversal detected: invalid path '{scrub_path(path_str)}'"
                ) from exc
            if not any(
                self._is_path_under(resolved_abs, root) for root in allow_roots
            ):
                raise ValueError(
                    f"Path traversal detected: '{scrub_path(path_str)}' resolves outside allowed roots"
                )
            return Path(path_str)
        p = Path(path_str)
        if p.is_absolute():
            # Defensive: should be unreachable because _is_effectively_absolute
            # already covers Posix absolute paths — kept for safety.
            return p
        resolved = (Path(self.config_path).parent / p).resolve()
        # Use the explicit separator-boundary check instead of a naive
        # str.startswith, which would match /app/config_evil against
        # /app/config. Allowlist also includes source_roots so legitimate
        # network paths under configured roots continue to work.
        if not any(self._is_path_under(resolved, root) for root in allow_roots):
            raise ValueError(
                f"Path traversal detected: '{scrub_path(path_str)}' resolves outside project root"
            )
        return resolved

    def _allowlist_roots(
        self, config_dir: Path, project_root: Path
    ) -> List[Path]:
        """Trusted roots: configured paths.source_roots + config dir + project root."""
        roots: List[Path] = [config_dir, project_root]
        paths_cfg = (
            self.config.get("paths", {}) if isinstance(self.config, dict) else {}
        )
        src_roots_raw = (
            paths_cfg.get("source_roots") or paths_cfg.get("source_root") or []
        )
        if isinstance(src_roots_raw, (str, Path)):
            src_roots_raw = [src_roots_raw]
        if not isinstance(src_roots_raw, list):
            return roots
        for raw in src_roots_raw:
            try:
                roots.append(Path(str(raw)).resolve())
            except (OSError, ValueError):
                continue
        return roots

    @staticmethod
    def _is_path_under(path: Path, root: Path) -> bool:
        """Return True if ``path`` equals or is nested under ``root``.

        Case-insensitive to match Windows file-system semantics and the
        pre-existing traversal-check behaviour. Uses an explicit separator
        boundary to avoid the ``/app/config`` vs ``/app/config_evil``
        prefix collision that a naive ``startswith`` would accept.
        """
        p = str(path).lower().rstrip("\\/")
        r = str(root).lower().rstrip("\\/")
        if not r:
            return False
        if p == r:
            return True
        return p.startswith(r + "\\") or p.startswith(r + "/")

    @staticmethod
    def _is_effectively_absolute(path_str: str) -> bool:
        p = Path(path_str)
        if p.is_absolute():
            return True
        if path_str.startswith("\\\\"):
            return True
        return bool(re.match(r"^[A-Za-z]:[\\/]", path_str))

    def get_paths(self) -> Dict[str, str]:
        """Returns the general paths configuration."""
        return cast(Dict[str, str], self.config.get("paths", {}))
