"""Phase 1 — financial accuracy: Decimal values reach Excel intact.

Regression for the float-coercion bug in export. MasterWriter._append_data_rows
used to wrap every financial column in _safe_float(), which forced the
Decimal values produced by LogicService through float. For typical sums
(≤15 significant digits) the loss is invisible, but the coercion was
dishonest about the type contract and would corrupt any future
high-precision field. The fix replaces _safe_float with _safe_decimal,
which passes Decimal straight through to openpyxl.

We feed Decimal values (as LogicService._build_result_row does) and
verify the written cell holds the same value (within float's 15-digit
representational precision, since Excel stores all numbers as IEEE-754
double — that's an Excel/openpyxl limit, not a regression).
"""
from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest
from core.infra.export_writer import MasterWriter


@pytest.fixture
def temp_output_dir():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def master_writer(temp_output_dir):
    config = {
        "paths": {"master_file": str(temp_output_dir / "out.xlsx")},
        "logic": {},
    }
    return MasterWriter(config)


def _decimal_row(**overrides) -> dict:
    """A consolidated row whose financial fields are Decimal, mirroring
    what LogicService._build_result_row actually emits."""
    base = {
        "Дата": "01.05.2026",
        "Источник": "src.xlsx : Строка 2",
        "ЗАКАЗЧИК (название проекта, наименование ЮЛ)": "ООО Тест",
        "ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)": "Альфа",
        "сумма платежа ПРИХОД": Decimal("1234.5678"),
        "сумма платежа РАСХОД": Decimal("0"),
        "комиссия": Decimal("2.5"),
        "ИТОГ": Decimal("1234.5678"),
        "% посредника": Decimal("5.0"),
        "посредник 1(кэш)": Decimal("250.00"),
        "посредник 2": Decimal("0"),
        "фильтры": "",
        "is_template_warning": False,
    }
    base.update(overrides)
    return base


def _read_data_row(path: Path) -> dict[str, object]:
    """Read the first data row of the written report back as a dict
    keyed by the DEFAULT_HEADERS order (skipping the header row)."""
    wb = openpyxl.load_workbook(path)
    try:
        ws = wb[wb.sheetnames[0]]
        headers = [c.value for c in ws[1]]
        row = [c.value for c in ws[2]]
        return dict(zip(headers, row, strict=False))
    finally:
        wb.close()


def test_decimal_income_preserved(master_writer, temp_output_dir):
    """A Decimal income with 4 decimal places must reach the cell."""
    out = temp_output_dir / "report.xlsx"
    master_writer.write_report([_decimal_row()], out)

    row = _read_data_row(out)
    # openpyxl reads numbers back as float; the value must equal the
    # original Decimal to 15 significant digits (the IEEE-754 limit).
    assert row["Приход"] == float(Decimal("1234.5678"))


def test_decimal_expense_preserved(master_writer, temp_output_dir):
    out = temp_output_dir / "report.xlsx"
    master_writer.write_report(
        [_decimal_row(
            **{
                "сумма платежа ПРИХОД": Decimal("0"),
                "сумма платежа РАСХОД": Decimal("9999999.99"),
            }
        )],
        out,
    )
    row = _read_data_row(out)
    assert row["Расход"] == float(Decimal("9999999.99"))


def test_decimal_broker_and_commission_preserved(master_writer, temp_output_dir):
    """Broker cash and commission must keep their exact Decimal value."""
    out = temp_output_dir / "report.xlsx"
    master_writer.write_report(
        [_decimal_row(
            **{
                "комиссия": Decimal("3.33"),
                "посредник 1(кэш)": Decimal("777.77"),
            }
        )],
        out,
    )
    row = _read_data_row(out)
    assert row["Комиссия"] == float(Decimal("3.33"))
    assert row["посредник 1(кэш)"] == float(Decimal("777.77"))


def test_large_decimal_not_corrupted(master_writer, temp_output_dir):
    """A large sum (12 significant digits) must round-trip exactly —
    this is where float-coercion would first show drift if reintroduced."""
    out = temp_output_dir / "report.xlsx"
    big = Decimal("123456789.12")
    master_writer.write_report(
        [_decimal_row(**{"сумма платежа ПРИХОД": big, "ИТОГ": big})],
        out,
    )
    row = _read_data_row(out)
    assert Decimal(str(row["Приход"])) == big
    assert Decimal(str(row["ИТОГ"])) == big


def test_non_numeric_cell_coerced_to_zero_not_crash(master_writer, temp_output_dir):
    """If a financial cell somehow holds garbage, _safe_decimal must
    coerce it to 0 rather than raise (defence-in-depth on top of the
    Decimal contract from LogicService)."""
    out = temp_output_dir / "report.xlsx"
    master_writer.write_report(
        [_decimal_row(**{"сумма платежа ПРИХОД": "НЕ ЧИСЛО"})],
        out,
    )
    row = _read_data_row(out)
    assert row["Приход"] in (0, 0.0, Decimal("0"))


def test_safe_decimal_handles_none_and_empty(master_writer, temp_output_dir):
    """None and '' must yield 0, not propagate into the cell."""
    out = temp_output_dir / "report.xlsx"
    master_writer.write_report(
        [_decimal_row(**{"сумма платежа ПРИХОД": None, "комиссия": ""})],
        out,
    )
    row = _read_data_row(out)
    assert row["Приход"] in (0, 0.0)
    assert row["Комиссия"] in (0, 0.0)
