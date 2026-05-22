from decimal import Decimal

import openpyxl
import pytest

from core.infra.ingestion_reader import CalamineReader


@pytest.fixture
def reader():
    markers = {
        "customer": "заказчик",
        "contractor": "исполнитель",
        "amount": "сумма платежа",
        "income": "приход",
        "expense": "расход",
        "commission": "комиссия",
        "total": "итог",
        "percent_broker": "% посредника",
        "broker1": "посредник 1(кэш)",
        "broker2": "посредник 2",
    }
    aliases = {
        "amount": ["сумма платежа", "бн рф руб", "бн"],
        "customer": ["заказчик", "агент"],
        "contractor": ["исполнитель", "вторая сторона"],
    }
    return CalamineReader(markers, aliases)


@pytest.fixture
def temp_xlsx(tmp_path):
    def _create(name, sheets_data):
        f = tmp_path / name
        wb = openpyxl.Workbook()
        for sheet_name, rows in sheets_data.items():
            ws = (
                wb.create_sheet(sheet_name) if wb.active.title != "Sheet" else wb.active
            )
            ws.title = sheet_name
            for row in rows:
                ws.append(row)
        if "Sheet" in wb.sheetnames and len(wb.sheetnames) > 1:
            del wb["Sheet"]
        wb.save(f)
        return f

    return _create


def test_read_marks_text_total_as_template_warning(reader, temp_xlsx):
    f = temp_xlsx(
        "text_total.xlsx",
        {
            "07.04.26": [
                [
                    "Заказчик",
                    "Исполнитель",
                    "Сумма платежа",
                    "Комиссия",
                    "Итог",
                    "% посредника",
                    "посредник 1(кэш)",
                    "посредник 2",
                    "Фильтры",
                ],
                [
                    "(Дядя) Комплекс бар",
                    "Мос ВТБ",
                    -346.8,
                    None,
                    "инвентарь МГ",
                    None,
                    None,
                    None,
                    None,
                ],
            ]
        },
    )

    rows = reader.read(f)

    assert len(rows) == 1
    assert rows[0]["amount"] == Decimal("-346.80")
    assert rows[0]["is_template_warning"] is True
    assert rows[0]["total"] is None


def test_read_keeps_invalid_amount_text_for_logic_error_row(reader, temp_xlsx):
    f = temp_xlsx(
        "text_amount.xlsx",
        {
            "07.04.26": [
                [
                    "Заказчик",
                    "Исполнитель",
                    "Сумма платежа",
                    "Комиссия",
                    "Итог",
                    "% посредника",
                    "посредник 1(кэш)",
                    "посредник 2",
                    "Фильтры",
                ],
                [
                    "ООО Ромашка",
                    "ИП Иванов",
                    "не число",
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ],
            ]
        },
    )

    rows = reader.read(f)

    assert len(rows) == 1
    assert rows[0]["customer"] == "ООО Ромашка"
    assert rows[0]["amount"] == "не число"
    assert rows[0]["is_template_warning"] is True
    assert rows[0]["_template_warning_reason"] == "text in numeric field: amount"


def test_read_realigns_shifted_amount_bank_row_as_warning(reader, temp_xlsx):
    f = temp_xlsx(
        "shifted_amount.xlsx",
        {
            "03.04.2026": [
                [
                    "Заказчик",
                    "Исполнитель",
                    "Сумма платежа",
                    "Комиссия",
                    "Итог",
                    "Итог дня",
                    "% посредника",
                    "посредник 1(кэш)",
                    "посредник 2",
                    "Фильтры",
                ],
                [
                    "Олег ООО Индифуд",
                    "Олег ООО ЛМ ГРУПП",
                    "Мос ВТБ",
                    -1206250.0,
                    -0.095,
                    -1091656.25,
                    None,
                    None,
                    None,
                    "Транзит",
                ],
            ]
        },
    )

    rows = reader.read(f)

    assert len(rows) == 1
    assert rows[0]["amount"] == Decimal("-1206250.0")
    assert rows[0]["commission"] == Decimal("-0.095")
    assert rows[0]["total"] == Decimal("-1091656.25")
    assert rows[0]["is_template_warning"] is True


def test_read_skips_day_total_row(reader, temp_xlsx):
    f = temp_xlsx(
        "day_total.xlsx",
        {
            "07.04.26": [
                ["Заказчик", "Исполнитель", "Сумма платежа", "Итог"],
                ["ООО А", "ИП Б", 1000, 1000],
                ["Итоги дня", None, None, 1000],
            ]
        },
    )

    rows = reader.read(f)

    assert len(rows) == 1
    assert rows[0]["customer"] == "ООО А"


def test_read_uses_best_header_not_first_partial_header(reader, temp_xlsx):
    f = temp_xlsx(
        "headers.xlsx",
        {
            "07.04.26": [
                ["Сумма платежа", "Заказчик"],
                ["Заказчик", "Исполнитель", "Сумма платежа", "Итог", "Фильтры"],
                ["ООО А", "ИП Б", 1500, 1500, ""],
            ]
        },
    )

    rows = reader.read(f)

    assert len(rows) == 1
    assert rows[0]["customer"] == "ООО А"
    assert rows[0]["contractor"] == "ИП Б"
    assert rows[0]["amount"] == Decimal("1500")
