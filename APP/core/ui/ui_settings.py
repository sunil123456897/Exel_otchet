"""Universal settings dialog — modal ``Toplevel`` with 8 tabs.

Design principles
-----------------
*   The dialog edits a **deep copy** of the config sections it touches,
    not the live ``ConfigController.config``.  Nothing is saved to disk
    until the user clicks **Apply** or **OK**.
*   **Cancel** restores any live preview changes (theme, scale, density)
    from a snapshot taken when the dialog opened.
*   Each tab is a plain ``ttk.Frame`` built by a dedicated ``_build_*``
    method — easy to extend without touching unrelated tabs.
"""

from __future__ import annotations

import copy
import logging
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Any

from core.infra.config_controller import ConfigController
from core.infra.settings_store import SettingsStore, UIPreferences
from core.ui.theme import ThemeManager

_log = logging.getLogger(__name__)

# ── helpers ───────────────────────────────────────────────────

_PATH_TYPE_DIR = "dir"
_PATH_TYPE_FILE = "file"
_PATH_TYPE_SAVE_DIR = "save_dir"


def _scrollable(parent: tk.Widget) -> tuple[tk.Canvas, ttk.Frame]:
    """Wrap *parent* in a scrollable canvas; return ``(canvas, frame)``.

    The returned *frame* is where content is packed/placed.  The canvas
    registers itself with ``ThemeManager.register`` so its background
    follows theme switches.
    """
    canvas = tk.Canvas(
        parent,
        borderwidth=0,
        highlightthickness=0,
        background=ThemeManager.COLORS.get("bg_sidebar", "#ffffff"),
    )
    ThemeManager.register(canvas, bg_key="bg_sidebar", fg_key=None)
    scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
    frame = ttk.Frame(canvas)
    canvas.configure(yscrollcommand=scrollbar.set)
    frame.bind(
        "<Configure>",
        lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
    )
    canvas.create_window((0, 0), window=frame, anchor=tk.NW)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _on_enter(_e: tk.Event) -> None:
        canvas.bind_all("<MouseWheel>", _on_wheel)

    def _on_leave(_e: tk.Event) -> None:
        canvas.unbind_all("<MouseWheel>")

    def _on_wheel(event: tk.Event) -> None:
        canvas.yview_scroll(-int(event.delta / 120), "units")

    canvas.bind("<Enter>", _on_enter)
    canvas.bind("<Leave>", _on_leave)
    return canvas, frame


class _PathRow(ttk.Frame):
    """A labelled path field with a ``…`` browse button."""

    def __init__(
        self,
        parent: tk.Widget,
        label: str,
        *,
        path_type: str = _PATH_TYPE_DIR,
        initial: str = "",
    ) -> None:
        super().__init__(parent)
        self._path_type = path_type
        self._var = tk.StringVar(value=initial)

        ttk.Label(self, text=label).pack(side=tk.LEFT)
        entry = ttk.Entry(self, textvariable=self._var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4, 4))
        ttk.Button(self, text="…", width=3, command=self._browse).pack(side=tk.LEFT)

    def _browse(self) -> None:
        current = self._var.get() or ""
        if self._path_type in (_PATH_TYPE_DIR, _PATH_TYPE_SAVE_DIR):
            chosen = filedialog.askdirectory(initialdir=current or None)
        elif self._path_type == _PATH_TYPE_FILE:
            chosen = filedialog.askopenfilename(initialdir=current or None)
        else:
            chosen = filedialog.asksaveasfilename(initialdir=current or None)
        if chosen:
            self._var.set(chosen)

    def get(self) -> str:
        return self._var.get()


