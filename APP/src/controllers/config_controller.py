import os
import logging
import hashlib
from pathlib import Path
from typing import List, Dict, Any, Optional
from ruamel.yaml import YAML

class ConfigController:
    def __init__(self, config_path: str):
        self.config_path = config_path
        # Use round-trip loader/dumper to preserve comments
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        self.yaml.indent(mapping=2, sequence=4, offset=2)
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """Loads the configuration from the YAML file."""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
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
            with open(self.config_path, 'w', encoding='utf-8') as f:
                self.yaml.dump(self.config, f)
        except Exception as e:
            logging.error(f"Error saving config: {e}")

    def add_employee(self, name: str):
        """Adds a new employee to the configuration."""
        name = name.strip()
        if not name:
            return
        
        employees = self.config.get('employees', [])
        if name not in employees:
            employees.append(name)
            self.config['employees'] = sorted(employees)
            self.save_config()

    def delete_employee(self, name: str):
        """Removes an employee and their custom paths from the configuration."""
        employees = self.config.get('employees', [])
        if name in employees:
            employees.remove(name)
            self.config['employees'] = employees
        
        custom_paths = self.config.get('employee_paths', {})
        if name in custom_paths:
            del custom_paths[name]
            self.config['employee_paths'] = custom_paths
            
        self.save_config()

    def attach_files(self, emp_name: str, files: List[str], append: bool = True):
        """Attaches files to an employee, updating metadata for smart tracking."""
        new_metas = []
        for fp in files:
            p = Path(fp).absolute()
            if not p.exists():
                continue
            try:
                stat = os.stat(p)
                with open(p, 'rb') as f:
                    h = hashlib.md5(f.read(8192)).hexdigest()
                new_metas.append({"path": str(p), "id": stat.st_ino, "fp": h})
            except Exception as e:
                logging.error(f"Error generating metadata for {fp}: {e}")
                new_metas.append({"path": str(p)})
        
        current = self.config.get('employee_paths', {}).get(emp_name, [])
        if not isinstance(current, list):
            current = [current] if current else []
        
        combined = current + new_metas if append else new_metas
        
        # Deduplicate by path
        final = []
        seen = set()
        for m in combined:
            p = m['path'] if isinstance(m, dict) else m
            if p not in seen:
                final.append(m)
                seen.add(p)
        
        self.config.setdefault('employee_paths', {})[emp_name] = final
        self.save_config()

    def get_employees(self) -> List[str]:
        """Returns the list of employees."""
        return self.config.get('employees', [])

    def get_paths(self) -> Dict[str, str]:
        """Returns the general paths configuration."""
        return self.config.get('paths', {})
