"""Non-modal toast notifications.

Replaces blocking ``messagebox.showinfo`` / ``showerror`` for non-critical
notifications. Stack of up to 3 toasts in the bottom-right corner of the
root window, each fading out after ``duration_ms``.

Each toast is a borderless ``tk.Toplevel`` so it can fade and slide
independently of the root window's alpha (Tkinter Frames do not support
per-widget alpha). On platforms where ``-alpha`` is unsupported (some
X11 builds), the fade is skipped and the toast appears at full opacity;
the slide-in still runs because it only depends on window position.

For notifications that genuinely require user choice (e.g. "open the
finished file?"), keep using ``messagebox.askyesno``.
"""
from __future__ import annotations

import logging
import tkinter as tk
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ToastLevel(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


_LEVEL_ICONS = {
    ToastLevel.INFO: "ℹ",
    ToastLevel.SUCCESS: "✓",
    ToastLevel.WARNING: "⚠",
    ToastLevel.ERROR: "✕",
}

# Level → (bg_key, fg_key) into ThemeManager.COLORS. Resolved at ``show``
# time so a theme switch picks up the new palette immediately.
_LEVEL_THEME_KEYS = {
    ToastLevel.INFO: ("info", "text_inverse"),
    ToastLevel.SUCCESS: ("success", "text_inverse"),
    # UX-020: use text_inverse (not text) for WARNING so the foreground
    # is dark on the yellow warning background in both light and dark
    # themes. Previously "text" gave light-on-yellow in dark theme =
    # WCAG AA fail.
    ToastLevel.WARNING: ("warning", "text_inverse"),
    ToastLevel.ERROR: ("danger", "text_inverse"),
}

_FADE_IN_STEPS = 8       # ~150 ms total (8 × 18 ms)
_FADE_OUT_STEPS = 10     # ~180 ms total (10 × 18 ms)
_FADE_DELAY_MS = 18
_SLIDE_PX = 30           # subtle slide-in from the right edge


def _darken(hex_color: str, factor: float = 0.88) -> str:
    """Darken a ``#rrggbb`` color by ``factor`` (0..1). Best-effort."""
    try:
        h = hex_color.lstrip("#")
        r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
        r = max(0, min(255, int(r * factor)))
        g = max(0, min(255, int(g * factor)))
        b = max(0, min(255, int(b * factor)))
        return f"#{r:02x}{g:02x}{b:02x}"
    except (ValueError, IndexError):
        return hex_color


@dataclass
class _Toast:
    level: ToastLevel
    title: str
    message: str
    toplevel: tk.Toplevel
    target_x: int = 0
    target_y: int = 0
    auto_after_id: Optional[str] = None      # auto-dismiss timer
    fade_after_id: Optional[str] = None      # active fade-step timer
    fading_out: bool = False
    fade_step: int = 0
    alpha_supported: bool = True
    pending_fade: bool = True                # False once _tick_fade has run
    detail_frame: Optional[tk.Frame] = None  # FIX-006: expandable detail section
    detail_visible: bool = False


class ToastManager:
    """Stack of non-modal toast popups anchored to a Tk root."""

    def __init__(self, root: tk.Misc, max_stack: int = 3) -> None:
        self._root = root
        self._max_stack = max_stack
        self._stack: list[_Toast] = []
        # Cancel all pending animations when the app closes so we don't
        # leave orphaned ``after`` callbacks trying to touch a dead root.
        try:
            self._root.bind("<Destroy>", self._cleanup_all, add="+")
        except tk.TclError:
            pass

    # ----------------------------------------------------------------- public API

    def show(
        self,
        level: ToastLevel,
        title: str,
        message: str,
        duration_ms: int = 4000,
        detail: str = "",
    ) -> None:
        """Show a toast. Older toasts above ``max_stack`` are dismissed early.

        FIX-006: When ``detail`` is a non-empty string, an expandable
        "Подробнее ▼" link is rendered below the message. Clicking it
        toggles a smaller-font block showing the detail text (e.g. the
        underlying exception message, file path, or recovery hint).
        """
        try:
            from core.ui.theme import ThemeManager

            colors = ThemeManager.COLORS
            bg_key, fg_key = _LEVEL_THEME_KEYS[level]
            bg = colors[bg_key]
            fg = colors[fg_key]
            icon = _LEVEL_ICONS[level]
            border = colors.get("border_subtle", colors.get("trough", "#ced4da"))
        except (KeyError, tk.TclError):
            return

        # Make room — dismiss oldest visible toasts beyond max_stack.
        visible = [t for t in self._stack if not t.fading_out]
        while len(visible) >= self._max_stack:
            self._dismiss(visible[0], early=True)
            visible = [t for t in self._stack if not t.fading_out]

        toplevel = tk.Toplevel(self._root)
        toplevel.wm_overrideredirect(True)
        try:
            toplevel.configure(bg=bg)
        except tk.TclError:
            pass

        # Initial alpha = 0 to prevent a flash before the fade-in starts.
        # On platforms that don't support per-window alpha (some X11 builds),
        # this raises TclError — we record that and skip further alpha animation.
        alpha_supported = True
        try:
            toplevel.wm_attributes("-alpha", 0.0)
        except tk.TclError:
            alpha_supported = False

        # Park the toplevel off-screen so the mapping that happens during
        # ``_repack``'s ``update_idletasks()`` is invisible on platforms
        # without alpha (otherwise the WM default position flashes briefly).
        try:
            toplevel.wm_geometry("+-10000+-10000")
        except tk.TclError:
            pass

        # Inner frame carries the 1px highlight border + content padding.
        inner = tk.Frame(
            toplevel,
            bg=bg,
            padx=16,
            pady=10,
            highlightthickness=1,
            highlightbackground=border,
            highlightcolor=border,
        )
        inner.pack(fill="both", expand=True)

        title_label = tk.Label(
            inner,
            text=f"{icon}  {title}",
            bg=bg,
            fg=fg,
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        title_label.pack(fill="x")

        if message:
            msg_label = tk.Label(
                inner,
                text=message,
                bg=bg,
                fg=fg,
                font=("Segoe UI", 9),
                anchor="w",
                wraplength=360,
                justify="left",
            )
            msg_label.pack(fill="x", pady=(2, 0))

        toast = _Toast(
            level=level,
            title=title,
            message=message,
            toplevel=toplevel,
            alpha_supported=alpha_supported,
        )

        # FIX-006: expandable detail section for error/warning toasts.
        # When ``detail`` is non-empty, render a "Подробнее ▼" link that
        # toggles a smaller-font block showing the detail text. This lets
        # the user see the underlying cause (exception message, file path,
        # recovery hint) without flooding the toast for all viewers.
        if detail:
            detail_bg = _darken(bg, 0.94)
            toggle_label = tk.Label(
                inner,
                text="Подробнее ▼",
                bg=bg,
                fg=fg,
                font=("Segoe UI", 8, "underline"),
                anchor="w",
                cursor="hand2",
            )
            toggle_label.pack(fill="x", pady=(4, 0))

            detail_frame = tk.Frame(
                inner,
                bg=detail_bg,
                padx=8,
                pady=6,
            )
            # Hidden initially; shown when toggle is clicked.
            detail_label = tk.Label(
                detail_frame,
                text=detail,
                bg=detail_bg,
                fg=fg,
                font=("Segoe UI", 8),
                anchor="w",
                wraplength=340,
                justify="left",
            )
            detail_label.pack(fill="x")

            def _toggle_detail(_event=None, t=toast, lbl=toggle_label):
                if t.detail_visible:
                    t.detail_frame.pack_forget()
                    lbl.configure(text="Подробнее ▼")
                    t.detail_visible = False
                else:
                    t.detail_frame.pack(fill="x", pady=(4, 0))
                    lbl.configure(text="Скрыть ▲")
                    t.detail_visible = True
                # Repack to reposition all toasts (height changed).
                self._repack()

            toggle_label.bind("<Button-1>", _toggle_detail)
            toast.detail_frame = detail_frame

        # Close button (×), top-right corner. Clicking it dismisses early
        # via the same fade-out path as the auto-dismiss timer.
        close_bg_hover = _darken(bg, 0.88)
        close_label = tk.Label(
            toplevel,
            text="×",
            bg=bg,
            fg=fg,
            font=("Segoe UI", 11, "bold"),
            cursor="hand2",
        )
        close_label.place(relx=1.0, x=-8, y=4, anchor="ne")
        close_label.bind("<Button-1>", lambda e, t=toast: self._dismiss(t))
        close_label.bind(
            "<Enter>",
            lambda e, lbl=close_label, c=close_bg_hover: lbl.configure(bg=c),
        )
        close_label.bind(
            "<Leave>",
            lambda e, lbl=close_label, c=bg: lbl.configure(bg=c),
        )

        self._stack.append(toast)
        # Compute target positions for all toasts (also slides older ones up).
        self._repack()
        # Start the new toast offset to the right for the slide-in.
        self._set_position(toast, toast.target_x + _SLIDE_PX, toast.target_y)
        toast.fade_step = 0
        toast.fading_out = False
        self._tick_fade(toast)
        # Auto-dismiss after the requested duration.
        toast.auto_after_id = self._root.after(
            duration_ms, lambda t=toast: self._dismiss(t)
        )

    def info(self, title: str, message: str = "", *, detail: str = "", **kwargs) -> None:
        self.show(ToastLevel.INFO, title, message, detail=detail, **kwargs)

    def success(self, title: str, message: str = "", *, detail: str = "", **kwargs) -> None:
        self.show(ToastLevel.SUCCESS, title, message, detail=detail, **kwargs)

    def warning(self, title: str, message: str = "", *, detail: str = "", **kwargs) -> None:
        self.show(ToastLevel.WARNING, title, message, detail=detail, **kwargs)

    def error(self, title: str, message: str = "", *, detail: str = "", **kwargs) -> None:
        self.show(ToastLevel.ERROR, title, message, detail=detail, **kwargs)

    # ------------------------------------------------------------------- internals

    def _set_alpha(self, toast: _Toast, alpha: float) -> None:
        if not toast.alpha_supported:
            return
        try:
            toast.toplevel.wm_attributes("-alpha", alpha)
        except tk.TclError:
            # Platform doesn't support per-window alpha — disable further
            # attempts for this toast (it stays at full opacity).
            toast.alpha_supported = False

    def _set_position(self, toast: _Toast, x: int, y: int) -> None:
        try:
            toast.toplevel.wm_geometry(f"+{int(x)}+{int(y)}")
        except tk.TclError:
            pass

    def _tick_fade(self, toast: _Toast) -> None:
        """Advance one fade animation step. Reschedules itself via ``after``."""
        toast.pending_fade = False
        toast.fade_after_id = None
        if toast.fading_out:
            total = _FADE_OUT_STEPS
            step = toast.fade_step
            if step >= total:
                # Fade-out complete — destroy.
                self._destroy_toplevel(toast)
                return
            alpha = 1.0 - (step + 1) / total
            self._set_alpha(toast, alpha)
            toast.fade_step = step + 1
            toast.fade_after_id = self._root.after(
                _FADE_DELAY_MS, lambda: self._tick_fade(toast)
            )
        else:
            # Fade-in. Abort if the toast was dismissed out-of-band.
            if toast not in self._stack:
                self._destroy_toplevel(toast)
                return
            total = _FADE_IN_STEPS
            step = toast.fade_step
            if step >= total:
                # Fade-in complete — pin to final position & full opacity.
                self._set_alpha(toast, 1.0)
                self._set_position(toast, toast.target_x, toast.target_y)
                return
            alpha = (step + 1) / total
            x = toast.target_x + int(_SLIDE_PX * (1 - (step + 1) / total))
            self._set_alpha(toast, alpha)
            self._set_position(toast, x, toast.target_y)
            toast.fade_step = step + 1
            toast.fade_after_id = self._root.after(
                _FADE_DELAY_MS, lambda: self._tick_fade(toast)
            )

    def _dismiss(self, toast: _Toast, early: bool = False) -> None:
        if toast not in self._stack:
            return
        if toast.fading_out:
            if not early:
                return  # already dismissing — wait for the fade to complete
            # early=True: accelerate to instant destroy so the new toast
            # gets visual space immediately.
            self._destroy_toplevel(toast)
            self._repack()
            return

        # Cancel auto-dismiss timer.
        if toast.auto_after_id is not None:
            try:
                self._root.after_cancel(toast.auto_after_id)
            except tk.TclError:
                pass
            toast.auto_after_id = None
        # Cancel any pending fade-in step.
        if toast.fade_after_id is not None:
            try:
                self._root.after_cancel(toast.fade_after_id)
            except tk.TclError:
                pass
            toast.fade_after_id = None

        if early or not toast.alpha_supported:
            # Instant destroy — make room quickly or platform can't fade.
            self._destroy_toplevel(toast)
            self._repack()
            return

        # Fade out, then destroy. Keep in stack so _cleanup_all can find it
        # if the app exits mid-fade; _repack skips fading-out toasts.
        toast.fading_out = True
        toast.fade_step = 0
        self._repack()
        self._tick_fade(toast)

    def _destroy_toplevel(self, toast: _Toast) -> None:
        """Cancel timers, remove from stack, and destroy the underlying Toplevel."""
        if toast.fade_after_id is not None:
            try:
                self._root.after_cancel(toast.fade_after_id)
            except tk.TclError:
                pass
            toast.fade_after_id = None
        if toast.auto_after_id is not None:
            try:
                self._root.after_cancel(toast.auto_after_id)
            except tk.TclError:
                pass
            toast.auto_after_id = None
        if toast in self._stack:
            self._stack.remove(toast)
        try:
            toast.toplevel.destroy()
        except tk.TclError:
            pass

    def _repack(self) -> None:
        """Re-anchor all visible toasts vertically, newest at the bottom."""
        try:
            root_x = self._root.winfo_rootx()
            root_y = self._root.winfo_rooty()
            root_w = self._root.winfo_width()
            root_h = self._root.winfo_height()
        except tk.TclError:
            return
        margin = 20
        offset = margin
        for toast in reversed(self._stack):
            if toast.fading_out:
                continue
            try:
                toast.toplevel.update_idletasks()
                w = toast.toplevel.winfo_reqwidth() or 320
                h = toast.toplevel.winfo_reqheight() or 60
            except tk.TclError:
                w, h = 320, 60
            toast.target_x = root_x + root_w - w - margin
            toast.target_y = root_y + root_h - h - offset
            # If the toast is mid-fade-in (or about to start), the next
            # tick will reposition it using the updated target. Otherwise
            # jump to the new position instantly (YAGNI: no slide on repack).
            if toast.fade_after_id is None and not toast.pending_fade:
                self._set_position(toast, toast.target_x, toast.target_y)
            offset += h + 8

    def _cleanup_all(self, event: Optional[tk.Event] = None) -> None:
        """Cancel all pending animations and destroy toasts on app close."""
        if event is not None and getattr(event, "widget", None) is not self._root:
            return
        for toast in list(self._stack):
            self._destroy_toplevel(toast)
        self._stack.clear()


__all__ = ["ToastManager", "ToastLevel"]
