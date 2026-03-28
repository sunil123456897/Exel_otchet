import tkinter as tk
from tkinter import ttk, scrolledtext
from ..theme import ThemeManager

class LogPanel(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, style='Sidebar.TFrame')
        self.controller = controller
        self._setup_ui()

    def _setup_ui(self):
        header_frame = ttk.Frame(self, style='Sidebar.TFrame')
        header_frame.pack(fill=tk.X, pady=(10, 2))
        
        ttk.Label(
            header_frame, 
            text="📝 Логи:", 
            font=('Segoe UI', 9), 
            background=ThemeManager.COLORS['sidebar']
        ).pack(side=tk.LEFT)
        
        ttk.Button(
            header_frame, 
            text="🧹", 
            width=3, 
            command=self.clear_logs
        ).pack(side=tk.RIGHT)
        
        self.log_area = scrolledtext.ScrolledText(
            self, 
            height=12, 
            state='disabled', 
            font=('Consolas', 8), 
            borderwidth=1, 
            relief='solid'
        )
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def clear_logs(self):
        self.log_area.configure(state='normal')
        self.log_area.delete('1.0', tk.END)
        self.log_area.configure(state='disabled')

    def append_log(self, message):
        self.log_area.configure(state='normal')
        self.log_area.insert(tk.END, message + '\n')
        self.log_area.configure(state='disabled')
        self.log_area.yview(tk.END)

    def get_widget(self):
        return self.log_area
