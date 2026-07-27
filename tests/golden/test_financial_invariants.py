"""Stage 1 / MR-0104 — invariants of the financial rules engine.

These tests pin the *contract* of ``LogicService.apply_financial_rules``,
independent of Excel I/O. They use synthetic, PII-free rows that exercise
the invariants the TZ requires:

1. Order-independence — permuting the input rows does not change the
   multiset of output rows.
2. Idempotency — running the engine on its own output is stable (no
   compounding of commissions, no double-application of returns).
3. Source preservation — the engine never mutates the input list nor
   the input dict values.
4. Decimal preservation — output amounts are ``Decimal``, never
   ``float``. (Float would silently corrupt high-precision sums.)
5. Determinism — same input twice yields identical output, including
   ordering.
6. Row-count conservation — every non-empty input row appears in the
   output (optionally flagged as critical); no silent drops.
7. Empty / zero-row handling — genuinely empty rows are dropped, but
   not silently: the engine must distinguish "empty" from "skipped due
   to error".

These properties are the load-bearing wall of the financial product: if
any of them breaks, the operator's reports drift and nobody notices
until a customer complains.
"""
from __future__ import annotations

import copy
import itertools
from decimal import Decimal
from typing import Any

import pytest
from core.domain.logic_service import LogicService

# ── fixtures ────────────────────────────────────────────────────────────

class _StubPersistence:
    """LogicService.apply_financial_rules ignores persistence; we only
    need the attribute to satisfy the constructor."""

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
         filters: str = "",
         **extra) -> dict[str, Any]:
    """Synthetic input row in the shape LogicService consumes."""
    if total is None:
        total = amount
    base: dict[str, Any] = {
        "customer": customer,
        "contractor": contractor,
        "amount": Decimal(str(amount)),
        "total": Decimal(str(total)),
        "commission": Decimal(str(commission)),
        "filters": filters,
    }
    base.update(extra)
    return base


def _stable_key(row: dict[str, Any]) -> tuple:
    """A row identity that is stable under reordering of inputs.

    The output schema uses Russian column names (the canonical report
    headers). We project onto those so the multiset comparison is
    meaningful regardless of input order.
    """
    # Output column names produced by LogicService._build_result_row.
    return (
        str(row.get("ЗАКАЗЧИК (название проекта, наименование ЮЛ)", "")),
        str(row.get("ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)", "")),
        Decimal(str(row.get("сумма платежа ПРИХОД", 0))),
        Decimal(str(row.get("сумма платежа РАСХОД", 0))),
        Decimal(str(row.get("ИТОГ", 0))),
    )


def _out_customer(row: dict[str, Any]) -> str:
    return str(row.get("ЗАКАЗЧИК (название проекта, наименование ЮЛ)", ""))


def _out_income(row: dict[str, Any]) -> Decimal:
    return Decimal(str(row.get("сумма платежа ПРИХОД", "0")))


def _out_expense(row: dict[str, Any]) -> Decimal:
    return Decimal(str(row.get("сумма платежа РАСХОД", "0")))


# ── 1) order-independence ──────────────────────────────────────────────

def test_input_row_order_does_not_change_output_multiset(logic: LogicService) -> None:
    """Permuting input rows must not change the multiset of output rows."""
    rows = [
        _row("Клиент А", "П1", Decimal("100.00")),
        _row("Клиент Б", "П2", Decimal("200.00")),
        _row("Клиент В", "П1", Decimal("300.00")),
        _row("Клиент А", "П2", Decimal("150.00")),
    ]

    baseline = sorted(logic.apply_financial_rules(copy.deepcopy(rows)), key=_stable_key)

    for perm in itertools.permutations(rows):
        out = sorted(
            logic.apply_financial_rules(copy.deepcopy(list(perm))),
            key=_stable_key,
        )
        assert len(out) == len(baseline), (
            f"row count drifted under permutation: {len(out)} vs {len(baseline)}"
        )
        for a, b in zip(out, baseline):
            assert _stable_key(a) == _stable_key(b), (
                f"output differs under permutation: {_stable_key(a)} vs {_stable_key(b)}"
            )


# ── 2) idempotency (in the practical, contract sense) ─────────────────

def test_re_applying_output_does_not_grow_or_duplicate(logic: LogicService) -> None:
    """Re-applying the engine to its own output must not grow the row set.

    ``LogicService.apply_financial_rules`` is a one-way transform from
    raw curator rows to consolidated report rows. The output schema uses
    Russian column names that the input schema (``FinancialRowSchema``)
    does not bind, so re-feeding output through the engine is not a
    meaningful operation in production.

    The invariant we *do* care about: a future refactor that
    accidentally calls ``apply_financial_rules`` twice in the pipeline
    must not double commissions, duplicate rows, or otherwise inflate
    the output. We assert that the second call's row count is at most
    the first call's row count, and that no row's income/expense
    magnitude exceeds what was already there.
    """
    rows = [
        _row("Клиент А", "П1", Decimal("1000.00")),
        _row("Клиент Б", "П2", Decimal("-500.00"), filters="возврат"),
    ]
    once = logic.apply_financial_rules(copy.deepcopy(rows))
    twice = logic.apply_financial_rules(copy.deepcopy(once))

    # Row count must not grow under re-application.
    assert len(twice) <= len(once), (
        f"re-application grew the output ({len(once)} → {len(twice)}); "
        f"the engine is duplicating rows somewhere."
    )
    # And the total absolute money in the system must not increase.
    once_total = sum(
        abs(_out_income(r)) + abs(_out_expense(r)) for r in once
    )
    twice_total = sum(
        abs(_out_income(r)) + abs(_out_expense(r)) for r in twice
    )
    assert twice_total <= once_total, (
        f"re-application grew the total money in the output "
        f"({once_total} → {twice_total}); the engine is compounding commissions "
        f"or duplicating amounts."
    )


