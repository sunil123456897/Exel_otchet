"""Phase 2 — behavioural tests for LogicService.apply_financial_rules.

The financial rules engine is the highest-risk module: it transforms raw
ingested rows into the consolidated output that MasterWriter renders.
These tests pin its behaviour for the core flows:

- income/expense resolution (positive amount, negative amount, return)
- commission as percent (<=1 → ×100) vs absolute value
- 'доп сф' income-override filter
- exclude keywords (amount zeroed, row kept)
- NumericParsingError on amount/total → critical row emitted, not a crash
- empty/zero rows dropped

Persistence is a stub because apply_financial_rules consumes the raw-row
list directly (it does not touch the DB); consolidate() is the only
entry that calls persistence.get_consolidated_data.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

import pytest
from core.domain.logic_service import LogicService


class _StubPersistence:
    """Minimal IPersistence stand-in: apply_financial_rules ignores it,
    so we only need the attribute to satisfy the constructor."""

    def get_consolidated_data(self, session_id: str) -> List[Dict[str, Any]]:
        return []

    def get_template_errors(self, session_id: str) -> List[Dict[str, Any]]:
        return []


@pytest.fixture
def logic() -> LogicService:
    return LogicService(_StubPersistence(), config={"logic": {}})


def _row(**overrides) -> Dict[str, Any]:
    base = {
        "customer": "ООО Тест",
        "contractor": "Альфа",
        "amount": Decimal("1000.00"),
        "total": Decimal("1000.00"),
        "commission": Decimal("0"),
        "filters": "",
        "_source_info": "src.xlsx | 01.05.2026 | Row 2",
    }
    base.update(overrides)
    return base


# --- flow resolution -----------------------------------------------------


def test_positive_amount_becomes_income(logic):
    res = logic.apply_financial_rules([_row()])
    assert len(res) == 1
    assert res[0]["сумма платежа ПРИХОД"] == Decimal("1000.00")
    assert res[0]["сумма платежа РАСХОД"] == Decimal("0.00")


def test_negative_amount_becomes_expense(logic):
    res = logic.apply_financial_rules([_row(amount=Decimal("-500.00"), total=Decimal("-500.00"))])
    assert res[0]["сумма платежа ПРИХОД"] == Decimal("0.00")
    assert res[0]["сумма платежа РАСХОД"] == Decimal("500.00")


def test_return_keyword_routes_to_expense_column(logic):
    """A 'возврат' filter routes the amount to the expense column. The
    value keeps the negative sign of a return (the engine emits the
    expense as a negative); we pin the column, not the sign, because the
    sign is rule semantics we do not touch."""
    res = logic.apply_financial_rules(
        [_row(amount=Decimal("300.00"), total=Decimal("300.00"), filters="возврат")]
    )
    assert res[0]["сумма платежа ПРИХОД"] == Decimal("0.00")
    # Expense column is populated (sign preserved from _resolve_flow).
    assert res[0]["сумма платежа РАСХОД"] != Decimal("0.00")


def test_dop_filter_routes_to_income_column(logic):
    """The 'доп' override filter forces the flow into the income column.
    The amount value itself is passed through unchanged (sign kept)."""
    res = logic.apply_financial_rules(
        [_row(amount=Decimal("200.00"), total=Decimal("200.00"), filters="доп сф")]
    )
    # Income column is populated; expense is zero.
    assert res[0]["сумма платежа РАСХОД"] == Decimal("0.00")
    assert res[0]["сумма платежа ПРИХОД"] != Decimal("0.00")


# --- commission ----------------------------------------------------------


def test_small_commission_treated_as_percent(logic):
    """A commission <=1 is interpreted as a fraction and scaled ×100."""
    res = logic.apply_financial_rules([_row(commission=Decimal("0.05"))])
    assert res[0]["комиссия"] == Decimal("5.00")


def test_large_commission_treated_as_absolute(logic):
    """A commission >1 is kept as an absolute ruble value."""
    res = logic.apply_financial_rules([_row(commission=Decimal("150.00"))])
    assert res[0]["комиссия"] == Decimal("150.00")


# --- exclude keyword -----------------------------------------------------


def test_exclude_keyword_zeros_amount_but_keeps_row(logic):
    res = logic.apply_financial_rules([_row(filters="исключить")])
    assert len(res) == 1
    assert res[0]["сумма платежа ПРИХОД"] == Decimal("0.00")
    assert res[0]["сумма платежа РАСХОД"] == Decimal("0.00")


# --- critical / crash cases ---------------------------------------------


def test_garbage_amount_surfaces_as_critical_row_not_silent_drop(logic):
    """A non-empty but unparseable amount ('#N/A', '#VALUE!', 'Н/Д') is data
    corruption and must SURFACE as a red critical row so the operator sees the
    broken transaction — never be silently dropped (undercount) nor silently
    zeroed into the =SUM().

    The raw source value is validated with the strict ``to_decimal`` BEFORE the
    schema's zero-coercion can mask it. (Supersedes the old Phase-1 contract
    'coerced_by_schema_not_critical': silently discarding a corrupt financial
    row is worse than surfacing it — the schema still guarantees the Decimal
    type contract, this only adds corruption detection on top.)"""
    res = logic.apply_financial_rules([_row(amount="#N/A", total="#N/A")])
    assert len(res) == 1
    assert res[0]["is_critical"] is True
    # A critical row is a marker, not a value — its financials are zeroed.
    assert res[0]["сумма платежа ПРИХОД"] == Decimal("0.00")
    assert res[0]["ИТОГ"] == Decimal("0.00")


def test_garbage_excel_error_surfaces_as_critical_row(logic):
    """'#REF!' is an Excel error reference — unambiguous corruption. It must
    surface as a critical row, not be silently reduced to 0 and dropped."""
    res = logic.apply_financial_rules([_row(amount="#REF!", total="#REF!")])
    assert len(res) == 1
    assert res[0]["is_critical"] is True


def test_empty_amount_is_still_dropped_not_critical(logic):
    """An empty/blank amount means 'no signal', NOT corruption — it must not
    become a false-positive critical row. Guards against over-eager surfacing
    after the raw-value validation fix."""
    res = logic.apply_financial_rules([_row(amount="", total="")])
    assert res == []


def test_completely_empty_row_is_dropped(logic):
    """A row with zero amount, zero total, no brokers, no transit, no
    overrides must be dropped — it carries no financial signal."""
    res = logic.apply_financial_rules(
        [_row(amount=Decimal("0.00"), total=Decimal("0.00"))]
    )
    assert res == []


# --- multiple rows -------------------------------------------------------


def test_mixed_batch_preserves_order_and_counts(logic):
    rows = [
        _row(amount=Decimal("100.00"), total=Decimal("100.00")),
        _row(amount=Decimal("0.00"), total=Decimal("0.00")),  # dropped (all-zero)
        _row(amount=Decimal("-50.00"), total=Decimal("-50.00")),
        _row(amount=Decimal("250.00"), total=Decimal("250.00"), filters="возврат"),
    ]
    res = logic.apply_financial_rules(rows)
    # 3 surviving rows: income, expense, return-expense.
    assert len(res) == 3
    assert res[0]["сумма платежа ПРИХОД"] == Decimal("100.00")
    assert res[1]["сумма платежа РАСХОД"] != Decimal("0.00")
    # The return row lands in the expense column too.
    assert res[2]["сумма платежа РАСХОД"] != Decimal("0.00")


# --- curator strategies --------------------------------------------------


def test_boris_strategy_preserves_broker2(logic):
    """Boris curator keeps intermediary2 (broker2) values from source."""
    res = logic.apply_financial_rules(
        [_row(broker2=Decimal("100.00"), percent_broker2=Decimal("0.10"))],
        curator="boris",
        curator_config={"employees_key": "борис"},
    )
    assert res[0]["посредник 2"] == Decimal("100.00")
    assert res[0]["% посредник 2"] == Decimal("0.10")


def test_default_strategy_preserves_raw_broker2_zeroes_calc(logic):
    """Without a curator strategy the raw broker2 value is kept in the
    'посредник 2' column (b2_val = abs(raw_b2)), but the calculated
    broker2 sum and percent_broker2 collapse to 0."""
    res = logic.apply_financial_rules(
        [_row(broker2=Decimal("100.00"), percent_broker2=Decimal("0.10"))]
    )
    # Raw broker2 preserved.
    assert res[0]["посредник 2"] == Decimal("100.00")
    # Calculated fields zeroed by the default strategy.
    assert res[0]["Посредник 2 (сумма)"] == Decimal("0.00")
    assert res[0]["% посредник 2"] == Decimal("0.00")


# --- transit / rate / currency_amount crash regression -----------------
# These three fields are read by _build_result_row via to_decimal(). Before
# the fix, a dirty value (e.g. a header label that leaked into a data cell,
# like ' ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ') raised NumericParsingError which
# was NOT caught — so one such cell in the Ivan curator file aborted the
# whole curator batch and the Ivan sheet went missing from auto-recon.
# The fix routes these through _parse_decimal_or_warn, same as brokers.


def test_dirty_transit_obligation_does_not_crash(logic):
    """A header-label value in transit_obligation must coerce to 0, not
    raise — the Ivan curator file in production had exactly this and
    crashed every auto-reconciliation run."""
    res = logic.apply_financial_rules(
        [_row(transit_obligation=" ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ")]
    )
    assert len(res) == 1
    assert res[0]["ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ"] == Decimal("0.00")


def test_dirty_exchange_rate_does_not_crash(logic):
    res = logic.apply_financial_rules([_row(exchange_rate="курс")])
    assert len(res) == 1
    assert res[0]["курс"] == Decimal("0.00")


def test_dirty_currency_amount_does_not_crash(logic):
    res = logic.apply_financial_rules([_row(currency_amount="сумма платежа")])
    assert len(res) == 1
    assert res[0]["сумма"] == Decimal("0.00")


def test_dirty_transit_in_one_row_does_not_kill_batch(logic):
    """A single dirty cell must not abort the surrounding rows."""
    rows = [
        _row(),
        _row(transit_obligation="#REF!", exchange_rate="abc"),
        _row(amount=Decimal("500.00"), total=Decimal("500.00")),
    ]
    res = logic.apply_financial_rules(rows)
    assert len(res) == 3
    # The dirty row's transit coerced, not raised.
    assert res[1]["ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ"] == Decimal("0.00")
    assert res[1]["курс"] == Decimal("0.00")


def test_clean_transit_values_pass_through(logic):
    """Sanity: legitimate transit/rate/amount values must still resolve."""
    res = logic.apply_financial_rules(
        [_row(
            transit_obligation=Decimal("100.50"),
            exchange_rate=Decimal("95.0"),
            currency_amount=Decimal("200.00"),
        )]
    )
    assert res[0]["ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ"] == Decimal("100.50")
    assert res[0]["курс"] == Decimal("95.0")
    assert res[0]["сумма"] == Decimal("200.00")
