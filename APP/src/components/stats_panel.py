import tkinter as tk
from tkinter import ttk
from ..theme import ThemeManager

class StatsPanel(ttk.LabelFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, text="📈 СТАТИСТИКА ДНЯ", padding=10)
        self.controller = controller
        self._setup_ui()

    def _setup_ui(self):
        self.stats_label = ttk.Label(
            self, 
            text="Сотрудников: 0\nОтчетов готово: 0\nОшибок: 0", 
            justify=tk.LEFT, 
            background=ThemeManager.COLORS['sidebar']
        )
        self.stats_label.pack(fill=tk.X)
        
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            self, 
            variable=self.progress_var, 
            maximum=100
        )
        self.progress_bar.pack(fill=tk.X, pady=(10, 0))

    def update_stats(self, ready_count, total_count, total_income=None, total_expense=None, error_count=0):
        text = f"Готово: {ready_count}/{total_count}"
        if total_income is not None and total_expense is not None:
            text += f"\nПриход: {total_income:,.2f}\nРасход: {total_expense:,.2f}"
        text += f"\nОшибки: {error_count}"
        self.stats_label.config(text=text)

    def set_progress(self, value):
        self.progress_var.set(value)

    def get_progress(self):
        return self.progress_var.get()
