"""Bootstrap — Composition Root для Dependency Injection."""

import logging
import logging.handlers
import importlib.util
import re
import sqlite3
from pathlib import Path
from typing import Tuple, Optional, Dict, Any, List

from pydantic import BaseModel

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
    allow_local_fallback: bool = False


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


def _can_open_sqlite_path(db_path: Path, timeout: float) -> tuple[bool, str | None]:
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return False, f"parent dir error: {e}"

    conn = None
    try:
        conn = sqlite3.connect(db_path, timeout=timeout)
        return True, None
    except sqlite3.OperationalError as e:
        return False, str(e)
    finally:
        if conn is not None:
            conn.close()


class Bootstrap:
    """Статический класс для инициализации всех зависимостей приложения."""

    @staticmethod
    def _has_required_dependency() -> bool:
        return importlib.util.find_spec("python_calamine") is not None

    @staticmethod
    def _coerce_raw_config(raw_cfg: Any) -> Dict[str, Any]:
        if not isinstance(raw_cfg, dict):
            logging.warning("Config is not a dict — using safe defaults.")
            return {}
        return dict(raw_cfg)

    @staticmethod
    def _validate_section(
        raw_cfg: Dict[str, Any], section_name: str, model_cls: type[BaseModel]
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

    @staticmethod
    def _validate_and_normalize_config(
        cfg_ctl: ConfigController,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        raw_cfg = cfg_ctl.config
        raw_cfg_dict = raw_cfg if isinstance(raw_cfg, dict) else {}
        cfg = Bootstrap._coerce_raw_config(raw_cfg)

        cfg["paths"] = Bootstrap._validate_section(raw_cfg_dict, "paths", PathsConfig)
        cfg["database"] = Bootstrap._validate_section(
            raw_cfg_dict, "database", DatabaseConfig
        )
        cfg["locking"] = Bootstrap._validate_section(
            raw_cfg_dict, "locking", LockingConfig
        )
        cfg["network"] = Bootstrap._validate_section(raw_cfg_dict, "network", NetworkConfig)

        if not isinstance(cfg.get("sh1"), dict):
            cfg["sh1"] = {}
        if not isinstance(cfg.get("logic"), dict):
            cfg["logic"] = {}
        if not isinstance(cfg.get("curators"), dict):
            cfg["curators"] = {}
        if not isinstance(cfg.get("validation"), dict):
            cfg["validation"] = {}

        cfg.setdefault("paths", {})
        cfg.setdefault("sh1", {})
        cfg.setdefault("logic", {})
        cfg.setdefault("curators", {})

        cfg_ctl.config = cfg
        return cfg, raw_cfg_dict

    @staticmethod
    def _resolve_rel_factory(app_root: Path):
        def resolve_rel(p: Optional[str], default_filename: str = None) -> str:
            if not p:
                if default_filename:
                    return str(app_root / default_filename)
                return ""
            path = Path(p)
            allow_external = _is_effectively_absolute(p)
            resolved = path if allow_external else app_root / path
            resolved = _validate_path_safety(resolved, app_root, allow_external)
            return str(resolved)

        return resolve_rel

    @staticmethod
    def _resolve_database_paths(
        cfg: Dict[str, Any], app_root: Path, resolve_rel
    ) -> tuple[str, str, float, bool]:
        persist_recovered_paths = False
        db_cfg = cfg.setdefault("database", {})
        db_path = db_cfg["path"] = resolve_rel(db_cfg.get("path", "cache.db"), "cache.db")
        schema_path = db_cfg["schema_path"] = resolve_rel(
            db_cfg.get("schema_path", "db_schema.sql"), "db_schema.sql"
        )
        db_timeout = float(db_cfg.get("timeout", 30.0))

        db_ok, db_error = _can_open_sqlite_path(Path(db_path), db_timeout)
        if not db_ok:
            if not bool(db_cfg.get("allow_local_fallback", False)):
                raise RuntimeError(
                    f"Configured DB path is not writable: {db_path} ({db_error}). "
                    "Refusing local fallback in production. Set "
                    "database.allow_local_fallback: true for dev/test fallback."
                )
            logging.warning(
                "Configured DB path is not writable (%s). Falling back to local app DB.",
                db_error,
            )
            fallback_db = str(app_root / "cache.db")
            if db_path != fallback_db:
                persist_recovered_paths = True
            db_path = db_cfg["path"] = fallback_db

        schema_candidate = Path(schema_path)
        if not schema_candidate.exists():
            fallback_schema = app_root / "db_schema.sql"
            if fallback_schema.exists():
                logging.warning(
                    "Configured schema path missing: %s. Using fallback: %s",
                    schema_candidate,
                    fallback_schema,
                )
                fallback_schema_str = str(fallback_schema)
                if schema_path != fallback_schema_str:
                    persist_recovered_paths = True
                schema_path = db_cfg["schema_path"] = fallback_schema_str

        return db_path, schema_path, db_timeout, persist_recovered_paths

    @staticmethod
    def _resolve_path_config(
        cfg: Dict[str, Any], raw_cfg: Dict[str, Any], app_root: Path, resolve_rel
    ) -> None:
        p_cfg = cfg.get("paths", {})
        raw_paths = raw_cfg.get("paths", {}) if isinstance(raw_cfg, dict) else {}
        if not isinstance(raw_paths, dict):
            raw_paths = {}

        master_base = app_root.parent if (app_root / "main.py").exists() else app_root
        p_cfg["master_file"] = str(master_base / "Master_Report.xlsx")
        p_cfg["source_root"] = resolve_rel(p_cfg.get("source_root", "REPORTS"), "REPORTS")
        if "source_roots" in p_cfg and isinstance(p_cfg["source_roots"], list):
            p_cfg["source_roots"] = [resolve_rel(r) for r in p_cfg["source_roots"]]

        sr = p_cfg.get("source_root")
        raw_sr = str(raw_paths.get("source_root", "")).replace("\\", "/").lower().strip()
        source_root_is_default = "source_root" not in raw_paths or raw_sr in {
            "",
            "reports",
            "./reports",
        }

        if source_root_is_default and sr and not Path(sr).exists():
            p_cfg["source_root"] = "Q:/Отчет кураторов 1"
            if not p_cfg.get("source_roots"):
                p_cfg["source_roots"] = [
                    "Q:/Отчет кураторов 1",
                    "Q:/Отчет кураторов 2",
                    "Q:/Отчет кураторов 3",
                ]

    @staticmethod
    def _build_runtime_components(
        cfg_ctl: ConfigController,
        cfg: Dict[str, Any],
        db_path: str,
        schema_path: str,
        config_path: str,
    ):
        drive_letters = tuple(cfg.get("network", {}).get("drive_letters", ["Q", "Z"]))
        ingestion = IngestionEngine(cfg.get("sh1", {}).get("markers", {}), drive_letters)
        persistence = SQLiteManager(db_path, schema_path, cfg)
        validator = Validator(cfg)
        logic = LogicService(persistence, cfg)
        writer = MasterWriter(cfg, config_path)
        app_ctl = AppController(cfg_ctl, ingestion, persistence, validator, logic, writer)
        return cfg_ctl, app_ctl, persistence

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
        if not Bootstrap._has_required_dependency():
            logging.critical(
                "Критическая ошибка: библиотека 'python-calamine' не найдена!"
            )
            return None, None, None

        cfg_ctl = ConfigController(config_path)
        cfg, raw_cfg = Bootstrap._validate_and_normalize_config(cfg_ctl)
        resolve_rel = Bootstrap._resolve_rel_factory(app_root)
        db_path, schema_path, _db_timeout, persist_recovered_paths = (
            Bootstrap._resolve_database_paths(cfg, app_root, resolve_rel)
        )

        if persist_recovered_paths:
            save_config = getattr(cfg_ctl, "save_config", None)
            if callable(save_config):
                save_config()

        Bootstrap._resolve_path_config(cfg, raw_cfg, app_root, resolve_rel)
        return Bootstrap._build_runtime_components(
            cfg_ctl,
            cfg,
            db_path,
            schema_path,
            config_path,
        )
