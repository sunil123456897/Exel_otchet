"""Pure-expense customer label ("расход") with empty contractor and comment
must not flag a row as a problem when a sum is present.

Customer report: rows where заказчик = "расход" with пустой контрагент and
пустой комментарий were highlighted yellow even though there is nothing to
fill in — such rows represent an internal cash withdrawal / transfer that
legitimately has only a Расход value.

Mirrors the special-marker exemption (% по выплате, комиссия, ...) but for
a different business case: the заказчик field is a pure-expense label. Like
the special-marker exemption it requires a non-zero sum (a label with no
sum is still flagged). Case- and space-insensitive via _normalize_text.
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "APP"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from core.infra.rsch._format import _is_problem_row  # noqa: E402


def _row(customer="", contractor="", comment="", income="0", expense="0",
         account="", executor="ХАНДЕ"):
    return {
        "executor": executor, "customer": customer, "contractor": contractor,
        "comment": comment, "account": account,
        "income": Decimal(income), "expense": Decimal(expense),
    }


@pytest.mark.parametrize("label", ["расход", "Расход", "РАСХОД", "  расход  "])
def test_expense_label_with_empty_fields_and_sum_not_highlighted(label):
    """Row with заказчик = "расход", empty contractor/comment and a sum
    must NOT be a problem row."""
    row = _row(customer=label, expense="500.00")
    assert _is_problem_row(row) is False, (
        f"row with customer={label!r}, empty contractor/comment, expense=500 "
        "highlighted as problem"
    )


def test_expense_label_with_income_also_not_highlighted():
    """Income side also exempts (sum is a sum regardless of direction)."""
    row = _row(customer="расход", income="1000.00")
    assert _is_problem_row(row) is False


def test_expense_label_with_contractor_still_problem():
    """Regression guard: if a contractor IS present it is not a pure-expense
    row — the exemption does not apply."""
    row = _row(customer="расход", contractor="ООО Ромашка", expense="500.00")
    assert _is_problem_row(row) is True


def test_expense_label_with_comment_still_problem():
    """Regression guard: a non-empty comment disqualifies the exemption."""
    row = _row(customer="расход", comment="примечание", expense="500.00")
    assert _is_problem_row(row) is True


def test_expense_label_without_sum_still_problem():
    """A pure-expense label with NO sum is still flagged — the exemption
    requires a non-zero sum, matching the special-marker behaviour."""
    row = _row(customer="расход")  # income=0, expense=0
    assert _is_problem_row(row) is True


def test_normal_customer_without_contractor_still_problem():
    """Regression guard: an ordinary customer without contractor/account
    is still flagged so we don't silence real problems."""
    row = _row(customer="ООО Ромашка", expense="500.00")
    assert _is_problem_row(row) is True