class _ListEditor(ttk.Frame):
    """A list of strings with Add / Edit / Delete buttons."""

    def __init__(self, parent: tk.Widget, initial: list[str] | None = None) -> None:
        super().__init__(parent)
        self._items: list[str] = list(initial or [])

        self._listbox = tk.Listbox(self, height=6, exportselection=False)
        # Theme the Listbox — tk widgets don't follow ttk styles.
        ThemeManager.register(self._listbox, bg_key="bg_sidebar", fg_key="text")
        self._listbox.configure(
            selectbackground=ThemeManager.COLORS["primary"],
            selectforeground=ThemeManager.COLORS["text_inverse"],
            highlightthickness=0,
            borderwidth=0,
        )
        self._listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._listbox.yview)
        self._listbox.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.LEFT, fill=tk.Y)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(btn_frame, text="Добавить", command=self._add).pack(fill=tk.X, pady=(0, 2))
        ttk.Button(btn_frame, text="Изменить", command=self._edit).pack(fill=tk.X, pady=(0, 2))
        ttk.Button(btn_frame, text="Удалить", command=self._delete).pack(fill=tk.X)
        self._refresh()

    def _refresh(self) -> None:
        self._listbox.delete(0, tk.END)
        for item in self._items:
            self._listbox.insert(tk.END, item)

    def _add(self) -> None:
        self._edit_item(None)

    def _edit(self) -> None:
        sel = self._listbox.curselection()
        if not sel:
            return
        self._edit_item(self._items[sel[0]], sel[0])

    def _edit_item(self, current: str | None, index: int | None = None) -> None:
        from tkinter.simpledialog import askstring

        result = askstring(
            "Редактирование",
            "Значение:",
            initialvalue=current or "",
            parent=self.winfo_toplevel(),
        )
        if result is None:
            return
        result = result.strip()
        if index is not None:
            self._items[index] = result
        else:
            self._items.append(result)
        self._refresh()

    def _delete(self) -> None:
        sel = self._listbox.curselection()
        if not sel:
            return
        del self._items[sel[0]]
        self._refresh()

    def get(self) -> list[str]:
        return list(self._items)


# ── dialog ────────────────────────────────────────────────────


