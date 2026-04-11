import sys
import logging
import threading
from pathlib import Path
import os

app_root = Path(__file__).parent.absolute()
if str(app_root) not in sys.path:
    sys.path.insert(0, str(app_root))

from core.bootstrap import Bootstrap


def main():
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger("Headless-Toxic")
    db = None
    try:
        config_path = (
            sys.argv[1] if len(sys.argv) > 1 else os.environ.get("CONFIG_PATH")
        )
        if not config_path:
            logger.error(
                "Usage: python toxic_run.py <config_path>  OR  set CONFIG_PATH env var"
            )
            sys.exit(1)
        _, app_ctl, db = Bootstrap.setup(app_root, config_path)
        done = threading.Event()

        def on_comp(ok, msg, path):
            if ok:
                logger.info(f"DONE: {msg}")
            else:
                logger.error(f"FAIL: {msg}")
            done.set()

        logger.info("Triggering run_consolidation_all_dates with Toxic Data...")
        app_ctl.run_consolidation_all_dates(lambda p: None, on_comp)

        if not done.wait(timeout=600):
            logger.error("Timed out waiting for consolidation to complete")
            sys.exit(1)
    except Exception as e:
        logger.critical(f"Failed: {e}")
        sys.exit(1)
    finally:
        if db is not None:
            db.close()


if __name__ == "__main__":
    main()
