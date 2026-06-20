"""Shared Excel style constants used by rsch, reconciliation, and export modules.

Consolidates duplicated PatternFill / Font / Border / Alignment / number-format
definitions that were previously copy-pasted across ``rsch/_build.py``,
``rsch/_format.py``, ``rsch/_template.py``, and ``reconciliation/_utils.py``.
"""

from __future__ import annotations

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

INCOME_FILL = PatternFill(
    start_color="FFC6EFCE", end_color="FFC6EFCE", fill_type="solid"
)
EXPENSE_FILL = PatternFill(
    start_color="FFFFC7CE", end_color="FFFFC7CE", fill_type="solid"
)
WARNING_FILL = PatternFill(
    start_color="FFFFFF00", end_color="FFFFFF00", fill_type="solid"
)
INCOME_FONT = Font(color="FF006100", bold=True)
EXPENSE_FONT = Font(color="FF9C0006", bold=True)
HEADER_FILL = PatternFill(
    start_color="FF1F4E79", end_color="FF1F4E79", fill_type="solid"
)
TOTAL_FILL = PatternFill(
    start_color="FFD9E1F2", end_color="FFD9E1F2", fill_type="solid"
)
HEADER_FONT = Font(color="FFFFFFFF", bold=True)
THIN_SIDE = Side(style="thin", color="FF000000")
MEDIUM_SIDE = Side(style="medium", color="FF000000")
THIN_BORDER = Border(
    left=THIN_SIDE,
    right=THIN_SIDE,
    top=THIN_SIDE,
    bottom=THIN_SIDE,
)
TOTAL_BORDER = Border(
    left=MEDIUM_SIDE,
    right=MEDIUM_SIDE,
    top=MEDIUM_SIDE,
    bottom=MEDIUM_SIDE,
)
HEADER_ALIGNMENT = Alignment(
    horizontal="center", vertical="center", wrap_text=True
)
TEXT_ALIGNMENT = Alignment(horizontal="left", vertical="top", wrap_text=True)
ACCOUNT_ALIGNMENT = Alignment(horizontal="left", vertical="center")
AMOUNT_ALIGNMENT = Alignment(horizontal="right", vertical="center")
DATE_ALIGNMENT = Alignment(horizontal="left", vertical="center")
DEFAULT_AMOUNT_NUMBER_FORMAT = "#,##0.00"
