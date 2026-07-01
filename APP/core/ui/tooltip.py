"""Lightweight tooltip widget for Tk/ttk.

A ``Tooltip`` is attached to any widget and shows a small Toplevel
next to the cursor on hover. The tooltip is non-modal, follows the
cursor, and hides itself as soon as the pointer leaves the bound
widget. No third-party dependency, no images.

The tooltip fades in over ~100 ms (alpha 0 → 1). On platforms that
do not support per-window alpha (some X11 builds), the fade is
skipped and the tooltip appears at full opacity instantly. Fade-out
is intentionally omitted — on mouse-leave an instant disappear feels
snappier than a slow fade.

Usage::

    btn = ttk.Button(parent, text="Run")
    Tooltip(btn, "Run the consolidation")

The widget is a thin wrapper — it does not own its data and can be
garbage-collected normally once the underlying widget is destroyed.
"""
from __future__ import annotations

import logging
import tkinter as tk
from typing import Any, Callable, Optional, Union

_logger = logging.getLogger(__name__)

_DEFAULT_DELAY_MS = 300  # UX-011: reduced from 400ms for snappier feel
_DEFAULT_OFFSET_PX = 12

# Animation params sourced from the shared ANIMATION tokens in theme.py so
# the tooltip's fade stays in lockstep with toasts (one motion system).
# Kept as module aliases so existing call sites need no change.
from core.ui.theme import ANIMATION as _ANIM

_FADE_STEPS = _ANIM["tooltip_fade_steps"]      # ~96 ms total
_FADE_DELAY_MS = _ANIM["fade_delay_ms"]


class Tooltip:
    """Bind a tooltip to a Tk widget.

    Parameters
    ----------
    widget:
        The widget to attach the tooltip to. Must support the standard
        ``<Enter>``, ``<Leave>``, ``<Motion>``, and ``<Destroy>``
        events (all built-in Tk widgets do).
    text:
        Either a plain string or a callable that returns the text
        dynamically. The callable form is useful for status messages
        that depend on the current state of the application.
    delay_ms:
        Hover delay before the tooltip appears.
    """

    def __init__(
        self,
        widget: tk.Misc,
        text: Union[str, Callable[[], str]],
        delay_ms: int = _DEFAULT_DELAY_MS,
    ) -> None:
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms

        self._tip: Optional[tk.Toplevel] = None
        self._after_id: Optional[str] = None      # show-delay timer
        self._fade_after_id: Optional[str] = None  # active fade-step timer
        self._alpha_supported: bool = True
        self._last_x = 0
        self._last_y = 0

        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<Motion>", self._on_motion, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")
        widget.bind("<Destroy>", self._on_destroy, add="+")

    def set_text(self, text: str) -> None:
        """Replace the tooltip text. Updates the visible window if any."""
        self.text = text
        if self._tip is not None and self._tip.winfo_exists():
            label = getattr(self._tip, "_label", None)
            if label is not None:
                label.configure(text=text)

    def _on_enter(self, event: tk.Event) -> None:
        self._last_x, self._last_y = event.x_root, event.y_root
        self._cancel_pending()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _on_leave(self, _event: Optional[tk.Event] = None) -> None:
        self._cancel_pending()
        self._hide()

    def _on_motion(self, event: tk.Event) -> None:
        self._last_x, self._last_y = event.x_root, event.y_root
        if self._tip is not None and self._tip.winfo_exists():
            self._tip.geometry(
                f"+{self._last_x + _DEFAULT_OFFSET_PX}+{self._last_y + _DEFAULT_OFFSET_PX}"
            )

    def _on_destroy(self, _event: tk.Event) -> None:
        self._cancel_pending()
        self._hide()

    def _cancel_pending(self) -> None:
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _cancel_fade(self) -> None:
        if self._fade_after_id is not None:
            try:
                self.widget.after_cancel(self._fade_after_id)
            except tk.TclError:
                pass
            self._fade_after_id = None

    def _show(self) -> None:
        self._after_id = None
        if self._tip is not None and self._tip.winfo_exists():
            return
        popup_frame_factory: Any = None
        try:
            from core.ui.theme import ThemeManager, make_popup_frame

            colors = ThemeManager.COLORS
            fonts = ThemeManager.FONTS
            bg = colors["tooltip_bg"]
            fg = colors["tooltip_fg"]
            popup_frame_factory = make_popup_frame
        except (KeyError, tk.TclError):
            # Emergency fallback when ThemeManager is unavailable — mirror
            # the dark tooltip palette so the tooltip is at least legible
            # instead of the legacy light-yellow (#ffffe0) which is gone
            # from the design system.
            bg, fg = "#0f172a", "#e2e8f0"
            fonts = {"caption": ("Segoe UI", 9)}

        try:
            tip = tk.Toplevel(self.widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(
                f"+{self._last_x + _DEFAULT_OFFSET_PX}+{self._last_y + _DEFAULT_OFFSET_PX}"
            )
            tip.configure(bg=bg)

            # Shared popup-frame constructor (1px themed border) when the
            # theme is available; plain tk.Frame as an emergency fallback.
            if popup_frame_factory is not None:
                frame = popup_frame_factory(tip, bg, pad_x=8, pad_y=6)
            else:
                frame = tk.Frame(tip, bg=bg, padx=8, pady=6)
            frame.pack(fill="both", expand=True)

            label = tk.Label(
                frame,
                text=self._resolved_text(),
                bg=bg,
                fg=fg,
                font=fonts["caption"],
                wraplength=280,
                justify="left",
            )
            label.pack()
            tip._label = label  # type: ignore[attr-defined]
            self._tip = tip
        except tk.TclError as e:
            # The widget tree may have been destroyed between the
            # after-schedule and the show call. Silently ignore —
            # the tooltip simply won't appear.
            _logger.debug("Tooltip show failed: %s", e)
            return

        # Fade-in: alpha 0 → 1 over _FADE_STEPS × _FADE_DELAY_MS.
        # Try alpha=0 first; if the platform rejects it, skip the fade.
        self._alpha_supported = True
        try:
            tip.wm_attributes("-alpha", 0.0)
        except tk.TclError:
            self._alpha_supported = False
            return  # tooltip already visible at full opacity — nothing to animate

        self._fade_after_id = self.widget.after(
            _FADE_DELAY_MS, lambda: self._tick_fade_in(1)
        )

    def _tick_fade_in(self, step: int) -> None:
        self._fade_after_id = None
        if self._tip is None or not self._tip.winfo_exists():
            return
        if step > _FADE_STEPS:
            # Finalize at full opacity.
            try:
                self._tip.wm_attributes("-alpha", 1.0)
            except tk.TclError:
                self._alpha_supported = False
            return
        try:
            self._tip.wm_attributes("-alpha", step / _FADE_STEPS)
        except tk.TclError:
            # Platform withdrew alpha support mid-fade — stop animating.
            self._alpha_supported = False
            return
        self._fade_after_id = self.widget.after(
            _FADE_DELAY_MS, lambda: self._tick_fade_in(step + 1)
        )

    def _resolved_text(self) -> str:
        if callable(self.text):
            try:
                return str(self.text())
            except Exception as e:  # noqa: BLE001
                _logger.debug("Tooltip text callable raised: %s", e)
                return ""
        return str(self.text)

    def _hide(self) -> None:
        self._cancel_fade()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


__all__ = ["Tooltip"]
