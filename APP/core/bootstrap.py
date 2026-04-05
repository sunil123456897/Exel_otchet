"""Bootstrap — Composition Root для Dependency Injection."""
import logging
import importlib.util
from pathlib import Path
from typing import Tuple, Optional, Dict, Any

from core.infra.config_controller import ConfigController
from core.infra.ingestion_engine import IngestionEngine
from core.infra.persistence_manager import SQLiteManager
from core.domain.logic_service import LogicService, Validator
from core.infra.export_writer import MasterWriter
from core.app_controller import AppController


class Bootstrap:
    """Статический класс для инициализации всех зависимостей приложения."""

    @staticmethod
    def setup(app_root: Path, config_path: str) -> Tuple[Optional[ConfigController], Optional[AppController], Optional[SQLiteManager]]:
        """Инициализировать все зависимости и вернуть контроллеры.

        Returns:
            (config_controller, app_controller, persistence) или (None, None, None)
            при отсутствии критической зависимости.
        """
        # Dependency check
        if importlib.util.find_spec("python_calamine") is None:
            logging.critical("Критическая ошибка: библиотека 'python-calamine' не найдена!")
            return None, None, None

        cfg_ctl = ConfigController(config_path)
        cfg = cfg_ctl.config
        
        # Fix 10: Config Validation
        if not cfg or 'paths' not in cfg or 'sh1' not in cfg:
            import tkinter.messagebox as mb
            msg = "Файл config.yaml поврежден или не содержит необходимых ключей ('paths', 'sh1')!"
            mb.showerror("Ошибка конфигурации", msg)
            raise ValueError(msg)

        # Helper to resolve relative paths
        def resolve_rel(p: Optional[str]) -> str:
            if not p:
                return str(app_root / 'cache.db')  # fallback, actual default set below
            path = Path(p)
            if not path.is_absolute():
                return str(app_root / path)
            return p

        # Resolve essential paths
        db_cfg = cfg.setdefault('database', {})
        db_path = db_cfg['path'] = resolve_rel(db_cfg.get('path', 'cache.db'))
        schema_path = db_cfg['schema_path'] = resolve_rel(db_cfg.get('schema_path', 'db_schema.sql'))
        
        # Resolve config paths
        p_cfg = cfg.get('paths', {})
        p_cfg['master_file'] = resolve_rel(p_cfg.get('master_file', 'Master_Report.xlsx'))
        p_cfg['source_root'] = resolve_rel(p_cfg.get('source_root', 'REPORTS'))
        if 'source_roots' in p_cfg and isinstance(p_cfg['source_roots'], list):
            p_cfg['source_roots'] = [resolve_rel(r) for r in p_cfg['source_roots']]

        ingestion = IngestionEngine(cfg.get('sh1', {}).get('markers', {}))
        persistence = SQLiteManager(db_path, schema_path, cfg)
        validator = Validator(cfg)
        logic = LogicService(persistence, cfg)
        writer = MasterWriter(cfg)
        app_ctl = AppController(cfg_ctl, ingestion, persistence, validator, logic, writer)
        return cfg_ctl, app_ctl, persistence
