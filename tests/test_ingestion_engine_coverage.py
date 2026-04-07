"""Расширенные тесты для ingestion_engine.py — Покрытие пропущенных веток."""
import pytest
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.infra.ingestion_engine import IngestionEngine

@pytest.fixture
def markers():
    return {
        'customer': 'заказчик',
        'amount': 'сумма платежа',
    }

@pytest.fixture
def engine(markers):
    return IngestionEngine(markers)

def test_get_available_dates_network_mock(engine, tmp_path):
    """Cover lines 42-45: Network file detection and copying."""
    # Mocking network path starts with '\\\\'
    network_path = Path("\\\\server\\share\\file.xlsx")
    
    # We need to mock os.path.abspath to return the network path
    # and mock CalamineWorkbook to not actually try to open it.
    with patch('os.path.abspath', return_value=str(network_path)), \
         patch('tempfile.mkstemp', return_value=(99, "temp_path.xlsx")), \
         patch('os.close'), \
         patch('shutil.copy2') as mock_copy, \
         patch('python_calamine.CalamineWorkbook.from_path') as mock_wb, \
         patch('os.path.exists', return_value=True), \
         patch('os.remove') as mock_remove:
        
        mock_wb.return_value.sheet_names = ["Отчет 01.01"]
        
        dates = engine.get_available_dates(network_path)
        
        assert "01.01.2026" in dates
        mock_copy.assert_called_once()
        mock_remove.assert_called_once_with("temp_path.xlsx")

def test_get_available_dates_exception_logging(engine, tmp_path):
    """Cover lines 56-57: Exception logging in get_available_dates."""
    f = tmp_path / "error.xlsx"
    f.touch()
    
    with patch('python_calamine.CalamineWorkbook.from_path', side_effect=RuntimeError("Test error")), \
         patch('core.infra.ingestion_engine.logger') as mock_logger:
        dates = engine.get_available_dates(f)
        assert dates == []
        mock_logger.error.assert_called()

def test_scan_directory_exception_logging(engine, tmp_path):
    """Cover lines 80-81: Exception logging in scan_directory."""
    f = tmp_path / "unreadable.xlsx"
    f.touch()
    
    # We want root_path.exists() to succeed, so we need to be careful with patching os.stat
    # since pathlib.Path.exists() calls os.stat.
    # We'll use a side_effect function that only raises error for the specific file.
    original_stat = os.stat
    def side_effect(path, *args, **kwargs):
        if str(path).endswith("unreadable.xlsx"):
            raise PermissionError("Access denied")
        return original_stat(path, *args, **kwargs)

    with patch('os.stat', side_effect=side_effect), \
         patch('core.infra.ingestion_engine.logger') as mock_logger:
        res = engine.scan_directory(tmp_path)
        # Should still find the directory but fail on the file
        mock_logger.error.assert_called()

def test_scan_directory_network_drive(engine, tmp_path):
    """Cover network drive detection (Q: or Z:)."""
    # Case Q:
    with patch('os.path.abspath', return_value="Q:\\some\\file.xlsx"), \
         patch('tempfile.mkstemp', return_value=(100, "temp_q.xlsx")), \
         patch('os.close'), \
         patch('shutil.copy2'), \
         patch('python_calamine.CalamineWorkbook.from_path') as mock_wb, \
         patch('os.path.exists', return_value=True), \
         patch('os.remove'):
        
        mock_wb.return_value.sheet_names = ["Отчет 02.02"]
        dates = engine.get_available_dates(Path("Q:\\some\\file.xlsx"))
        assert "02.02.2026" in dates

    # Case Z:
    with patch('os.path.abspath', return_value="Z:\\some\\file.xlsx"), \
         patch('tempfile.mkstemp', return_value=(101, "temp_z.xlsx")), \
         patch('os.close'), \
         patch('shutil.copy2'), \
         patch('python_calamine.CalamineWorkbook.from_path') as mock_wb, \
         patch('os.path.exists', return_value=True), \
         patch('os.remove'):
        
        mock_wb.return_value.sheet_names = ["Отчет 03.03"]
        dates = engine.get_available_dates(Path("Z:\\some\\file.xlsx"))
        assert "03.03.2026" in dates
