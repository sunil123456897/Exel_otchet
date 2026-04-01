import sys
import logging
import threading
import time
from pathlib import Path

app_root = Path(__file__).parent.absolute()
if str(app_root) not in sys.path: sys.path.insert(0, str(app_root))

from core.bootstrap import Bootstrap

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger("Headless")
    try:
        _, app_ctl, db = Bootstrap.setup(app_root, str(app_root / "config.yaml"))
        done = threading.Event()
        
        def on_comp(ok, msg, path):
            if ok: logger.info(f"DONE: {msg}")
            else: logger.error(msg)
            done.set()

        logger.info("Triggering run_consolidation_all_dates...")
        app_ctl.run_consolidation_all_dates(lambda p: None, on_comp)
        
        while not done.is_set():
            time.sleep(0.5)
            
        db.close()
    except Exception as e: logger.critical(f"Failed: {e}"); sys.exit(1)

if __name__ == "__main__": main()
