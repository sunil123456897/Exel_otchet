import pytest
from datetime import datetime
from pathlib import Path
from core.infra.export_writer import MasterWriter
from openpyxl import load_workbook

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

def test_export_skips_datetime_objects(master_writer, temp_output_dir):
    """
    Bug: write_report assumes the 'Дата' field is always a string.
    If ingestion passes a datetime object (common in openpyxl Excel reads),
    str(d) generates 'YYYY-MM-DD HH:MM:SS', which strptime('%d.%m.%Y') fails to parse,
    silently skipping valid data.
    Expected: datetime objects should be gracefully handled or exported.
    """
    output_path = temp_output_dir / "report_datetime.xlsx"
    valid_date_obj = datetime(2026, 4, 1)
    
    data = [
        {
            "Дата": valid_date_obj,
            "Источник": "datetime_test",
            "сумма платежа ПРИХОД": 100,
            "сумма платежа РАСХОД": 0,
            "комиссия": 0,
            "ИТОГ": 100,
        }
    ]
    
    # write_report returns False if all rows were skipped
    result = master_writer.write_report(data, output_path)
    assert result is True, "Export failed or skipped the row because 'Дата' was a datetime object, not a string"

def test_export_empty_report_inverted_sum_formula(master_writer, temp_output_dir):
    """
    Bug: When writing an empty report, ws.max_row is 1.
    build_total_row creates a formula `=SUM(C2:C1)`, which is inverted and includes the header row.
    Expected: Formula should safely handle zero data rows (e.g. `=0` or `=SUM(C2:C2)`).
    """
    output_path = temp_output_dir / "report_empty.xlsx"
    
    master_writer.write_empty_daily_report(output_path, datetime(2026, 4, 1))
    
    wb = load_workbook(output_path)
    ws = wb["01.04.2026"]
    
    # Total row is added at row 2 (since header is row 1 and there is no data)
    sum_formula = ws.cell(2, 4).value # Column 4 is 'Приход'
    assert sum_formula != "=SUM(D2:D1)", "Formula is an inverted range spanning over headers"

def test_export_trust_curator_total_when_commission_filled(master_writer, temp_output_dir):
    """
    Reverted in commit fix-math-error-trust-commission: curators often
    write commission as a small rate (e.g. 8.5 meaning 8.5%) and
    pre-compute the total as expense * (1 - rate/100). The strict
    "total == income - expense - commission" check that landed in
    dce35bd flagged 75% of valid rows as math errors. We now trust
    the curator's total whenever commission is non-zero.
    """
    output_path = temp_output_dir / "report_math.xlsx"

    data = [
        {
            "Дата": "01.04.2026",
            "Источник": "math_test",
            "сумма платежа ПРИХОД": 100,
            "сумма платежа РАСХОД": 0,
            "комиссия": 10,
            "ИТОГ": 500,
        }
    ]

    master_writer.write_report(data, output_path)

    wb = load_workbook(output_path)
    ws = wb["01.04.2026"]

    fill_color = ws.cell(2, 7).fill.fgColor.rgb
    assert fill_color != "00FFFF00", (
        "Row with non-zero commission must NOT be flagged as math "
        "error — curator total is trusted when commission is filled."
    )

def test_export_ivan_curator_row_index_desync(master_writer, temp_output_dir):
    """
    Bug: When curator='ivan', _append_data_rows inserts synthetic 'employee header' rows.
    However, apply_cell_styling iter_rows assumes 1:1 mapping with rows_data array via r_idx.
    This causes conditional formatting (is_critical, returns) to map to wrong rows or out-of-bounds.
    Expected: The critical row should be highlighted in red ("FF9999").
    """
    output_path = temp_output_dir / "report_ivan.xlsx"
    
    data = [
        {
            "Дата": "01.04.2026",
            "Сотрудник": "Ivanov",
            "Источник": "Normal Data",
            "is_critical": False,
            "сумма платежа ПРИХОД": 10,
        },
        {
            "Дата": "01.04.2026",
            "Сотрудник": "Ivanov",
            "Источник": "Critical Data",
            "is_critical": True,
            "сумма платежа ПРИХОД": 20,
        }
    ]
    
    master_writer.write_report(data, output_path, curator="ivan")
    
    wb = load_workbook(output_path)
    ws = wb["01.04.2026"]
    
    # Row 1: Columns Header
    # Row 2: Synthetic Employee Header ("Ivanov")
    # Row 3: Normal Data
    # Row 4: Critical Data
    
    critical_cell_fill = ws.cell(4, 1).fill.fgColor.rgb
    # The expected fill for critical is 'FF9999' (alpha "00" in openpyxl stored rgb)
    assert critical_cell_fill == "00FF9999", "Critical styling applied to the wrong row due to index desync"
