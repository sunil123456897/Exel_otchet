import os
import pytest
from datetime import datetime
from pathlib import Path
import openpyxl
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from APP.src.writer import MasterWriter

@pytest.fixture
def writer(tmp_path):
    config = {
        'paths': {
            'master_file': str(tmp_path / 'Master_Report_Test.xlsx')
        }
    }
    return MasterWriter(config)

@pytest.fixture
def dummy_data():
    return [
        {
            'Дата': '25.03.2026',
            'Источник': 'Emp1',
            'ЗАКАЗЧИК (название проекта, наименование ЮЛ)': 'Cust1',
            'ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)': 'Contr1',
            'сумма платежа ПРИХОД': 500.0,
            'сумма платежа РАСХОД': 0,
            'комиссия': 10.0,
            'ИТОГ': 490.0,
            '% посредника': 0,
            'посредник 1(кэш)': 0,
            'посредник 2': 0,
            'фильтры': ''
        },
        {
            'Дата': '25.03.2026',
            'Источник': 'Emp2',
            'ЗАКАЗЧИК (название проекта, наименование ЮЛ)': 'Cust2',
            'ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)': 'Contr2',
            'сумма платежа ПРИХОД': 0,
            'сумма платежа РАСХОД': 300.0,
            'комиссия': 0,
            'ИТОГ': -300.0,
            '% посредника': 0,
            'посредник 1(кэш)': 0,
            'посредник 2': 0,
            'фильтры': ''
        },
        {
            'Дата': '25.03.2026',
            'Источник': 'Emp3',
            'ЗАКАЗЧИК (название проекта, наименование ЮЛ)': 'Cust3',
            'ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)': 'Contr3',
            'сумма платежа ПРИХОД': 1000.0,
            'сумма платежа РАСХОД': 100.0,
            'комиссия': 0,
            'ИТОГ': 900.0,
            '% посредника': 0,
            'посредник 1(кэш)': 0,
            'посредник 2': 0,
            'фильтры': ''
        }
    ]

# --- write_daily_data ---
def test_sheet_created_with_correct_name(writer, dummy_data):
    """date=2026-03-25 -> sheet named '25.03'"""
    dt = datetime(2026, 3, 25)
    writer.write_daily_data(dt, dummy_data)

    wb = openpyxl.load_workbook(writer.master_path)
    assert "25.03" in wb.sheetnames

def test_headers_correct(writer, dummy_data):
    """check if all 12 expected columns are in the first row"""
    dt = datetime(2026, 3, 25)
    writer.write_daily_data(dt, dummy_data)

    wb = openpyxl.load_workbook(writer.master_path)
    ws = wb["25.03"]

    expected_headers = [
        "Дата", "Источник", "ЗАКАЗЧИК", "ИСПОЛНИТЕЛЬ", "Приход",
        "Расход", "Комиссия", "ИТОГ", "% посредника", "посредник 1(кэш)",
        "посредник 2", "Фильтры"
    ]

    header_row = [cell.value for cell in ws[1]]
    assert header_row == expected_headers

def test_data_rows_written(writer, dummy_data):
    """3 employee rows passed, checked if 3 rows in sheet (+ header + total = 5 rows)"""
    dt = datetime(2026, 3, 25)
    writer.write_daily_data(dt, dummy_data)

    wb = openpyxl.load_workbook(writer.master_path)
    ws = wb["25.03"]

    assert ws.max_row == 5

    # Check some data
    assert ws.cell(row=2, column=2).value == 'Emp1'
    assert ws.cell(row=3, column=2).value == 'Emp2'
    assert ws.cell(row=4, column=2).value == 'Emp3'

def test_total_row_has_sum_formulas(writer, dummy_data):
    """last row cells E-H contain SUM formulas"""
    dt = datetime(2026, 3, 25)
    writer.write_daily_data(dt, dummy_data)

    wb = openpyxl.load_workbook(writer.master_path)
    ws = wb["25.03"]

    total_row = ws.max_row
    assert total_row == 5

    assert ws.cell(row=total_row, column=5).value == "=SUM(E2:E4)"
    assert ws.cell(row=total_row, column=6).value == "=SUM(F2:F4)"
    assert ws.cell(row=total_row, column=7).value == "=SUM(G2:G4)"
    assert ws.cell(row=total_row, column=8).value == "=SUM(H2:H4)"

def test_freeze_panes_set(writer, dummy_data):
    """ws.freeze_panes == 'A2'"""
    dt = datetime(2026, 3, 25)
    writer.write_daily_data(dt, dummy_data)

    wb = openpyxl.load_workbook(writer.master_path)
    ws = wb["25.03"]

    assert ws.freeze_panes == 'A2'

def test_named_styles_registered(writer, dummy_data):
    """wb.named_styles contains expected styles"""
    dt = datetime(2026, 3, 25)
    writer.write_daily_data(dt, dummy_data)

    wb = openpyxl.load_workbook(writer.master_path)
    assert 'header_row' in wb.named_styles

def test_named_styles_not_duplicated(writer, dummy_data):
    """calling write twice for same sheet doesn't raise DuplicateNamedStyleError"""
    dt = datetime(2026, 3, 25)
    writer.write_daily_data(dt, dummy_data)
    # Call again with the same wb logic inside write_daily_data via write_report or wb passed
    wb = openpyxl.load_workbook(writer.master_path)
    try:
        writer.write_daily_data(dt, dummy_data, wb=wb)
    except Exception as e:
        pytest.fail(f"DuplicateNamedStyleError raised: {e}")

