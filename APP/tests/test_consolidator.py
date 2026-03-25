import pytest
import os
import yaml
import pandas as pd
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch, MagicMock
from consolidator import Config, Template1Reader, Consolidator


class TestConfig:

    def test_config_loads_valid_yaml(self, tmp_path, mock_config_dict):
        """Load valid YAML, verify all top-level sections parsed correctly."""
        config_file = tmp_path / "config.yaml"
        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.dump(mock_config_dict, f)
        cfg = Config(str(config_file))
        assert cfg.sh1.get('markers') is not None
        assert cfg.logic.get('income_overrides') == ['доп', 'доп сф', '% посред']
        assert cfg.employees == ['EmpA', 'EmpB']

    def test_config_missing_file(self):
        """Pass nonexistent path — must not raise, data must be empty dict."""
        cfg = Config("/nonexistent/path/config.yaml")
        assert cfg.data == {}
        assert cfg.paths == {}

    def test_config_relative_paths_resolved(self, tmp_path, mock_config_dict):
        """Relative paths in 'paths' section must be converted to absolute paths."""
        config_file = tmp_path / "config.yaml"
        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.dump(mock_config_dict, f)
        cfg = Config(str(config_file))
        for key, val in cfg.paths.items():
            if val:
                assert os.path.isabs(val), f"Path '{key}' is not absolute: {val}"

    def test_config_get_default(self, tmp_path, mock_config_dict):
        """config.get('nonexistent_key', 'fallback') must return 'fallback'."""
        config_file = tmp_path / "config.yaml"
        with open(config_file, 'w', encoding='utf-8') as f:
            yaml.dump(mock_config_dict, f)
        cfg = Config(str(config_file))
        assert cfg.get('nonexistent_key', 'fallback') == 'fallback'
        assert cfg.get('nonexistent_key') is None


class TestFindHeaderRow:

    @pytest.fixture
    def reader(self, consolidator):
        """Returns a Template1Reader instance."""
        return consolidator.reader

    def test_finds_header_with_all_markers(self, reader):
        """Row containing дата, заказчик, исполнитель, приход must be detected."""
        rows = [
            (None, None, None),
            ("дата", "заказчик", "исполнитель", "приход", "расход", "итог"),
            ("01.01", "Client A", "Bank", "1000"),
        ]
        idx = reader.find_header_row(rows)
        assert idx == 1

    def test_finds_best_header_among_multiple_candidates(self, reader):
        """Two rows partially match — verify highest score wins."""
        rows = [
            ("дата", "заказчик", "исполнитель"),        # score=3 — minimum match
            ("дата", "заказчик", "исполнитель", "приход", "расход", "итог"),  # score=6 — best
            ("01.01", "Client", "Bank", "500"),
        ]
        idx = reader.find_header_row(rows)
        assert idx == 1

    def test_returns_none_if_no_match(self, reader):
        """Rows with random data — must return None."""
        rows = [
            ("apple", "banana", "cherry"),
            ("123", "456", "789"),
            (None, None, None),
        ]
        idx = reader.find_header_row(rows)
        assert idx is None

    def test_header_at_row_0(self, reader):
        """Header is the very first row — boundary check."""
        rows = [
            ("дата", "заказчик", "исполнитель", "приход", "расход"),
            ("01.01", "Client", "Bank", "1000"),
        ]
        idx = reader.find_header_row(rows)
        assert idx == 0

    def test_header_at_row_149(self, reader):
        """Header is at last scanned row (row 149) — boundary check."""
        rows = [("random", "data") for _ in range(149)]
        rows.append(("дата", "заказчик", "исполнитель", "приход", "расход"))
        idx = reader.find_header_row(rows)
        assert idx == 149

    def test_minimum_score_threshold(self, reader):
        """Row with only 2 matching markers must NOT be detected (score < 3)."""
        rows = [
            ("дата", "заказчик", "nothing", "nothing"),  # score=2
        ]
        idx = reader.find_header_row(rows)
        assert idx is None


# --- Consolidator Tests ---

@pytest.fixture
def consolidator(tmp_path, mock_config_dict):
    config_file = tmp_path / "config.yaml"
    with open(config_file, 'w', encoding='utf-8') as f:
        yaml.dump(mock_config_dict, f)
    return Consolidator(str(config_file))


