from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional


@dataclass(frozen=True)
class MasterReconciliationRow:
    values: list[Any]
    source: Any
    source_link: str | None
    customer: str
    executor: str
    income: Decimal
    expense: Decimal


@dataclass(frozen=True)
class RschReconciliationRow:
    row_id: str
    executor: str
    customer: str
    contractor: str
    comment: str
    income: Decimal
    expense: Decimal
    source_link: str | None


@dataclass(frozen=True)
class ReconciliationRow:
    master: Optional[MasterReconciliationRow]
    rsch: Optional[RschReconciliationRow]
    status: str
    reason: str = ""
