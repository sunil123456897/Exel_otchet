import sys
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

app_root = Path("APP").absolute()
if str(app_root) not in sys.path: sys.path.insert(0, str(app_root))

from core.bootstrap import Bootstrap

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger("FullCycle")

try:
    _, app_ctl, db = Bootstrap.setup(app_root, str(app_root / "config.yaml"))
    target_date = datetime(2026, 3, 23)
    
    done_refresh = threading.Event()
    def on_refresh_complete(*args):
        done_refresh.set()
        
    logger.info("Triggering refresh_status...")
    app_ctl.refresh_status(target_date, lambda p: None, on_refresh_complete)
    while not done_refresh.is_set(): time.sleep(0.5)

    done_consolidation = threading.Event()
    def on_consolidation_complete(ok, msg, path):
        if ok:
            logger.info(f"SUCCESS: Report saved to: {path}")
        else:
            logger.error(f"FAILED: {msg}")
        done_consolidation.set()

    logger.info("Triggering run_consolidation for 23.03.2026...")
    app_ctl.run_consolidation(target_date, lambda p: None, on_consolidation_complete)
    
    while not done_consolidation.is_set():
        time.sleep(0.5)
        
    db.close()
except Exception as e: 
    logger.critical(f"Failed: {e}")

# Now run verify_colors
print("\n--- RUNNING COLOR VERIFICATION ---")
import verify_colors
verify_colors.verify_report()
