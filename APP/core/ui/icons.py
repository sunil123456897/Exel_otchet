"""Icon manager — lazy-loading themed PNG icons for the UI.

Replaces astral-plane emoji (🟢🔴📊✅…) with crisp single-colour vector
icons (drawn by ``tools/generate_ui_icons.py``). Emoji render through
the OS emoji font with unpredictable colour and metrics; these icons
follow the active palette and the adaptive ``_scale`` cleanly.

Design:
- Icons live under ``APP/assets/icons/<theme>/<name>.png`` (24×24 source).
- ``IconManager`` loads them lazily via ``ImageTk.PhotoImage``, caching by
  ``(name, theme)``. Cache is invalidated on theme switch.
- ``get(name)`` returns a ``PhotoImage`` ready for ``image=`` / ``compound=``
  on ttk/tk widgets, or ``None`` if the file is missing (graceful: callers
  fall back to text-only).
- Scale: icons are rendered at the source 24px; widgets display them at
  ``CONTROL['icon']`` (16px). Tk handles the downscale. This keeps the
  asset set small (60 files) while staying crisp on HiDPI via LANCZOS in
  the generator's supersample pass.

Integration points:
- ``ttk.Button(text="Собрать", image=icons.get('play'), compound='left')``
- ``tk.Label(image=icons.get('dot_ok'))`` for status indicators
- Theme reactivity: ``ThemeManager`` calls ``IconManager.invalidate()``
  on every ``set_theme``, so a light↔dark switch swaps the icon set.
"""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import Any, Optional

# Late imports to avoid hard PIL dependency at module import (tests that
# only touch the token system shouldn't require Pillow).

_ICONS_DIR = Path(__file__).resolve().parents[2] / "assets" / "icons"


class IconManager:
    """Lazy, cached, theme-aware PNG icon provider.

    A single shared instance is exposed as ``icons`` at module level.
    Widgets call ``icons.get('play')`` and receive a ``PhotoImage`` (or
    ``None`` if unavailable). The cache rebuilds automatically when the
    active theme changes.
    """

    _cache: dict[tuple[str, str], object] = {}
    _theme: str = "light"
    _tk_root: Optional[tk.Tk] = None
    # Widgets that display an icon via image=, registered so a theme
    # switch can re-render them with the new theme's coloured icon.
    # Each entry: (widget, name, set_via) where set_via is "image" or
    # "compound" — how to re-apply the image after a rebuild.
    _registered: list[Any] = []

    @classmethod
    def bind_root(cls, root: tk.Tk) -> None:
        """Bind a Tk root for PhotoImage creation (must be called once).

        ``ImageTk.PhotoImage`` requires a Tk interpreter to exist; we
        capture the root on first use so subsequent ``get()`` calls can
        construct images without re-passing it.
        """
        cls._tk_root = root

    @classmethod
    def register(cls, widget: Any, name: str) -> None:
        """Track a widget that displays icon ``name`` via ``image=``.

        On a theme switch, ``invalidate()`` re-fetches the themed icon and
        re-applies it to every registered widget — otherwise ttk/tk
        widgets keep showing the old-theme PhotoImage indefinitely (the
        same staleness problem tkcalendar DateEntry and tk.Menu have, now
        extended to raster icons). Safe to call multiple times; dead
        widgets are pruned lazily on the next invalidate.
        """
        cls._registered.append((widget, name))

    @classmethod
    def set_theme(cls, theme: str) -> None:
        """Invalidate the cache when the active theme changes.

        Called by ``ThemeManager.set_theme`` (wired in theme.py). Clears
        the cache AND re-applies the new-theme icon to every registered
        widget, so buttons/labels switch colour immediately instead of
        keeping the old-theme PhotoImage.
        """
        if theme != cls._theme:
            cls._theme = theme
            cls._cache.clear()
            cls._reapply_registered()

    @classmethod
    def invalidate(cls) -> None:
        """Force a full cache clear + re-apply icons to widgets.

        Called on theme switch AND scale change. Re-fetches each
        registered widget's icon in the active theme and re-applies it.
        """
        cls._cache.clear()
        cls._reapply_registered()

    @classmethod
    def _reapply_registered(cls) -> None:
        """Re-apply the active-theme icon to every registered widget.

        Prunes dead/destroyed widgets lazily. Catches TclError for
        widgets whose window was torn down between calls.
        """
        live = []
        for widget, name in cls._registered:
            try:
                # winfo_exists() returns 0 if the widget's window is gone.
                if not widget.winfo_exists():
                    continue
                img = cls.get(name)
                try:
                    widget.configure(image=img)
                except tk.TclError:
                    pass
                live.append((widget, name))
            except (tk.TclError, AttributeError):
                # Widget destroyed — drop it from the registry.
                continue
        cls._registered = live

    @classmethod
    def get(cls, name: str) -> Any:
        """Return a ``PhotoImage`` for ``name`` in the active theme.

        Returns ``None`` (not raises) if PIL is unavailable or the icon
        file is missing — callers fall back to text-only rendering.
        """
        key = (name, cls._theme)
        if key in cls._cache:
            return cls._cache[key]

        img = cls._load(name)
        cls._cache[key] = img
        return img

    @classmethod
    def _load(cls, name: str) -> Any:
        path = _ICONS_DIR / cls._theme / f"{name}.png"
        if not path.exists():
            return None
        try:
            from PIL import Image, ImageTk  # noqa: PLC0415 — lazy, optional
        except ImportError:
            return None
        if cls._tk_root is None:
            # No root bound yet — can't create a PhotoImage. Return None
            # so the caller falls back to text; once bind_root is called
            # the next get() will succeed.
            return None
        try:
            pil = Image.open(path)
            return ImageTk.PhotoImage(pil, master=cls._tk_root)
        except Exception:
            return None

    @classmethod
    def available(cls) -> list[str]:
        """List icon names available on disk (for diagnostics/tests)."""
        d = _ICONS_DIR / cls._theme
        if not d.exists():
            return []
        return sorted(p.stem for p in d.glob("*.png"))


# Shared singleton — import as ``from core.ui.icons import icons``.
icons = IconManager
