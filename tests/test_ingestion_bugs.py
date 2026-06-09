import pytest
import openpyxl
from decimal import Decimal
from core.infra.ingestion_reader import CalamineReader

@pytest.fixture
def markers():
    return {
        'customer': 'заказчик',
        'contractor': 'исполнитель',
        'amount': 'сумма платежа',
        'commission': 'комиссия',
    }

@pytest.fixture
def aliases():
    return {}

@pytest.fixture
def temp_xlsx(tmp_path):
    def _create(name, sheets_data):
        f = tmp_path / name
        wb = openpyxl.Workbook()
        for sheet_name, rows in sheets_data.items():
            ws = wb.create_sheet(sheet_name) if wb.active.title != "Sheet" else wb.active
            ws.title = sheet_name
            for row in rows:
                ws.append(row)
        if "Sheet" in wb.sheetnames and len(wb.sheetnames) > 1:
            del wb["Sheet"]
        wb.save(f)
        return f
    return _create

def test_bug_trash_filtering_substring_match(temp_xlsx, markers, aliases):
    """
    Test demonstrates a bug where valid rows are dropped because _is_trash_row 
    uses substring matching instead of exact or word-boundary matching.
    'всего' matches 'Всегородов'
    'итого' matches 'Итогов'
    """
    reader = CalamineReader(markers, aliases)
    f = temp_xlsx("trash_bug.xlsx", {
        "Отчет 01.04.2026": [
            ["Заказчик", "Сумма платежа"],
            ["ООО Всегородов", "100"],
            ["ИП Итогов", "200"],
        ]
    })
    rows = reader.read(f)
    assert len(rows) == 2, f"Expected 2 rows, got {len(rows)}. Rows with valid substrings are incorrectly dropped."

def test_bug_silent_coercion_of_non_numeric_fields(temp_xlsx, markers, aliases):
    """
    Test demonstrates a bug where non-numeric text in financial fields other than 'amount' 
    (e.g., 'commission', 'total') is silently coerced to None without triggering a template_warning.
    """
    reader = CalamineReader(markers, aliases)
    f = temp_xlsx("silent_coercion.xlsx", {
        "Отчет 01.04.2026": [
            ["Заказчик", "Сумма платежа", "Комиссия"],
            ["ООО Ромашка", "5000", "ОШИБКА"],
        ]
    })
    rows = reader.read(f)
    assert len(rows) == 1
    row = rows[0]
    
    # The 'amount' field triggers a warning if it's text. 
    # But 'commission' just silently becomes None and doesn't trigger a warning.
    # We expect 'is_template_warning' to be True to alert the user of invalid data.
    assert row.get("is_template_warning") is True, "Expected template warning for text in commission field, but it was silently dropped."

def test_bug_income_expense_flagged_as_unexpected(temp_xlsx, markers, aliases):
    """
    Test demonstrates a bug where standard columns 'income' and 'expense' are flagged as unexpected 
    because they are missing from _STRICT_TEMPLATE_ORDER, causing a 'hard_structure' template warning
    for completely valid files.
    """
    markers.update({
        'total': 'итог',
        'percent_broker': '% посредника',
        'broker1': 'посредник 1',
        'broker2': 'посредник 2',
        'income': 'приход',
        'expense': 'расход'
    })
    reader = CalamineReader(markers, aliases)
    f = temp_xlsx("income_expense.xlsx", {
        "Отчет 01.04.2026": [
            [
                "Заказчик", "Исполнитель", "Сумма платежа", "Приход", "Расход", 
                "Комиссия", "Итог", "% посредника", "Посредник 1", "Посредник 2"
            ],
            ["ООО А", "ИП Б", "1000", "1000", "0", "10", "1010", "1", "10", "5"],
        ]
    })
    rows = reader.read(f)
    assert len(rows) == 1
    row = rows[0]
    
    assert row.get("is_template_warning") in (False, None), f"Bug: standard income/expense columns triggered warning: {row.get('_template_warning_reason')}"
