import os
import shutil
import pytest
import tempfile
import logging
from decimal import Decimal
from unittest.mock import patch, MagicMock
from pathlib import Path
from core.infra.ingestion_core import CalamineReader
from python_calamine import CalamineWorkbook

# Standard markers for testing
MARKERS = {
    'amount': ['сумма'],
    'customer': ['клиент', 'контрагент'],
    'contractor': ['контрагент'],
    'date': ['дата']
}
ALIASES = {}

@pytest.fixture
def reader():
    return CalamineReader(markers=MARKERS, aliases=ALIASES)

def test_local_copy_success(tmp_path, reader, create_temp_xlsx):
    """
    Успешное копирование с UNC-пути (\\\\server\\share\\file.xlsx) во временную папку и чтение.
    """
    # Create a real temporary file to be used as source
    real_source_file = tmp_path / "network_file.xlsx"
    data = [
        ["Дата", "Контрагент", "Сумма"],
        ["01.01.2023", "Network Client", 1234.56]
    ]
    # Sheet name must contain a date for the reader to process it
    sheet_name = "Data 01.01.2023"
    create_temp_xlsx(real_source_file, data, sheet_name=sheet_name)

    unc_path = r"\\server\share\file.xlsx"
    temp_copy_path = str(tmp_path / "local_temp_copy.xlsx")

    with patch('os.path.abspath', return_value=unc_path), \
         patch('tempfile.mkstemp', return_value=(999, temp_copy_path)), \
         patch('os.close'), \
         patch('shutil.copy2') as mock_copy, \
         patch('os.remove') as mock_remove:
        
        # Real shutil.copy to actually copy the file so Calamine can read it
        def real_copy_sim(src, dst):
            shutil.copy(real_source_file, dst)
        mock_copy.side_effect = real_copy_sim
        
        results = reader.read(Path(unc_path))
        
        assert len(results) > 0
        assert results[0]['amount'] == Decimal('1234.56')
        assert results[0]['contractor'] == "Network Client"
        
        # Verify shutil.copy2 was called with the correct arguments
        mock_copy.assert_called_once_with(unc_path, temp_copy_path)
        # Verify cleanup attempt
        mock_remove.assert_called_once()

def test_network_failure_mid_copy(reader):
    """
    Имитация ошибки IOError во время shutil.copy2. 
    Проверка, что CalamineReader логирует ошибку и возвращает пустой список.
    """
    unc_path = r"\\server\share\unreachable.xlsx"
    temp_path = "C:\\temp\\temp_file.xlsx"
    
    with patch('os.path.abspath', return_value=unc_path), \
         patch('tempfile.mkstemp', return_value=(1, temp_path)), \
         patch('os.close'), \
         patch('shutil.copy2', side_effect=IOError("Connection reset by peer")), \
         patch('core.infra.ingestion_core.logger.error') as mock_log_error, \
         patch('os.remove'), \
         patch('os.path.exists', return_value=True):
        
        results = reader.read(Path(unc_path))
        
        assert results == []
        mock_log_error.assert_called()
        # Verify the error message contains the simulated exception
        error_msg = str(mock_log_error.call_args)
        assert "Connection reset by peer" in error_msg

def test_file_deleted_mid_read(tmp_path, reader, create_temp_xlsx):
    """
    Имитация удаления локальной временной копии прямо во время CalamineWorkbook.from_path. 
    Проверка корректной очистки.
    """
    # Create source file
    src_file = tmp_path / "src.xlsx"
    create_temp_xlsx(src_file, [["Date", "Client", "Sum"], ["01.01.2023", "A", 100]], sheet_name="01.01.2023")
    
    unc_path = r"\\server\share\volatile.xlsx"
    temp_file = str(tmp_path / "temp_volatile.xlsx")
    
    with patch('os.path.abspath', return_value=unc_path), \
         patch('tempfile.mkstemp', return_value=(2, temp_file)), \
         patch('os.close'), \
         patch('shutil.copy2', side_effect=lambda src, dst: shutil.copy(src_file, dst)), \
         patch('python_calamine.CalamineWorkbook.from_path') as mock_from_path, \
         patch('os.remove') as mock_remove:
        
        def simulate_vanishing(path):
            # Delete file right before read attempt
            if os.path.exists(path):
                os.remove(path)
            raise FileNotFoundError(f"File {path} disappeared during read!")
            
        mock_from_path.side_effect = simulate_vanishing
        
        results = reader.read(Path(unc_path))
        
        assert results == []
        # Ensure cleanup was attempted despite failure
        assert mock_remove.called

def test_unsupported_network_path(reader):
    """
    Проверка поведения при путях типа http:// или ftp:// (не должны считаться сетью для Local Copy).
    """
    http_path = "http://raw.githubusercontent.com/test/data.xlsx"
    
    # We mock abspath to return exactly this string
    # We also mock from_path to just return an empty workbook or raise error
    with patch('os.path.abspath', return_value=http_path), \
         patch('shutil.copy2') as mock_copy, \
         patch('python_calamine.CalamineWorkbook.from_path', side_effect=Exception("Skip read")):
        
        results = reader.read(Path(http_path))
        
        # Local copy should NOT be triggered for http://
        mock_copy.assert_not_called()
        assert results == []
