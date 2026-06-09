import pytest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime

from core.infra.export_writer import MasterWriter

@pytest.fixture
def temp_output_dir(tmp_path):
    return tmp_path

@pytest.fixture
def master_writer(temp_output_dir):
    config = {
        "paths": {"master_file": str(temp_output_dir / "test_output.xlsx")},
        "logic": {},
    }
    return MasterWriter(config)

def test_export_survives_null_row_in_data(master_writer, temp_output_dir):
    """
    Bug: A single None row in the data list causes the entire write_report 
    to drop all valid data.
    Expected: It should skip the None row and export the valid rows.
    """
    output_path = temp_output_dir / "report_null.xlsx"
    data = [
        {
            "Дата": "01.04.2026",
            "Источник": "valid.xlsx",
            "сумма платежа ПРИХОД": 100,
            "сумма платежа РАСХОД": 0,
            "комиссия": 0,
            "ИТОГ": 100,
        },
        None,  # This triggers AttributeError in r.get("Дата")
    ]
    
    result = master_writer.write_report(data, output_path)
    assert result is True, "Export failed completely due to a single None row"

def test_export_survives_invalid_numeric_data(master_writer, temp_output_dir):
    """
    Bug: A row with an invalid numeric string ("N/A") causes float() to raise ValueError.
    This exception is caught at the date level, dropping subsequent valid rows for that date.
    Expected: It should skip the invalid row or treat the invalid number as 0, and process the rest.
    """
    output_path = temp_output_dir / "report_invalid_num.xlsx"
    data = [
        {
            "Дата": "01.04.2026",
            "Источник": "valid1.xlsx",
            "сумма платежа ПРИХОД": 100,
            "сумма платежа РАСХОД": 0,
            "комиссия": 0,
            "ИТОГ": 100,
        },
        {
            "Дата": "01.04.2026",
            "Источник": "invalid.xlsx",
            "сумма платежа ПРИХОД": "N/A",  # Triggers ValueError
            "сумма платежа РАСХОД": 0,
            "комиссия": 0,
            "ИТОГ": 0,
        },
        {
            "Дата": "01.04.2026",
            "Источник": "valid2.xlsx",
            "сумма платежа ПРИХОД": 200,
            "сумма платежа РАСХОД": 0,
            "комиссия": 0,
            "ИТОГ": 200,
        }
    ]
    
    master_writer.write_report(data, output_path)
    from openpyxl import load_workbook
    wb = load_workbook(output_path)
    ws = wb["01.04.2026"]
    source_cells = [ws.cell(r, 1).value for r in range(2, ws.max_row)]
    assert "valid2.xlsx" in source_cells, "Subsequent valid rows were dropped after invalid numeric row"

def test_write_empty_daily_report_mkdir_permission_error_crashes(master_writer, temp_output_dir):
    """
    Bug: write_empty_daily_report calls _save_workbook without a try-except block.
    If Path.mkdir fails, it crashes the app instead of returning False gracefully.
    """
    output_path = temp_output_dir / "protected_dir" / "report.xlsx"
    
    with patch("pathlib.Path.mkdir", side_effect=PermissionError("Network drive unavailable")):
        try:
            result = master_writer.write_empty_daily_report(output_path, datetime(2026, 4, 1))
            assert result is False, "Should have gracefully returned False"
        except PermissionError:
            pytest.fail("Unhandled PermissionError during mkdir crashed the empty report export")
