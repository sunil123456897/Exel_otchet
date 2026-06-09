"""Regression: _is_math_error must trust the curator's total when commission != 0.

In commit dce35bd (2026-04-23, "feat/docs: final sync and index update"),
the _is_math_error function in core/infra/export_formatting.py was
tightened to also verify that ``total == income - expense - commission``
whenever commission is non-zero. In practice, curators often write
commission as a small rate (e.g. 8.5 meaning 8.5 %) and pre-compute the
total as ``expense * (1 - rate/100)``. The strict check flagged these
valid rows as math errors and painted 75 % of the report yellow.

The previous behavior — trust the curator's total whenever commission is
non-zero, and only check the math when commission is missing — was the
intended behavior and is restored in commit
``fix-math-error-trust-commission``.

This test pins the restored behavior across the realistic production
shapes.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "APP"
sys.path.insert(0, str(APP_DIR))

from core.infra.export_formatting import _is_math_error  # noqa: E402


def test_curator_rate_8_5_percent_is_not_math_error():
    """Real production row: expense=4_003_526, commission=8.5 (rate),
    total=-3_663_226.29 (curator's pre-computed expense * 0.915).
    The strict check that lived in dce35bd flagged this as a math
    error and turned 75 % of the report yellow.
    """
    result = _is_math_error(
        is_return=False,
        income=0,
        expense=4_003_526,
        total=-3_663_226.29,
        commission=8.5,
    )
    assert result is False, (
        "Row with curator rate (8.5 = 8.5 %) and pre-computed total "
        "was incorrectly flagged as a math error."
    )


def test_curator_rate_5_percent_is_not_math_error():
    """Another production shape: income=1_000_000, commission=5 (rate),
    total=950_000 (curator's pre-computed income * 0.95)."""
    result = _is_math_error(
        is_return=False,
        income=1_000_000,
        expense=0,
        total=950_000,
        commission=5,
    )
    assert result is False, (
        "Row with curator rate (5 = 5 %) and pre-computed total "
        "must not be flagged."
    )


def test_forgot_total_with_money_is_math_error():
    """Total is zero but money exists — classic 'forgot to fill total'."""
    assert (
        _is_math_error(
            is_return=False, income=100, expense=0, total=0, commission=0
        )
        is True
    )


def test_forgot_commission_with_mismatch_is_math_error():
    """Commission is zero and total doesn't match income - expense —
    the only case where the math check is allowed to fire."""
    assert (
        _is_math_error(
            is_return=False, income=100, expense=0, total=500, commission=0
        )
        is True
    )


def test_total_only_with_no_money_is_math_error():
    """No income / no expense but total has a value — anomalous row."""
    assert (
        _is_math_error(
            is_return=False, income=0, expense=0, total=100, commission=0
        )
        is True
    )


def test_return_row_is_never_math_error():
    """Return rows are exempt from math checks regardless of values."""
    assert (
        _is_math_error(
            is_return=True, income=0, expense=100, total=-100, commission=0
        )
        is False
    )
