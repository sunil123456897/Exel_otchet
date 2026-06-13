"""Reconciliation report package — decomposed from reconciliation_report.py.

Layout:
    _types.py   — data classes (MasterReconciliationRow, RschReconciliationRow, ReconciliationRow)
    _utils.py   — pure utility functions, constants, _to_decimal, _excel_safe_text
    _resolve.py — date/sheet resolution, executor/customer matching
    _collect.py — reading from Excel: _collect_master_rows, _collect_rsch_rows
    _build.py   — writing to Excel: _build_workbook, build_reconciliation_report, build_combined
"""

from ._types import (
    MasterReconciliationRow,
    RschReconciliationRow,
    ReconciliationRow,
)
from ._utils import _row_id

from ._build import (
    build_reconciliation_report,
    build_combined_reconciliation_report,
)

__all__ = [
    "MasterReconciliationRow",
    "RschReconciliationRow",
    "ReconciliationRow",
    "_row_id",
    "build_reconciliation_report",
    "build_combined_reconciliation_report",
]
