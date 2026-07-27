"""Phase 0 — stability: reconciliation survives dirty amount cells.

Regression for the "one trashy cell aborts the whole sheet" bug. Before
the fix, ``_collect_master_rows``/``_collect_rsch_rows`` called the
strict ``_to_decimal`` which raises ``ValueError`` on garbage like
``"abc"`` or ``"#REF!"``; that exception propagated all the way up and
killed the entire reconciliation report. The fail-soft wrapper must
instead log the loss to ``data_loss.log`` and treat the cell as 0, so
the sheet builds and only the unusable row is dropped.
"""
from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import openpyxl
import pytest
from core.domain.data_loss_log import reset_for_testing
from core.infra.reconciliation._collect import (
    _collect_master_rows,
    _collect_rsch_rows,
    _to_decimal_soft,
)

# --- _to_decimal_soft unit behaviour --------------------------------------


@pytest.fixture(autouse=True)
def _isolate_data_loss_log(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    reset_for_testing()
    yield
    reset_for_testing()


def test_to_decimal_soft_returns_zero_on_garbage():
    """A non-numeric string must not raise; it returns Decimal("0")."""
    assert _to_decimal_soft(
        "not a number",
        sheet="01.05.2026",
        row_index=5,
        field="Приход",
        source="reconciliation:01.05.2026",
    ) == Decimal("0")


def test_to_decimal_soft_logs_loss_on_garbage(tmp_path):
    """The dropped value must be recorded in data_loss.log."""
    _to_decimal_soft(
        "#REF!",
        sheet="01.05.2026",
        row_index=7,
        field="Расход",
        source="reconciliation:01.05.2026",
    )
    log_path = Path(os.getcwd()) / "logs" / "data_loss.log"
    assert log_path.exists()
    payload = json.loads(
        log_path.read_text(encoding="utf-8").splitlines()[-1].split(" ", 1)[1]
    )
    assert payload["kind"] == "reconciliation_amount_parse"
    assert payload["row"] == 7
    assert payload["sheet"] == "01.05.2026"
    assert payload["field"] == "Расход"
    assert payload["value"] == "#REF!"


def test_to_decimal_soft_passes_through_valid_numbers():
    """Valid numeric input must round-trip unchanged."""
    assert _to_decimal_soft(
        "1 234,56",
        sheet="x",
        row_index=1,
        field="Приход",
        source="reconciliation:x",
    ) == Decimal("1234.56")
    assert _to_decimal_soft(
        None,
        sheet="x",
        row_index=1,
        field="Приход",
        source="reconciliation:x",
    ) == Decimal("0")


# --- _collect_master_rows integration ------------------------------------


MASTER_HEADERS = [
    "Источник",
    "ЗАКАЗЧИК",
    "ИСПОЛНИТЕЛЬ",
    "Приход",
    "Расход",
    "Комиссия",
    "ИТОГ",
    "% посредника",
    "посредник 1(кэш)",
    "посредник 2",
]


def _master_sheet(rows: list[list[Any]]) -> openpyxl.Workbook:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "01.05.2026"
    ws.append(MASTER_HEADERS)
    for r in rows:
        ws.append(r)
    return wb


def test_collect_master_rows_survives_garbage_amount():
    """A trashy Приход cell must not abort the whole collection.

    Row 2 has a valid 100/0 amount; row 3 has garbage in Приход but a
    valid Расход. After the fix, collection returns at least the valid
    row, and the garbage row is logged rather than raising.
    """
    wb = _master_sheet(
        [
            ["Иванов", "ООО Ромашка", "Альфа", 100, 0, 0, 100, 0, 0, 0],
            ["Петров", "ООО Плюс", "Сбер", "НЕ ЧИСЛО", 50, 0, 0, 0, 0, 0],
            ["Сидоров", "ООО Минус", "ВТБ", 0, 0, 0, 0, 0, 0, 0],  # all-zero → dropped
        ]
    )
    ws = wb.active

    # Must not raise.
    _headers, rows, excluded = _collect_master_rows(ws)

    # The all-zero row is dropped by the existing filter; the garbage
    # row (50 expense) survives as a real row; the clean row survives.
    assert len(rows) >= 1
    sources = {r.source for r in rows}
    assert "Иванов" in sources
    # The garbage-amount row appears too: expense 50 is valid, income
    # coerced to 0 by the fail-soft wrapper.
    assert "Петров" in sources
    wb.close()


def test_collect_master_rows_logs_garbage_cell(tmp_path):
    wb = _master_sheet(
        [
            ["Петров", "ООО Плюс", "Сбер", "TRASH", 0, 0, 0, 0, 0, 0],
        ]
    )
    ws = wb.active
    _collect_master_rows(ws)
    wb.close()

    log_path = Path(os.getcwd()) / "logs" / "data_loss.log"
    assert log_path.exists()
    payloads = [
        json.loads(line.split(" ", 1)[1])
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    amount_losses = [
        p for p in payloads if p["kind"] == "reconciliation_amount_parse"
    ]
    assert amount_losses, "garbage amount cell was not logged"
    assert any(p["value"] == "TRASH" for p in amount_losses)


# --- _collect_rsch_rows integration --------------------------------------


RSCH_HEADERS = [
    "ИСПОЛНИТЕЛЬ",
    "ЗАКАЗЧИК",
    "Контрагент",
    "Комментарий",
    "Приход",
    "Расход",
]


def _rsch_sheet(rows: list[list[Any]]) -> openpyxl.Workbook:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "01.05.2026"
    ws.append(RSCH_HEADERS)
    for r in rows:
        ws.append(r)
    return wb


def test_collect_rsch_rows_survives_garbage_amount():
    """Same guarantee for the РСЧ side: a trashy cell must not raise."""
    wb = _rsch_sheet(
        [
            ["Альфа", "ООО Ромашка", "Альфа", "оплата", 200, 0],
            ["Сбер", "ООО Плюс", "Сбер", "перевод", "ГРЯНЬ", 0],
        ]
    )
    ws = wb.active
    rows = _collect_rsch_rows(ws)
    # Clean row survives; the garbage-income row had both amounts zero
    # (income coerced to 0, expense was 0) → dropped by the filter.
    assert any(r.customer == "ООО Ромашка" for r in rows)
    wb.close()


def test_collect_rsch_rows_logs_garbage_cell(tmp_path):
    wb = _rsch_sheet(
        [
            ["Сбер", "ООО Плюс", "Сбер", "коммент", "ОШИБКА", 30],
        ]
    )
    ws = wb.active
    _collect_rsch_rows(ws)
    wb.close()

    log_path = Path(os.getcwd()) / "logs" / "data_loss.log"
    assert log_path.exists()
    payloads = [
        json.loads(line.split(" ", 1)[1])
        for line in log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(
        p["kind"] == "reconciliation_amount_parse" and p["value"] == "ОШИБКА"
        for p in payloads
    )
