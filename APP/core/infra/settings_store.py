"""UI-preferences persistence — reads/writes the ``ui:`` section of ``config.yaml``.

All values are validated and coerced on load; a broken or missing ``ui:``
section never raises — defaults are returned instead.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from core.infra.config_controller import ConfigController

_log = logging.getLogger(__name__)

# ── valid value sets ──────────────────────────────────────────
_VALID_THEMES = frozenset({"light", "dark", "system"})
_VALID_SCALE_MODES = frozenset({"auto", "manual"})
_VALID_DENSITIES = frozenset({"compact", "normal", "comfortable"})

_SCALE_MIN = 0.80
_SCALE_MAX = 1.50
_SIDEBAR_MIN = 0
_SIDEBAR_MAX = 800


# ── prefs dataclass ───────────────────────────────────────────
@dataclass
class UIPreferences:
    """Typed representation of the ``ui:`` section in ``config.yaml``."""

    theme: str = "light"
    scale_mode: str = "auto"
    user_scale: float = 1.0
    density: str = "normal"
    sidebar_width: int = 0  # 0 = auto
    window_geometry: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict suitable for YAML serialisation."""
        d: dict[str, Any] = {}
        d["theme"] = self.theme
        d["scale_mode"] = self.scale_mode
        d["user_scale"] = self.user_scale
        d["density"] = self.density
        d["sidebar_width"] = self.sidebar_width
        if self.window_geometry is not None:
            d["window_geometry"] = self.window_geometry
        return d


# ── coercers ──────────────────────────────────────────────────
def _coerce_str(value: Any, valid: frozenset[str], default: str) -> str:
    if isinstance(value, str) and value in valid:
        return value
    return default


def _coerce_float(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        v = float(value)
        return max(lo, min(hi, v))
    except (TypeError, ValueError):
        return default


def _coerce_int(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        v = int(value)
        return max(lo, min(hi, v))
    except (TypeError, ValueError):
        return default


def _coerce_opt_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None


# ── store ─────────────────────────────────────────────────────
class SettingsStore:
    """Read/write ``ui:`` section from the shared ``config.yaml``.

    Uses the *existing* ``ConfigController`` instance — we never hold
    our own YAML parser or file handle.  All mutations go through
    ``cc.save_config()`` so there is exactly one serialisation path.
    """

    def __init__(self, config_controller: ConfigController) -> None:
        self._cc = config_controller

    # ── public API ────────────────────────────────────────────

    def load_preferences(self) -> UIPreferences:
        """Read and validate the ``ui:`` section; return defaults on failure."""
        cfg = self._cc.config
        if not isinstance(cfg, dict):
            return UIPreferences()
        section = cfg.get("ui", {})
        if not isinstance(section, dict):
            return UIPreferences()
        return UIPreferences(
            theme=_coerce_str(section.get("theme"), _VALID_THEMES, "light"),
            scale_mode=_coerce_str(section.get("scale_mode"), _VALID_SCALE_MODES, "auto"),
            user_scale=_coerce_float(section.get("user_scale"), _SCALE_MIN, _SCALE_MAX, 1.0),
            density=_coerce_str(section.get("density"), _VALID_DENSITIES, "normal"),
            sidebar_width=_coerce_int(section.get("sidebar_width"), _SIDEBAR_MIN, _SIDEBAR_MAX, 0),
            window_geometry=_coerce_opt_str(section.get("window_geometry")),
        )

    def save_preferences(self, prefs: UIPreferences) -> bool:
        """Write ``prefs`` into the ``ui:`` section and flush to disk.

        Returns ``True`` on success, ``False`` on write failure (logged).
        """
        try:
            cfg = self._cc.config
            if not isinstance(cfg, dict):
                self._cc.config = {}
                cfg = self._cc.config
            cfg["ui"] = prefs.to_dict()
            self._cc.save_config()
            return True
        except Exception:
            _log.exception("Failed to save UI preferences")
            return False

    def update(self, **changes: Any) -> UIPreferences:
        """Partial update helper — load, merge, save, return new prefs.

        Example::

            store = SettingsStore(cc)
            prefs = store.update(user_scale=1.25, density="compact")
        """
        prefs = self.load_preferences()
        for key, value in changes.items():
            if hasattr(prefs, key):
                setattr(prefs, key, value)
        self.save_preferences(prefs)
        return prefs
