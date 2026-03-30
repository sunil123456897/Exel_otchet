import sys
import os
import logging
import threading
import time
from pathlib import Path

# Ensure the root folder containing 'src' is in sys.path
app_root = Path(__file__).parent.absolute()
if str(app_root) not in sys.path:
    sys.path.insert(0, str(app_root))

from src.ingestion import IngestionEngine
from src.sqlite_manager import SQLiteManager
from src.logic_service import LogicService, Validator
from src.writer import MasterWriter
from src.controllers.config_controller import ConfigController
from src.controllers.app_controller import AppController

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger("Headless")
    logger.info("Starting headless consolidation...")
    
    config_path = app_root / "config.yaml"
    config_controller = ConfigController(str(config_path))
    config = config_controller.config
    
    ingestion = IngestionEngine(config.get('sh1', {}).get('markers', {}))
    db_config = config.get('database', {})
    db_path = db_config.get('path', str(app_root / "cache.db"))
    schema_path = db_config.get('schema_path', str(app_root / "src" / "db_schema.sql"))
    persistence = SQLiteManager(db_path, schema_path, config)
    validator = Validator(config)
    logic_service = LogicService(persistence, config)
    writer = MasterWriter(config)
    
    controller = AppController(
        config_controller=config_controller,
        ingestion=ingestion,
        persistence=persistence,
        validator=validator,
        logic_service=logic_service,
        writer=writer
    )

    done_event = threading.Event()
    
    def on_progress(p):
        if int(p) % 10 == 0:
            logger.info(f"Progress: {p:.1f}%")

    def on_complete(success, msg, path):
        if success:
            logger.info(f"SUCCESS: {msg}. Report: {path}")
        else:
            logger.error(f"FAILED: {msg}")
        done_event.set()

    logger.info("Triggering run_consolidation_all_dates...")
    controller.run_consolidation_all_dates(on_progress, on_complete)
    
    # Wait for completion
    while not done_event.is_set():
        time.sleep(1)
    
    persistence.close()
    logger.info("Done.")

if __name__ == "__main__":
    main()
