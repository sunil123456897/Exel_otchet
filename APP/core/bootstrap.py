import logging
from pathlib import Path
from core.infra.config_controller import ConfigController
from core.infra.ingestion_engine import IngestionEngine
from core.infra.persistence_manager import SQLiteManager
from core.domain.logic_service import LogicService, Validator
from core.infra.export_writer import MasterWriter
from core.app_controller import AppController

class Bootstrap:
    @staticmethod
    def setup(app_root: Path, config_path: str):
        cfg_ctl = ConfigController(config_path)
        cfg = cfg_ctl.config
        
        # Fix 10: Config Validation
        if not cfg or 'paths' not in cfg or 'sh1' not in cfg:
            import tkinter.messagebox as mb
            msg = "Файл config.yaml поврежден или не содержит необходимых ключей ('paths', 'sh1')!"
            mb.showerror("Ошибка конфигурации", msg)
            raise ValueError(msg)

        ingestion = IngestionEngine(cfg.get('sh1', {}).get('markers', {}))
        db_cfg = cfg.get('database', {})
        persistence = SQLiteManager(db_cfg.get('path', str(app_root / "cache.db")), str(app_root / "db_schema.sql"), cfg)
        validator = Validator(cfg)
        logic = LogicService(persistence, cfg)
        writer = MasterWriter(cfg)
        app_ctl = AppController(cfg_ctl, ingestion, persistence, validator, logic, writer)
        return cfg_ctl, app_ctl, persistence