def test_existing_sheet_replaced(writer, dummy_data):
    """writing same date twice -> only one sheet exists, with latest data"""
    dt = datetime(2026, 3, 25)
    writer.write_daily_data(dt, dummy_data)

    dummy_data_2 = [dummy_data[0]] # Only 1 row now
    writer.write_daily_data(dt, dummy_data_2)

    wb = openpyxl.load_workbook(writer.master_path)
    sheet_names = wb.sheetnames

    assert sheet_names.count("25.03") == 1
    ws = wb["25.03"]
    assert ws.max_row == 3 # 1 header + 1 data + 1 total

def test_income_cell_style(writer, dummy_data):
    """income > 0 -> cell in col 5 has 'income' background color"""
    dt = datetime(2026, 3, 25)
    wb = openpyxl.Workbook()
    writer.write_daily_data(dt, dummy_data, wb=wb)

    ws = wb["25.03"]
    # Row 2 (Emp1) has income = 500
    cell = ws.cell(row=2, column=5)
    assert cell.fill.start_color.rgb == "00C6EFCE"  # AARRGGBB for openpyxl

def test_expense_cell_style(writer, dummy_data):
    """expense > 0 -> cell in col 6 has 'expense' background color"""
    dt = datetime(2026, 3, 25)
    wb = openpyxl.Workbook()
    writer.write_daily_data(dt, dummy_data, wb=wb)

    ws = wb["25.03"]
    # Row 3 (Emp2) has expense = 300
    cell = ws.cell(row=3, column=6)
    assert cell.fill.start_color.rgb == "00FFC7CE"  # AARRGGBB for openpyxl

# --- write_report ---
def test_multiple_dates_written(writer, dummy_data):
    """3 dates passed -> 3 sheets created"""
    data = []
    for d in ["25.03.2026", "26.03.2026", "27.03.2026"]:
        for row in dummy_data:
            new_row = row.copy()
            new_row['Дата'] = d
            data.append(new_row)
            
    writer.write_report(data, Path(writer.master_path))

    wb = openpyxl.load_workbook(writer.master_path)
    assert "25.03" in wb.sheetnames
    assert "26.03" in wb.sheetnames
    assert "27.03" in wb.sheetnames

def test_sheets_sorted_by_date(writer, dummy_data):
    """dates written out of order -> sheets sorted correctly (01.03 to 25.03)"""
    data = []
    for d in ["25.03.2026", "01.03.2026", "10.03.2026"]:
        for row in dummy_data:
            new_row = row.copy()
            new_row['Дата'] = d
            data.append(new_row)

    writer.write_report(data, Path(writer.master_path))

    wb = openpyxl.load_workbook(writer.master_path)

    expected_order = ["01.03", "10.03", "25.03"]

    # Filter out 'Sheet' if it exists, focus on date sheets
    actual_order = [s for s in wb.sheetnames if '.' in s]
    assert actual_order == expected_order

@patch.object(MasterWriter, '_save_workbook')
def test_workbook_saved_once(mock_save, writer, dummy_data):
    """mock _save_workbook, verify called exactly once regardless of dates"""
    writer.write_report(dummy_data, Path(writer.master_path))
    mock_save.assert_called_once()

# --- _sort_sheets ---
def test_sort_date_sheets(writer):
    """sheets ["25.03", "01.03", "10.03"] -> ["01.03", "10.03", "25.03"]"""
    wb = openpyxl.Workbook()
    wb.create_sheet("25.03")
    wb.create_sheet("01.03")
    wb.create_sheet("10.03")
    if "Sheet" in wb.sheetnames: del wb["Sheet"]

    writer._sort_sheets(wb)
    assert wb.sheetnames == ["01.03", "10.03", "25.03"]

def test_sort_by_month_then_day(writer):
    """["31.01", "01.03", "15.02"] -> ["31.01", "15.02", "01.03"]"""
    wb = openpyxl.Workbook()
    wb.create_sheet("31.01")
    wb.create_sheet("01.03")
    wb.create_sheet("15.02")
    if "Sheet" in wb.sheetnames: del wb["Sheet"]

    writer._sort_sheets(wb)
    assert wb.sheetnames == ["31.01", "15.02", "01.03"]

def test_non_date_sheets_go_last(writer):
    """["25.03", "СВОД", "01.03"] -> date sheets first, "СВОД" last"""
    wb = openpyxl.Workbook()
    wb.create_sheet("25.03")
    wb.create_sheet("СВОД")
    wb.create_sheet("01.03")
    if "Sheet" in wb.sheetnames: del wb["Sheet"]

    writer._sort_sheets(wb)
    assert wb.sheetnames == ["01.03", "25.03", "СВОД"]

# --- _auto_adjust_columns ---
def test_column_width_set(writer, dummy_data):
    """write data of known length, verify column width > 0"""
    wb = openpyxl.Workbook()
    dt = datetime(2026, 3, 25)
    writer.write_daily_data(dt, dummy_data, wb=wb)

    ws = wb["25.03"]
    # width should be adjusted for columns that have data
    assert ws.column_dimensions['A'].width is not None
    assert ws.column_dimensions['A'].width > 0

def test_numeric_columns_minimum_width(writer, dummy_data):
    """numeric cols (5-11) should have width >= 15"""
    wb = openpyxl.Workbook()
    dt = datetime(2026, 3, 25)
    writer.write_daily_data(dt, dummy_data, wb=wb)

    ws = wb["25.03"]
    for col_idx in range(5, 12):
        col_letter = openpyxl.utils.get_column_letter(col_idx)
        width = ws.column_dimensions[col_letter].width
        assert width is not None
        assert width >= 15

def test_handles_empty_sheet(writer):
    """empty worksheet -> no exception raised"""
    wb = openpyxl.Workbook()
    ws = wb.active
    try:
        writer._auto_adjust_columns(ws)
    except Exception as e:
        pytest.fail(f"Exception raised on empty sheet: {e}")
