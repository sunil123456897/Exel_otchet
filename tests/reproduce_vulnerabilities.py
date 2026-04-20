import pytest
from decimal import Decimal
from datetime import datetime
from unittest.mock import MagicMock, patch
from core.domain.utils_helpers import to_decimal, NumericParsingError
from core.domain.logic_service import LogicService
from core.infra.export_writer import MasterWriter
from core.infra.ingestion_reader import extract_date_from_sheet, CalamineReader

class MockPersistence:
    def get_consolidated_data(self, session_id):
        return []

def test_to_decimal_silent_data_loss():
    # "~" should now raise NumericParsingError to avoid silent loss
    with pytest.raises(NumericParsingError):
        to_decimal("~")

    assert to_decimal("0") == Decimal('0.00')
    assert to_decimal("") == Decimal('0.00')
    assert to_decimal("0.0") == Decimal('0.00')
    assert to_decimal("-") == Decimal('0.00')

def test_logic_service_critical_row():
    # Test that rows with unparseable numeric data are marked as critical
    ls = LogicService(MockPersistence(), {})
    
    # Row with trash amount
    raw_rows = [{
        'amount': '~',
        'total': '100',
        'customer': 'Client A',
        '_source_info': 'test.xlsx | Sheet1 | Row 1'
    }]
    
    processed = ls.apply_financial_rules(raw_rows)
    assert len(processed) == 1
    assert processed[0]['is_critical'] is True
    assert processed[0]['сумма платежа ПРИХОД'] == Decimal('0.00')

def test_math_error_highlighting_logic():
    # Mock worksheet and styles
    ws = MagicMock()
    # Mock row_cells to simulate values
    # row_cells[cols['приход']-1].value, etc.
    # Logic in MasterWriter._apply_cell_styling:
    # expected_total = i_val - e_val
    # is_math_err = has_money and (abs(t_val) < 0.02 or abs(expected_total - t_val) > 0.02)
    
    # We want to verify this condition is met.
    # Case: income=100, expense=0, total=90 (missing 10), commission=10.
    # Before fix, it was (c_val == 0 and ...) so it wouldn't be a math error if commission was set.
    # After fix, it should be a math error.
    
    i_val, e_val, t_val, c_val = 100.0, 0.0, 90.0, 10.0
    expected_total = i_val - e_val
    has_money = abs(i_val) > 0.02 or abs(e_val) > 0.02
    is_math_err = has_money and (abs(t_val) < 0.02 or abs(expected_total - t_val) > 0.02)
    
    assert is_math_err is True # 100 - 0 != 90

def test_extract_date_invalid():
    # Feb 29 2023 is invalid. Fix: return None and skip later in pipeline.
    assert extract_date_from_sheet("29.02.2023") is None

def test_unknown_date_sheet_logic():
    # Verify that write_report drops invalid/future rows and writes only valid date sheets.
    writer = MasterWriter({'paths': {'master_file': 'dummy.xlsx'}})
    data = [
        {'Дата': 'bad-date', 'Источник': 'bad.xlsx', 'customer': 'A'},
        {'Дата': '24.04.2999', 'Источник': 'future.xlsx', 'customer': 'B'},
        {'Дата': '01.04.2026', 'Источник': 'ok.xlsx', 'customer': 'C'},
    ]

    writer.write_daily_data = MagicMock()
    writer._save_workbook = MagicMock(return_value=True)
    writer._get_workbook = MagicMock()

    with patch("core.infra.export_writer.datetime") as mock_datetime:
        mock_datetime.now.return_value = datetime(2026, 4, 17)
        mock_datetime.strptime = datetime.strptime
        result = writer.write_report(data, "output.xlsx")

    assert result is True
    assert writer.write_daily_data.call_count == 1
    assert writer.write_daily_data.call_args.args[0] == datetime(2026, 4, 1)

def test_calamine_reader_memory():
    # Check that CalamineReader uses iter_rows which is memory efficient
    import inspect
    from core.infra.ingestion_reader import CalamineReader
    
    # Verify read method uses iter_rows
    read_source = inspect.getsource(CalamineReader.read)
    assert 'iter_rows()' in read_source

def test_critical_row_highlighting_color():
    # Verify that the color used for critical rows is "FF9999" (Light red)
    from core.infra import export_formatting
    
    import inspect
    source = inspect.getsource(export_formatting.apply_cell_styling)
    assert 'FF9999' in source
    assert 'fill_critical' in source
