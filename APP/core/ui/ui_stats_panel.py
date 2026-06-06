import tkinter as tk
from tkinter import ttk
from core.ui.theme import ThemeManager


class StatsPanel(ttk.LabelFrame):
    """Two progress bars: readiness (top, small) and operation (big, main).

    The two are intentionally separated so the user can see at a glance:

    * ``readiness`` — fraction of employees whose reports are ready for
      the currently selected date. Driven by
      :meth:`EmployeeListViewModel.get_progress_percent` whenever the
      employee table is re-synced.
    * ``operation`` — fraction of the long-running build/RSC/
      reconciliation task that is currently running. Driven by
      :class:`OperationState` snapshots.
    """

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

        # Readiness (small, on top). Tracks how many of today's reports
        # are present on disk — a "how much work is left" indicator.
        self._readiness_caption = ttk.Label(
            self,
            text="Готовность сотрудников:",
            background=ThemeManager.COLORS['sidebar'],
        )
        self._readiness_caption.pack(fill=tk.X, pady=(10, 0))
        self.readiness_var = tk.DoubleVar()
        self.readiness_bar = ttk.Progressbar(
            self,
            variable=self.readiness_var,
            maximum=100,
            length=120,
        )
        self.readiness_bar.pack(fill=tk.X)

        # Operation (big, main). Tracks the running consolidation/RSC/
        # reconciliation operation, identical to what
        # OperationStatusBar shows but as a graphical bar.
        self._operation_caption = ttk.Label(
            self,
            text="Текущая операция:",
            background=ThemeManager.COLORS['sidebar'],
        )
        self._operation_caption.pack(fill=tk.X, pady=(8, 0))
        self.operation_var = tk.DoubleVar()
        self.operation_bar = ttk.Progressbar(
            self,
            variable=self.operation_var,
            maximum=100,
        )
        self.operation_bar.pack(fill=tk.X, pady=(2, 0))

    def update_stats(self, ready_count, total_count, total_income=None, total_expense=None, error_count=0):
        text = f"Готово: {ready_count}/{total_count}"
        if total_income is not None and total_expense is not None:
            text += f"\nПриход: {total_income:,.2f}\nРасход: {total_expense:,.2f}"
        text += f"\nОшибки: {error_count}"
        self.stats_label.config(text=text)

    def set_readiness(self, value: float) -> None:
        """Set the small readiness bar to ``value`` (0-100)."""
        self.readiness_var.set(max(0.0, min(100.0, value)))

    def set_operation(self, value: float) -> None:
        """Set the big operation bar to ``value`` (0-100)."""
        self.operation_var.set(max(0.0, min(100.0, value)))

    def set_progress(self, value):
        """Back-compat shim. Treats the value as the operation progress
        because that was the original single-bar use; the readiness
        bar is updated explicitly via :meth:`set_readiness`.
        """
        self.set_operation(value)

    def get_progress(self):
        return self.operation_var.get()
