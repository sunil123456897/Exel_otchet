import sys
import tkinter as tk
import logging
import logging.handlers
from pathlib import Path

app_root = Path(__file__).parent.absolute()
if str(app_root) not in sys.path:
    sys.path.insert(0, str(app_root))

from core.bootstrap import Bootstrap  # noqa: E402


def preflight_gui_imports():
    from core.ui.gui_master import GuiMaster

    return GuiMaster


def main():
    log_file = app_root / "startup_log.txt"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.handlers.RotatingFileHandler(
                log_file,
                encoding="utf-8",
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
            ),
            logging.StreamHandler(),
        ],
    )
    logger = logging.getLogger("Main")
    logger.info(f"--- STARTING: {app_root} ---")
    app_ctl = None
    root = None
    try:
        GuiMaster = preflight_gui_imports()
        cfg_ctl, app_ctl, db = Bootstrap.setup(app_root, str(app_root / "config.yaml"))
        root = tk.Tk()
        GuiMaster(root, cfg_ctl, app_ctl)

        def on_close():
            logger.info("Shutdown...")
            try:
                if app_ctl:
                    app_ctl.shutdown()
            except Exception as e:
                logger.error(f"Shutdown error: {e}")
            finally:
                if root:
                    root.destroy()
                sys.exit(0)

        root.protocol("WM_DELETE_WINDOW", on_close)
        root.mainloop()
    except Exception as e:
        logger.critical(f"Failed: {e}", exc_info=True)
        if app_ctl:
            try:
                app_ctl.shutdown()
            except Exception:
                pass
        sys.exit(1)


if __name__ == "__main__":
    main()