# --- to_decimal ---
@pytest.mark.parametrize("input_val, expected", [
    ("1234.56", Decimal('1234.56')),
    ("1 234,56", Decimal('1234.56')), # thousand separator spaces, decimal comma
    ("1234,56", Decimal('1234.56')), # decimal comma
    ("0", Decimal('0.00')),
    ("", Decimal('0.00')),
    (None, Decimal('0.00')),
    (float('nan'), Decimal('0.00')),
    ("-500.00", Decimal('-500.00')), # negative
    ("1.5e2", Decimal('150.00')), # scientific notation
    ("abc", Decimal('0.00')), # invalid input
    (1234, Decimal('1234.00')), # integer
    (1234.567, Decimal('1234.57')), # float rounding ROUND_HALF_UP
    ("1234.", Decimal('1234.00')), # trailing dot
    ("1,234,567.89", Decimal('1234567.89')), # US format
    ("1.234", Decimal('1234.00')),    # European thousands dot, 3 digits after
    ("12.500", Decimal('12500.00')),  # European thousands dot, 3 digits after
    ("1.000", Decimal('1000.00')),    # European thousands dot, 3 digits after
    ("1.23", Decimal('1.23')),        # Normal decimal dot, 2 digits — must stay
    ("(1234,56)", Decimal('-1234.56')),  # Accounting negative notation
    ("(500.00)", Decimal('-500.00')),    # Accounting negative notation with dot
])
def test_to_decimal(consolidator, input_val, expected):
    """Test various input types and formatting for precise Decimal output."""
    assert consolidator.to_decimal(input_val) == expected

# --- to_decimal_percent ---
@pytest.mark.parametrize("input_val, expected", [
    ("15%", Decimal('0.15')), # percentage sign present, value > 1
    ("0.15", Decimal('0.15')), # already a fraction
    ("15", Decimal('15')), # no percent sign -> no division
    ("", Decimal('0')),
    (None, Decimal('0')),
    (float('nan'), Decimal('0')),
])
def test_to_decimal_percent(consolidator, input_val, expected):
    """Test percentage parsing logic."""
    assert consolidator.to_decimal_percent(input_val) == expected

# --- is_junk_row ---
def test_junk_total_word(consolidator, mock_col_map):
    """row contains 'итого' -> True"""
    row = {'a': 'something', 'b': 'итого'}
    assert consolidator.is_junk_row(row, mock_col_map) is True

def test_junk_total_word_with_spaces(consolidator, mock_col_map):
    """row contains ' итого: ' -> True"""
    row = {'a': ' итого: '}
    assert consolidator.is_junk_row(row, mock_col_map) is True

def test_junk_header_repeat(consolidator, mock_col_map):
    """row contains 'заказчик' AND 'исполнитель' -> True"""
    row = {'col1': 'заказчик', 'col2': 'исполнитель'}
    assert consolidator.is_junk_row(row, mock_col_map) is True

def test_junk_needs_two_markers(consolidator, mock_col_map):
    """row contains only 'заказчик' -> False"""
    row = {'col1': 'заказчик', 'col2': 'random'}
    assert consolidator.is_junk_row(row, mock_col_map) is False

def test_valid_row_not_junk(consolidator, mock_col_map):
    """normal data row -> False"""
    row = {'col1': 'Client A', 'col2': 'Contractor B', 'col3': '1000'}
    assert consolidator.is_junk_row(row, mock_col_map) is False

def test_all_nan_row(consolidator, mock_col_map):
    """all values are NaN -> False (not junk, just empty)"""
    row = {'col1': float('nan'), 'col2': None}
    assert consolidator.is_junk_row(row, mock_col_map) is False

def test_junk_case_insensitive(consolidator, mock_col_map):
    """'ИТОГО' uppercase -> True"""
    row = {'a': 'ИТОГО'}
    assert consolidator.is_junk_row(row, mock_col_map) is True

# --- transform_row ---
@patch('consolidator.audit.log_action')
def test_positive_amount_becomes_income(mock_log, consolidator, mock_col_map):
    """amount=500, no special filters -> income=500, expense=0"""
    row = {mock_col_map['amount']: '500', mock_col_map['filters']: ''}
    res = consolidator.transform_row(row, mock_col_map, 'Emp', 'Sheet1', 1)
    assert res['сумма платежа ПРИХОД'] == Decimal('500.00')
    assert res['сумма платежа РАСХОД'] == Decimal('0.00')

