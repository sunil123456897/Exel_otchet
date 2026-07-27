"""Special-customer markers (% по выплате, % по депозиту, комиссия, ...)
must not flag a row as a problem when a sum is present.

Customer report: rows where the заказчик/контрагент/комментарий contains
"% по выплате" / "% по депозиту" / "комиссия" / "налог" / "взносы" were
highlighted yellow even though Приход/Расход were filled. These rows
represent fees/taxes that legitimately have no contractor or account —
the customer remembers "алиасы что не подсвечивать" existed before.

Root cause: _is_problem_row checked _is_special_customer_label only for
the missing-contractor branch, but these rows still tripped the
missing-account branch (they have no р/с and the marker is not in
_NO_ACCOUNT_MARKERS). The fix: when any searchable field carries a
special marker AND a sum is present, the row is never a problem.
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


@pytest.mark.parametrize(
    "marker",
    ["% по выплате", "% по депозиту", "комиссия", "налог", "взносы"],
)
def test_special_marker_in_customer_with_sum_not_highlighted(marker):
    """Row with special customer + a sum must NOT be a problem row,
    even without contractor, comment, or account."""
    row = _row(customer=marker, expense="500.00")
    assert _is_problem_row(row) is False, (
        f"row with customer={marker!r} and expense=500 highlighted as problem"
    )


@pytest.mark.parametrize(
    "marker",
    ["% по выплате", "% по депозиту", "комиссия"],
)
def test_special_marker_in_contractor_with_sum_not_highlighted(marker):
    """Marker in the contractor field (not customer) also exempts the row."""
    row = _row(customer="ООО Ромашка", contractor=marker, expense="500.00")
    assert _is_problem_row(row) is False


@pytest.mark.parametrize(
    "marker",
    ["% по выплате", "% по депозиту", "комиссия"],
)
def test_special_marker_in_comment_with_sum_not_highlighted(marker):
    """Marker in the comment field also exempts the row."""
    row = _row(customer="ООО Ромашка", comment=marker, expense="500.00")
    assert _is_problem_row(row) is False


def test_special_marker_with_income_not_highlighted():
    """Income side also exempts."""
    row = _row(customer="% по депозиту", income="1000.00")
    assert _is_problem_row(row) is False


def test_special_marker_without_sum_still_problem():
    """A special marker with NO sum at all is still a problem row —
    the exemption requires a non-zero sum."""
    row = _row(customer="% по выплате")  # income=0, expense=0
    assert _is_problem_row(row) is True


def test_normal_customer_without_contractor_still_problem():
    """Regression guard: ordinary customers without contractor/account
    are still flagged, so we don't silence real problems."""
    row = _row(customer="ООО Ромашка", expense="500.00")
    assert _is_problem_row(row) is True


def test_special_marker_case_and_space_insensitive():
    """Normalization handles spaces and case."""
    row = _row(customer="  %  ПО  ВЫПЛАТЕ  ", expense="500.00")
    assert _is_problem_row(row) is False
