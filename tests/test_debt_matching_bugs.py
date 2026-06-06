import pytest
import sys
import os
from decimal import Decimal
from openpyxl import Workbook

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'APP'))

from core.infra.reconciliation_report import (
    MasterReconciliationRow,
    RschReconciliationRow,
    ReconciliationRow,
    _build_reconciliation_rows,
    _executor_matches,
    _common_sheet_dates,
    STATUS_ERROR,
    STATUS_REVIEW,
    STATUS_VERIFIED,
    REASON_NO_RSCH,
    REASON_NO_CURATOR,
)
from datetime import date

def create_master_row(executor: str, customer: str, income: str = "0", expense: str = "0") -> MasterReconciliationRow:
    return MasterReconciliationRow(
        values=[],
        source="Test Source",
        source_link=None,
        customer=customer,
        executor=executor,
        income=Decimal(income),
        expense=Decimal(expense),
    )

def create_rsch_row(executor: str, customer: str, income: str = "0", expense: str = "0", row_id: str = "1") -> RschReconciliationRow:
    return RschReconciliationRow(
        row_id=row_id,
        executor=executor,
        customer=customer,
        contractor="",
        comment="",
        income=Decimal(income),
        expense=Decimal(expense),
        source_link=None,
    )

def test_negative_debt_return_signs():
    # Master has expense=-500, RSCH has income=500
    master_rows = [create_master_row("Исполнитель", "Заказчик", expense="-500")]
    rsch_rows = [create_rsch_row("Исполнитель", "Заказчик", income="500")]
    
    result = _build_reconciliation_rows(master_rows, rsch_rows)
    
    # Expected behavior: A negative expense (-500) should be conceptually matched to a positive income (500).
    # The test will fail because the buggy system just compares income to income and expense to expense.
    for r in result:
        assert r.status == STATUS_VERIFIED, f"Negative debt return signs failed to reconcile correctly: {r.reason}"

def test_subset_heuristic_false_positive():
    # Expected behavior: "ООО" is too generic and should NOT match "ООО Ромашка" as the same executor.
    # The test will fail because the subset heuristic bug incorrectly returns True.
    assert _executor_matches("ООО", "ООО Ромашка") is False, "Subset heuristic incorrectly matched ООО with ООО Ромашка"
