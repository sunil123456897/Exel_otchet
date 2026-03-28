import sys
import os
import tkinter as tk
import logging
from pathlib import Path

# Ensure the root folder containing 'src' is in sys.path
app_root = Path(__file__).parent.absolute()
if str(app_root) not in sys.path:
    sys.path.insert(0, str(app_root))

# Correctly import from the src package
from src.gui_master import GuiMaster
from src.ingestion import IngestionEngine
from src.sqlite_manager import SQLiteManager
from src.logic_service import LogicService, Validator
from src.writer import MasterWriter
from src.controllers.config_controller import ConfigController
from src.controllers.app_controller import AppController

def setup_logging():
    log_file = app_root / "startup_log.txt"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )

def main():
    setup_logging()
    logger = logging.getLogger("Main")
    logger.info(f"--- APP STARTING AT: {app_root} ---")
    
    config_path = app_root / "config.yaml"

    # Initialize components
    try:
        # 1. Config Controller
        config_controller = ConfigController(str(config_path))
        config = config_controller.config
        
        # 2. Ingestion Engine
        ingestion = IngestionEngine(config.get('sh1', {}).get('markers', {}))
        
        # 3. SQLite Manager
        db_config = config.get('database', {})
        db_path = db_config.get('path', str(app_root / "cache.db"))
        schema_path = db_config.get('schema_path', str(app_root / "src" / "db_schema.sql"))
        persistence = SQLiteManager(db_path, schema_path, config)
        
        # 4. Validator
        validator = Validator(config)
        
        # 5. Logic Service
        logic_service = LogicService(persistence, config)
        
        # 6. Master Writer
        writer = MasterWriter(config)
        
        # 7. App Controller
        app_controller = AppController(
            config_controller=config_controller,
            ingestion=ingestion,
            persistence=persistence,
            validator=validator,
            logic_service=logic_service,
            writer=writer
        )
        
        # Start GUI
        root = tk.Tk()
        app = GuiMaster(
            root, 
            config_controller=config_controller,
            app_controller=app_controller
        )
        
        def on_closing():
            logger.info("Shutting down application...")
            try:
                persistence.close()
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")
            root.destroy()
            
        root.protocol("WM_DELETE_WINDOW", on_closing)
        root.mainloop()
        
    except Exception as e:
        logger.critical(f"Initialization failed: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
