import sys
import os
import pytest
import pandas as pd
from pathlib import Path
from unittest.mock import patch

_MkdirPath = str | bytes | os.PathLike[str] | os.PathLike[bytes]


def _install_codex_windows_mkdir_compat() -> None:
    """Keep pytest temp directories readable in the Codex Windows sandbox."""
    if os.name != "nt" or not os.environ.get("CODEX_THREAD_ID"):
        return

    original_mkdir = os.mkdir
    if getattr(original_mkdir, "_codex_windows_mode_compat", False):
        return

    def mkdir_compat(path: _MkdirPath, mode: int = 0o777, *, dir_fd: int | None = None) -> None:
        effective_mode = 0o777 if mode == 0o700 else mode
        if dir_fd is None:
            original_mkdir(path, effective_mode)
            return
        original_mkdir(path, effective_mode, dir_fd=dir_fd)

    mkdir_compat._codex_windows_mode_compat = True
    os.mkdir = mkdir_compat


_install_codex_windows_mkdir_compat()

# Add APP directory to sys.path
app_root = Path(__file__).parent.parent / "APP"
if str(app_root) not in sys.path:
    sys.path.insert(0, str(app_root))

@pytest.fixture
def create_temp_xlsx():
    """Returns a function to create a temporary XLSX file."""
    def _create(path, data, sheet_name="Sheet1"):
        # If data is a list of lists, treat as raw rows
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
             # For raw rows (like [ ['header1', 'header2'], [1, 2] ])
             import openpyxl
             wb = openpyxl.Workbook()
             ws = wb.active
             ws.title = sheet_name
             for row in data:
                 ws.append(row)
             wb.save(path)
        else:
            df = pd.DataFrame(data)
            df.to_excel(path, index=False, sheet_name=sheet_name)
        return path
    return _create

@pytest.fixture
def create_temp_xlsb():
    """Returns a function to create a temporary XLSB file."""
    def _create(path, data, sheet_name="Sheet1"):
        # Note: pandas supports writing to xlsb via 'pyxlsb' engine in some versions,
        # but often it's easier to just use the engine directly or skip if not needed.
        # Calamine is the reader, we just need a valid file.
        df = pd.DataFrame(data)
        # Using xlsxwriter as fallback or pyxlsb if supported
        try:
            df.to_excel(path, index=False, sheet_name=sheet_name, engine='pyxlsb')
        except:
            # If pyxlsb writing is not supported, we might need a pre-generated file or another way
            # For now, let's assume it works or fall back to xlsx for logic tests
            df.to_excel(path, index=False, sheet_name=sheet_name)
        return path
    return _create

@pytest.fixture
def mock_network_drive():
    """Mocks os.path.abspath and path checks to simulate network drive behavior."""
    original_abspath = os.path.abspath
    
    def _mock_abspath(path):
        p_str = str(path).replace('/', '\\')
        if p_str.startswith('Q:') or p_str.startswith('Z:') or p_str.startswith('\\\\'):
            return p_str
        return original_abspath(path)
        
    with patch('os.path.abspath', side_effect=_mock_abspath):
        yield