@patch('consolidator.audit.log_action')
def test_negative_amount_becomes_expense(mock_log, consolidator, mock_col_map):
    """amount=-300 -> income=0, expense=300"""
    row = {mock_col_map['amount']: '-300', mock_col_map['filters']: ''}
    res = consolidator.transform_row(row, mock_col_map, 'Emp', 'Sheet1', 1)
    assert res['сумма платежа ПРИХОД'] == Decimal('0.00')
    assert res['сумма платежа РАСХОД'] == Decimal('300.00')

@patch('consolidator.audit.log_action')
def test_return_keyword_becomes_expense(mock_log, consolidator, mock_col_map):
    """filters contains 'возврат', amount=200 -> expense=200"""
    row = {mock_col_map['amount']: '200', mock_col_map['filters']: 'возврат средств'}
    res = consolidator.transform_row(row, mock_col_map, 'Emp', 'Sheet1', 1)
    assert res['сумма платежа ПРИХОД'] == Decimal('0.00')
    assert res['сумма платежа РАСХОД'] == Decimal('200.00')

@patch('consolidator.audit.log_action')
def test_additional_income_override(mock_log, consolidator, mock_col_map):
    """filters contains 'доп', amount=100 -> income=100 regardless of sign"""
    row = {mock_col_map['amount']: '-100', mock_col_map['filters']: 'доп оплата'}
    res = consolidator.transform_row(row, mock_col_map, 'Emp', 'Sheet1', 1)
    assert res['сумма платежа ПРИХОД'] == Decimal('-100.00')
    assert res['сумма платежа РАСХОД'] == Decimal('0.00')

@patch('consolidator.audit.log_action')
def test_zero_amount_returns_none(mock_log, consolidator, mock_col_map):
    """amount=0, total=0, no overrides -> returns None"""
    row = {mock_col_map['amount']: '0', mock_col_map['total']: '0', mock_col_map['filters']: ''}
    res = consolidator.transform_row(row, mock_col_map, 'Emp', 'Sheet1', 1)
    assert res is None

@patch('consolidator.audit.log_action')
def test_nan_amount_returns_none(mock_log, consolidator, mock_col_map):
    """amount=NaN, no overrides -> returns None"""
    row = {mock_col_map['amount']: float('nan'), mock_col_map['filters']: ''}
    res = consolidator.transform_row(row, mock_col_map, 'Emp', 'Sheet1', 1)
    assert res is None

@patch('consolidator.audit.log_action')
def test_formula_injection_sanitized(mock_log, consolidator, mock_col_map):
    """customer='=HYPERLINK(...)' -> Result starts with '''"""
    row = {mock_col_map['amount']: '100', mock_col_map['customer']: '=HYPERLINK("http://evil.com")'}
    res = consolidator.transform_row(row, mock_col_map, 'Emp', 'Sheet1', 1)
    assert res['ЗАКАЗЧИК (название проекта, наименование ЮЛ)'] == "'=HYPERLINK(\"http://evil.com\")"

@patch('consolidator.audit.log_action')
def test_filename_added_to_employee_label(mock_log, consolidator, mock_col_map):
    """filename='report.xlsx' -> 'Сотрудник' contains '[report.xlsx]'"""
    row = {mock_col_map['amount']: '100'}
    res = consolidator.transform_row(row, mock_col_map, 'EmpA', 'Sheet1', 42, filename='report.xlsx')
    assert 'EmpA [report.xlsx]' in res['Сотрудник']

@patch('consolidator.audit.log_action')
def test_row_index_in_employee_label(mock_log, consolidator, mock_col_map):
    """row_index=42 -> 'Сотрудник' contains '(стр. 42)'"""
    row = {mock_col_map['amount']: '100'}
    res = consolidator.transform_row(row, mock_col_map, 'EmpA', 'Sheet1', 42)
    assert '(стр. 42)' in res['Сотрудник']

