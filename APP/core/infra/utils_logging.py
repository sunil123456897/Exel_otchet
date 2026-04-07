"""
Module: utils_logging
Description: Part of the Master-Report v5.5 architecture.
This module provides specialized functionality for the financial consolidation system.
Maintained for high modularity, testability, and structural integrity.
"""
import logging
import tkinter as tk
import queue

class TextHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        self.msg_queue = queue.Queue()
        self._is_scheduled = False

    def emit(self, record):
        msg = self.format(record)
        self.msg_queue.put(msg)
        if not self._is_scheduled:
            self._is_scheduled = True
            self.text_widget.after_idle(self._process_queue)

    def _process_queue(self):
        try:
            self.text_widget.configure(state='normal')
            count = 0
            while not self.msg_queue.empty() and count < 50:
                try:
                    msg = self.msg_queue.get_nowait()
                    self.text_widget.insert(tk.END, msg + '\n')
                    count += 1
                except queue.Empty: break
            self.text_widget.configure(state='disabled')
            self.text_widget.yview(tk.END)
        finally:
            self._is_scheduled = False
            # Fix 9: Avoid UI freeze during burst by processing in chunks
            if not self.msg_queue.empty():
                self._is_scheduled = True
                self.text_widget.after(100, self._process_queue)

def setup_gui_logging(log_widget):
    handler = TextHandler(log_widget)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S'))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    return handler


