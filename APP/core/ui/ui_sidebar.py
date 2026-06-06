import tkinter as tk
from tkinter import ttk
from tkcalendar import DateEntry
from datetime import datetime, timedelta
from core.ui.theme import ThemeManager


def _last_day_of_month(month_start: datetime) -> datetime:
    if month_start.month == 12:
        return month_start.replace(day=31)
    return (month_start.replace(day=28) + timedelta(days=4)).replace(
        day=1
    ) - timedelta(days=1)


def _previous_month_start(today: datetime) -> datetime:
    if today.month == 1:
        return today.replace(year=today.year - 1, month=12, day=1)
    return today.replace(month=today.month - 1, day=1)


def get_default_period_range(today: datetime | None = None) -> tuple[datetime, datetime]:
    today = today or datetime.now()
    if today.day == 1:
        start = _previous_month_start(today)
        return start, _last_day_of_month(start)

    start = today.replace(day=1)
    return start, today


class Sidebar(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, width=300, padding="10", style="Sidebar.TFrame")
        self.controller = controller
        self.pack_propagate(False)
        self.canvas = tk.Canvas(
            self,
            borderwidth=0,
            highlightthickness=0,
            background=ThemeManager.COLORS["sidebar"],
        )
        self.scrollbar = ttk.Scrollbar(
            self, orient=tk.VERTICAL, command=self.canvas.yview
        )
        self.content = ttk.Frame(self.canvas, style="Sidebar.TFrame")
        self._content_window = self.canvas.create_window(
            (0, 0), window=self.content, anchor=tk.NW
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.content.bind("<Configure>", self._on_content_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)
        self._setup_ui()

    def _on_content_configure(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self._content_window, width=event.width)

    def _bind_mousewheel(self, _event):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        # X11 / Linux use discrete Button-4 (up) and Button-5 (down) for
        # the wheel — ``<MouseWheel>`` does not fire on those platforms.
        self.canvas.bind_all("<Button-4>", self._on_button4)
        self.canvas.bind_all("<Button-5>", self._on_button5)

    def _unbind_mousewheel(self, _event):
        self.canvas.unbind_all("<MouseWheel>")
        self.canvas.unbind_all("<Button-4>")
        self.canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_button4(self, _event):
        self.canvas.yview_scroll(-1, "units")
        return "break"

    def _on_button5(self, _event):
        self.canvas.yview_scroll(1, "units")
        return "break"

    def _setup_ui(self):
        ttk.Label(
            self.content,
            text="📊 ПАНЕЛЬ УПРАВЛЕНИЯ",
            style="Header.TLabel",
            background=ThemeManager.COLORS["sidebar"],
        ).pack(pady=(0, 10), anchor=tk.W)

        # Date Selection
        date_frame = ttk.LabelFrame(self.content, text="📅 ВЫБОР ДАТЫ", padding=6)
        date_frame.pack(fill=tk.X, pady=(0, 6))

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
        self.date_entry.pack(pady=(0, 5), fill=tk.X)
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
        emp_frame = ttk.LabelFrame(self.content, text="👤 СОТРУДНИКИ", padding=6)
        emp_frame.pack(fill=tk.X, pady=(0, 6))

        self.add_employee_btn = ttk.Button(
            emp_frame, text="➕ Добавить", command=self.controller.add_employee_dialog
        )
        self.add_employee_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        self.attach_btn = ttk.Button(
            emp_frame, text="📎 Привязать", command=self.controller.attach_file_dialog
        )
        self.attach_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Consolidation Actions
        action_frame = ttk.LabelFrame(self.content, text="🚀 СБОРКА", padding=6)
        action_frame.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(action_frame, text="Кураторский отчет:").pack(anchor=tk.W)
        self.curator_var = tk.StringVar(value="Общий отчет")
        self.curator_combo = ttk.Combobox(
            action_frame,
            textvariable=self.curator_var,
            state="readonly",
            values=["Общий отчет", "Куратор Борис", "Куратор Иван"],
        )
        self.curator_combo.pack(fill=tk.X, pady=(0, 3))

        self.consolidate_btn = ttk.Button(
            action_frame,
            text="⚡ СОБРАТЬ ДЕНЬ",
            style="Action.TButton",
            command=self.controller.run_consolidation,
        )
        self.consolidate_btn.pack(fill=tk.X, pady=(0, 3))

        self.consolidate_all_btn = ttk.Button(
            action_frame,
            text="🌍 СОБРАТЬ ВСЕ ДАТЫ",
            command=self.controller.run_consolidation_all_dates,
        )
        self.consolidate_all_btn.pack(fill=tk.X, pady=(0, 3))

        # Monthly Range Section
        month_frame = ttk.LabelFrame(self.content, text="📆 СБОРКА ЗА ПЕРИОД", padding=6)
        month_frame.pack(fill=tk.X, pady=(0, 6))

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
        self.month_start_entry.pack(pady=(0, 4), fill=tk.X)
        # По умолчанию — текущий месяц, а 1-го числа — прошлый полный месяц.
        today = datetime.now()
        default_start, default_end = get_default_period_range(today)
        self.month_start_entry.set_date(default_start)

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
        self.month_end_entry.pack(pady=(0, 4), fill=tk.X)
        self.month_end_entry.set_date(default_end)

        # Quick month preset buttons
        preset_frame = ttk.Frame(month_frame)
        preset_frame.pack(fill=tk.X, pady=(0, 4))
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
        self.consolidate_month_btn.pack(fill=tk.X, pady=(0, 3))

        self.rsch_month_btn = ttk.Button(
            month_frame,
            text="🧾 СОБРАТЬ РСЧ ЗА ПЕРИОД",
            command=self.controller.run_rsch_report_month,
        )
        self.rsch_month_btn.pack(fill=tk.X)

        self.rsch_btn = ttk.Button(
            action_frame,
            text="🧾 СОБРАТЬ РСЧ",
            command=self.controller.run_rsch_report,
        )
        self.rsch_btn.pack(fill=tk.X, pady=(0, 3))

        self.reconciliation_btn = ttk.Button(
            action_frame,
            text="✅ СВЕРИТЬ С РСЧ",
            command=self.controller.run_reconciliation_report,
        )
        self.reconciliation_btn.pack(fill=tk.X, pady=(0, 3))

        self.auto_reconciliation_btn = ttk.Button(
            action_frame,
            text="✅ АВТОСВЕРКА",
            style="Action.TButton",
            command=self.controller.run_auto_reconciliation_day,
        )
        self.auto_reconciliation_btn.pack(fill=tk.X, pady=(0, 3))

        # Theme switcher: 3 options (light/dark/system). The "system"
        # option is auto-disabled on Windows 8 where the registry key
        # we read is not present — there's nothing to follow.
        theme_frame = ttk.LabelFrame(self.content, text="🎨 ТЕМА", padding=6)
        theme_frame.pack(fill=tk.X, pady=(0, 6))
        self.theme_var = tk.StringVar(value="light")
        from core.ui.system_theme import is_windows_8_or_earlier
        win8 = is_windows_8_or_earlier()
        for value, label in (
            ("light", "☀️ Светлая"),
            ("dark", "🌙 Тёмная"),
        ):
            ttk.Radiobutton(
                theme_frame,
                text=label,
                variable=self.theme_var,
                value=value,
                command=self._on_theme_changed,
            ).pack(anchor=tk.W)
        # "Системная" only useful on Win 10/11, macOS, modern Linux.
        rb_system = ttk.Radiobutton(
            theme_frame,
            text="💻 Системная" + (" (нет данных)" if win8 else ""),
            variable=self.theme_var,
            value="system",
            command=self._on_theme_changed,
        )
        rb_system.pack(anchor=tk.W)
        if win8:
            rb_system.state(["disabled"])
        from core.ui.tooltip import Tooltip
        Tooltip(rb_system, "Следовать теме ОС. На Windows 8/8.1 недоступно — ОС не публикует тему.")

    def _on_theme_changed(self):
        """Forward the chosen theme to the master controller."""
        value = self.theme_var.get()
        setter = getattr(self.controller, "set_theme", None)
        if callable(setter):
            setter(value)

    def _set_current_month(self):
        today = datetime.now()
        self.month_start_entry.set_date(today.replace(day=1))
        self.month_end_entry.set_date(_last_day_of_month(today))

    def _set_previous_month(self):
        today = datetime.now()
        prev_month = _previous_month_start(today)
        self.month_start_entry.set_date(prev_month)
        self.month_end_entry.set_date(_last_day_of_month(prev_month))

    def get_date(self):
        return self.date_entry.get_date()

    def get_curator(self):
        value = self.curator_var.get()
        if value == "Куратор Борис":
            return "boris"
        if value == "Куратор Иван":
            return "ivan"
        return None

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
        if hasattr(self, "rsch_month_btn"):
            self.rsch_month_btn.config(state=state)

    def set_reconciliation_state(self, state):
        self.reconciliation_btn.config(state=state)
        self.auto_reconciliation_btn.config(state=state)

    # --- global state ---------------------------------------------------

    _OPERATION_BUTTONS_ATTRS = (
        "refresh_btn",
        "add_employee_btn",
        "attach_btn",
        "consolidate_btn",
        "consolidate_all_btn",
        "consolidate_month_btn",
        "rsch_btn",
        "rsch_month_btn",
        "reconciliation_btn",
        "auto_reconciliation_btn",
    )

    def apply(self, snap) -> None:
        """Apply global operation state to all action widgets.

        When any operation is running, every action button is disabled.
        This fixes the original bug where only the clicked button was disabled
        and the user could fire a second operation that conflicted with the first.
        """
        busy = snap.current.value != ""
        state = "disabled" if busy else "normal"
        for attr in self._OPERATION_BUTTONS_ATTRS:
            btn = getattr(self, attr, None)
            if btn is not None:
                try:
                    btn.config(state=state)
                except tk.TclError:
                    pass
