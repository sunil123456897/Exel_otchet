import os
import logging
import hashlib
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from ruamel.yaml import YAML


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

    def _load_employees(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self.employees_path):
                with open(self.employees_path, "r", encoding="utf-8") as f:
                    return self.yaml.load(f) or {}
        except Exception as e:
            logging.error(f"Error loading employees: {e}")
        return {}

    def _save_employees(self):
        try:
            with open(self.employees_path, "w", encoding="utf-8") as f:
                self.yaml.dump(self.employees, f)
        except Exception as e:
            logging.error(f"Error saving employees: {e}")

    def load_config(self) -> Dict[str, Any]:
        """Loads the configuration from the YAML file."""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return self.yaml.load(f)
            else:
                logging.warning(f"Config file not found: {self.config_path}")
                return {}
        except Exception as e:
            logging.error(f"Error loading config: {e}")
            return {}

    def save_config(self):
        """Saves the current configuration to the YAML file."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                self.yaml.dump(self.config, f)
        except Exception as e:
            logging.error(f"Error saving config: {e}")

    def add_employee(self, name: str):
        name = name.strip()
        if not name:
            return
        self.employees.setdefault(name, [])
        self._save_employees()

    def delete_employee(self, name: str):
        if name in self.employees:
            del self.employees[name]
            self._save_employees()

    def attach_files(self, emp_name: str, files: List[str], append: bool = True):
        """Attaches files to an employee, updating metadata for smart tracking."""
        new_metas = []
        for fp in files:
            p = Path(fp).absolute()
            if not p.exists():
                continue
            try:
                stat = os.stat(p)
                with open(p, "rb") as f:
                    h = hashlib.md5(f.read(8192)).hexdigest()
                new_metas.append({"path": str(p), "id": stat.st_ino, "fp": h})
            except Exception as e:
                logging.error(f"Error generating metadata for {fp}: {e}")
                new_metas.append({"path": str(p)})

        current = self.employees.get(emp_name, [])
        if not isinstance(current, list):
            current = [current] if current else []

        combined = current + new_metas if append else new_metas

        final = []
        seen = set()
        for m in combined:
            p = m["path"] if isinstance(m, dict) else m
            if p not in seen:
                final.append(m)
                seen.add(p)

        self.employees[emp_name] = final
        self._save_employees()

    def get_employees(self) -> List[str]:
        return sorted(self.employees.keys())

    def resolve_path(self, path_str: str) -> Path:
        if self._is_effectively_absolute(path_str):
            return Path(path_str)
        p = Path(path_str)
        if p.is_absolute():
            return p
        return Path(self.config_path).parent / p

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
        return self.config.get("paths", {})
