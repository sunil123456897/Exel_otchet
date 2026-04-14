"""Bootstrap — Composition Root для Dependency Injection."""

import logging
import logging.handlers
import importlib.util
import re
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


def _validate_path_safety(
    resolved: Path, app_root: Path, allow_external: bool = False
) -> Path:
    """Ensure resolved path does not escape the app_root via traversal.

    Returns the resolved path, or raises ValueError if traversal detected.
    """
    try:
        resolved_abs = resolved.resolve()
        app_root_abs = app_root.resolve()
        if resolved_abs.is_relative_to(app_root_abs):
            return resolved_abs
        if allow_external:
            return resolved_abs
        raise ValueError(
            f"Path traversal detected: '{resolved}' escapes app root '{app_root}'"
        )
    except OSError:
        return resolved


def _is_effectively_absolute(path_str: str) -> bool:
    p = Path(path_str)
    if p.is_absolute():
        return True
    if path_str.startswith("\\\\"):
        return True
    return bool(re.match(r"^[A-Za-z]:[\\/]", path_str))


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
        cfg = dict(raw_cfg)

        def validate_section(
            section_name: str, model_cls: type[BaseModel]
        ) -> Dict[str, Any]:
            section_raw = raw_cfg.get(section_name, {})
            if section_raw is None:
                section_raw = {}
            if not isinstance(section_raw, dict):
                logging.warning(
                    "Config validation warning: %s is not a dict. Using safe defaults.",
                    section_name,
                )
                return model_cls().model_dump(exclude_none=True)

            validated = model_cls().model_dump(exclude_none=True)
            extras = {
                key: value
                for key, value in section_raw.items()
                if key not in model_cls.model_fields
            }
            for key in model_cls.model_fields:
                if key not in section_raw:
                    continue
                try:
                    partial = model_cls.model_validate({key: section_raw[key]})
                    partial_dump = partial.model_dump(exclude_none=True)
                    if key in partial_dump:
                        validated[key] = partial_dump[key]
                except Exception as e:
                    logging.warning(
                        "Config validation warning for %s.%s: %s. Using default value.",
                        section_name,
                        key,
                        e,
                    )
            validated.update(extras)
            return validated

        cfg["paths"] = validate_section("paths", PathsConfig)
        cfg["database"] = validate_section("database", DatabaseConfig)
        cfg["locking"] = validate_section("locking", LockingConfig)
        cfg["network"] = validate_section("network", NetworkConfig)
        if not isinstance(cfg.get("sh1"), dict):
            cfg["sh1"] = {}
        if not isinstance(cfg.get("logic"), dict):
            cfg["logic"] = {}
        if not isinstance(cfg.get("curators"), dict):
            cfg["curators"] = {}
        if not isinstance(cfg.get("validation"), dict):
            cfg["validation"] = {}

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
            allow_external = _is_effectively_absolute(p)
            if not allow_external:
                resolved = app_root / path
            else:
                resolved = path
            resolved = _validate_path_safety(resolved, app_root, allow_external)
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
