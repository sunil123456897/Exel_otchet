import logging
from pathlib import Path
from core.config_controller import ConfigController
from core.ingestion_manager import IngestionEngine
from core.persistence_manager import SQLiteManager
from core.logic_service import LogicService, Validator
from core.export_writer import MasterWriter
from core.app_controller import AppController

class Bootstrap:
    @staticmethod
    def setup(app_root: Path, config_path: str):
        cfg_ctl = ConfigController(config_path)
        cfg = cfg_ctl.config
        ingestion = IngestionEngine(cfg.get('sh1', {}).get('markers', {}))
        db_cfg = cfg.get('database', {})
        persistence = SQLiteManager(db_cfg.get('path', str(app_root / "cache.db")), str(app_root / "db_schema.sql"), cfg)
        validator = Validator(cfg)
        logic = LogicService(persistence, cfg)
        writer = MasterWriter(cfg)
        app_ctl = AppController(cfg_ctl, ingestion, persistence, validator, logic, writer)
        return cfg_ctl, app_ctl, persistence
