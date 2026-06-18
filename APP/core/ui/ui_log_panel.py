import tkinter as tk
from tkinter import ttk, scrolledtext
from core.ui.theme import ThemeManager

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
            font=ThemeManager.FONTS['caption'],
            background=ThemeManager.COLORS['bg_sidebar']
        ).pack(side=tk.LEFT)
        
        ttk.Button(
            header_frame,
            text="🧹 Очистить",
            command=self.clear_logs
        ).pack(side=tk.RIGHT)
        
        self.log_area = scrolledtext.ScrolledText(
            self,
            state='disabled',
            font=ThemeManager.FONTS['mono'],
            borderwidth=1,
            relief='solid',
            bg=ThemeManager.COLORS["bg_panel"],
            fg=ThemeManager.COLORS["text"],
            insertbackground=ThemeManager.COLORS["text"],
            selectbackground=ThemeManager.COLORS["primary"],
            selectforeground=ThemeManager.COLORS["text_inverse"],
        )
        # ScrolledText uses explicit colours that do not follow ttk
        # styles — register so dark-mode switches re-colour the bg/fg.
        ThemeManager.register(self.log_area, bg_key="bg_panel", fg_key="text")
        self.log_area.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)

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

