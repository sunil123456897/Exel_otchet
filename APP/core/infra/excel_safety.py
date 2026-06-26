"""Shared Excel safety helpers.

Provides ``excel_safe_text`` — the single canonical implementation of
formula-injection sanitisation used by both the reconciliation writer
(``core.infra.reconciliation._utils``) and the RSCH writer
(``core.infra.rsch._format``). Previously each module carried its own
private copy of ``_excel_safe_text``; the two could silently drift
(e.g. one adds a new dangerous char, the other forgets). This module
is the single source of truth.

Sanitisation rule: if a string cell starts (after left-strip) with one
of the formula-injection characters ``= + - @``, prepend a single
apostrophe ``'`` so Excel treats the cell as literal text rather than
a formula. Non-string values pass through unchanged.
"""
from __future__ import annotations

from typing import Any

# Characters that trigger Excel formula parsing when they appear as the
# first character of a cell. Tab/CR/LF are also dangerous because they
# can be used to break out of CSV-style quoting, but the original
# implementations only checked the four formula triggers — we preserve
# that behaviour to avoid changing the on-disk output of existing
# reports. The domain-layer ``LogicService._sanitize`` covers the
# broader set (including \t \r \n) for the master-report path.
_FORMULA_INJECTION_CHARS = ("=", "+", "-", "@")


def excel_safe_text(value: Any) -> Any:
    """Prevent Excel formula injection by prefixing dangerous cells with ``'``.

    If ``value`` is a string whose first non-space character is one of
    ``= + - @``, return ``"'" + value``. Otherwise return ``value``
    unchanged. Non-string types (int, float, Decimal, None, …) are
    returned as-is.

    This is the canonical implementation — both
    ``core.infra.reconciliation._utils._excel_safe_text`` and
    ``core.infra.rsch._format._excel_safe_text`` delegate here.
    """
    if isinstance(value, str):
        stripped = value.lstrip()
        if stripped and stripped[0] in _FORMULA_INJECTION_CHARS:
            return "'" + value
    return value


__all__ = ["excel_safe_text"]
