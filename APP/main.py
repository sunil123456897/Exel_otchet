import sys
import tkinter as tk
import logging
import logging.handlers
import ctypes
from pathlib import Path
from tkinter import messagebox
from typing import Any

app_root = Path(__file__).parent.absolute()
if str(app_root) not in sys.path:
    sys.path.insert(0, str(app_root))

from core.bootstrap import Bootstrap  # noqa: E402
from core.shared.path_scrub import scrub_path  # noqa: E402


class _PiiScrubFilter(logging.Filter):
    """Redact Windows user names / SMB shares from every log record.

    Attached to the root handlers so logs shared with support (diagnostic
    package) never leak PII such as ``C:\\Users\\<name>``. ``scrub_path``
    only masks the user-name segment and ``\\\\server\\share`` — ordinary
    drive/relative paths pass through, so diagnostic value is preserved.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = scrub_path(record.msg)
        return True


def preflight_gui_imports() -> type[Any]:
    from core.ui.gui_master import GuiMaster

    gui_master_cls: type[Any] = GuiMaster
    return gui_master_cls


def _enable_dpi_awareness() -> None:
    """Enable per-monitor DPI awareness so the UI is crisp on HiDPI displays."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main() -> None:
    log_file = app_root / "startup_log.txt"
    # Build log handlers defensively. On a read-only install (e.g. under
    # Program Files without admin rights) opening the log file must NOT kill
    # startup — especially under pythonw, where there is no console to show
    # the error and the app just "silently dies". delay=True defers opening
    # the file until the first record; if even that fails, logging degrades
    # gracefully (stderr) instead of raising here before the GUI exists.
    handlers: list[logging.Handler] = []
    try:
        handlers.append(
            logging.handlers.RotatingFileHandler(
                log_file,
                encoding="utf-8",
                maxBytes=10 * 1024 * 1024,  # 10 MB
                backupCount=5,
                delay=True,
            )
        )
    except Exception:
        pass
    handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )
    logger = logging.getLogger("Main")
    # Scrub PII (user names / SMB shares) from everything the handlers emit,
    # including records propagated from child loggers across the app.
    _pii_filter = _PiiScrubFilter()
    for _handler in logging.getLogger().handlers:
        _handler.addFilter(_pii_filter)
    logger.info(f"--- STARTING: {app_root} ---")
    _enable_dpi_awareness()

    # License check: in production mode (.py removed), this returns True
    # once the trial period expires. The app still launches but in
    # view-only mode (action buttons disabled). In development (.py
    # present) this is always False — no interference for the developer.
    try:
        from core.license import check_license
        view_only = check_license()
    except Exception:
        view_only = False
    if view_only:
        logger.warning("License expired — starting in view-only mode")

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
        GuiMaster(root, cfg_ctl, app_ctl, view_only=view_only)

        def on_close() -> None:
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