@patch('consolidator.audit.log_action')
def test_audit_not_called_when_log_audit_false(mock_log, consolidator, mock_col_map):
    """log_audit=False -> audit.log_action NOT called"""
    row = {mock_col_map['amount']: '100'}
    consolidator.transform_row(row, mock_col_map, 'EmpA', 'Sheet1', 1, log_audit=False)
    mock_log.assert_not_called()

@patch('consolidator.audit.log_action')
def test_result_keys_complete(mock_log, consolidator, mock_col_map):
    """verify presence of all expected keys in the result dictionary"""
    row = {mock_col_map['amount']: '100', mock_col_map['commission']: '10', mock_col_map['percent_broker']: '5%'}
    res = consolidator.transform_row(row, mock_col_map, 'Emp', 'Sheet1', 1)
    expected_keys = [
        'Дата', 'Сотрудник', 'ЗАКАЗЧИК (название проекта, наименование ЮЛ)',
        'ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)', 'сумма платежа ПРИХОД',
        'сумма платежа РАСХОД', 'комиссия', 'ИТОГ', '% посредника',
        'посредник 1(кэш)', 'посредник 2', 'фильтры', 'is_critical'
    ]
    for key in expected_keys:
        assert key in res

# --- _get_sheetnames_fast ---
@patch('consolidator.os.path.exists')
@patch('consolidator.os.path.getmtime')
@patch('consolidator.zipfile.ZipFile')
def test_reads_from_zip_workbook_xml(mock_zip, mock_mtime, mock_exists, consolidator):
    mock_exists.return_value = True
    """valid workbook.xml with 3 sheets -> returns 3 names"""
    mock_mtime.return_value = 1000
    mock_zip_instance = MagicMock()
    mock_zip.return_value.__enter__.return_value = mock_zip_instance
    mock_zip_instance.namelist.return_value = ['xl/workbook.xml']

    xml_content = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
        <sheets>
            <sheet name="Sheet1" sheetId="1" r:id="rId1" state="visible"/>
            <sheet name="Sheet2" sheetId="2" r:id="rId2"/>
            <sheet name="Sheet3" sheetId="3" r:id="rId3" state="visible"/>
        </sheets>
    </workbook>'''

    import io
    mock_file = MagicMock()
    mock_file.__enter__.return_value = io.BytesIO(xml_content)
    mock_zip_instance.open.return_value = mock_file

    names = consolidator._get_sheetnames_fast("dummy.xlsx")
    # Sheet 1, 2, 3 should all be there, sheet2 state defaults to visible if not provided based on parsing logic
    assert names == ["Sheet1", "Sheet2", "Sheet3"]

@patch('consolidator.os.path.exists')
@patch('consolidator.os.path.getmtime')
@patch('consolidator.zipfile.ZipFile')
def test_hidden_sheets_excluded(mock_zip, mock_mtime, mock_exists, consolidator):
    mock_exists.return_value = True
    """one sheet has state 'hidden' -> excluded from result"""
    mock_mtime.return_value = 1000
    mock_zip_instance = MagicMock()
    mock_zip.return_value.__enter__.return_value = mock_zip_instance
    mock_zip_instance.namelist.return_value = ['xl/workbook.xml']

    xml_content = b'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
        <sheets>
            <sheet name="VisibleSheet" sheetId="1" r:id="rId1"/>
            <sheet name="HiddenSheet" sheetId="2" r:id="rId2" state="hidden"/>
        </sheets>
    </workbook>'''
    import io
    mock_file = MagicMock()
    mock_file.__enter__.return_value = io.BytesIO(xml_content)
    mock_zip_instance.open.return_value = mock_file

    names = consolidator._get_sheetnames_fast("dummy.xlsx")
    assert names == ["VisibleSheet"]

@patch('consolidator.os.path.exists')
@patch('consolidator.os.path.getmtime')
@patch('consolidator.zipfile.ZipFile')
def test_cache_hit_returns_cached(mock_zip, mock_mtime, mock_exists, consolidator):
    mock_exists.return_value = True
    """call twice with same mtime -> zipfile opened only once"""
    mock_mtime.return_value = 1000
    mock_zip_instance = MagicMock()
    mock_zip.return_value.__enter__.return_value = mock_zip_instance
    mock_zip_instance.namelist.return_value = ['xl/workbook.xml']

    xml_content = b'''<?xml version="1.0" encoding="UTF-8"?>
    <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
        <sheets><sheet name="Sheet1"/></sheets>
    </workbook>'''
    import io
    mock_file = MagicMock()
    mock_file.__enter__.return_value = io.BytesIO(xml_content)
    mock_zip_instance.open.return_value = mock_file

    names1 = consolidator._get_sheetnames_fast("dummy.xlsx")
    names2 = consolidator._get_sheetnames_fast("dummy.xlsx")

    assert names1 == names2
    assert mock_zip.call_count == 1

