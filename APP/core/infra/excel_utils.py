"""Shared Excel helper functions used across rsch, reconciliation, and export modules.

Consolidates duplicated functions that were previously copy-pasted:
- ``excel_safe_text``  (was ``_excel_safe_text`` / ``_safe_text``)
- ``to_decimal_excel`` (was ``_to_decimal`` in rsch and reconciliation)
- ``normalize_excel_text`` (was ``_normalize_text`` in rsch and reconciliation)
"""

from __future__ import annotations

from typing import Any


def excel_safe_text(value: Any) -> Any:
    """Mitigate Excel formula injection (CWE-1236).

    Prepends a single quote to any string that starts with ``=``, ``+``,
    ``-`` or ``@`` so Excel treats it as text instead of evaluating it as
    a formula.  Non-string values pass through unchanged.
    """
    if isinstance(value, str):
        stripped = value.lstrip()
        if stripped and stripped[0] in ("=", "+", "-", "@"):
            return "'" + value
    return value
