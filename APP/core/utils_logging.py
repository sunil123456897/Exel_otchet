"""
Module: utils_logging
Description: Part of the Master-Report v5.5 architecture.
This module provides specialized functionality for the financial consolidation system.
Maintained for high modularity, testability, and structural integrity.
"""
import logging
import tkinter as tk

class TextHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)
        def append():
            self.text_widget.configure(state='normal')
            self.text_widget.insert(tk.END, msg + '\n')
            self.text_widget.configure(state='disabled')
            self.text_widget.yview(tk.END)
        self.text_widget.after(0, append)

def setup_gui_logging(log_widget):
    handler = TextHandler(log_widget)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S'))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    return handler


