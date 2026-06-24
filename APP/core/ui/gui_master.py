import logging
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Optional

from core.ui.ui_sidebar import Sidebar
from core.ui.ui_employee_table import EmployeeTable
from core.ui.ui_stats_panel import StatsPanel
from core.ui.ui_log_panel import LogPanel
from core.ui.ui_dashboard import DashboardTabs
from core.ui.theme import ThemeManager
from core.ui.geometry import (
    is_geometry_visible,
    load_geometry,
    save_geometry,
)
from core.ui.operation_state import OPERATION_LABELS, OperationState
from core.ui.operation_status_bar import OperationStatusBar
from core.ui.toast import ToastManager
from core.infra import ConfigController, setup_gui_logging, open_path
from core.app_controller import AppController

from core.view_models.employee_list_viewmodel import EmployeeListViewModel
from core.view_models.consolidation_viewmodel import ConsolidationViewModel
from core.ui.gui_commands import GuiCommands
from core.ui.gui_master_settings import GuiMasterSettingsMixin


def _fit_window_geometry(
    preferred_width: int,
    preferred_height: int,
    screen_width: int,
    screen_height: int,
) -> str:
    max_width = max(800, int(screen_width * 0.82))
    max_height = max(560, int(screen_height * 0.88))
    width = min(preferred_width, max_width)
    height = min(preferred_height, max_height)
    x = max(0, (screen_width - width) // 2)
    y = max(0, (screen_height - height) // 2)
    return f"{width}x{height}+{x}+{y}"


def _resolve_initial_geometry(
    preferred: tuple[int, int],
    screen_width: int,
    screen_height: int,
) -> str:
    """Pick the geometry to use at startup.

    Preference order:
    1. Persisted geometry (if it still fits the current display).
    2. Auto-fitted default (centred, capped to 82% of screen width).
    """
    saved = load_geometry()
    if saved and is_geometry_visible(saved, screen_width, screen_height):
        return saved
    return _fit_window_geometry(preferred[0], preferred[1], screen_width, screen_height)


class GuiMaster(GuiMasterSettingsMixin):
    def __init__(
        self,
        root: tk.Tk,
        config_controller: ConfigController,
        app_controller: AppController,
    ):
        self.root, self.config_controller, self.app_controller = (
            root,
            config_controller,
            app_controller,
        )
        self.root.title("🚀 Master-Report v5.5 | Financial Consolidator")
        ThemeManager.init_scaling(self.root)
        ThemeManager.attach_resize_listener(self.root)
        ThemeManager.apply_styles()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(_resolve_initial_geometry((1100, 840), sw, sh))
        self.root.minsize(max(640, int(sw * 0.5)), max(420, int(sh * 0.5)))
        self.root.configure(bg=ThemeManager.COLORS["bg_main"])

        # Persist the geometry on close. The protocol is set by main.py
        # to call on_close; we intercept that to save the geometry.
        self._install_geometry_save_handler()

        self.employee_vm = EmployeeListViewModel()
        self.operation_state = OperationState()
        self.consolidation_vm = ConsolidationViewModel(
            app_controller, operation_state=self.operation_state
        )

        self.employee_vm.set_update_callback(self._on_employee_vm_update)
        self.consolidation_vm.set_callbacks(
            self._on_consolidation_progress, self._on_consolidation_complete
        )

        ThemeManager.apply_styles()
        self.setup_ui()
        # Show operation progress in the window title.
        # Two mechanisms working together:
        # 1. <<TitleUpdate>> virtual event: generated on the GUI thread
        #    from _on_consolidation_progress (which is itself called
        #    from the consolidation worker). The event_generate call is
        #    marshalled via root.after(0, …) so no Tk API is touched
        #    from a worker thread.
        # 2. Fallback poll every 500ms from GUI thread — catches the
        #    edge case where the virtual event is dropped.
        self._base_title = "🚀 Master-Report v5.5"

        def _refresh_title(_event=None) -> None:
            try:
                snap = self.operation_state.snapshot()
                if snap.current:
                    label = OPERATION_LABELS.get(snap.current, "")
                    self.root.title(f"{self._base_title} — {label} {snap.progress:.0f}%")
                else:
                    self.root.title(self._base_title)
            except Exception:
                pass

        self.root.bind("<<TitleUpdate>>", _refresh_title)

        def _poll() -> None:
            _refresh_title()
            self.root.after(500, _poll)

        self.root.after(500, _poll)
        self.operation_state.add_listener(
            lambda snap: self.root.after(0, lambda: self.sidebar.apply(snap))
        )
        # Drive the StatsPanel operation progress bar from the same
        # snapshot stream. The OperationStatusBar reads this too, but
        # the StatsPanel bar lives in a different widget that the
        # listener must update explicitly.
        # Must be marshalled via root.after() — OperationState._notify
        # is called from background threads during consolidation.
        self.operation_state.add_listener(
            lambda snap: self.root.after(0, lambda: self._on_operation_snapshot(snap))
        )
        setup_gui_logging(self.log_panel.get_widget())

        self.commands = GuiCommands(
            self.root,
            config_controller,
            app_controller,
            self.employee_vm,
            self.consolidation_vm,
            self.sidebar,
            self.employee_table,
            self.stats_panel,
            self.dashboard_tabs,
            self.operation_state,
            self.toasts,
        )

        self.root.after(100, self.commands.refresh_status)
        # Begin polling the OS theme every 5 s so that when the user
        # has picked "Системная" we follow OS dark/light changes without
        # an app restart. No-op when the user has chosen light/dark.
        self.start_theme_polling()
        self._init_settings(config_controller)

    def setup_ui(self):
        self.sidebar = Sidebar(self.root, self)
        self.sidebar.pack(side=tk.LEFT, fill=tk.Y)

        self.main_area = ttk.Frame(self.root, padding="15", style="Main.TFrame")
        self.main_area.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.stats_panel = StatsPanel(self.sidebar, self)
        self.stats_panel.pack(fill=tk.X, pady=(0, 10))

        self.log_panel = LogPanel(self.sidebar, self)
        self.log_panel.pack(fill=tk.BOTH, expand=True)

        # Status bar lives at the bottom of the main window (not the
        # sidebar) so the progress indicator is always visible
        # regardless of which tab is open or how tall the window is.
        self.status_bar = OperationStatusBar(
            self.root,
            self.operation_state,
            on_cancel=self._request_cancel,
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.notebook = ttk.Notebook(self.main_area)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.dashboard_tabs = DashboardTabs(
            self.notebook,
            self,
            self.config_controller,
        )

        self.employee_table = EmployeeTable(self.dashboard_tabs.employees_tab, self)
        self.employee_table.pack(fill=tk.BOTH, expand=True)
        self.dashboard_tabs.refresh()

        self.toasts = ToastManager(self.root)

    def _on_employee_vm_update(self):
        self.root.after(0, self.commands._sync_employee_ui)

    def _request_cancel(self) -> None:
        if not self.operation_state.is_busy:
            return
        cancelled = self.operation_state.request_cancel()
        if cancelled:
            self.toasts.info("Отмена", "Операция будет остановлена на ближайшей контрольной точке")

    def _on_consolidation_progress(self, progress: float):
        # Called from the consolidation worker thread. OperationState is
        # thread-safe, but ``event_generate`` (and any Tk call) must run
        # on the GUI thread — calling it directly from the worker races
        # the Tcl event loop and corrupts Tk state under load (e.g.
        # several concurrent consolidations + cancel). Marshal it.
        self.operation_state.set_progress(progress)
        self.root.after(0, lambda: self.root.event_generate("<<TitleUpdate>>"))

    def _update_title_from_state(self, _event=None) -> None:
        """Refresh window title from OperationState — always runs on GUI thread."""
        snap = self.operation_state.snapshot()
        if snap.current:
            label = OPERATION_LABELS.get(snap.current, "")
            self.root.title(f"{self._base_title} — {label} {snap.progress:.0f}%")
        else:
            self.root.title(self._base_title)

    def _on_operation_snapshot(self, snap) -> None:
        """Forward the operation progress to the StatsPanel bar."""
        try:
            self.stats_panel.set_operation(snap.progress)
        except (AttributeError, tk.TclError):
            pass

    def _on_consolidation_complete(self, ok: bool, msg: str, path: Optional[Path]):
        def fin():
            self.operation_state.end()
            cancelled = "отменена пользователем" in (msg or "").lower()

            if ok:
                logging.info(f"Успешно: {msg}")
                self.dashboard_tabs.record_result("Master", ok, msg, path)
                if path and messagebox.askyesno("Успех", "Консолидация завершена. Открыть файл?"):
                    open_path(str(path))
                self.toasts.success("Master-отчет", msg, duration_ms=4000)
            elif cancelled:
                logging.info(f"Отменено: {msg}")
                self.dashboard_tabs.record_result("Master", False, msg, path)
                self.toasts.warning("Master-отчет: отменено", msg, duration_ms=4000)
            else:
                logging.error(f"Ошибка: {msg}")
                self.dashboard_tabs.record_result("Master", ok, msg, path)
                self.toasts.error("Master-отчет: ошибка", msg, duration_ms=6000)

        self.root.after(0, fin)

    def refresh_status(self):
        self.commands.refresh_status()

    def run_consolidation(self):
        self.commands.run_consolidation()

    def run_consolidation_all_dates(self):
        self.commands.run_consolidation_all_dates()

    def run_consolidation_month(self):
        self.commands.run_consolidation_month()

    def run_rsch_report(self):
        self.commands.run_rsch_report()

    def run_rsch_report_month(self):
        self.commands.run_rsch_report_month()

    def run_reconciliation_report(self):
        self.commands.run_reconciliation_report()

    def run_auto_reconciliation_day(self):
        self.commands.run_auto_reconciliation_day()

    def add_employee_dialog(self):
        self.commands.add_employee_dialog()

    def attach_file_dialog(self):
        self.commands.attach_file_dialog()

    def open_master_folder(self):
        self.commands.open_master_folder()

    def copy_missing_to_clipboard(self):
        self.commands.copy_missing_to_clipboard()

    def filter_tree(self):
        self.commands.filter_tree()

    def open_employee_folder(self):
        self.commands.open_employee_folder()

    def open_employee_file(self):
        self.commands.open_employee_file()

    def delete_employee(self):
        self.commands.delete_employee()

    def _install_geometry_save_handler(self) -> None:
        """Wrap WM_DELETE_WINDOW so we can persist the geometry.

        ``main.py`` sets ``root.protocol("WM_DELETE_WINDOW", on_close)``
        *after* ``GuiMaster.__init__`` runs, which clobbers any protocol
        we install here. As a robust fallback we also bind to the root
        ``<Destroy>`` event — that fires when the root is torn down no
        matter which close path was taken, so the geometry is persisted
        even when ``main.py``'s handler is the one that ran.

        ``_persist_geometry`` is idempotent (guarded by a flag) so it is
        safe for both bindings to fire on the same shutdown.
        """
        self._geometry_saved = False
        original = self.root.protocol("WM_DELETE_WINDOW")

        def _save_then_close() -> None:
            self._persist_geometry()
            if original:
                original()
            else:
                self.root.destroy()

        self.root.protocol("WM_DELETE_WINDOW", _save_then_close)
        # Fallback for the case where main.py overwrites WM_DELETE_WINDOW
        # after __init__ returns. <Destroy> propagates up from any child
        # widget, so filter to root only.
        self.root.bind(
            "<Destroy>",
            lambda e: self._persist_geometry() if e.widget is self.root else None,
            add="+",
        )

    def _persist_geometry(self) -> None:
        """Save the current window geometry to disk — idempotent."""
        if getattr(self, "_geometry_saved", False):
            return
        try:
            save_geometry(self.root.geometry())
        except Exception as e:  # noqa: BLE001
            logging.debug("Geometry save failed: %s", e)
        finally:
            self._geometry_saved = True

    def save_geometry_and_close(self) -> None:
        """Persist the window geometry and then destroy the root."""
        self._persist_geometry()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def start_theme_polling(self) -> None:
        """Begin polling the OS theme every 5 s.

        Only re-applies the theme when the user has selected "Системная"
        in the sidebar AND the resolved OS value has changed since the
        last poll. This avoids touching Tk widgets unnecessarily on every
        tick (which would also fight manual light/dark choices).
        """
        try:
            self._last_system_theme = ThemeManager.resolve_effective("system")
        except Exception:
            self._last_system_theme = "light"
        self._poll_system_theme()

    def _poll_system_theme(self) -> None:
        try:
            theme_var = getattr(self.sidebar, "theme_var", None)
            if theme_var is not None and theme_var.get() == "system":
                current = ThemeManager.resolve_effective("system")
                if current != self._last_system_theme:
                    self._last_system_theme = current
                    ThemeManager.set_theme(current)
                    self.root.configure(bg=ThemeManager.COLORS["bg_main"])
        except (tk.TclError, AttributeError):
            # Root or sidebar destroyed — let the polling loop die
            # quietly.
            return
        try:
            self.root.after(5000, self._poll_system_theme)
        except tk.TclError:
            pass

    def set_theme(self, name: str) -> None:
        """Switch the active palette and reconfigure ttk styles.

        ``name`` may be "light", "dark", or "system" (the last one
        resolves to whichever the OS reports — falling back to light
        on Windows 8). The main window's background is updated to
        match the new palette so the change is visible immediately.
        """
        resolved = ThemeManager.resolve_effective(name)
        if resolved not in ("light", "dark"):
            resolved = "light"
        ThemeManager.set_theme(resolved)
        self.root.configure(bg=ThemeManager.COLORS["bg_main"])
        if hasattr(self, "employee_table"):
            self.employee_table.refresh_theme()
        if hasattr(self, "dashboard_tabs"):
            self.dashboard_tabs.refresh_theme()
        self.toasts.info(
            "Тема",
            f"Применена тема: {resolved}",
            duration_ms=2000,
        )
