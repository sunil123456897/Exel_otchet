"""
Module: utils_logging
Description: Part of the Master-Report v5.5 architecture.
This module provides specialized functionality for the financial consolidation system.
Maintained for high modularity, testability, and structural integrity.
"""
import logging
import queue
import re

# TD-007: path-scrubbing helpers now live in core.shared.path_scrub so
# that domain code can import them without depending on infra. This
# module re-exports them for backward compatibility with the many
# existing callers that do ``from core.infra.utils_logging import
# scrub_path``.
from core.shared.path_scrub import scrub_path, safe_file_label  # noqa: F401

try:
    import tkinter as tk
except ModuleNotFoundError:  # pragma: no cover - headless environments
    tk = None


WINDOWS_USER_RE = re.compile(r"C:\\Users\\[^\\]+", re.IGNORECASE)
SMB_RE = re.compile(r"\\\\[^\\]+\\[^\\]+")

class TextHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        self.msg_queue = queue.Queue(maxsize=10000)

    def emit(self, record):
        msg = self.format(record)
        try:
            self.msg_queue.put_nowait(msg)
        except queue.Full:
            try:
                self.msg_queue.get_nowait()
                self.msg_queue.put_nowait(msg)
            except queue.Empty:
                pass

    def _process_queue(self):
        try:
            self.text_widget.configure(state='normal')
            count = 0
            while not self.msg_queue.empty() and count < 50:
                try:
                    msg = self.msg_queue.get_nowait()
                    self.text_widget.insert(tk.END, msg + '\n')
                    count += 1
                except queue.Empty:
                    break
            self.text_widget.configure(state='disabled')
            self.text_widget.yview(tk.END)
        finally:
            # ALWAYS reschedule the next poll. Previously this was gated on
            # `if not self.msg_queue.empty()`, so once the queue drained the
            # polling loop died and any subsequent records emitted from
            # worker threads sat in the queue forever, never reaching the
            # GUI. The 100 ms delay throttles the loop — it is NOT a tight
            # spin.
            try:
                self.text_widget.after(100, self._process_queue)
            except Exception:
                # Widget may have been destroyed during shutdown; ignore.
                pass

def setup_gui_logging(log_widget):
    if tk is None:
        raise RuntimeError("tkinter is not available in this environment")
    handler = TextHandler(log_widget)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S'))
    root = logging.getLogger()
    # Prevent duplicate handlers
    for h in root.handlers[:]:
        if isinstance(h, TextHandler):
            root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    # Start the queue polling loop from the GUI thread
    if handler.msg_queue.empty():
        # Initial empty queue — still schedule first poll so future messages are picked up
        pass
    log_widget.after(100, handler._process_queue)
    return handler
