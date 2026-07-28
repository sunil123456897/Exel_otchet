"""Mixin that adds settings-loading / settings-dialog support to ``GuiMaster``.

Usage::

    class GuiMaster(GuiMasterSettingsMixin):   # was: class GuiMaster:
        ...

Add ``ThemeManager.attach_resize_listener(self.root)`` after ``init_scaling``
and ``self._init_settings(config_controller)`` at the end of ``__init__``.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.ui.theme import ThemeManager
from core.infra.settings_store import SettingsStore, UIPreferences

if TYPE_CHECKING:
    import tkinter as tk

    from core.infra.config_controller import ConfigController

_log = logging.getLogger(__name__)


class GuiMasterSettingsMixin:
    """Mixin that adds settings lifecycle to ``GuiMaster``.

    Expects ``self`` to be a ``GuiMaster`` instance with:
    - ``self.root: tk.Tk``
    - ``self.config_controller: ConfigController``
    - ``self.sidebar: Sidebar``
    - ``self.employee_table: EmployeeTable``
    """

    # Provided by the composed GuiMaster; declared so the mixin type-checks.
    root: tk.Tk

    # ── public setup — call from GuiMaster.__init__ ───────────

    def _load_theme_early(self, config_controller: ConfigController) -> None:
        """Load persisted theme/scale/density and apply to ThemeManager.

        Must be called **before** ``setup_ui()`` so that all widgets are
        created with the correct palette from the start, avoiding the
        flash of light-theme colours on a dark-theme startup.
        """
        self._settings_store = SettingsStore(config_controller)
        prefs = self._settings_store.load_preferences()
        self._early_prefs = prefs

        # Apply the persisted theme to ThemeManager before any widget
        # is created, so widgets pick up the correct colours at birth.
        effective = ThemeManager.resolve_effective(prefs.theme)
        try:
            ThemeManager.set_theme(effective)
        except Exception:
            _log.exception("Failed to apply persisted theme %s", prefs.theme)

        # Apply scale/density to ThemeManager (triggers _rebuild_tokens → apply_styles).
        ThemeManager.apply_preferences(
            scale_mode=prefs.scale_mode,
            user_scale=prefs.user_scale,
            density=prefs.density,
        )

    def _init_settings(self, config_controller: ConfigController) -> None:
        """Sync sidebar theme picker and subscribe to scale changes.

        Must be called **after** ``setup_ui()`` so that all widgets
        (sidebar, employee_table) exist.
        """
        prefs = getattr(self, "_early_prefs", None)
        if prefs is None:
            # Fallback: load now if _load_theme_early wasn't called
            self._settings_store = SettingsStore(config_controller)
            prefs = self._settings_store.load_preferences()
            effective = ThemeManager.resolve_effective(prefs.theme)
            try:
                ThemeManager.set_theme(effective)
            except Exception:
                _log.exception("Failed to apply persisted theme %s", prefs.theme)
            ThemeManager.apply_preferences(
                scale_mode=prefs.scale_mode,
                user_scale=prefs.user_scale,
                density=prefs.density,
            )

        # Sync theme picker in sidebar to the persisted value.
        if hasattr(self, "sidebar") and self.sidebar is not None:
            try:
                sidebar = self.sidebar
                if hasattr(sidebar, "theme_var"):
                    sidebar.theme_var.set(prefs.theme)
            except Exception:
                _log.exception("Failed to sync sidebar theme")

        # Update root bg to match the (possibly changed) theme.
        if hasattr(self, "root"):
            self.root.configure(bg=ThemeManager.COLORS["bg_main"])

        # Subscribe to scale changes so the table reflows.
        ThemeManager.add_scale_listener(self._reflow_on_scale)

    # ── settings dialog ───────────────────────────────────────

    def open_settings(self) -> None:
        """Open the universal settings dialog (modal)."""
        # Late import: avoid circular dependency at module load time.
        from core.ui.ui_settings import SettingsDialog

        prefs_before = self._settings_store.load_preferences()

        dialog = SettingsDialog(
            parent=self.root,
            config_controller=self.config_controller,  # type: ignore[attr-defined]
            settings_store=self._settings_store,
            current_prefs=prefs_before,
            gui=self,
        )
        # Show modal and block until closed.
        self.root.wait_window(dialog)

    # ── apply prefs to live GUI ───────────────────────────────

    def apply_ui_preferences(self, prefs: UIPreferences) -> None:
        """Apply UI prefs to the running GUI (called by dialog on Apply/OK)."""
        # Theme switching — run the SAME full pass the sidebar picker
        # uses (root bg + table/dashboard/sidebar refresh_theme). Calling
        # only ThemeManager.set_theme here was the bug that made a theme
        # chosen in Settings half-apply: global styles changed, but the
        # employee table / dashboard / sidebar kept the old colours.
        effective = ThemeManager.resolve_effective(prefs.theme)
        try:
            ThemeManager.set_theme(effective)
        except Exception:
            _log.exception("Failed to apply theme %s", prefs.theme)
        refresh = getattr(self, "_refresh_theme_on_widgets", None)
        if callable(refresh):
            try:
                refresh()
            except Exception:
                _log.exception("Failed to refresh themed widgets")

        # Scale / density
        ThemeManager.apply_preferences(
            scale_mode=prefs.scale_mode,
            user_scale=prefs.user_scale,
            density=prefs.density,
        )

        # Sidebar width
        if hasattr(self, "sidebar") and self.sidebar is not None:
            try:
                self.sidebar._recompute_width()
            except Exception:
                _log.exception("Failed to recompute sidebar width")

    # ── scale-listener callback ───────────────────────────────

    def _reflow_on_scale(self, _scale: float, _mode: str) -> None:
        """React to scale changes: reflow table columns, update theme."""
        # Reflow employee-table columns (if the method exists).
        if hasattr(self, "employee_table") and self.employee_table is not None:
            try:
                if hasattr(self.employee_table, "reflow_columns"):
                    self.employee_table.reflow_columns()
            except Exception:
                _log.exception("Failed to reflow employee-table columns")
        # Re-theme the dashboard tabs on scale change. The attribute is
        # ``dashboard_tabs`` (see _refresh_theme_on_widgets); the old
        # ``dashboard`` name never existed, so this refresh silently
        # never ran — one of the "small" settings glitches.
        if hasattr(self, "dashboard_tabs") and self.dashboard_tabs is not None:
            try:
                if hasattr(self.dashboard_tabs, "refresh_theme"):
                    self.dashboard_tabs.refresh_theme()
            except Exception:
                pass
