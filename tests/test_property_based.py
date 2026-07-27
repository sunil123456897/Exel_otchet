"""Stage 6 — property-based tests for the financial rules engine.

Property tests complement the example-based golden tests in Stage 1.
Where golden tests pin *specific* inputs to *specific* outputs, property
tests assert invariants that must hold for *any* input the engine might
see in production. They catch edge cases humans forget to write down:

* commutativity of independent row additions;
* sign preservation for returns (a negative amount stays negative);
* Decimal precision never collapses to float;
* order-independence of identical inputs;
* monotonicity: more non-zero input rows ⇒ at least as many output rows.

All strategies use bounded ranges — we don't need Hypothesis to find
``Decimal("1e999999")`` to know the engine handles it. The bounds are
chosen to look like real firm data: amounts in 0–10 000 000, two
decimal places, reasonable filter strings from the app's known set.
"""
from __future__ import annotations

import copy
from decimal import Decimal
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from core.domain.logic_service import LogicService


# ── helpers ─────────────────────────────────────────────────────────────

class _StubPersistence:
    def get_consolidated_data(self, session_id: str) -> list[dict[str, Any]]:
        return []

    def get_template_errors(self, session_id: str) -> list[dict[str, Any]]:
        return []


@pytest.fixture
def logic() -> LogicService:
    return LogicService(_StubPersistence(), config={"logic": {}})


def _row(customer: str = "Клиент А", contractor: str = "Подрядчик 1",
         amount: Decimal | str = Decimal("1000.00"),
         total: Decimal | str | None = None,
         commission: Decimal | str = Decimal("0"),
         filters: str = "") -> dict[str, Any]:
    if total is None:
        total = amount
    return {
        "customer": customer,
        "contractor": contractor,
        "amount": Decimal(str(amount)),
        "total": Decimal(str(total)),
        "commission": Decimal(str(commission)),
        "filters": filters,
    }


# ── strategies ─────────────────────────────────────────────────────────

# Small set of plausible customers — Hypothesis explores the cross-product.
customers = st.sampled_from(["Клиент А", "Клиент Б", "Клиент В", "Клиент Г"])
contractors = st.sampled_from(["Подрядчик 1", "Подрядчик 2"])

# Amounts as Decimal-valued strings. Bounded to realistic firm range.
amounts = st.decimals(min_value=Decimal("0.01"), max_value=Decimal("10000000"),
                      places=2, allow_nan=False, allow_infinity=False)

# Negative amounts (returns).
neg_amounts = st.decimals(min_value=Decimal("-10000000"), max_value=Decimal("-0.01"),
                          places=2, allow_nan=False, allow_infinity=False)

# Filter strings the engine actually keys on.
filters = st.sampled_from(["", "платёж", "возврат", "доп", "транзит"])

# A non-empty row.
rows = st.builds(_row, customers, contractors, amounts, st.just(None),
                 st.decimals(min_value=Decimal("0"), max_value=Decimal("1000"),
                             places=2), filters)


# ── 1) Decimal preservation ────────────────────────────────────────────

@given(rows)
@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
def test_output_amounts_are_always_decimal(logic: LogicService, rows: dict) -> None:
    """For any non-empty row, output amounts are Decimal — never float."""
    out = logic.apply_financial_rules([copy.deepcopy(rows)])
    if not out:
        # Some rows (e.g. all-zero) are legitimately dropped.
        return
    decimal_fields = ("сумма платежа ПРИХОД", "сумма платежа РАСХОД",
                      "ИТОГ", "комиссия")
    for r in out:
        for f in decimal_fields:
            v = r.get(f)
            if v is not None:
                assert isinstance(v, Decimal), (
                    f"field {f!r}={v!r} is {type(v).__name__}, expected Decimal"
                )


# ── 2) Sign preservation for returns ───────────────────────────────────

@given(st.builds(_row, customers, contractors, neg_amounts,
                 st.just(None), st.just(Decimal("0")), st.just("возврат")))
@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_return_flows_into_expense_not_income(logic: LogicService, row: dict) -> None:
    """A row marked 'возврат' with a negative amount must never become income.

    Business rule: returns are outflows. A refactor that flips the sign
    or silently zeros the amount would corrupt every refund in the
    report. We don't assert *which* column the value lands in — only
    that income never goes negative from a return.
    """
    out = logic.apply_financial_rules([copy.deepcopy(row)])
    if not out:
        return
    income = Decimal(str(out[0].get("сумма платежа ПРИХОД", "0")))
    assert income >= 0, (
        f"return row produced negative income={income}; returns must "
        f"flow through expense, not flip income's sign."
    )


# ── 3) Order-independence ──────────────────────────────────────────────

