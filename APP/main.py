import sys
import tkinter as tk
import logging
import logging.handlers
import ctypes
from pathlib import Path
from tkinter import messagebox

app_root = Path(__file__).parent.absolute()
if str(app_root) not in sys.path:
    sys.path.insert(0, str(app_root))

from core.bootstrap import Bootstrap  # noqa: E402


def preflight_gui_imports():
    from core.ui.gui_master import GuiMaster

    return GuiMaster


def _enable_dpi_awareness() -> None:
    """Enable per-monitor DPI awareness so the UI is crisp on HiDPI displays."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


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
    _enable_dpi_awareness()
    app_ctl = None
    root = None
    try:
        GuiMaster = preflight_gui_imports()
        try:
            cfg_ctl, app_ctl, db = Bootstrap.setup(
                app_root, str(app_root / "config.yaml")
            )
        except RuntimeError as e:
            # Bootstrap signals missing critical dependency (or other
            # hard config failures) by raising RuntimeError. Surface a
            # friendly dialog *before* Tk root exists; messagebox will
            # spin up a default root for us.
            logger.critical(f"Bootstrap failed: {e}")
            try:
                messagebox.showerror("Ошибка запуска", str(e))
            except Exception:
                pass
            sys.exit(1)
        root = tk.Tk()
        if Bootstrap._integrity_warning:
            # Surfaced by _check_db_integrity_on_startup during bootstrap.
            # Tk root is now available so we can show a real messagebox.
            try:
                messagebox.showwarning(
                    "Предупреждение: целостность БД",
                    Bootstrap._integrity_warning,
                )
            except Exception:
                logger.warning(
                    "Could not show integrity warning dialog: %s",
                    Bootstrap._integrity_warning,
                )
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
