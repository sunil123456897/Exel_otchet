import pytest
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from core.infra.ingestion_utils import extract_date_from_sheet
from core.infra.ingestion_readers import ExcelReader, XlsxReader, XlsbReader
from core.infra.ingestion_engine import IngestionEngine

def test_extract_date_from_sheet():
    assert extract_date_from_sheet("01.01.2026") == "01.01.2026"
    assert extract_date_from_sheet("01,01,2026") == "01.01.2026"
    assert extract_date_from_sheet("Sheet 01.01") is not None
    assert extract_date_from_sheet("No date here") is None
    assert extract_date_from_sheet("32.01.2026") is None # Invalid date
    
    # Test year rollover logic
    # If today is 01.01.2026 and sheet is 31.12, it should probably be 2025 if 31.12.2026 is > 30 days in future
    with patch('core.infra.ingestion_utils.datetime') as mock_datetime:
        mock_datetime.now.return_value = datetime(2026, 1, 1)
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        
        # Removed smart rollover logic: year should always default to current year
        assert extract_date_from_sheet("31.12") == "31.12.2026"
        # 05.01 (no year) -> should be 2026 because 05.01.2026 is < 30 days from 01.01.2026
        assert extract_date_from_sheet("05.01") == "05.01.2026"

def test_ingestion_engine_scan_directory(tmp_path):
    engine = IngestionEngine({})
    
    # Create some files
    (tmp_path / "test1.xlsx").write_text("content")
    (tmp_path / "test2.xlsb").write_text("content")
    (tmp_path / "test3.txt").write_text("content")
    (tmp_path / "~$test4.xlsx").write_text("content")
    
    res = engine.scan_directory(tmp_path)
    assert len(res) == 2
    paths = [r['path'] for r in res]
    assert any("test1.xlsx" in p for p in paths)
    assert any("test2.xlsb" in p for p in paths)
    assert not any("test3.txt" in p for p in paths)
    assert not any("~$test4.xlsx" in p for p in paths)

def test_ingestion_engine_get_available_dates_xlsx(tmp_path):
    engine = IngestionEngine({})
    test_file = tmp_path / "test.xlsx"
    test_file.write_text("content")
    
    with patch('openpyxl.load_workbook') as mock_load:
        mock_wb = MagicMock()
        mock_ws1 = MagicMock()
        mock_ws1.sheet_state = 'visible'
        mock_ws1.title = '01.01.2026'
        mock_ws2 = MagicMock()
        mock_ws2.sheet_state = 'hidden'
        mock_ws2.title = '02.01.2026'
        mock_wb.worksheets = [mock_ws1, mock_ws2]
        mock_load.return_value = mock_wb
        
        dates = engine.get_available_dates(test_file)
        assert dates == ["01.01.2026"]

def test_ingestion_engine_get_available_dates_xlsb(tmp_path):
    engine = IngestionEngine({})
    test_file = tmp_path / "test.xlsb"
    test_file.write_text("content")
    
    with patch('core.infra.ingestion_engine.open_xlsb') as mock_open:
        mock_wb = MagicMock()
        mock_wb.__enter__.return_value = mock_wb
        mock_wb.sheets = ['01.01.2026', 'Invalid']
        mock_open.return_value = mock_wb
        
        dates = engine.get_available_dates(test_file)
        assert dates == ["01.01.2026"]

def test_excel_reader_map_columns():
    markers = {
        'amount': 'сумма платежа',
        'customer': 'заказчик',
        'commission': 'комиссия'
    }
    aliases = {
        'amount': ['бн'],
        'customer': ['агент']
    }
    reader = ExcelReader(markers, aliases)
    
    header = ["Дата", "Заказчик", "Сумма платежа", "Комиссия"]
    col_map = reader._map_columns(header)
    assert col_map['customer'] == 1
    assert col_map['amount'] == 2
    assert col_map['commission'] == 3

    header_aliases = ["Дата", "Агент", "БН", "Комиссия"]
    col_map = reader._map_columns(header_aliases)
    assert col_map['customer'] == 1
    assert col_map['amount'] == 2

def test_xlsx_reader_mocked():
    markers = {'amount': 'сумма'}
    aliases = {'amount': ['сумма'], 'income': ['приход'], 'expense': ['расход'], 'customer': ['заказчик']}
    reader = XlsxReader(markers, aliases)
    
    # Mock openpyxl.load_workbook
    with patch('openpyxl.load_workbook') as mock_load:
        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_ws.sheet_state = 'visible'
        mock_ws.title = '01.01.2026'
        
        # Mock iter_rows
        # First pass for standard_keys (score >= 4)
        # Second pass for processing
        header = ['сумма', 'заказчик', 'приход', 'расход']
        data = [100, 'Client A', 100, 0]
        
        mock_ws.iter_rows.return_value = [header, data]
        mock_wb.worksheets = [mock_ws]
        mock_load.return_value = mock_wb
        
        res = reader.read(Path("dummy.xlsx"))
        assert len(res) == 1
        assert res[0]['amount'] == Decimal('100.00')

def test_xlsb_reader_mocked():
    markers = {'amount': 'сумма'}
    aliases = {'amount': ['сумма'], 'income': ['приход'], 'expense': ['расход'], 'customer': ['заказчик']}
    reader = XlsbReader(markers, aliases)
    
    with patch('core.infra.ingestion_readers.open_xlsb') as mock_open:
        mock_wb = MagicMock()
        mock_wb.__enter__.return_value = mock_wb
        mock_wb.sheets = ['01.01.2026']
        
        mock_ws = MagicMock()
        mock_ws.__enter__.return_value = mock_ws
        
        # Mock rows()
        # Each row is a list of cell objects with .v attribute
        class Cell:
            def __init__(self, v): self.v = v
            
        header_row = [Cell('сумма'), Cell('заказчик'), Cell('приход'), Cell('расход')]
        data_row = [Cell(100), Cell('Client A'), Cell(100), Cell(0)]
        
        mock_ws.rows.return_value = [header_row, data_row]
        mock_wb.get_sheet.return_value = mock_ws
        mock_open.return_value = mock_wb
        
        res = reader.read(Path("dummy.xlsb"))
        assert len(res) == 1
        assert res[0]['amount'] == Decimal('100.00')

def test_process_row_cleaning():
    markers = {'amount': 'сумма'}
    aliases = {}
    reader = ExcelReader(markers, aliases)
    col_map = {'amount': 0}
    
    # Row with only numbers should be ignored (likely a total or junk)
    assert reader._process_row([100, 200], col_map, "01.01", 1, "file.xlsx") is None
    
    # Row with some text should be kept
    res = reader._process_row([100, "Client A"], col_map, "01.01", 1, "file.xlsx")
    assert res is not None
    assert res['amount'] == Decimal('100.00')
    assert res.get('customer') is None # Not in col_map
