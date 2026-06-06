"""Property-based tests for Phase 7 invariants.

These tests use hypothesis to verify that the bug-fixes from Phases 1-5
preserve their invariants across a wide range of random inputs.
"""
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from APP.core.domain.utils_helpers import to_decimal_percent
from APP.core.infra.reconciliation_report import (
    _executor_matches,
    _row_amount_matches,
    MasterReconciliationRow,
    RschReconciliationRow,
)


# --- to_decimal_percent invariants ----------------------------------------


@given(
    val=st.one_of(
        st.integers(min_value=-1_000_000, max_value=1_000_000),
        st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
        st.decimals(min_value=-1_000_000, max_value=1_000_000, allow_nan=False, allow_infinity=False, places=4),
    )
)
@settings(max_examples=50, deadline=None)
def test_to_decimal_percent_numeric_never_raises(val):
    """Numeric inputs must always return a Decimal (data integrity invariant)."""
    out = to_decimal_percent(val)
    assert isinstance(out, Decimal), f"Got {type(out).__name__} for {val!r}"


@given(text=st.text(min_size=0, max_size=50).filter(lambda s: not s.replace(".", "").replace("-", "").replace(",", "").replace("%", "").isdigit() or not s))
@settings(max_examples=50, deadline=None)
def test_to_decimal_percent_garbage_never_returns_string(text):
    """Bug fix: garbage inputs must NOT be silently returned as the original string."""
    out = to_decimal_percent(text)
    assert isinstance(out, Decimal), f"String {text!r} leaked through as {type(out).__name__}"


# --- _executor_matches invariants ------------------------------------------


@given(text=st.text(min_size=4, max_size=30, alphabet=st.characters(whitelist_categories=("Lu", "Ll"), whitelist_characters=" ")))
@settings(max_examples=30, deadline=None)
def test_executor_matches_substring_only_when_subset(text):
    """`issubset` heuristic should not match single short tokens against multi-word names.

    Invariant: a single short token (e.g. "ООО") MUST NOT match a longer
    multi-word name (e.g. "ООО Ромашка") purely by token subset.
    """
    short = "ООО"
    long = f"ООО {text.strip()}" if text.strip() else "ООО"
    if not long.replace("ООО", "", 1).strip():
        return
    assert _executor_matches(short, long) is False, (
        f"Sub-token '{short}' incorrectly matched '{long}'"
    )


# --- _row_amount_matches return-sign invariants ----------------------------


def make_master(expense: Decimal) -> MasterReconciliationRow:
    return MasterReconciliationRow(
        values=[],
        source="Test",
        source_link=None,
        customer="",
        executor="",
        income=Decimal("0"),
        expense=expense,
    )


def make_rsch(income: Decimal) -> RschReconciliationRow:
    return RschReconciliationRow(
        row_id="1",
        executor="",
        customer="",
        contractor="",
        comment="",
        income=income,
        expense=Decimal("0"),
        source_link=None,
    )


@given(amount=st.decimals(min_value=1, max_value=1_000_000, places=2, allow_nan=False, allow_infinity=False))
@settings(max_examples=30, deadline=None)
def test_row_amount_matches_negative_debt_signs(amount):
    """Bug fix: negative debt (-X) on master expense must match positive X on rsch income."""
    master = make_master(-amount)
    rsch = make_rsch(amount)
    assert _row_amount_matches(master, rsch) is True, (
        f"Negative debt {amount} on master expense did not match positive {amount} on rsch income"
    )