class SettingsDialog(tk.Toplevel):
    """Modal settings dialog with 8 tabs.

    Args:
        parent:              Parent Tk window.
        config_controller:   Shared config controller.
        settings_store:      Persistence layer for UI prefs.
        current_prefs:       Snapshot of UI prefs at dialog open time.
        gui:                 ``GuiMaster`` instance (or any object with
                             ``apply_ui_preferences``).
    """

    def __init__(
        self,
        parent: tk.Widget,
        config_controller: ConfigController,
        settings_store: SettingsStore,
        current_prefs: UIPreferences,
        gui: Any,
    ) -> None:
        super().__init__(parent)
        self.title("Настройки")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        # Theme the Toplevel background to match the active palette.
        # Without this, the dialog body is white in dark mode.
        self.configure(background=ThemeManager.COLORS.get("bg_main", "#f3f4f6"))

        self._cc = config_controller
        self._store = settings_store
        self._gui = gui

        # Deep-copy the sections we touch so Cancel never trashes live config.
        self._work = (
            copy.deepcopy(
                {
                    k: v
                    for k, v in config_controller.config.items()
                    if k
                    in {
                        "paths",
                        "rsch",
                        "curators",
                        "performance",
                        "network",
                        "logic",
                        "database",
                        "backup",
                    }
                }
            )
            if isinstance(config_controller.config, dict)
            else {}
        )

        self._original_prefs = current_prefs
        self._current_prefs = copy.copy(current_prefs)

        # ── notebook ──────────────────────────────────────────
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self._build_appearance_tab(notebook)
        self._build_paths_tab(notebook)
        self._build_performance_tab(notebook)
        self._build_network_tab(notebook)
        self._build_logic_tab(notebook)
        self._build_database_tab(notebook)
        self._build_backup_tab(notebook)
        self._build_about_tab(notebook)

        # ── action buttons ────────────────────────────────────
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Button(btn_frame, text="OK", command=self._ok).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(btn_frame, text="Отмена", command=self._cancel).pack(side=tk.RIGHT, padx=(4, 0))
        ttk.Button(btn_frame, text="Применить", command=self._apply).pack(
            side=tk.RIGHT, padx=(4, 0)
        )
        # UX-016: Reset to defaults button — restores factory defaults
        # for UI preferences (theme, scale, geometry) with a confirm.
        ttk.Button(btn_frame, text="↺ Сброс", command=self._reset_defaults).pack(
            side=tk.LEFT, padx=(0, 4)
        )

        # Centre on parent
        self.update_idletasks()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        dw, dh = self.winfo_width(), self.winfo_height()
        x = parent.winfo_x() + (pw - dw) // 2
        y = parent.winfo_x() + (ph - dh) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.minsize(600, 400)

    # ── tab builders ──────────────────────────────────────────

    def _build_appearance_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="🎨 Внешний вид")

        # Theme
        row = ttk.Frame(tab)
        row.pack(fill=tk.X, pady=(8, 4))
        ttk.Label(row, text="Тема:").pack(side=tk.LEFT)
        self._theme_var = tk.StringVar(value=self._current_prefs.theme)
        for val, lbl in (("light", "☀️ Светлая"), ("dark", "🌙 Тёмная"), ("system", "💻 Системная")):
            ttk.Radiobutton(
                row, text=lbl, variable=self._theme_var, value=val, command=self._preview_appearance
            ).pack(side=tk.LEFT, padx=(4, 0))

        # Scale mode
        row = ttk.Frame(tab)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text="Масштаб:").pack(side=tk.LEFT)
        self._scale_mode_var = tk.StringVar(value=self._current_prefs.scale_mode)
        ttk.Radiobutton(
            row,
            text="Авто",
            variable=self._scale_mode_var,
            value="auto",
            command=self._preview_appearance,
        ).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Radiobutton(
            row,
            text="Ручной",
            variable=self._scale_mode_var,
            value="manual",
            command=self._preview_appearance,
        ).pack(side=tk.LEFT, padx=(4, 0))

        # User scale — Spinbox with fine step + preset buttons.
        # Previously a ttk.Scale was used, but its 0.70 range combined
        # with _preview_appearance() on every pixel move made the slider
        # freeze and jump to min/max. Spinbox gives precise control.
        row = ttk.Frame(tab)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text="× множитель:").pack(side=tk.LEFT)
        self._scale_var = tk.DoubleVar(value=self._current_prefs.user_scale)
        scale_spin = ttk.Spinbox(
            row,
            from_=0.80,
            to=1.50,
            increment=0.05,
            textvariable=self._scale_var,
            width=6,
            format="%.2f",
        )
        scale_spin.pack(side=tk.LEFT, padx=(4, 8))
        # Live preview on any value change (spin buttons, typing, presets)
        self._scale_var.trace_add("write", lambda *_: self._preview_appearance())

        # Preset buttons for quick selection
        preset_row = ttk.Frame(tab)
        preset_row.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(preset_row, text="Пресеты:").pack(side=tk.LEFT)
        for val, lbl in ((0.85, "Мелкий"), (1.0, "Норма"), (1.15, "Крупный"), (1.30, "Большой")):
            btn = ttk.Button(
                preset_row,
                text=f"{lbl} ({val:.2f})",
                command=lambda v=val: self._set_scale_preset(v),
            )
            btn.pack(side=tk.LEFT, padx=(2, 0))

        # Density
        row = ttk.Frame(tab)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text="Плотность:").pack(side=tk.LEFT)
        self._density_var = tk.StringVar(value=self._current_prefs.density)
        for val, lbl in (
            ("compact", "Компактная"),
            ("normal", "Обычная"),
            ("comfortable", "Просторная"),
        ):
            ttk.Radiobutton(
                row,
                text=lbl,
                variable=self._density_var,
                value=val,
                command=self._preview_appearance,
            ).pack(side=tk.LEFT, padx=(4, 0))

        # Sidebar width
        row = ttk.Frame(tab)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text="Ширина панели:").pack(side=tk.LEFT)
        self._sidebar_w_var = tk.IntVar(value=self._current_prefs.sidebar_width)
        ttk.Spinbox(row, from_=0, to=800, textvariable=self._sidebar_w_var, width=6).pack(
            side=tk.LEFT, padx=(4, 0)
        )
        ttk.Label(row, text="(0 = авто)").pack(side=tk.LEFT, padx=(4, 0))

        # Diagnostics
        row = ttk.Frame(tab)
        row.pack(fill=tk.X, pady=(8, 4))
        ttk.Label(
            row,
            text=f"DPI: {ThemeManager._dpi:.0f}, "
            f"Экран: {ThemeManager._screen_h} px, "
            f"Окно: {ThemeManager._viewport_w}×{ThemeManager._viewport_h}, "
            f"Масштаб: {ThemeManager._scale:.2f}, "
            f"Режим: {ThemeManager.viewport_mode()}",
            foreground=ThemeManager.COLORS.get("text_muted", "#64748b"),
        ).pack(side=tk.LEFT)

    def _build_paths_tab(self, notebook: ttk.Notebook) -> None:
        outer = ttk.Frame(notebook)
        notebook.add(outer, text="📁 Пути и файлы")
        _, tab = _scrollable(outer)
        outer.columnconfigure(0, weight=1)

        paths = self._work.get("paths", {})
        rsch = self._work.get("rsch", {})
        curators = self._work.get("curators", {})
        pad = (8, 4)
        _PathRow(
            tab, "Master-файл:", path_type="save_file", initial=paths.get("master_file", "")
        ).pack(fill=tk.X, pady=pad)
        list_row = ttk.LabelFrame(tab, text="Корневые папки источников", padding=4)
        list_row.pack(fill=tk.X, pady=pad)
        self._source_roots_editor = _ListEditor(list_row, initial=paths.get("source_roots", []))
        self._source_roots_editor.pack(fill=tk.X)
        _PathRow(tab, "Папка архива:", initial=paths.get("archive_dir", "")).pack(
            fill=tk.X, pady=pad
        )
        _PathRow(tab, "Корень вывода:", initial=paths.get("output_root", "")).pack(
            fill=tk.X, pady=pad
        )

        # Curator paths (save-as file dialog — choose where the report file will be saved)
        for cname in ("boris", "ivan"):
            section = (curators or {}).get(cname, {})
            label = f"Вывод {cname.capitalize()}:"
            _PathRow(
                tab, label, path_type=_PATH_TYPE_SAVE_DIR, initial=section.get("output_path", "")
            ).pack(fill=tk.X, pady=pad)

        rsch_out = rsch.get("last_output_dir", "")
        _PathRow(tab, "Папка вывода РСЧ:", initial=rsch_out or "../РСЧ").pack(fill=tk.X, pady=pad)
        row = ttk.Frame(tab)
        row.pack(fill=tk.X, pady=pad)
        ttk.Label(row, text="Режим РСЧ:").pack(side=tk.LEFT)
        self._rsch_mode_var = tk.StringVar(value=rsch.get("mode", "combined"))
        ttk.Radiobutton(row, text="Общий", variable=self._rsch_mode_var, value="combined").pack(
            side=tk.LEFT, padx=(4, 0)
        )
        ttk.Radiobutton(
            row, text="Раздельный", variable=self._rsch_mode_var, value="separate"
        ).pack(side=tk.LEFT, padx=(4, 0))

        self._path_rows = tab.winfo_children()

    def _build_performance_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="⚡ Производительность")
        perf = self._work.get("performance", {})

        row = ttk.Frame(tab)
        row.pack(fill=tk.X, pady=8)
        ttk.Label(row, text="Потоков (0 = авто):").pack(side=tk.LEFT)
        self._workers_var = tk.IntVar(value=perf.get("max_workers") or 0)
        ttk.Spinbox(row, from_=0, to=64, textvariable=self._workers_var, width=6).pack(
            side=tk.LEFT, padx=(4, 0)
        )

        row = ttk.Frame(tab)
        row.pack(fill=tk.X, pady=4)
        self._calamine_var = tk.BooleanVar(value=perf.get("isolate_calamine", False))
        ttk.Checkbutton(row, text="Изолировать calamine", variable=self._calamine_var).pack(
            side=tk.LEFT
        )

    def _build_network_tab(self, notebook: ttk.Notebook) -> None:
        outer = ttk.Frame(notebook)
        notebook.add(outer, text="🌐 Сеть")
        _, tab = _scrollable(outer)
        net = self._work.get("network", {})

        list_row = ttk.LabelFrame(tab, text="Буквы сетевых дисков", padding=4)
        list_row.pack(fill=tk.X, pady=8)
        self._drive_letters_editor = _ListEditor(
            list_row, initial=net.get("drive_letters", ["Q", "Z"])
        )
        self._drive_letters_editor.pack(fill=tk.X)

    def _build_logic_tab(self, notebook: ttk.Notebook) -> None:
        outer = ttk.Frame(notebook)
        notebook.add(outer, text="🧮 Логика")
        _, tab = _scrollable(outer)
        logic = self._work.get("logic", {})

        row = ttk.Frame(tab)
        row.pack(fill=tk.X, pady=8)
        self._commission_var = tk.BooleanVar(value=logic.get("commission_is_percent", True))
        ttk.Checkbutton(row, text="Комиссия в процентах", variable=self._commission_var).pack(
            side=tk.LEFT
        )

        list_row = ttk.LabelFrame(tab, text="Переопределение прихода (income_overrides)", padding=4)
        list_row.pack(fill=tk.X, pady=4)
        self._income_overrides_editor = _ListEditor(
            list_row, initial=logic.get("income_overrides", [])
        )
        self._income_overrides_editor.pack(fill=tk.X)

        list_row = ttk.LabelFrame(tab, text="Ключевые слова возврата (return_keywords)", padding=4)
        list_row.pack(fill=tk.X, pady=4)
        self._return_keywords_editor = _ListEditor(
            list_row, initial=logic.get("return_keywords", [])
        )
        self._return_keywords_editor.pack(fill=tk.X)

    def _build_database_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="🗄 База данных")
        db = self._work.get("database", {})

        row = ttk.Frame(tab)
        row.pack(fill=tk.X, pady=8)
        ttk.Label(row, text="Путь к БД:").pack(side=tk.LEFT)
        self._db_path_var = tk.StringVar(value=db.get("path", "cache.db"))
        ttk.Entry(row, textvariable=self._db_path_var).pack(side=tk.LEFT, padx=(4, 0))

        row = ttk.Frame(tab)
        row.pack(fill=tk.X, pady=4)
        ttk.Label(row, text="Таймаут (сек):").pack(side=tk.LEFT)
        self._db_timeout_var = tk.DoubleVar(value=db.get("timeout", 30.0))
        ttk.Spinbox(row, from_=1, to=120, textvariable=self._db_timeout_var, width=6).pack(
            side=tk.LEFT, padx=(4, 0)
        )

        row = ttk.Frame(tab)
        row.pack(fill=tk.X, pady=4)
        self._db_wal_var = tk.BooleanVar(value=db.get("use_wal", True))
        ttk.Checkbutton(row, text="Использовать WAL", variable=self._db_wal_var).pack(side=tk.LEFT)

    def _build_backup_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="💾 Бэкапы")
        backup = self._work.get("backup", {})

        row = ttk.Frame(tab)
        row.pack(fill=tk.X, pady=8)
        ttk.Label(row, text="Хранить копий файлов:").pack(side=tk.LEFT)
        self._backup_keep_var = tk.IntVar(value=backup.get("excel_keep", 10))
        ttk.Spinbox(row, from_=1, to=100, textvariable=self._backup_keep_var, width=6).pack(
            side=tk.LEFT, padx=(4, 0)
        )

    def _build_about_tab(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="ℹ О программе")

        info = [
            ("Версия", "5.6"),
            ("Путь к config.yaml", getattr(self._cc, "config_path", "—")),
            ("employees.yaml", getattr(self._cc, "employees_path", "—")),
            ("Тема", self._current_prefs.theme),
            ("Масштаб", f"{self._current_prefs.user_scale:.2f}"),
            ("Плотность", self._current_prefs.density),
        ]
        for i, (label, value) in enumerate(info):
            row = ttk.Frame(tab)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=f"{label}:").pack(side=tk.LEFT, padx=(0, 8))
            ttk.Label(
                row, text=value, foreground=ThemeManager.COLORS.get("text_muted", "#64748b")
            ).pack(side=tk.LEFT)

        # External editor buttons
        ext_frame = ttk.LabelFrame(tab, text="Внешние редакторы", padding=8)
        ext_frame.pack(fill=tk.X, pady=(16, 4))
        ttk.Button(
            ext_frame,
            text="📝 Открыть config.yaml в Блокноте",
            command=self._open_config_external,
        ).pack(fill=tk.X, pady=(0, 4))
        ttk.Button(
            ext_frame,
            text="👥 Открыть employees.yaml в Блокноте",
            command=self._open_employees_external,
        ).pack(fill=tk.X)

        ttk.Button(
            tab,
            text="↺ Сбросить настройки интерфейса к умолчаниям",
            command=self._reset_defaults,
        ).pack(pady=(16, 4))

    # ── actions ───────────────────────────────────────────────

    def _open_config_external(self) -> None:
        """Open config.yaml in the system's default text editor."""
        import os
        path = getattr(self._cc, "config_path", "")
        if path and os.path.exists(path):
            try:
                os.startfile(path)  # Windows: opens with default .yaml editor
            except (OSError, AttributeError):
                # Fallback: notepad
                try:
                    os.system(f'notepad "{path}"')
                except OSError:
                    pass

    def _open_employees_external(self) -> None:
        """Open employees.yaml in the system's default text editor."""
        import os
        path = getattr(self._cc, "employees_path", "")
        if path and os.path.exists(path):
            try:
                os.startfile(path)
            except (OSError, AttributeError):
                try:
                    os.system(f'notepad "{path}"')
                except OSError:
                    pass

    def _preview_appearance(self) -> None:
        """Live preview of theme/scale/density changes (Cancel will revert)."""
        ThemeManager.apply_preferences(
            scale_mode=self._scale_mode_var.get(),
            user_scale=float(self._scale_var.get()),
            density=self._density_var.get(),
        )
        effective = ThemeManager.resolve_effective(self._theme_var.get())
        try:
            ThemeManager.set_theme(effective)
        except Exception:
            pass

    def _set_scale_preset(self, value: float) -> None:
        """Set the scale spinbox to a preset value and trigger preview."""
        self._scale_var.set(round(value, 2))

    def _collect_prefs(self) -> UIPreferences:
        return UIPreferences(
            theme=self._theme_var.get(),
            scale_mode=self._scale_mode_var.get(),
            user_scale=round(float(self._scale_var.get()), 2),
            density=self._density_var.get(),
            sidebar_width=int(self._sidebar_w_var.get()),
            window_geometry=None,
        )

    def _collect_work(self) -> dict[str, Any]:
        """Gather config values from all tab widgets into ``self._work``."""
        return self._work

    def _writeback_config(self) -> None:
        """Copy working sections back into the live ConfigController."""
        for section_key, section_data in self._work.items():
            self._cc.config[section_key] = section_data
        self._cc.save_config()

    def _ok(self) -> None:
        self._apply()
        self.destroy()

    def _apply(self) -> None:
        """Apply UI prefs + write back business config."""
        # UX-009: compute a diff of UI prefs before applying so we can
        # show the user what changed (toast on apply).
        old_prefs = self._original_prefs
        # 1. UI prefs
        prefs = self._collect_prefs()
        changes = self._compute_prefs_diff(old_prefs, prefs)
        self._store.save_preferences(prefs)
        if hasattr(self._gui, "apply_ui_preferences"):
            self._gui.apply_ui_preferences(prefs)

        # 2. Business config — collect from widgets
        paths = self._work.setdefault("paths", {})
        # PathRow widgets are collected below via _path_rows loop
        if hasattr(self, "_source_roots_editor"):
            paths["source_roots"] = self._source_roots_editor.get()

        # Collect PathRow widgets that were packed into the paths tab
        path_rows = getattr(self, "_path_rows", [])
        known_labels = {
            "Master-файл:": ("paths", "master_file"),
            "Папка архива:": ("paths", "archive_dir"),
            "Корень вывода:": ("paths", "output_root"),
            "Вывод Boris:": ("curators", "boris", "output_path"),
            "Вывод Ivan:": ("curators", "ivan", "output_path"),
            "Папка вывода РСЧ:": ("rsch", "last_output_dir"),
        }
        for child in path_rows:
            if isinstance(child, _PathRow):
                lbl = child.winfo_children()[0].cget("text") if child.winfo_children() else ""
                key_path = known_labels.get(lbl)
                if key_path is not None:
                    section = self._work
                    for k in key_path[:-1]:
                        section = section.setdefault(k, {})
                    section[key_path[-1]] = child.get()

        if hasattr(self, "_rsch_mode_var"):
            rsch = self._work.setdefault("rsch", {})
            rsch["mode"] = self._rsch_mode_var.get()

        # Performance
        perf = self._work.setdefault("performance", {})
        perf["max_workers"] = int(self._workers_var.get()) if hasattr(self, "_workers_var") else 0
        if hasattr(self, "_calamine_var"):
            perf["isolate_calamine"] = bool(self._calamine_var.get())

        # Network
        if hasattr(self, "_drive_letters_editor"):
            net = self._work.setdefault("network", {})
            net["drive_letters"] = self._drive_letters_editor.get()

        # Logic
        logic = self._work.setdefault("logic", {})
        if hasattr(self, "_commission_var"):
            logic["commission_is_percent"] = bool(self._commission_var.get())
        if hasattr(self, "_income_overrides_editor"):
            logic["income_overrides"] = self._income_overrides_editor.get()
        if hasattr(self, "_return_keywords_editor"):
            logic["return_keywords"] = self._return_keywords_editor.get()

        # DB
        db = self._work.setdefault("database", {})
        if hasattr(self, "_db_path_var"):
            db["path"] = self._db_path_var.get()
        if hasattr(self, "_db_timeout_var"):
            db["timeout"] = float(self._db_timeout_var.get())
        if hasattr(self, "_db_wal_var"):
            db["use_wal"] = bool(self._db_wal_var.get())

        # Backup
        if hasattr(self, "_backup_keep_var"):
            backup = self._work.setdefault("backup", {})
            backup["excel_keep"] = int(self._backup_keep_var.get())

        self._writeback_config()

        # UX-009: show a toast summarising what UI prefs changed
        if changes and hasattr(self._gui, "toasts"):
            try:
                summary = "; ".join(changes[:5])
                if len(changes) > 5:
                    summary += f" (+{len(changes) - 5} ещё)"
                self._gui.toasts.info("Настройки применены", summary, duration_ms=3000)
            except Exception:
                pass

    @staticmethod
    def _compute_prefs_diff(old, new) -> list[str]:
        """UX-009: Return a list of human-readable change descriptions."""
        changes = []
        labels = {
            "theme": "Тема",
            "scale_mode": "Масштаб",
            "user_scale": "Размер",
            "density": "Плотность",
            "window_geometry": "Геометрия",
        }
        for field in ("theme", "scale_mode", "user_scale", "density", "window_geometry"):
            old_val = getattr(old, field, None)
            new_val = getattr(new, field, None)
            if old_val != new_val:
                label = labels.get(field, field)
                changes.append(f"{label}: {old_val} → {new_val}")
        return changes

    def _cancel(self) -> None:
        """Revert any live preview changes and close."""
        # Restore ThemeManager to original prefs
        ThemeManager.apply_preferences(
            scale_mode=self._original_prefs.scale_mode,
            user_scale=self._original_prefs.user_scale,
            density=self._original_prefs.density,
        )
        effective = ThemeManager.resolve_effective(self._original_prefs.theme)
        try:
            ThemeManager.set_theme(effective)
        except Exception:
            pass
        self.destroy()

    def _reset_defaults(self) -> None:
        """UX-016: Reset to defaults with confirmation."""
        from tkinter import messagebox
        if not messagebox.askyesno(
            "Сброс настроек",
            "Сбросить настройки интерфейса к значениям по умолчанию?\n"
            "(тема, масштаб, плотность, геометрия окна)",
        ):
            return
        self._reset_ui_defaults()

    def _reset_ui_defaults(self) -> None:
        """Reset UI settings to factory defaults."""
        defaults = UIPreferences()
        self._store.save_preferences(defaults)
        if hasattr(self._gui, "apply_ui_preferences"):
            self._gui.apply_ui_preferences(defaults)
        self.destroy()
