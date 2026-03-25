import os
import yaml
import pytest
import pandas as pd
from datetime import datetime
from unittest.mock import patch, MagicMock
import openpyxl

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from consolidator import Consolidator
from writer import MasterWriter

@pytest.fixture
def mock_pipeline_config(tmp_path):
    config_dict = {
        'paths': {
            'source_root': str(tmp_path / 'reports'),
            'master_file': str(tmp_path / 'Master_Report_E2E.xlsx')
        },
        'sh1': {
            'markers': {
                'customer': 'ЗАКАЗЧИК',
                'contractor': 'ИСПОЛНИТЕЛЬ',
                'amount': 'сумма платежа',
                'total': 'ИТОГ',
            }
        },
        'sh2': {},
        'logic': {},
        'employees': ['EmpA', 'EmpB', 'EmpC']
    }

    config_file = tmp_path / "config.yaml"
    with open(config_file, 'w', encoding='utf-8') as f:
        yaml.dump(config_dict, f)

    return str(config_file)

@pytest.fixture
def base_df():
    return pd.DataFrame({
        'ЗАКАЗЧИК': ['Cust1', 'Cust2', 'Cust3', 'Cust4', 'Cust5'],
        'ИСПОЛНИТЕЛЬ': ['Contr1', 'Contr2', 'Contr3', 'Contr4', 'Contr5'],
        'сумма платежа': [100, -200, 300, -400, 500],
        'ИТОГ': [100, 100, 400, 0, 500]
    })

# --- Integration Tests ---

@patch('consolidator.audit.log_action')
@patch('consolidator.Template1Reader.read_file')
@patch('consolidator.Consolidator.get_employees')
def test_full_pipeline_single_date(mock_get_emp, mock_read_file, mock_log, mock_pipeline_config, base_df):
    """1 employee, 1 date, 5 rows -> proper file generated with exact values."""
    mock_get_emp.return_value = {'EmpA': ['/dummy/path/EmpA.xlsx']}

    col_map = {
        'customer': 'ЗАКАЗЧИК',
        'contractor': 'ИСПОЛНИТЕЛЬ',
        'amount': 'сумма платежа',
        'total': 'ИТОГ'
    }

    mock_read_file.return_value = {
        "25.03.2026": [(base_df, col_map, "25.03", 0)]
    }

    consolidator = Consolidator(mock_pipeline_config)
    results = consolidator.consolidate_multiple([datetime(2026, 3, 25)])

    writer = MasterWriter(consolidator.config)
    writer.write_all_days(results)

    wb = openpyxl.load_workbook(writer.master_path)
    assert "25.03" in wb.sheetnames
    ws = wb["25.03"]

    # Header (1) + 5 rows + Total (1) = 7
    assert ws.max_row == 7

    # Check income/expense matching input
    # Row 2 corresponds to first data row
    assert ws.cell(row=2, column=5).value == pytest.approx(100.0)
    assert ws.cell(row=2, column=6).value == pytest.approx(0.0)

    assert ws.cell(row=3, column=5).value == pytest.approx(0.0)
    assert ws.cell(row=3, column=6).value == pytest.approx(200.0)

@patch('consolidator.audit.log_action')
@patch('consolidator.Template1Reader.read_file')
@patch('consolidator.Consolidator.get_employees')
def test_full_pipeline_multiple_employees(mock_get_emp, mock_read_file, mock_log, mock_pipeline_config):
    """3 employees, 2 dates, 10 rows each. Employees in output, totals correct."""
    mock_get_emp.return_value = {
        'EmpA': ['/dummy/A.xlsx'],
        'EmpB': ['/dummy/B.xlsx'],
        'EmpC': ['/dummy/C.xlsx']
    }

    df_emp = pd.DataFrame({
        'ЗАКАЗЧИК': [f'Cust_{i}' for i in range(10)],
        'ИСПОЛНИТЕЛЬ': [f'Contr_{i}' for i in range(10)],
        'сумма платежа': [100] * 10,
        'ИТОГ': [100] * 10
    })

    col_map = {'customer': 'ЗАКАЗЧИК', 'contractor': 'ИСПОЛНИТЕЛЬ', 'amount': 'сумма платежа', 'total': 'ИТОГ'}

    def side_effect(path, dates):
        return {
            "25.03.2026": [(df_emp, col_map, "25.03", 0)],
            "26.03.2026": [(df_emp, col_map, "26.03", 0)]
        }

    mock_read_file.side_effect = side_effect

    consolidator = Consolidator(mock_pipeline_config)
    results = consolidator.consolidate_multiple([datetime(2026, 3, 25), datetime(2026, 3, 26)])

    writer = MasterWriter(consolidator.config)
    writer.write_all_days(results)

    wb = openpyxl.load_workbook(writer.master_path)
    assert "25.03" in wb.sheetnames
    assert "26.03" in wb.sheetnames

    ws = wb["25.03"]
    # 3 employees * 10 rows = 30 data rows
    # Header (1) + Total (1) = 2
    # Total rows = 32
    assert ws.max_row == 32

    employees_in_sheet = [ws.cell(row=r, column=2).value for r in range(2, 32)]
    assert any('EmpA' in str(e) for e in employees_in_sheet)
    assert any('EmpB' in str(e) for e in employees_in_sheet)
    assert any('EmpC' in str(e) for e in employees_in_sheet)

