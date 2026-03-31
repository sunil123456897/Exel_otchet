import logging
from pathlib import Path
from .config_controller import ConfigController
from .backend.ingestion_service import IngestionEngine
from .backend.persistence_manager import SQLiteManager
from .backend.logic_service import LogicService, Validator
from .backend.export_writer import MasterWriter
from .app_controller import AppController

class Bootstrap:
    @staticmethod
    def setup(app_root: Path, config_path: str):
        cfg_ctl = ConfigController(config_path)
        cfg = cfg_ctl.config
        ingestion = IngestionEngine(cfg.get('sh1', {}).get('markers', {}))
        db_cfg = cfg.get('database', {})
        persistence = SQLiteManager(db_cfg.get('path', str(app_root / "cache.db")), db_cfg.get('schema_path', str(app_root / "src" / "backend" / "db_schema.sql")), cfg)
        validator = Validator(cfg)
        logic = LogicService(persistence, cfg)
        writer = MasterWriter(cfg)
        app_ctl = AppController(cfg_ctl, ingestion, persistence, validator, logic, writer)
        return cfg_ctl, app_ctl, persistence
