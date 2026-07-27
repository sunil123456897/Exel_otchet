"""Phase 1 — financial accuracy: schema validator never leaks raw strings.

Regression for the Decimal contract bug in FinancialRowSchema.to_decimal.
The validator is shared across all numeric fields (amount, income,
expense, total, commission, broker1/2, transit, rates). Two code paths
used to ``return v`` on an unparseable value, leaking the raw string
into Decimal-typed fields. Downstream code (LogicService) then received
a str where it expected Decimal, and to_decimal() had to paper over the
mismatch silently. The fix makes every unparseable path return
Decimal("0.00") — downstream stays typed, and Any-typed fields
(percent_broker/percent_broker2) are unaffected because their consumers
already coerce any input.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from core.domain.data_schemas import FinancialRowSchema

# --- Decimal fields must never hold a raw string -------------------------


DECIMAL_FIELDS = [
    "amount",
    "income",
    "expense",
    "total",
    "transit_obligation",
    "commission",
    "broker1",
    "broker2",
    "exchange_rate",
    "currency_amount",
]


@pytest.mark.parametrize("field", DECIMAL_FIELDS)
def test_validator_returns_decimal_for_text_input(field):
    """A text value (e.g. 'high') must coerce to Decimal, never leak as str."""
    row = FinancialRowSchema(**{field: "high"})
    value = getattr(row, field)
    assert isinstance(value, Decimal), (
        f"{field} leaked a {type(value).__name__} for text input"
    )


@pytest.mark.parametrize("field", DECIMAL_FIELDS)
def test_validator_returns_decimal_for_garbage_input(field):
    """Random garbage must coerce to Decimal, never leak as str."""
    row = FinancialRowSchema(**{field: "#REF!"})
    value = getattr(row, field)
    assert isinstance(value, Decimal)


@pytest.mark.parametrize("field", DECIMAL_FIELDS)
def test_validator_returns_decimal_for_numeric_string(field):
    """Legit numeric strings must parse to the expected Decimal."""
    row = FinancialRowSchema(**{field: "1 234,56"})
    assert getattr(row, field) == Decimal("1234.56")


@pytest.mark.parametrize("field", DECIMAL_FIELDS)
def test_validator_returns_zero_for_empty_and_none(field):
    assert getattr(FinancialRowSchema(**{field: None}), field) == Decimal("0.00")
    assert getattr(FinancialRowSchema(**{field: ""}), field) == Decimal("0.00")


@pytest.mark.parametrize("field", DECIMAL_FIELDS)
def test_validator_preserves_existing_decimal(field):
    """A real Decimal must pass through unchanged."""
    d = Decimal("999.99")
    assert getattr(FinancialRowSchema(**{field: d}), field) == d


def test_text_percent_broker_coerces_to_decimal():
    """percent_broker is Any-typed but must still not leak a raw str —
    the validator now returns Decimal for unparseable input, and
    downstream to_decimal_percent handles it."""
    row = FinancialRowSchema(percent_broker="low")
    # Either Decimal (new behaviour) is acceptable; raw str is not.
    assert isinstance(row.percent_broker, Decimal)


def test_numeric_percent_broker_preserved():
    row = FinancialRowSchema(percent_broker="5.5")
    assert row.percent_broker == Decimal("5.5")


def test_amount_text_yields_zero_decimal():
    """The original bug: 'high' in amount returned the raw string."""
    row = FinancialRowSchema(amount="high")
    assert row.amount == Decimal("0.00")
    assert isinstance(row.amount, Decimal)


def test_full_row_with_mixed_garbage_stays_typed():
    """A realistic row where one field is garbage: every Decimal field
    must remain a Decimal instance."""
    row = FinancialRowSchema(
        amount="100.00",
        income="мусор",
        expense="50",
        total="",
        commission=None,
    )
    for field in ("amount", "income", "expense", "total", "commission"):
        assert isinstance(getattr(row, field), Decimal), field
    assert row.amount == Decimal("100.00")
    assert row.income == Decimal("0.00")
    assert row.expense == Decimal("50")
    assert row.total == Decimal("0.00")
    assert row.commission == Decimal("0.00")
