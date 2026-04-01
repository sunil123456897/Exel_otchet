import sys
import logging
import threading
import time
from pathlib import Path
import os

app_root = Path(__file__).parent.absolute()
if str(app_root) not in sys.path: sys.path.insert(0, str(app_root))

from core.bootstrap import Bootstrap

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger("Headless-Toxic")
    try:
        config_path = r"E:\Для Даши\Версия 5\temp_config.yaml"
        _, app_ctl, db = Bootstrap.setup(app_root, config_path)
        done = threading.Event()
        
        def on_comp(ok, msg, path):
            if ok: logger.info(f"DONE: {msg}")
            else: logger.error(f"FAIL: {msg}")
            done.set()

        logger.info("Triggering run_consolidation_all_dates with Toxic Data...")
        app_ctl.run_consolidation_all_dates(lambda p: None, on_comp)
        
        while not done.is_set():
            time.sleep(0.5)
            
        db.close()
    except Exception as e: logger.critical(f"Failed: {e}"); sys.exit(1)

if __name__ == "__main__": main()
