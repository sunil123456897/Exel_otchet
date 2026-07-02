import sys
import logging
import threading
import tkinter as tk
from tkinter import ttk
from tkcalendar import DateEntry
from datetime import datetime, timedelta
from typing import Optional
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
        super().__init__(parent, width=sidebar_w, padding=ThemeManager.SPACING["xs"], style="Sidebar.TFrame")
        self.controller = controller
        self.pack_propagate(False)
        # Debounce date changes so clicking through dates in the picker
        # does not fire a full refresh per click.
        self._date_debouncer = Debouncer(self, self.controller.refresh_status, delay_ms=250)
        # The scrollable settings area (canvas + scrollbar) lives in its
        # OWN sub-frame. Previously canvas and scrollbar were packed
        # directly into ``self`` (side=LEFT / side=RIGHT), which clashed
        # with StatsPanel/LogPanel packed later from gui_master without a
        # ``side=`` (default TOP). With canvas ``expand=True`` grabbing the
        # full width, those TOP widgets were squeezed into a narrow strip
        # between the canvas and the scrollbar — visible as a "parasitic
        # vertical strip" with clipped content when the window was
        # maximised. Wrapping canvas+scrollbar in a dedicated frame lets
        # StatsPanel/LogPanel pack cleanly below it (side=BOTTOM in
        # gui_master) without competing for space.
        self.scroll_host = ttk.Frame(self, style="Sidebar.TFrame")
        self.scroll_host.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(
            self.scroll_host,
            borderwidth=0,
            highlightthickness=0,
            background=ThemeManager.COLORS["bg_sidebar"],
        )
        # Canvas uses explicit colours (not a ttk style), so register
        # it to be re-themed on ThemeManager.set_theme().  Canvas has
        # no foreground option, so pass fg_key=None.
        ThemeManager.register(self.canvas, bg_key="bg_sidebar", fg_key=None)
        self.scrollbar = ttk.Scrollbar(self.scroll_host, orient=tk.VERTICAL, command=self.canvas.yview)
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
        # Local spacing aliases — keep the section bodies readable while
        # guaranteeing that every sidebar section / button uses the same
        # token instead of ad-hoc magic numbers (audit found four
        # different pady values and three LabelFrame paddings here).
        sp = ThemeManager.SPACING
        _section_pad = sp["xs"]          # sidebar LabelFrame padding (compact)
        _section_gap = (0, sp["sm"])     # vertical gap between sections
        _btn_gap = (0, sp["xs"])         # bottom gap for full-width action buttons

        ttk.Label(
            self.content,
            text="📊 ПАНЕЛЬ",
            style="Header.TLabel",
            background=ThemeManager.COLORS["bg_sidebar"],
        ).pack(pady=(0, sp["xs"]), anchor=tk.W)

        # UX-017: network drive indicator — shows a green/red dot
        # indicating whether the configured network drives are reachable.
        # Updated every 30s by ``_poll_network_drives``.
        self._net_indicator = tk.Label(
            self.content,
            text="🔴 Сеть: проверка...",
            background=ThemeManager.COLORS["bg_sidebar"],
            foreground=ThemeManager.COLORS.get("text_muted", "#64748b"),
            font=ThemeManager.FONTS["micro"],
            anchor=tk.W,
        )
        # Register for re-theming on dark/light switch.
        ThemeManager.register(self._net_indicator, bg_key="bg_sidebar", fg_key="text_muted")
        self._net_indicator.pack(pady=(0, sp["xs"]), anchor=tk.W)
        self._net_poll_after_id: Optional[str] = None
        self.after(2000, self._poll_network_drives)

        # Date Selection
        date_frame = ttk.LabelFrame(self.content, text="📅 ВЫБОР ДАТЫ", padding=_section_pad)
        date_frame.pack(fill=tk.X, pady=(sp["xs"] // 2, sp["sm"]))

        date_row = ttk.Frame(date_frame)
        date_row.pack(fill=tk.X)

        self.date_entry = DateEntry(
            date_row,
            width=12,
            background=ThemeManager.COLORS["primary"],
            foreground=ThemeManager.COLORS["text_inverse"],
            borderwidth=2,
            date_pattern="dd.mm.yyyy",
            locale="ru_RU",
            headersbackground=ThemeManager.COLORS["primary"],
            selectbackground=ThemeManager.COLORS["primary"],
        )
        self.date_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.date_entry.bind("<<DateEntrySelected>>", lambda e: self._date_debouncer())
        self.bind("<Destroy>", self._on_destroy, add="+")

        from core.ui.tooltip import Tooltip

        # UX-014: show weekday abbreviation as a tooltip on the date
        # entry — tkcalendar doesn't support custom date patterns with
        # weekday, so we use a dynamic tooltip instead.
        self._date_tooltip = Tooltip(
            self.date_entry,
            self._weekday_tooltip_text,
        )
        self.date_entry.bind(
            "<<DateEntrySelected>>",
            lambda e: self._date_tooltip.set_text(self._weekday_tooltip_text()),
            add="+",
        )

        self.refresh_btn = ttk.Button(
            date_row,
            text="🔄",
            width=3,
            command=self.controller.refresh_status,
        )
        self.refresh_btn.pack(side=tk.RIGHT, padx=(sp["xs"], 0))
        Tooltip(self.refresh_btn, "Обновить статус")
        emp_frame = ttk.LabelFrame(self.content, text="👤 СОТРУДНИКИ", padding=_section_pad)
        emp_frame.pack(fill=tk.X, pady=_section_gap)

        self.add_employee_btn = ttk.Button(
            emp_frame, text="➕ Добавить", command=self.controller.add_employee_dialog
        )
        self.add_employee_btn.pack(fill=tk.X, pady=_btn_gap)

        self.attach_btn = ttk.Button(
            emp_frame, text="📎 Привязать", command=self.controller.attach_file_dialog
        )
        self.attach_btn.pack(fill=tk.X)

        # Consolidation Actions
        action_frame = ttk.LabelFrame(self.content, text="🚀 СБОРКА", padding=_section_pad)
        action_frame.pack(fill=tk.X, pady=_section_gap)

        ttk.Label(action_frame, text="Кураторский отчет:").pack(anchor=tk.W)
        self.curator_var = tk.StringVar(value="Общий отчет")
        self.curator_combo = ttk.Combobox(
            action_frame,
            textvariable=self.curator_var,
            state="readonly",
            values=["Общий отчет", "Куратор Борис", "Куратор Иван"],
        )
        self.curator_combo.pack(fill=tk.X, pady=_btn_gap)

        self.consolidate_btn = ttk.Button(
            action_frame,
            text="⚡ СОБРАТЬ ДЕНЬ",
            style="Action.TButton",
            command=self.controller.run_consolidation,
        )
        self.consolidate_btn.pack(fill=tk.X, pady=_btn_gap)

        self.consolidate_all_btn = ttk.Button(
            action_frame,
            text="🌍 СОБРАТЬ ВСЕ ДАТЫ",
            command=self.controller.run_consolidation_all_dates,
        )
        self.consolidate_all_btn.pack(fill=tk.X, pady=_btn_gap)

        self.rsch_btn = ttk.Button(
            action_frame,
            text="🧾 СОБРАТЬ РСЧ",
            command=self.controller.run_rsch_report,
        )
        self.rsch_btn.pack(fill=tk.X, pady=_btn_gap)

        self.reconciliation_btn = ttk.Button(
            action_frame,
            text="✅ СВЕРИТЬ С РСЧ",
            command=self.controller.run_reconciliation_report,
        )
        self.reconciliation_btn.pack(fill=tk.X, pady=_btn_gap)

        self.auto_reconciliation_btn = ttk.Button(
            action_frame,
            text="✅ АВТОСВЕРКА",
            style="Action.TButton",
            command=self.controller.run_auto_reconciliation_day,
        )
        self.auto_reconciliation_btn.pack(fill=tk.X, pady=_btn_gap)

        # --- Collapsible Period Section ---------------------------------
        self._period_expanded = False
        self._per_container = ttk.LabelFrame(self.content, text="📆 ЗА ПЕРИОД", padding=0)
        self._per_container.pack(fill=tk.X, pady=_section_gap)

        self._per_toggle = ttk.Button(
            self._per_container,
            text="▶  Развернуть",
            command=self._toggle_period_section,
            style="Ghost.TButton",
        )
        self._per_toggle.pack(fill=tk.X, padx=_section_pad, pady=_section_pad)

        self._per_panel = ttk.Frame(self._per_container, padding=_section_pad, style="Sidebar.TFrame")
        # Panel content (built once, hidden until first expand)
        # Date inputs side by side: "С: [date]  По: [date]"
        dates_row = ttk.Frame(self._per_panel)
        dates_row.pack(fill=tk.X, pady=_btn_gap)
        ttk.Label(dates_row, text="С:").pack(side=tk.LEFT)
        self.month_start_entry = DateEntry(
            dates_row,
            width=7,
            background=ThemeManager.COLORS["primary"],
            foreground=ThemeManager.COLORS["text_inverse"],
            borderwidth=2,
            date_pattern="dd.mm.yyyy",
            locale="ru_RU",
            headersbackground=ThemeManager.COLORS["primary"],
        )
        self.month_start_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(sp["xs"] // 2, sp["sm"] // 2))
        today = datetime.now()
        default_start, default_end = get_default_period_range(today)
        self.month_start_entry.set_date(default_start)

        ttk.Label(dates_row, text="По:").pack(side=tk.LEFT)
        self.month_end_entry = DateEntry(
            dates_row,
            width=7,
            background=ThemeManager.COLORS["primary"],
            foreground=ThemeManager.COLORS["text_inverse"],
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
        preset_frame.pack(fill=tk.X, pady=_btn_gap)
        ttk.Button(preset_frame, text="Этот месяц", command=self._set_current_month).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, sp["xs"] // 2)
        )
        ttk.Button(preset_frame, text="Пред. месяц", command=self._set_previous_month).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(sp["xs"] // 2, 0)
        )

        self.consolidate_month_btn = ttk.Button(
            self._per_panel,
            text="📊 СОБРАТЬ ПЕРИОД",
            style="Action.TButton",
            command=self.controller.run_consolidation_month,
        )
        self.consolidate_month_btn.pack(fill=tk.X, pady=_btn_gap)

        self.rsch_month_btn = ttk.Button(
            self._per_panel,
            text="🧾 СОБРАТЬ РСЧ ЗА ПЕРИОД",
            command=self.controller.run_rsch_report_month,
        )
        self.rsch_month_btn.pack(fill=tk.X)

        # Theme switcher: 3 options (light/dark/system). The "system"
        # option follows the OS dark/light setting (polled every 5s).
        theme_frame = ttk.LabelFrame(self.content, text="🎨 ТЕМА", padding=_section_pad)
        theme_frame.pack(fill=tk.X, pady=_section_gap)
        self.theme_var = tk.StringVar(value="light")
        theme_row = ttk.Frame(theme_frame, style="Sidebar.TFrame")
        theme_row.pack(fill=tk.X)
        for value, label in (
            ("light", "☀️ Светлая"),
            ("dark", "🌙 Тёмная"),
            ("system", "💻 Системная"),
        ):
            ttk.Radiobutton(
                theme_row,
                text=label,
                variable=self.theme_var,
                value=value,
                command=self._on_theme_changed,
            ).pack(side=tk.LEFT, padx=(0, sp["xs"]))

        # Settings button (opens universal settings dialog)
        self.settings_btn = ttk.Button(
            self.content,
            text="⚙ НАСТРОЙКИ",
            command=self._open_settings_fallback,
        )
        self.settings_btn.pack(fill=tk.X, pady=(sp["xs"], 0))
        from core.ui.tooltip import Tooltip
        Tooltip(
            self.settings_btn,
            "Открыть диалог настроек: пути, сеть, бэкапы, логика, БД, тема",
        )

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
            self.month_start_entry.configure(foreground=ThemeManager.COLORS["danger"])
            self.month_end_entry.configure(foreground=ThemeManager.COLORS["danger"])
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
            # FIX-003: disable period buttons when range is invalid
            # to prevent the user from clicking "СОБРАТЬ ЗА ПЕРИОД" only
            # to receive a messagebox.showerror after the fact.
            try:
                self.consolidate_month_btn.config(state=tk.DISABLED)
                self.rsch_month_btn.config(state=tk.DISABLED)
            except (tk.TclError, AttributeError):
                pass
        else:
            self.month_start_entry.configure(foreground=ThemeManager.COLORS["text_inverse"])
            self.month_end_entry.configure(foreground=ThemeManager.COLORS["text_inverse"])
            from core.ui.tooltip import Tooltip

            if self._range_warning_tooltip is not None:
                self._range_warning_tooltip.set_text("")
            # FIX-003: re-enable period buttons when range becomes valid.
            # Respect the global busy-state: only re-enable if the
            # operation state is not currently busy (the controller
            # disables buttons during runs and re-enables them on end).
            try:
                if not getattr(self, "_period_buttons_locked", False):
                    self.consolidate_month_btn.config(state=tk.NORMAL)
                    self.rsch_month_btn.config(state=tk.NORMAL)
            except (tk.TclError, AttributeError):
                pass

    def get_date(self):
        return self.date_entry.get_date()

    # ── UX-014: weekday tooltip ─────────────────────────────────

    def _weekday_tooltip_text(self) -> str:
        """Return a tooltip string with the weekday for the selected date."""
        try:
            d = self.date_entry.get_date()
            weekdays = ["понедельник", "вторник", "среда", "четверг",
                        "пятница", "суббота", "воскресенье"]
            wd = weekdays[d.weekday()]
            return f"{d.strftime('%d.%m.%Y')} — {wd}"
        except Exception:
            return ""

    # ── UX-017: network drive indicator ─────────────────────────

    def _poll_network_drives(self) -> None:
        """Check if configured network drives are reachable; update indicator.

        Runs every 30 seconds. The ``os.path.exists`` probes are done on a
        daemon thread because on slow/unreachable network drives each probe
        blocks for the SMB redirector timeout (5-30 s) — running that on the
        GUI thread froze the whole window every poll cycle. Only the final
        ``config(text=...)`` call is marshalled back to the GUI thread.
        """
        try:
            cfg = getattr(self.controller, 'config_controller', None)
            if cfg is None:
                self._net_indicator.config(text="🟡 Сеть: нет конфиг")
                return
            config = getattr(cfg, 'config', {})
            network_cfg = config.get("network", {}) if isinstance(config, dict) else {}
            drive_letters = network_cfg.get("drive_letters", ["Q"])
            if not isinstance(drive_letters, list):
                drive_letters = [drive_letters]

            def _probe() -> tuple[int, int]:
                import os
                reachable = 0
                total = 0
                for letter in drive_letters:
                    drive_path = f"{str(letter)}:\\"
                    total += 1
                    if os.path.exists(drive_path):
                        reachable += 1
                return reachable, total

            def _on_done(result: tuple[int, int]) -> None:
                reachable, total = result
                if total == 0:
                    self._net_indicator.config(text="🟡 Сеть: нет дисков")
                elif reachable == total:
                    self._net_indicator.config(
                        text=f"🟢 Сеть: {reachable}/{total} дисков доступны"
                    )
                elif reachable > 0:
                    self._net_indicator.config(
                        text=f"🟡 Сеть: {reachable}/{total} дисков доступны"
                    )
                else:
                    self._net_indicator.config(
                        text=f"🔴 Сеть: {reachable}/{total} дисков доступны"
                    )

            def runner() -> None:
                try:
                    result = _probe()
                except Exception:
                    logging.exception("Network drive poll failed")
                    result = (0, 0)

                def safe_done() -> None:
                    try:
                        _on_done(result)
                    except tk.TclError:
                        pass

                try:
                    self.after(0, safe_done)
                except tk.TclError:
                    pass

            threading.Thread(target=runner, daemon=True).start()
        except Exception:
            self._net_indicator.config(text="🟡 Сеть: ошибка проверки")
        finally:
            # Schedule next poll in 30s
            try:
                self._net_poll_after_id = self.after(30000, self._poll_network_drives)
            except tk.TclError:
                pass

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