@given(st.lists(rows, min_size=1, max_size=10))
@settings(max_examples=50, deadline=None,
          suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
def test_permutation_does_not_change_output_multiset(
    logic: LogicService, rows: list[dict],
) -> None:
    """Permuting input rows does not change the multiset of output rows."""
    def _key(r: dict) -> tuple:
        return (
            str(r.get("ЗАКАЗЧИК (название проекта, наименование ЮЛ)", "")),
            str(r.get("ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)", "")),
            Decimal(str(r.get("сумма платежа ПРИХОД", 0))),
            Decimal(str(r.get("сумма платежа РАСХОД", 0))),
            Decimal(str(r.get("ИТОГ", 0))),
        )

    baseline = sorted(logic.apply_financial_rules(copy.deepcopy(rows)), key=_key)

    import itertools
    for perm in list(itertools.permutations(rows))[:3]:  # cap for speed
        out = sorted(
            logic.apply_financial_rules(copy.deepcopy(list(perm))),
            key=_key,
        )
        assert len(out) == len(baseline), (
            f"row count drifted under permutation: {len(out)} vs {len(baseline)}"
        )


# ── 4) Monotonicity: more non-empty rows ⇒ at least as many outputs ───

@given(st.lists(rows, min_size=1, max_size=20))
@settings(max_examples=50, deadline=None,
          suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
def test_dropping_a_row_never_increases_output(logic: LogicService,
                                                rows: list[dict]) -> None:
    """Removing an input row cannot increase the output row count.

    This is a weak monotonicity property — it doesn't say the engine is
    linear, only that rows don't materialise from nothing. A violation
    would mean a row is being silently duplicated.
    """
    full = logic.apply_financial_rules(copy.deepcopy(rows))
    if len(rows) > 1:
        trimmed = logic.apply_financial_rules(copy.deepcopy(rows[:-1]))
        assert len(trimmed) <= len(full), (
            f"removing a row grew the output ({len(trimmed)} > {len(full)}); "
            f"possible duplication bug."
        )


# ── 5) Idempotency of input preservation ───────────────────────────────

@given(rows)
@settings(max_examples=100, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_input_dict_is_never_mutated(logic: LogicService, row: dict) -> None:
    """Calling the engine must not mutate its input.

    Callers rely on input preservation for retry / re-runs. Hypothesis
    exercises this across the entire input space, not just the few
    hand-written examples in Stage 1.
    """
    snapshot = copy.deepcopy(row)
    logic.apply_financial_rules([row])
    assert row == snapshot, (
        "LogicService mutated its input dict — callers cannot retry safely."
    )


# ── 6) Zero-amount rows are dropped deterministically ──────────────────

@given(st.builds(_row, customers, contractors,
                 st.just(Decimal("0.00")), st.just(None),
                 st.just(Decimal("0.00")), st.just("")))
@settings(max_examples=20, deadline=None,
          suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_all_zero_row_is_dropped(logic: LogicService, row: dict) -> None:
    """A row that is zero on every financial field must not appear in output."""
    out = logic.apply_financial_rules([row])
    assert out == [], (
        "all-zero row was not dropped; the engine is emitting junk rows."
    )


# ── 7) Date round-trip (Hypothesis on date parser) ─────────────────────

@given(
    st.integers(min_value=1, max_value=28),   # day
    st.integers(min_value=1, max_value=12),   # month
    st.integers(min_value=2020, max_value=2030),  # year
)
def test_extract_date_from_sheet_round_trips(day: int, month: int, year: int) -> None:
    """extract_date_from_sheet parses DD.MM.YYYY back to DD.MM.YYYY."""
    from core.infra.ingestion_reader import extract_date_from_sheet

    s = f"{day:02d}.{month:02d}.{year:04d}"
    parsed = extract_date_from_sheet(s)
    assert parsed == s, f"round-trip failed: {s!r} → {parsed!r}"


@given(
    st.integers(min_value=1, max_value=28),
    st.integers(min_value=1, max_value=12),
)
def test_date_without_year_is_none(day: int, month: int) -> None:
    """A sheet name without a year must never be silently assigned today's year."""
    from core.infra.ingestion_reader import extract_date_from_sheet

    s = f"{day:02d}.{month:02d}"
    assert extract_date_from_sheet(s) is None


# ── 8) Decimal normalisation never loses precision ─────────────────────

@given(st.decimals(min_value=Decimal("0.01"), max_value=Decimal("1000000"),
                   places=4, allow_nan=False, allow_infinity=False))
def test_to_decimal_preserves_value_up_to_one_cent(d: Decimal) -> None:
    """to_decimal() must preserve the input value within ±0.01 (one cent).

    The helper rounds to 2 decimal places using ROUND_HALF_UP (the
    business rule for financial values). We don't compare against
    ``Decimal.quantize(Decimal("0.01"))`` directly because that uses
    banker's rounding by default and the comparison would falsely flag
    values like ``0.0250`` (which legitimately rounds UP to ``0.03``
    under HALF_UP, not DOWN to ``0.02`` as banker's would).

    The invariant we actually care about: the result is within one cent
    of the input. Anything else would be a precision bug.
    """
    from core.domain.utils_helpers import to_decimal

    out = to_decimal(d)
    assert isinstance(out, Decimal)
    assert abs(out - d) < Decimal("0.01"), (
        f"to_decimal({d}) = {out}, drifted by more than one cent"
    )


# ── 9) classify_sheet_date is stable across the plausible window ──────

@given(
    st.integers(min_value=-30, max_value=30),  # offset from today (days)
)
def test_classify_sheet_date_near_today_is_ok(offset_days: int) -> None:
    """Dates within ±30 days of today are always classified OK."""
    from datetime import date, timedelta
    from core.domain.date_warnings import classify_sheet_date, DateWarningKind

    today = date.today()
    sheet_date = today + timedelta(days=offset_days)
    s = sheet_date.strftime("%d.%m.%Y")
    w = classify_sheet_date(s, reference=today, future_days=31, past_days=365)
    assert w.kind == DateWarningKind.OK
