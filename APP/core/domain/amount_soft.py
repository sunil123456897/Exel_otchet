"""Fail-soft amount parsing with a ``data_loss.log`` audit trail.

Deliberately split from ``utils_helpers``: the L2 updater smoke copies a
*subset* of ``core/domain`` modules into the staged version, and
``logic_service`` must keep importing only light dependencies.
``to_decimal_soft`` pulls in ``data_loss_log`` (→ ``path_scrub``), so it
lives in its own module that nothing in the smoke's import chain touches.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

from core.domain.data_loss_log import record_loss
from core.domain.utils_helpers import to_decimal_lenient


def to_decimal_soft(
    value: Any,
    *,
    error_label: str,
    source: str,
    kind: str,
    reason: str,
    sheet: str | None = None,
    row_index: int | None = None,
    field: str | None = None,
) -> Decimal:
    """Fail-soft amount parsing with a ``data_loss.log`` audit trail.

    Calls :func:`core.domain.utils_helpers.to_decimal_lenient`; on an
    unparseable cell it records the loss (same JSON shape as the
    RSCh/reconciliation collectors) and returns ``Decimal("0")`` so one
    dirty amount never aborts a whole sheet.
    """
    try:
        return cast(Decimal, to_decimal_lenient(value, error_label=error_label))
    except (ValueError, ArithmeticError):
        record_loss(
            source=source,
            kind=kind,
            reason=reason,
            row_index=row_index,
            sheet=sheet,
            field=field,
            original_value=value,
        )
        return Decimal("0")
