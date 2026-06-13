"""Persist and restore the main window geometry between launches.

The geometry is stored in a single line in ``~/.master_report_geometry``
using the format ``WIDTHxHEIGHT+X+Y`` (the same string Tk returns
from ``geometry()``). We deliberately do not store width/height only:
position is also part of the user-visible state.

If the saved geometry is off-screen (e.g. a previously-attached
external monitor is no longer connected) we fall back to a sensible
default. The check is intentionally permissive: any single coordinate
outside the current virtual screen is enough to discard the saved
value.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional, Tuple

_logger = logging.getLogger(__name__)

_DEFAULT_FILE = Path.home() / ".master_report_geometry"
_GEOM_RE = re.compile(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$")


def _parse_geometry(geom: str) -> Optional[Tuple[int, int, int, int]]:
    m = _GEOM_RE.match(geom.strip())
    if not m:
        return None
    w, h, x, y = (int(m.group(i)) for i in range(1, 5))
    return w, h, x, y


def _is_visible(
    width: int, height: int, x: int, y: int, screen_w: int, screen_h: int
) -> bool:
    """Reject saved geometries that no longer fit on the current display."""
    if width < 100 or height < 100:
        return False
    if x < -width + 50 or y < -height + 50:
        return False
    if x > screen_w - 50 or y > screen_h - 50:
        return False
    return True


def load_geometry(file_path: Optional[Path] = None) -> Optional[str]:
    """Return a usable geometry string, or None when none is stored.

    The caller (GuiMaster) is expected to merge this with its own
    default-size hint: if the saved geometry is invalid or off-screen
    we return None and the GUI falls back to its hard-coded default.
    """
    path = file_path or _DEFAULT_FILE
    try:
        content = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError as e:
        _logger.debug("Geometry file not readable: %s", e)
        return None

    parsed = _parse_geometry(content)
    if parsed is None:
        _logger.info("Discarded malformed saved geometry: %r", content)
        return None
    w, h, x, y = parsed
    # Without a screen reference we can't validate visibility; return
    # the value and let the caller check after Tk is up.
    return f"{w}x{h}+{x}+{y}"


def is_geometry_visible(
    geometry: str, screen_w: int, screen_h: int
) -> bool:
    parsed = _parse_geometry(geometry)
    if parsed is None:
        return False
    return _is_visible(*parsed, screen_w=screen_w, screen_h=screen_h)


def save_geometry(geometry: str, file_path: Optional[Path] = None) -> None:
    """Persist the geometry for the next launch.

    Failures are logged but never raised — the GUI should still be
    able to close cleanly even if the disk is full or read-only.
    """
    path = file_path or _DEFAULT_FILE
    if _parse_geometry(geometry) is None:
        _logger.debug("Refusing to save malformed geometry: %r", geometry)
        return
    try:
        path.write_text(geometry, encoding="utf-8")
    except OSError as e:
        _logger.warning("Failed to persist window geometry: %s", e)


def default_geometry_path() -> Path:
    return _DEFAULT_FILE


__all__ = [
    "load_geometry",
    "save_geometry",
    "is_geometry_visible",
    "default_geometry_path",
]
