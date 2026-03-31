import sys
import tkinter as tk
import logging
from pathlib import Path

app_root = Path(__file__).parent.absolute()
if str(app_root) not in sys.path: sys.path.insert(0, str(app_root))

from src.bootstrap import Bootstrap
from src.frontend.gui_master import GuiMaster

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', handlers=[logging.FileHandler(app_root / "startup_log.txt", encoding='utf-8'), logging.StreamHandler()])
    logger = logging.getLogger("Main"); logger.info(f"--- STARTING: {app_root} ---")
    try:
        cfg_ctl, app_ctl, db = Bootstrap.setup(app_root, str(app_root / "config.yaml"))
        root = tk.Tk(); app = GuiMaster(root, cfg_ctl, app_ctl)
        root.protocol("WM_DELETE_WINDOW", lambda: (logger.info("Shutdown..."), db.close(), root.destroy()))
        root.mainloop()
    except Exception as e: logger.critical(f"Failed: {e}", exc_info=True); sys.exit(1)

if __name__ == "__main__": main()