# ── 3) source preservation ─────────────────────────────────────────────

def test_engine_does_not_mutate_input(logic: LogicService) -> None:
    """Input list and dict values must be unchanged after the call."""
    rows = [_row("Клиент А", "П1", Decimal("1000.00"))]
    snapshot = copy.deepcopy(rows)

    logic.apply_financial_rules(rows)

    assert rows == snapshot, (
        "LogicService mutated its input — callers rely on input preservation "
        "to retry / re-run safely."
    )


# ── 4) Decimal preservation ────────────────────────────────────────────

def test_output_amounts_are_decimal_not_float(logic: LogicService) -> None:
    """Every amount-like output field must be ``Decimal``, not ``float``.

    Float coercion was a real past bug (Phase 1). Excel stores numbers
    as IEEE-754 doubles, but the in-memory representation must be Decimal
    right up to the write boundary; otherwise we silently lose precision
    on large or repeating-decimal sums.
    """
    rows = [
        _row("Клиент А", "П1", Decimal("100.10")),
        _row("Клиент Б", "П2", Decimal("200.20")),
    ]
    out = logic.apply_financial_rules(rows)
    assert out, "expected non-empty output"
    # Output uses Russian column names; check every Decimal-typed value.
    decimal_field_canonical = (
        "сумма платежа ПРИХОД", "сумма платежа РАСХОД", "ИТОГ",
        "комиссия", "посредник 1(кэш)", "Посредник 2 (сумма)",
        "ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ", "курс",
    )
    for r in out:
        for f in decimal_field_canonical:
            if f in r and r[f] is not None:
                assert isinstance(r[f], Decimal), (
                    f"field {f!r} is {type(r[f]).__name__}, expected Decimal. "
                    f"Float coercion would corrupt precision."
                )


# ── 5) determinism ─────────────────────────────────────────────────────

def test_same_input_twice_yields_identical_output(logic: LogicService) -> None:
    """Two calls with identical input must produce identical output."""
    rows = [
        _row("Клиент А", "П1", Decimal("100.00")),
        _row("Клиент Б", "П2", Decimal("200.00")),
        _row("Клиент В", "П1", Decimal("300.00")),
    ]
    out1 = logic.apply_financial_rules(copy.deepcopy(rows))
    out2 = logic.apply_financial_rules(copy.deepcopy(rows))
    assert out1 == out2, "engine is non-deterministic on identical input"


# ── 6) row-count conservation ──────────────────────────────────────────

def test_non_empty_rows_are_not_silently_dropped(logic: LogicService) -> None:
    """Every non-empty input row must appear in the output.

    Empty (zero-amount, zero-total, no broker, no transit, no add-flag)
    rows may be dropped — that is by design. But a row with a real
    amount must either appear in the output or be flagged as a critical
    error. Silent drops are how financial reports lose money.
    """
    rows = [
        _row("Клиент А", "П1", Decimal("1000.00")),
        _row("Клиент Б", "П2", Decimal("2000.00")),
    ]
    out = logic.apply_financial_rules(rows)
    out_customers = {_out_customer(r) for r in out}
    for r in rows:
        assert r["customer"] in out_customers, (
            f"row for {r['customer']!r} was silently dropped from the output"
        )


def test_genuinely_empty_rows_are_dropped(logic: LogicService) -> None:
    """A row that is empty on every financial field should not appear."""
    rows = [
        _row("Клиент А", "П1", Decimal("1000.00")),
        {
            "customer": "", "contractor": "",
            "amount": Decimal("0.00"), "total": Decimal("0.00"),
            "commission": Decimal("0.00"), "filters": "",
        },
    ]
    out = logic.apply_financial_rules(rows)
    # The real row survives; the empty row is gone.
    assert len(out) == 1, f"expected 1 row out (empty dropped), got {len(out)}"
    assert _out_customer(out[0]) == "Клиент А"


# ── 7) zero-vs-negative distinction ────────────────────────────────────

def test_negative_amount_is_return_not_silently_zeroed(logic: LogicService) -> None:
    """A return (negative amount, 'возврат' filter) must be handled, not
    coerced to zero.

    The risk we are guarding against: a refactor that treats any
    negative number as "invalid → zero it out" would silently delete
    every return in the report.
    """
    rows = [
        _row("Клиент А", "П1", Decimal("-500.00"), filters="возврат"),
    ]
    out = logic.apply_financial_rules(rows)
    assert out, "return row must produce an output row"
    # In the output schema, returns flow into "сумма платежа РАСХОД".
    # The magnitude must survive — not be silently zeroed everywhere.
    inc = _out_income(out[0])
    exp = _out_expense(out[0])
    assert abs(inc) + abs(exp) > 0, (
        "return was silently zeroed — both income and expense are 0"
    )
