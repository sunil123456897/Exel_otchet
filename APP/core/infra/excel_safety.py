"""Shared Excel safety helpers.

Provides ``excel_safe_text`` — the single canonical implementation of
formula-injection sanitisation AND illegal-character stripping used by
both the reconciliation writer (``core.infra.reconciliation._utils``)
and the RSCH writer (``core.infra.rsch._format``). Previously each
module carried its own private copy of ``_excel_safe_text``; the two
could silently drift (e.g. one adds a new dangerous char, the other
forgets). This module is the single source of truth.

Sanitisation rule:
1. Strip XML-illegal control characters that openpyxl refuses outright
   (``IllegalCharacterError``). Source spreadsheets pasted from 1С /
   bank statements sometimes carry stray BEL / US / NUL bytes inside
   otherwise-valid text (e.g. «Диана М_Капстрой…»). Without stripping,
   ``ws.append(values)`` aborts the whole build — which is exactly the
   «грузит грузит и не выгружается» symptom on «РСЧ за период».
2. If the remaining string starts (after left-strip) with one of the
   formula-injection characters ``= + - @``, prepend a single apostrophe
   ``'`` so Excel treats the cell as literal text rather than a formula.
   Non-string values pass through unchanged.
"""
from __future__ import annotations

import re
from typing import Any

# Characters that trigger Excel formula parsing when they appear as the
# first character of a cell. Tab/CR/LF are also dangerous because they
# can be used to break out of CSV-style quoting, but the original
# implementations only checked the four formula triggers — we preserve
# that behaviour to avoid changing the on-disk output of existing
# reports. The domain-layer ``LogicService._sanitize`` covers the
# broader set (including \t \r \n) for the master-report path.
_FORMULA_INJECTION_CHARS = ("=", "+", "-", "@")

# XML 1.0 control characters that openpyxl rejects with
# IllegalCharacterError. We mirror openpyxl's own ILLEGAL_CHARACTERS_RE
# so the canonical rule lives in one place. Tab/newline/carriage-return
# are permitted by the OOXML spec and kept as-is.
_ILLEGAL_XML_CHARS_RE = re.compile(
    "["
    "\x00-\x08"
    "\x0b-\x0c"
    "\x0e-\x1f"
    "]"
)


def excel_safe_text(value: Any) -> Any:
    """Sanitise a cell value for safe writing via openpyxl.

    For strings: (1) strip XML-illegal control characters that would
    raise ``IllegalCharacterError`` at ``ws.append`` time, then
    (2) prefix formula-injection-leading cells with ``'``. Non-string
    types (int, float, Decimal, None, …) are returned as-is.

    This is the canonical implementation — both
    ``core.infra.reconciliation._utils._excel_safe_text`` and
    ``core.infra.rsch._format._excel_safe_text`` delegate here.
    """
    if isinstance(value, str):
        # 1. Remove control chars openpyxl refuses (\x00-\x08, \x0b-\x0c,
        #    \x0e-\x1f). Tab/newline/CR are part of the legal set and kept.
        if _ILLEGAL_XML_CHARS_RE.search(value):
            value = _ILLEGAL_XML_CHARS_RE.sub("", value)
        # 2. Formula-injection guard (unchanged behaviour).
        stripped = value.lstrip()
        if stripped and stripped[0] in _FORMULA_INJECTION_CHARS:
            return "'" + value
    return value


__all__ = ["excel_safe_text"]
