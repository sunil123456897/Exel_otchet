import os
import sys
import logging
import threading
import argparse
from datetime import datetime
from pathlib import Path

app_root = Path(__file__).parent.absolute()
if str(app_root) not in sys.path:
    sys.path.insert(0, str(app_root))

from core.bootstrap import Bootstrap


def main():
    parser = argparse.ArgumentParser(description="Run headless consolidation.")
    parser.add_argument("--date", type=str, help="Date to consolidate (DD.MM.YYYY)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger("Headless")
    app_ctl = None
    db = None
    timeout = int(os.environ.get("HEADLESS_RUN_TIMEOUT", "600"))
    try:
        _, app_ctl, db = Bootstrap.setup(app_root, str(app_root / "config.yaml"))
        done = threading.Event()

        def on_comp(ok, msg, path):
            if ok:
                logger.info(f"DONE: {msg}")
            else:
                logger.error(msg)
            done.set()

        if args.date:
            target_date = datetime.strptime(args.date, "%d.%m.%Y")
            logger.info(f"Triggering run_consolidation for {args.date}...")
            app_ctl.run_consolidation(target_date, lambda p: None, on_comp)
        else:
            logger.info("Triggering run_consolidation_all_dates...")
            app_ctl.run_consolidation_all_dates(lambda p: None, on_comp)

        finished = done.wait(timeout=timeout) if timeout > 0 else done.wait()
        if not finished:
            logger.error("Timed out waiting for consolidation to complete")
            sys.exit(1)
    except Exception as e:
        logger.critical(f"Failed: {e}")
        sys.exit(1)
    finally:
        if app_ctl is not None:
            app_ctl.shutdown()
        elif db is not None:
            db.close()


if __name__ == "__main__":
    main()
