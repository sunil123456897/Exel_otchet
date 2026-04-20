import tkinter as tk
from tkinter import ttk
from tkcalendar import DateEntry
from datetime import datetime, timedelta
from core.ui.theme import ThemeManager


class Sidebar(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, width=320, padding="15", style="Sidebar.TFrame")
        self.controller = controller
        self.pack_propagate(False)
        self._setup_ui()

    def _setup_ui(self):
        ttk.Label(
            self,
            text="📊 ПАНЕЛЬ УПРАВЛЕНИЯ",
            style="Header.TLabel",
            background=ThemeManager.COLORS["sidebar"],
        ).pack(pady=(0, 20), anchor=tk.W)

        # Date Selection
        date_frame = ttk.LabelFrame(self, text="📅 ВЫБОР ДАТЫ", padding=10)
        date_frame.pack(fill=tk.X, pady=(0, 10))

        self.date_entry = DateEntry(
            date_frame,
            width=12,
            background=ThemeManager.COLORS["primary"],
            foreground="white",
            borderwidth=2,
            date_pattern="dd.mm.yyyy",
            locale="ru_RU",
            headersbackground=ThemeManager.COLORS["primary"],
            selectbackground=ThemeManager.COLORS["accent"]
            if "accent" in ThemeManager.COLORS
            else "#007bff",
        )
        self.date_entry.pack(pady=(0, 10), fill=tk.X)
        self.date_entry.bind(
            "<<DateEntrySelected>>", lambda e: self.controller.refresh_status()
        )

        self.refresh_btn = ttk.Button(
            date_frame,
            text="🔄 Обновить статус",
            command=self.controller.refresh_status,
        )
        self.refresh_btn.pack(fill=tk.X)

        # Employee Management
        emp_frame = ttk.LabelFrame(self, text="👤 СОТРУДНИКИ", padding=10)
        emp_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Button(
            emp_frame, text="➕ Добавить", command=self.controller.add_employee_dialog
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        ttk.Button(
            emp_frame, text="📎 Привязать", command=self.controller.attach_file_dialog
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Consolidation Actions
        action_frame = ttk.LabelFrame(self, text="🚀 СБОРКА", padding=10)
        action_frame.pack(fill=tk.X, pady=(0, 10))

        self.consolidate_btn = ttk.Button(
            action_frame,
            text="⚡ СОБРАТЬ ДЕНЬ",
            style="Action.TButton",
            command=self.controller.run_consolidation,
        )
        self.consolidate_btn.pack(fill=tk.X, pady=(0, 5))

        self.consolidate_all_btn = ttk.Button(
            action_frame,
            text="🌍 СОБРАТЬ ВСЕ ДАТЫ",
            command=self.controller.run_consolidation_all_dates,
        )
        self.consolidate_all_btn.pack(fill=tk.X, pady=(0, 5))

        # Monthly Range Section
        month_frame = ttk.LabelFrame(self, text="📆 СБОРКА ЗА ПЕРИОД", padding=10)
        month_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(month_frame, text="С:").pack(anchor=tk.W)
        self.month_start_entry = DateEntry(
            month_frame,
            width=12,
            background=ThemeManager.COLORS["primary"],
            foreground="white",
            borderwidth=2,
            date_pattern="dd.mm.yyyy",
            locale="ru_RU",
            headersbackground=ThemeManager.COLORS["primary"],
        )
        self.month_start_entry.pack(pady=(0, 8), fill=tk.X)
        # По умолчанию — первое число текущего месяца
        today = datetime.now()
        self.month_start_entry.set_date(today.replace(day=1))

        ttk.Label(month_frame, text="По:").pack(anchor=tk.W)
        self.month_end_entry = DateEntry(
            month_frame,
            width=12,
            background=ThemeManager.COLORS["primary"],
            foreground="white",
            borderwidth=2,
            date_pattern="dd.mm.yyyy",
            locale="ru_RU",
            headersbackground=ThemeManager.COLORS["primary"],
        )
        self.month_end_entry.pack(pady=(0, 8), fill=tk.X)
        # По умолчанию — последнее число текущего месяца
        if today.month == 12:
            last_day = today.replace(day=31)
        else:
            last_day = (today.replace(day=28) + timedelta(days=4)).replace(
                day=1
            ) - timedelta(days=1)
        self.month_end_entry.set_date(last_day)

        # Quick month preset buttons
        preset_frame = ttk.Frame(month_frame)
        preset_frame.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(
            preset_frame, text="Этот месяц", command=self._set_current_month
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        ttk.Button(
            preset_frame, text="Пред. месяц", command=self._set_previous_month
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))

        self.consolidate_month_btn = ttk.Button(
            month_frame,
            text="📊 СОБРАТЬ ПЕРИОД",
            style="Action.TButton",
            command=self.controller.run_consolidation_month,
        )
        self.consolidate_month_btn.pack(fill=tk.X)

        self.rsch_btn = ttk.Button(
            action_frame,
            text="🧾 СОБРАТЬ РСЧ",
            command=self.controller.run_rsch_report,
        )
        self.rsch_btn.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(action_frame, text="Режим РСЧ:").pack(anchor=tk.W, pady=(2, 0))
        self.rsch_mode_var = tk.StringVar(value="Общий файл")
        self.rsch_mode_combo = ttk.Combobox(
            action_frame,
            textvariable=self.rsch_mode_var,
            state="readonly",
            values=["Общий файл", "Отдельные файлы"],
        )
        self.rsch_mode_combo.pack(fill=tk.X, pady=(0, 5))

    def _set_current_month(self):
        today = datetime.now()
        self.month_start_entry.set_date(today.replace(day=1))
        if today.month == 12:
            last_day = today.replace(day=31)
        else:
            last_day = (today.replace(day=28) + timedelta(days=4)).replace(
                day=1
            ) - timedelta(days=1)
        self.month_end_entry.set_date(last_day)

    def _set_previous_month(self):
        today = datetime.now()
        if today.month == 1:
            prev_month = today.replace(year=today.year - 1, month=12, day=1)
        else:
            prev_month = today.replace(month=today.month - 1, day=1)
        self.month_start_entry.set_date(prev_month)
        if prev_month.month == 12:
            last_day = prev_month.replace(day=31)
        else:
            last_day = (prev_month.replace(day=28) + timedelta(days=4)).replace(
                day=1
            ) - timedelta(days=1)
        self.month_end_entry.set_date(last_day)

    def get_date(self):
        return self.date_entry.get_date()

    def get_month_range(self):
        """Возвращает (start_date, end_date) для месячного отчёта."""
        start_date = self.month_start_entry.get_date()
        end_date = self.month_end_entry.get_date()
        today = datetime.now().date()
        if end_date > today:
            end_date = today
        return start_date, end_date

    def set_refresh_state(self, state):
        self.refresh_btn.config(state=state)

    def set_consolidate_state(self, state):
        self.consolidate_btn.config(state=state)

    def set_consolidate_all_state(self, state):
        self.consolidate_all_btn.config(state=state)

    def set_consolidate_month_state(self, state):
        self.consolidate_month_btn.config(state=state)

    def set_rsch_state(self, state):
        self.rsch_btn.config(state=state)

    def get_rsch_mode(self) -> str:
        value = self.rsch_mode_var.get()
        if value == "Отдельные файлы":
            return "per_file"
        return "combined"

    def set_rsch_mode(self, mode: str) -> None:
        if mode == "per_file":
            self.rsch_mode_var.set("Отдельные файлы")
        else:
            self.rsch_mode_var.set("Общий файл")