@patch('consolidator.os.path.exists')
@patch('consolidator.os.path.getmtime')
@patch('consolidator.zipfile.ZipFile')
def test_cache_miss_on_mtime_change(mock_zip, mock_mtime, mock_exists, consolidator):
    mock_exists.return_value = True
    """mtime changes -> cache invalidated, file re-read"""
    mock_mtime.side_effect = [1000, 2000]
    mock_zip_instance = MagicMock()
    mock_zip.return_value.__enter__.return_value = mock_zip_instance
    mock_zip_instance.namelist.return_value = ['xl/workbook.xml']

    xml_content = b'''<?xml version="1.0" encoding="UTF-8"?>
    <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
        <sheets><sheet name="Sheet1"/></sheets>
    </workbook>'''
    import io
    mock_file = MagicMock()
    mock_file.__enter__.return_value = io.BytesIO(xml_content)
    mock_zip_instance.open.return_value = mock_file

    consolidator._get_sheetnames_fast("dummy.xlsx")
    mock_file2 = MagicMock()
    mock_file2.__enter__.return_value = io.BytesIO(xml_content)
    mock_zip_instance.open.return_value = mock_file2
    consolidator._get_sheetnames_fast("dummy.xlsx")

    assert mock_zip.call_count == 2

@patch('consolidator.os.path.exists')
@patch('consolidator.os.path.getmtime')
@patch('consolidator.zipfile.ZipFile')
@patch('consolidator.openpyxl.load_workbook')
def test_fallback_to_openpyxl_on_zip_error(mock_openpyxl, mock_zip, mock_mtime, mock_exists, consolidator):
    mock_exists.return_value = True
    """broken zip -> falls back to openpyxl, no exception raised"""
    mock_mtime.return_value = 1000
    mock_zip.side_effect = Exception("Not a zip file")

    mock_wb = MagicMock()
    mock_sheet = MagicMock()
    mock_sheet.title = "FallbackSheet"
    mock_sheet.sheet_state = "visible"
    mock_wb.worksheets = [mock_sheet]
    mock_openpyxl.return_value = mock_wb

    names = consolidator._get_sheetnames_fast("dummy.xlsx")
    assert names == ["FallbackSheet"]
    mock_openpyxl.assert_called_once()

# --- check_date_exists ---
from datetime import datetime
@patch.object(Consolidator, '_get_sheetnames_fast')
def test_finds_exact_date(mock_fast, consolidator):
    """sheet '25.03' exists, check_date(2026,3,25) -> True"""
    mock_fast.return_value = ["25.03"]
    assert consolidator.check_date_exists("dummy.xlsx", datetime(2026, 3, 25)) is True

@patch.object(Consolidator, '_get_sheetnames_fast')
def test_finds_date_with_leading_zero(mock_fast, consolidator):
    """sheet '05.03' exists, check_date(2026,3,5) -> True"""
    mock_fast.return_value = ["05.03"]
    assert consolidator.check_date_exists("dummy.xlsx", datetime(2026, 3, 5)) is True

@patch.object(Consolidator, '_get_sheetnames_fast')
def test_no_false_positive_partial_match(mock_fast, consolidator):
    """sheet '16.03', check_date(2026,3,6) -> False"""
    mock_fast.return_value = ["16.03"]
    assert consolidator.check_date_exists("dummy.xlsx", datetime(2026, 3, 6)) is False

@patch.object(Consolidator, '_get_sheetnames_fast')
def test_date_not_found(mock_fast, consolidator):
    """no matching sheet -> False"""
    mock_fast.return_value = ["01.04"]
    assert consolidator.check_date_exists("dummy.xlsx", datetime(2026, 3, 25)) is False
