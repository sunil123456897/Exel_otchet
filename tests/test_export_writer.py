import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch
from core.infra.export_writer import MasterWriter
from openpyxl.styles import PatternFill

@pytest.fixture
def master_writer():
    config = {'paths': {'master_file': 'dummy.xlsx'}}
    return MasterWriter(config)

def test_math_error_detection_logic(master_writer):
    # Mock workbook and worksheet
    mock_wb = MagicMock()
    mock_ws = MagicMock()
    mock_wb.create_sheet.return_value = mock_ws
    
    # Mock headers in ws[1]
    headers = ["Дата", "Источник", "ЗАКАЗЧИК", "ИСПОЛНИТЕЛЬ", "Приход", "Расход", "Комиссия", "ИТОГ", "% посредника", "посредник 1(кэш)", "посредник 2", "Фильтры"]
    mock_ws.__getitem__.return_value = [MagicMock(value=h) for h in headers]
    
    # Mock iter_rows to return our data rows
    # We need to simulate the row cells after ws.append
    def mock_append(row_data):
        row_cells = [MagicMock(value=v) for v in row_data]
        # Store the row cells for iter_rows
        if not hasattr(mock_ws, '_rows'): mock_ws._rows = []
        mock_ws._rows.append(row_cells)
        mock_ws.max_row = len(mock_ws._rows) + 1 # +1 because headers are at row 1

    mock_ws.append.side_effect = mock_append
    mock_ws.iter_rows.side_effect = lambda min_row=1, max_row=None: mock_ws._rows[min_row-1:max_row]

    # Case 1: No error (has_money, commission > 0, total > 0)
    rows = [{
        'сумма платежа ПРИХОД': 100,
        'сумма платежа РАСХОД': 0,
        'комиссия': 10,
        'ИТОГ': 90
    }]
    master_writer.write_daily_data(datetime(2026, 1, 1), rows, wb=mock_wb)
    
    # Check if any cell in the first data row has yellow fill
    # mock_ws._rows[0] is headers, mock_ws._rows[1] is data
    first_data_row_cells = mock_ws._rows[1]
    # is_math_err should be False
    for cell in first_data_row_cells:
        if hasattr(cell.fill, 'fgColor'):
            assert cell.fill.fgColor.rgb != "00FFFF00"
            assert cell.fill.fgColor.rgb != "FFFF00"

    # Case 2: No math error (commission is 0, but total is correct)
    mock_ws._rows = []
    rows = [{
        'сумма платежа ПРИХОД': 100,
        'сумма платежа РАСХОД': 0,
        'комиссия': 0,
        'ИТОГ': 100
    }]
    master_writer.write_daily_data(datetime(2026, 1, 1), rows, wb=mock_wb)
    first_data_row_cells = mock_ws._rows[1]
    # is_math_err should be False
    for cell in first_data_row_cells:
        if hasattr(cell.fill, 'fgColor'):
            assert "FFFF00" not in str(cell.fill.fgColor.rgb)

    # Case 2b: Math error (commission is 0, total is incorrect)
    mock_ws._rows = []
    rows = [{
        'сумма платежа ПРИХОД': 100,
        'сумма платежа РАСХОД': 0,
        'комиссия': 0,
        'ИТОГ': 101
    }]
    master_writer.write_daily_data(datetime(2026, 1, 1), rows, wb=mock_wb)
    first_data_row_cells = mock_ws._rows[1]
    # is_math_err should be True, so all cells in row should be yellow
    assert "FFFF00" in first_data_row_cells[0].fill.fgColor.rgb

    # Case 3: Math error (total is 0)
    mock_ws._rows = []
    rows = [{
        'сумма платежа ПРИХОД': 0,
        'сумма платежа РАСХОД': -100,
        'комиссия': 10,
        'ИТОГ': 0
    }]
    master_writer.write_daily_data(datetime(2026, 1, 1), rows, wb=mock_wb)
    first_data_row_cells = mock_ws._rows[1]
    # is_math_err should be True
    assert "FFFF00" in first_data_row_cells[0].fill.fgColor.rgb

    # Case 4: Negative values, no error
    mock_ws._rows = []
    rows = [{
        'сумма платежа ПРИХОД': 0,
        'сумма платежа РАСХОД': -100,
        'комиссия': 10,
        'ИТОГ': -110
    }]
    master_writer.write_daily_data(datetime(2026, 1, 1), rows, wb=mock_wb)
    first_data_row_cells = mock_ws._rows[1]
    # is_math_err should be False
    for cell in first_data_row_cells:
        if hasattr(cell.fill, 'fgColor'):
            assert "FFFF00" not in str(cell.fill.fgColor.rgb)
