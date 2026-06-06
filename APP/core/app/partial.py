"""Mark interrupted output files as ``.partial`` so users can clean up.

When a long-running report is cancelled mid-write, the destination
workbook may exist on disk in an incomplete state. Removing it would
silently destroy work the user might want to inspect; leaving it
with the real filename risks the user opening a corrupted file by
accident later.

The convention: rename ``foo.xlsx`` → ``foo.partial.xlsx`` on cancel.
The user can then either delete the partial file or rename it back
once they understand what was written. This is the same pattern
used by web browsers for in-progress downloads.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

_PARTIAL_SUFFIX = ".partial"


def mark_partial(path: Optional[Path]) -> List[Path]:
    """Rename ``path`` (or its contents) to a ``.partial`` variant.

    ``None`` and missing paths are no-ops. When ``path`` is a directory,
    every ``*.xlsx`` file inside is renamed. Returns the list of
    resulting partial paths (empty when nothing was renamed).
    """
    if path is None:
        return []
    src = Path(path)
    if not src.exists():
        return []
    candidates: List[Path] = []
    if src.is_dir():
        candidates.extend(sorted(src.glob("*.xlsx")))
    else:
        candidates.append(src)

    renamed: List[Path] = []
    for entry in candidates:
        new_name = entry.with_name(entry.stem + _PARTIAL_SUFFIX + entry.suffix)
        # Avoid clobbering an existing partial from a previous attempt.
        counter = 1
        target = new_name
        while target.exists():
            target = entry.with_name(
                f"{entry.stem}{_PARTIAL_SUFFIX}.{counter}{entry.suffix}"
            )
            counter += 1
        try:
            entry.rename(target)
        except OSError as exc:
            logging.debug("Could not mark %s as partial: %s", entry, exc)
            continue
        renamed.append(target)
    return renamed


def format_partial_note(partials: List[Path]) -> str:
    """Return a human-readable note listing the partial files."""
    if not partials:
        return ""
    if len(partials) == 1:
        return f" Неполный файл: {partials[0].name} (переименован в .partial)."
    joined = ", ".join(p.name for p in partials[:3])
    suffix = "" if len(partials) <= 3 else f" и ещё {len(partials) - 3}"
    return f" Неполные файлы ({len(partials)}): {joined}{suffix}."


__all__ = ["mark_partial", "format_partial_note"]