@patch('consolidator.audit.log_action')
@patch('consolidator.Template1Reader.read_file')
@patch('consolidator.Consolidator.get_employees')
def test_pipeline_skips_junk_rows(mock_get_emp, mock_read_file, mock_log, mock_pipeline_config):
    """Input has 3 valid, 2 junk -> Output has exactly 3 data rows."""
    mock_get_emp.return_value = {'EmpA': ['/dummy/path/EmpA.xlsx']}

    df_with_junk = pd.DataFrame({
        'ЗАКАЗЧИК': ['Cust1', 'ИТОГО:', 'заказчик', 'Cust2', 'Cust3'],
        'ИСПОЛНИТЕЛЬ': ['Contr1', '', 'исполнитель', 'Contr2', 'Contr3'],
        'сумма платежа': [100, 500, '', 200, 300],
        'ИТОГ': [100, 500, '', 200, 300]
    })

    col_map = {'customer': 'ЗАКАЗЧИК', 'contractor': 'ИСПОЛНИТЕЛЬ', 'amount': 'сумма платежа', 'total': 'ИТОГ'}

    mock_read_file.return_value = {
        "25.03.2026": [(df_with_junk, col_map, "25.03", 0)]
    }

    consolidator = Consolidator(mock_pipeline_config)
    results = consolidator.consolidate_multiple([datetime(2026, 3, 25)])

    writer = MasterWriter(consolidator.config)
    writer.write_all_days(results)

    wb = openpyxl.load_workbook(writer.master_path)
    ws = wb["25.03"]

    # Header (1) + 3 valid data rows + Total (1) = 5
    assert ws.max_row == 5

@patch('consolidator.audit.log_action')
@patch('consolidator.Template1Reader.read_file')
@patch('consolidator.Consolidator.get_employees')
def test_pipeline_handles_missing_file_gracefully(mock_get_emp, mock_read_file, mock_log, mock_pipeline_config, base_df):
    """One employee missing, others processed, no crash."""
    mock_get_emp.return_value = {
        'EmpA': ['/dummy/A.xlsx'],
        'EmpMissing': ['/missing/file.xlsx'],
        'EmpC': ['/dummy/C.xlsx']
    }

    col_map = {'customer': 'ЗАКАЗЧИК', 'contractor': 'ИСПОЛНИТЕЛЬ', 'amount': 'сумма платежа', 'total': 'ИТОГ'}

    def side_effect(path, dates):
        if 'missing' in path:
            return None # Simulate missing or invalid file returning nothing
        return {
            "25.03.2026": [(base_df, col_map, "25.03", 0)]
        }

    mock_read_file.side_effect = side_effect

    consolidator = Consolidator(mock_pipeline_config)
    results = consolidator.consolidate_multiple([datetime(2026, 3, 25)])

    writer = MasterWriter(consolidator.config)
    writer.write_all_days(results)

    wb = openpyxl.load_workbook(writer.master_path)
    ws = wb["25.03"]

    # 2 successful employees * 5 rows = 10 data rows
    # 10 + Header(1) + Total(1) = 12
    assert ws.max_row == 12

    employees_in_sheet = [str(ws.cell(row=r, column=2).value) for r in range(2, 12)]
    assert any('EmpA' in e for e in employees_in_sheet)
    assert any('EmpC' in e for e in employees_in_sheet)
    assert not any('EmpMissing' in e for e in employees_in_sheet)

@patch('consolidator.audit.log_action')
@patch('consolidator.Consolidator.get_employees')
def test_pipeline_empty_input(mock_get_emp, mock_log, mock_pipeline_config):
    """No employees -> results={} -> writer handles gracefully, no crash."""
    mock_get_emp.return_value = {}

    consolidator = Consolidator(mock_pipeline_config)
    results = consolidator.consolidate_multiple([datetime(2026, 3, 25)])

    assert results == {}

    writer = MasterWriter(consolidator.config)

    # Test that saving an empty dictionary of results doesn't crash the script
    # It might fail to save due to openpyxl requiring at least 1 visible sheet,
    # but that's handled gracefully by the writer class' try-except block
    writer.write_all_days(results)

    # Check that the temp file might exist or the log might have an error, but script did not crash
    assert os.path.exists(mock_pipeline_config)
