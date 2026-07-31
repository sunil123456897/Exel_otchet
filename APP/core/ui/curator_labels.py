"""Curator label ↔ config-key mapping for the sidebar selector.

Extracted from ``core/ui/ui_sidebar.py`` (TD: god-widget decomposition).
The combobox shows human-readable labels; the controller expects the
config keys ``boris`` / ``ivan``.
"""

from __future__ import annotations

CURATOR_LABELS = ("Общий отчет", "Куратор Борис", "Куратор Иван")

_CURATOR_LABEL_TO_KEY = {
    "Куратор Борис": "boris",
    "Куратор Иван": "ivan",
}


def curator_key_from_label(label: str) -> str | None:
    """Map a combobox label to the curator config key (``None`` = general)."""
    return _CURATOR_LABEL_TO_KEY.get(label)
