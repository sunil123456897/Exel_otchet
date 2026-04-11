"""Bootstrap — Composition Root для Dependency Injection."""

import logging
import logging.handlers
import importlib.util
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List

from pydantic import BaseModel, field_validator

from core.infra import ConfigController, MasterWriter
from core.infra.ingestion_engine import IngestionEngine
from core.infra.session_repo import SessionRepository as SQLiteManager
from core.domain import LogicService, Validator
from core.app_controller import AppController


# ── Item 8: Pydantic config validation ──────────────────────

class PathsConfig(BaseModel):
    """Validates the 'paths' section of config."""
    master_file: str = "Master_Report.xlsx"
    source_root: str = "REPORTS"
    source_roots: Optional[List[str]] = None

class DatabaseConfig(BaseModel):
    """Validates the 'database' section."""
    path: str = "cache.db"
    schema_path: str = "db_schema.sql"
    timeout: float = 30.0

class LockingConfig(BaseModel):
    """Validates the 'locking' section."""
    retry_count: int = 3
    retry_backoff: float = 1.0

class NetworkConfig(BaseModel):
    """Validates the 'network' section."""
    drive_letters: List[str] = ["Q", "Z"]

class AppConfig(BaseModel):
    """Top-level config model with safe defaults."""
    paths: PathsConfig = PathsConfig()
    database: DatabaseConfig = DatabaseConfig()
    locking: LockingConfig = LockingConfig()
    network: NetworkConfig = NetworkConfig()
    sh1: Dict[str, Any] = {}
    logic: Dict[str, Any] = {}
    curators: Dict[str, Any] = {}
    validation: Dict[str, Any] = {}

    model_config = {"extra": "allow"}


# ── Item 10: Path traversal protection ──────────────────────

def _validate_path_safety(resolved: Path, app_root: Path) -> Path:
    """Ensure resolved path does not escape the app_root via traversal.

    Returns the resolved path, or raises ValueError if traversal detected.
    """
    try:
        resolved_abs = resolved.resolve()
        app_root_abs = app_root.resolve()
        # Allow paths inside app_root or on the same drive (Windows network paths)
        if str(resolved_abs).startswith(str(app_root_abs)):
            return resolved_abs
        # For absolute paths on other drives (Q:, Z:, UNC) we allow them
        if resolved.is_absolute():
            return resolved_abs
        # Relative paths must stay inside app_root
        raise ValueError(
            f"Path traversal detected: '{resolved}' escapes app root '{app_root}'"
        )
    except (OSError, ValueError) as e:
        if isinstance(e, ValueError):
            raise
        return resolved


class Bootstrap:
    """Статический класс для инициализации всех зависимостей приложения."""

    @staticmethod
    def setup(
        app_root: Path, config_path: str
    ) -> Tuple[
        Optional[ConfigController], Optional[AppController], Optional[SQLiteManager]
    ]:
        """Инициализировать все зависимости и вернуть контроллеры.

        Returns:
            (config_controller, app_controller, persistence) или (None, None, None)
            при отсутствии критической зависимости.
        """
        # Dependency check
        if importlib.util.find_spec("python_calamine") is None:
            logging.critical(
                "Критическая ошибка: библиотека 'python-calamine' не найдена!"
            )
            return None, None, None

        cfg_ctl = ConfigController(config_path)
        raw_cfg = cfg_ctl.config

        # Item 8: Validate config via Pydantic (safe defaults on invalid input)
        if not isinstance(raw_cfg, dict):
            logging.warning("Config is not a dict — using safe defaults.")
            raw_cfg = {}
        try:
            AppConfig(**raw_cfg)
            cfg = raw_cfg  # Keep original dict for backward compat
        except Exception as e:
            logging.warning(f"Config validation warning: {e}. Using safe defaults.")
            cfg = {}

        cfg_ctl.config = cfg

        cfg.setdefault("paths", {})
        cfg.setdefault("sh1", {})
        cfg.setdefault("logic", {})
        cfg.setdefault("curators", {})

        # Helper to resolve relative paths
        def resolve_rel(p: Optional[str], default_filename: str = None) -> str:
            if not p:
                if default_filename:
                    return str(app_root / default_filename)
                return ""
            path = Path(p)
            if not path.is_absolute():
                resolved = app_root / path
            else:
                resolved = path
            # Item 10: Validate path traversal
            _validate_path_safety(resolved, app_root)
            return str(resolved)

        # Resolve essential paths
        db_cfg = cfg.setdefault("database", {})
        db_path = db_cfg["path"] = resolve_rel(
            db_cfg.get("path", "cache.db"), "cache.db"
        )
        schema_path = db_cfg["schema_path"] = resolve_rel(
            db_cfg.get("schema_path", "db_schema.sql"), "db_schema.sql"
        )

        # Resolve config paths
        p_cfg = cfg.get("paths", {})
        p_cfg["master_file"] = resolve_rel(
            p_cfg.get("master_file", "Master_Report.xlsx"), "Master_Report.xlsx"
        )
        p_cfg["source_root"] = resolve_rel(
            p_cfg.get("source_root", "REPORTS"), "REPORTS"
        )
        if "source_roots" in p_cfg and isinstance(p_cfg["source_roots"], list):
            p_cfg["source_roots"] = [resolve_rel(r) for r in p_cfg["source_roots"]]

        drive_letters = tuple(cfg.get("network", {}).get("drive_letters", ["Q", "Z"]))
        ingestion = IngestionEngine(
            cfg.get("sh1", {}).get("markers", {}), drive_letters
        )
        persistence = SQLiteManager(db_path, schema_path, cfg)
        validator = Validator(cfg)
        logic = LogicService(persistence, cfg)
        writer = MasterWriter(cfg, config_path)
        app_ctl = AppController(
            cfg_ctl, ingestion, persistence, validator, logic, writer
        )
        return cfg_ctl, app_ctl, persistence
