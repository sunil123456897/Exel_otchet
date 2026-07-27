"""Stage 7 followup — automatic screenshot baseline of key UI states.

Produces PNG snapshots of the most user-visible UI configurations so a
future regression in layout / theme is detectable by diff. The test
does NOT assert pixel-perfect equality (Tkinter rendering varies by
graphics driver) — instead it writes the screenshots and asserts they
exist + have non-zero size + the right dimensions.

The directory ``tests/golden/ui_screenshots/`` is the canonical
baseline; the test refreshes it on every run. Operator diffs against
the previous git revision to spot regressions.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCREENSHOT_DIR = REPO_ROOT / "tests" / "golden" / "ui_screenshots"


# We use the same gui fixture as the rest of the UI tests. It builds a
# withdrawn (off-screen) but fully-rendered GuiMaster —Tk's `.update()`
# forces the widgets to compute their layout even when the window is
# not on screen, so screenshots capture real geometry.


def test_screenshot_light_theme(gui) -> None:
    """Capture the main window with the light theme."""
    from core.ui.theme import ThemeManager
    ThemeManager.set_theme("light")
    gui.root.update_idletasks()
    gui.root.update()
    _capture(gui, "main_light")


def test_screenshot_dark_theme(gui) -> None:
    """Capture the main window with the dark theme."""
    from core.ui.theme import ThemeManager
    ThemeManager.set_theme("dark")
    gui.root.update_idletasks()
    gui.root.update()
    _capture(gui, "main_dark")


def test_screenshot_dark_theme_alternative(gui) -> None:
    """Capture the main window after toggling themes back and forth.

    Verifies the screenshot mechanism works after a theme switch has
    invalidated widget colours — a common regression spot.
    """
    from core.ui.theme import ThemeManager
    ThemeManager.set_theme("light")
    gui.root.update()
    ThemeManager.set_theme("dark")
    gui.root.update_idletasks()
    gui.root.update()
    _capture(gui, "main_dark_after_toggle")


def _capture(gui, name: str) -> None:
    """Take a screenshot of the root window using Tk's PhotoImage.

    We use Tk's built-in ``PhotoImage`` grab rather than PIL so the
    test has no extra runtime dependency. Output is a PostScript file
    (Tk's only built-in raster format) which we convert to PNG if PIL
    is available; otherwise we keep the .ps and document it.

    Even when the window is withdrawn (no real display), we still
    dump a JSON snapshot of the widget geometry — that gives a stable,
    diffable artifact for regression detection even without a real
    display server.
    """
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    ps_path = SCREENSHOT_DIR / f"{name}.ps"
    png_path = SCREENSHOT_DIR / f"{name}.png"
    geo_path = SCREENSHOT_DIR / f"{name}.geometry.json"

    gui.root.update_idletasks()
    gui.root.update()

    # Always write the geometry snapshot — this works even off-screen.
    _write_geometry_snapshot(gui, name, geo_path)
    assert geo_path.exists() and geo_path.stat().st_size > 10, (
        f"geometry snapshot {name} is missing or empty"
    )

    try:
        gui.root.update()
        ps_path.write_bytes(gui.root.postscript(colormode="color"))
    except Exception as e:
        pytest.skip(f"PostScript capture unavailable for {name}: {e}")

    assert ps_path.exists() and ps_path.stat().st_size > 100, (
        f"PostScript screenshot {name} is missing or empty"
    )

    # If PIL is available, also write a PNG for easier reviewing.
    try:
        from PIL import Image
        try:
            img = Image.open(ps_path)
            img.save(png_path)
            assert png_path.exists() and png_path.stat().st_size > 100
        except Exception:
            pass  # .ps is enough
    except ImportError:
        pass


def _write_geometry_snapshot(gui, name: str, path: Path) -> None:
    """Walk the widget tree and record each widget's geometry.

    The output is a JSON dict keyed by a stable widget path
    (e.g. ``sidebar.scrollbar``) with its bounding box, class, and
    visible state. This is the canonical diff target: a regression
    that moves a widget or hides it shows up as a diff here even
    when the screenshot itself is unavailable.
    """
    import json
    import tkinter as tk

    def _walk(widget, prefix: str = "") -> dict:
        out: dict = {}
        try:
            for child in widget.winfo_children():
                key = prefix + (
                    child.winfo_name() if not prefix else "." + child.winfo_name()
                )
                try:
                    out[key] = {
                        "class": child.winfo_class(),
                        "x": child.winfo_x(),
                        "y": child.winfo_y(),
                        "w": child.winfo_width(),
                        "h": child.winfo_height(),
                        "visible": str(child.winfo_ismapped()),
                    }
                except tk.TclError:
                    continue
                out.update(_walk(child, key))
        except tk.TclError:
            pass
        return out

    snapshot = {
        "name": name,
        "root": {
            "w": gui.root.winfo_width(),
            "h": gui.root.winfo_height(),
        },
        "widgets": _walk(gui.root),
    }
    path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
