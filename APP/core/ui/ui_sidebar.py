import sys
import logging
import tkinter as tk
from tkinter import ttk
from tkcalendar import DateEntry
from datetime import datetime, timedelta
from core.ui.theme import ThemeManager
from core.ui.debounce import Debouncer


def _last_day_of_month(month_start: datetime) -> datetime:
    if month_start.month == 12:
        return month_start.replace(day=31)
    return (month_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


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
        screen_w = parent.winfo_screenwidth()
        sidebar_w = max(260, min(360, int(screen_w * 0.22)))
        super().__init__(parent, width=sidebar_w, padding="4", style="Sidebar.TFrame")
        self.controller = controller
        self.pack_propagate(False)
        # Debounce date changes so clicking through dates in the picker
        # does not fire a full refresh per click.
        self._date_debouncer = Debouncer(self, self.controller.refresh_status, delay_ms=250)
        self.canvas = tk.Canvas(
            self,
            borderwidth=0,
            highlightthickness=0,
            background=ThemeManager.COLORS["bg_sidebar"],
        )
        # Canvas uses explicit colours (not a ttk style), so register
        # it to be re-themed on ThemeManager.set_theme().
        ThemeManager.register(self.canvas, bg_key="bg_sidebar")
        self.scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas, style="Sidebar.TFrame")
        self._content_window = self.canvas.create_window((0, 0), window=self.content, anchor=tk.NW)
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
        # Bind on the canvas only — the previous implementation used
        # ``bind_all``, which routed the wheel to every widget while the
        # cursor was over the sidebar (a focus-eating overreach).
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        # X11 / Linux use discrete Button-4 (up) and Button-5 (down) for
        # the wheel — ``<MouseWheel>`` does not fire on those platforms.
        self.canvas.bind("<Button-4>", self._on_button4)
        self.canvas.bind("<Button-5>", self._on_button5)

    def _unbind_mousewheel(self, _event):
        self.canvas.unbind("<MouseWheel>")
        self.canvas.unbind("<Button-4>")
        self.canvas.unbind("<Button-5>")

    def _on_mousewheel(self, event):
        # macOS reports delta as ±1 (small integers); Windows uses
        # multiples of 120. ``int(delta / 120)`` truncates to zero on
        # macOS, so use the platform-specific scaling.
        if sys.platform == "darwin":
            steps = -event.delta
        else:
            steps = -int(event.delta / 120)
        self.canvas.yview_scroll(steps, "units")

    def _on_button4(self, _event):
        self.canvas.yview_scroll(-1, "units")
        return "break"

    def _on_button5(self, _event):
        self.canvas.yview_scroll(1, "units")
        return "break"

    def _setup_ui(self):
        ttk.Label(
            self.content,
            text="📊 ПАНЕЛЬ",
            style="Header.TLabel",
            background=ThemeManager.COLORS["bg_sidebar"],
        ).pack(pady=(0, 4), anchor=tk.W)

        # Date Selection
        date_frame = ttk.LabelFrame(self.content, text="📅 ВЫБОР ДАТЫ", padding=2)
        date_frame.pack(fill=tk.X, pady=(1, 2))

        date_row = ttk.Frame(date_frame)
        date_row.pack(fill=tk.X)

        self.date_entry = DateEntry(
            date_row,
            width=8,
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
        self.date_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.date_entry.bind("<<DateEntrySelected>>", lambda e: self._date_debouncer())
        self.bind("<Destroy>", self._on_destroy, add="+")

        from core.ui.tooltip import Tooltip

        self.refresh_btn = ttk.Button(
            date_row,
            text="🔄",
            width=3,
            command=self.controller.refresh_status,
        )
        self.refresh_btn.pack(side=tk.RIGHT, padx=(4, 0))
        Tooltip(self.refresh_btn, "Обновить статус")
        emp_frame = ttk.LabelFrame(self.content, text="👤 СОТРУДНИКИ", padding=2)
        emp_frame.pack(fill=tk.X, pady=(0, 2))

        self.add_employee_btn = ttk.Button(
            emp_frame, text="➕ Добавить", command=self.controller.add_employee_dialog
        )
        self.add_employee_btn.pack(fill=tk.X, pady=(0, 1))

        self.attach_btn = ttk.Button(
            emp_frame, text="📎 Привязать", command=self.controller.attach_file_dialog
        )
        self.attach_btn.pack(fill=tk.X)

        # Consolidation Actions
        action_frame = ttk.LabelFrame(self.content, text="🚀 СБОРКА", padding=2)
        action_frame.pack(fill=tk.X, pady=(0, 2))

        ttk.Label(action_frame, text="Кураторский отчет:").pack(anchor=tk.W)
        self.curator_var = tk.StringVar(value="Общий отчет")
        self.curator_combo = ttk.Combobox(
            action_frame,
            textvariable=self.curator_var,
            state="readonly",
            values=["Общий отчет", "Куратор Борис", "Куратор Иван"],
        )
        self.curator_combo.pack(fill=tk.X, pady=(0, 2))

        self.consolidate_btn = ttk.Button(
            action_frame,
            text="⚡ СОБРАТЬ ДЕНЬ",
            style="Action.TButton",
            command=self.controller.run_consolidation,
        )
        self.consolidate_btn.pack(fill=tk.X, pady=(0, 1))

        self.consolidate_all_btn = ttk.Button(
            action_frame,
            text="🌍 СОБРАТЬ ВСЕ ДАТЫ",
            command=self.controller.run_consolidation_all_dates,
        )
        self.consolidate_all_btn.pack(fill=tk.X, pady=(0, 1))

        self.rsch_btn = ttk.Button(
            action_frame,
            text="🧾 СОБРАТЬ РСЧ",
            command=self.controller.run_rsch_report,
        )
        self.rsch_btn.pack(fill=tk.X, pady=(0, 1))

        self.reconciliation_btn = ttk.Button(
            action_frame,
            text="✅ СВЕРИТЬ С РСЧ",
            command=self.controller.run_reconciliation_report,
        )
        self.reconciliation_btn.pack(fill=tk.X, pady=(0, 1))

        self.auto_reconciliation_btn = ttk.Button(
            action_frame,
            text="✅ АВТОСВЕРКА",
            style="Action.TButton",
            command=self.controller.run_auto_reconciliation_day,
        )
        self.auto_reconciliation_btn.pack(fill=tk.X, pady=(0, 2))

        # --- Collapsible Period Section ---------------------------------
        self._period_expanded = False
        self._per_container = ttk.LabelFrame(self.content, text="📆 ЗА ПЕРИОД", padding=0)
        self._per_container.pack(fill=tk.X, pady=(0, 2))

        self._per_toggle = ttk.Button(
            self._per_container,
            text="▶  Развернуть",
            command=self._toggle_period_section,
            style="Ghost.TButton",
        )
        self._per_toggle.pack(fill=tk.X, padx=2, pady=2)

        self._per_panel = ttk.Frame(self._per_container, padding=2, style="Sidebar.TFrame")
        # Panel content (built once, hidden until first expand)
        # Date inputs side by side: "С: [date]  По: [date]"
        dates_row = ttk.Frame(self._per_panel)
        dates_row.pack(fill=tk.X, pady=(0, 1))
        ttk.Label(dates_row, text="С:").pack(side=tk.LEFT)
        self.month_start_entry = DateEntry(
            dates_row,
            width=7,
            background=ThemeManager.COLORS["primary"],
            foreground="white",
            borderwidth=2,
            date_pattern="dd.mm.yyyy",
            locale="ru_RU",
            headersbackground=ThemeManager.COLORS["primary"],
        )
        self.month_start_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 6))
        today = datetime.now()
        default_start, default_end = get_default_period_range(today)
        self.month_start_entry.set_date(default_start)

        ttk.Label(dates_row, text="По:").pack(side=tk.LEFT)
        self.month_end_entry = DateEntry(
            dates_row,
            width=7,
            background=ThemeManager.COLORS["primary"],
            foreground="white",
            borderwidth=2,
            date_pattern="dd.mm.yyyy",
            locale="ru_RU",
            headersbackground=ThemeManager.COLORS["primary"],
        )
        self.month_end_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.month_end_entry.set_date(default_end)
        self.month_start_entry.bind(
            "<<DateEntrySelected>>", lambda e: self._validate_period_range()
        )
        self.month_end_entry.bind("<<DateEntrySelected>>", lambda e: self._validate_period_range())
        self._range_warning_tooltip = None
        self._range_invalid = False

        # Quick month preset buttons
        preset_frame = ttk.Frame(self._per_panel)
        preset_frame.pack(fill=tk.X, pady=(0, 1))
        ttk.Button(preset_frame, text="Этот месяц", command=self._set_current_month).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3)
        )
        ttk.Button(preset_frame, text="Пред. месяц", command=self._set_previous_month).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0)
        )

        self.consolidate_month_btn = ttk.Button(
            self._per_panel,
            text="📊 СОБРАТЬ ПЕРИОД",
            style="Action.TButton",
            command=self.controller.run_consolidation_month,
        )
        self.consolidate_month_btn.pack(fill=tk.X, pady=(0, 2))

        self.rsch_month_btn = ttk.Button(
            self._per_panel,
            text="🧾 СОБРАТЬ РСЧ ЗА ПЕРИОД",
            command=self.controller.run_rsch_report_month,
        )
        self.rsch_month_btn.pack(fill=tk.X)

        # Theme switcher: 3 options (light/dark/system). The "system"
        # option is auto-disabled on Windows 8 where the registry key
        # we read is not present — there's nothing to follow.
        theme_frame = ttk.LabelFrame(self.content, text="🎨 ТЕМА", padding=2)
        theme_frame.pack(fill=tk.X, pady=(0, 2))
        self.theme_var = tk.StringVar(value="light")
        theme_row = ttk.Frame(theme_frame, style="Sidebar.TFrame")
        theme_row.pack(fill=tk.X)
        for value, label in (
            ("light", "☀️ Светлая"),
            ("dark", "🌙 Тёмная"),
        ):
            ttk.Radiobutton(
                theme_row,
                text=label,
                variable=self.theme_var,
                value=value,
                command=self._on_theme_changed,
            ).pack(side=tk.LEFT, padx=(0, 4))

        # Settings button (opens universal settings dialog)
        self.settings_btn = ttk.Button(
            self.content,
            text="⚙ НАСТРОЙКИ",
            command=self._open_settings_fallback,
        )
        self.settings_btn.pack(fill=tk.X, pady=(2, 0))

        # Subscribe to scale changes for adaptive width
        self._scale_cb = lambda _s, _mode: self.after(0, self._recompute_width)
        ThemeManager.add_scale_listener(self._scale_cb)

    def _on_theme_changed(self):
        """Forward the chosen theme to the master controller."""
        value = self.theme_var.get()
        setter = getattr(self.controller, "set_theme", None)
        if callable(setter):
            setter(value)

    def _on_destroy(self, _event):
        # Cancel any pending debounced calls so a fast destroy during
        # the user's date-picking does not fire a stale refresh.
        self._date_debouncer.cancel()
        if hasattr(self, "_scale_cb"):
            ThemeManager.remove_scale_listener(self._scale_cb)

    def _recompute_width(self) -> None:
        """Recalculate sidebar width from CONTROL tokens and viewport mode."""
        ctrl = ThemeManager.CONTROL
        sidebar_min = ctrl.get("sidebar_min", 240)
        sidebar_max = ctrl.get("sidebar_max", 380)
        mode = ThemeManager.viewport_mode()
        pcts = {"compact": 0.20, "normal": 0.22, "large": 0.24}
        pct = pcts.get(mode, 0.22)
        screen_w = self.winfo_screenwidth()
        new_w = max(sidebar_min, min(sidebar_max, int(screen_w * pct)))
        if new_w != self.winfo_width():
            self.configure(width=new_w)

    def _open_settings_fallback(self) -> None:
        """Open settings dialog — forward to controller or open directly."""
        opener = getattr(self.controller, "open_settings", None)
        if callable(opener):
            opener()
        else:
            # Fallback: open dialog with a warning log
            from core.ui.ui_settings import SettingsDialog
            from core.infra.settings_store import SettingsStore

            cc = getattr(self.controller, "config_controller", None)
            store = SettingsStore(cc) if cc else None
            logging.warning("GuiMaster.open_settings() not available — direct open")
            SettingsDialog(
                parent=self,
                config_controller=cc,
                settings_store=store,
                current_prefs=store.load_preferences() if store else None,
                gui=self.controller,
            )

    def _toggle_period_section(self):
        """Expand/collapse the period compilation panel."""
        self._period_expanded = not getattr(self, "_period_expanded", False)
        if self._period_expanded:
            self._per_panel.pack(fill=tk.X, after=self._per_toggle)
            self._per_toggle.configure(text="▼  Свернуть")
        else:
            self._per_panel.pack_forget()
            self._per_toggle.configure(text="▶  Развернуть")

    def _set_current_month(self):
        today = datetime.now()
        self.month_start_entry.set_date(today.replace(day=1))
        self.month_end_entry.set_date(_last_day_of_month(today))

    def _set_previous_month(self):
        today = datetime.now()
        prev_month = _previous_month_start(today)
        self.month_start_entry.set_date(prev_month)
        self.month_end_entry.set_date(_last_day_of_month(prev_month))
        self._validate_period_range()

    def _validate_period_range(self) -> None:
        """Highlight the period DateEntries when end < start.

        The validation is purely visual — the actual guard still lives
        in the build commands, but giving the user immediate feedback
        when the picker shows an inverted range prevents them from
        clicking "СОБРАТЬ ПЕРИОД" only to be told about the error.
        """
        try:
            start = self.month_start_entry.get_date()
            end = self.month_end_entry.get_date()
        except (tk.TclError, ValueError):
            return
        invalid = start > end
        # Tk's ``configure`` does not change border colour on ttk
        # widgets, so we use the surrounding LabelFrame text colour as
        # a soft signal: red when invalid, normal otherwise.
        if invalid == self._range_invalid:
            # No change, but the preset buttons may have just been
            # clicked; nothing to do beyond the early-exit guard.
            return
        self._range_invalid = invalid
        if invalid:
            self.month_start_entry.configure(foreground="#dc3545")
            self.month_end_entry.configure(foreground="#dc3545")
            from core.ui.tooltip import Tooltip

            if self._range_warning_tooltip is None:
                self._range_warning_tooltip = Tooltip(
                    self.month_end_entry,
                    "Дата окончания раньше даты начала. Поменяйте одну из дат.",
                )
            else:
                self._range_warning_tooltip.set_text(
                    "Дата окончания раньше даты начала. Поменяйте одну из дат."
                )
        else:
            self.month_start_entry.configure(foreground="white")
            self.month_end_entry.configure(foreground="white")
            from core.ui.tooltip import Tooltip

            if self._range_warning_tooltip is not None:
                self._range_warning_tooltip.set_text("")

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
        for attr in self._OPERATION_BUTTONS_ATTRS:
            btn = getattr(self, attr, None)
            if btn is None:
                continue
            try:
                if busy:
                    btn.state(["disabled"])
                else:
                    btn.state(["!disabled"])
            except tk.TclError:
                pass
