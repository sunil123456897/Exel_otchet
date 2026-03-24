import os
import sys
from unittest.mock import MagicMock, call

# Mock dependencies before they are imported by the module under test
mock_openpyxl = MagicMock()
sys.modules['openpyxl'] = mock_openpyxl
sys.modules['openpyxl.utils'] = MagicMock()
sys.modules['openpyxl.styles'] = MagicMock()
sys.modules['pandas'] = MagicMock()

# Now we can import MasterWriter
# Add APP and APP/src to sys.path
sys.path.append(os.path.join(os.getcwd(), 'APP'))
sys.path.append(os.path.join(os.getcwd(), 'APP', 'src'))

from writer import MasterWriter
import pytest

def test_get_workbook_non_existent(monkeypatch):
    # Mock os.path.exists to return False
    monkeypatch.setattr(os.path, "exists", lambda x: False)

    mock_wb = MagicMock()
    mock_wb.sheetnames = ["Sheet"]
    mock_openpyxl.Workbook.return_value = mock_wb

    mock_sheet = MagicMock()
    mock_wb.__getitem__.return_value = mock_sheet

    config = {'paths': {'master_file': 'non_existent.xlsx'}}
    writer = MasterWriter(config)

    wb = writer._get_workbook()

    assert wb == mock_wb
    mock_wb.__getitem__.assert_called_with("Sheet")
    mock_wb.remove.assert_called_with(mock_sheet)

def test_get_workbook_exists_valid(monkeypatch):
    # Mock os.path.exists to return True
    monkeypatch.setattr(os.path, "exists", lambda x: True)

    mock_wb = MagicMock()
    mock_openpyxl.load_workbook.return_value = mock_wb
    mock_openpyxl.load_workbook.side_effect = None

    config = {'paths': {'master_file': 'valid.xlsx'}}
    writer = MasterWriter(config)

    wb = writer._get_workbook()

    assert wb == mock_wb
    mock_openpyxl.load_workbook.assert_called_with('valid.xlsx')

def test_get_workbook_exists_corrupted(monkeypatch):
    # Mock os.path.exists to return True
    monkeypatch.setattr(os.path, "exists", lambda x: True)
    # Mock load_workbook to raise an exception
    mock_openpyxl.load_workbook.side_effect = Exception("Corrupted file")

    mock_wb_new = MagicMock()
    mock_wb_new.sheetnames = ["Sheet"]
    mock_openpyxl.Workbook.return_value = mock_wb_new

    config = {'paths': {'master_file': 'corrupted.xlsx'}}
    writer = MasterWriter(config)

    wb = writer._get_workbook()

    assert wb == mock_wb_new
    # In current implementation, if corrupted, it returns Workbook() without removing "Sheet"
    assert mock_wb_new.remove.called is False
