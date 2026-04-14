import pytest
import os
import queue
import logging
import sqlite3
import shutil
import tempfile
from pathlib import Path
from decimal import Decimal
from unittest.mock import MagicMock, patch, DEFAULT

from core.infra.ingestion_reader import CalamineReader
from core.infra.config_controller import ConfigController
from core.bootstrap import Bootstrap
from core.infra.utils_logging import TextHandler
from core.app_controller import AppController
from core.infra.session_repo import SQLiteManager
from core.infra.export_writer import MasterWriter


@pytest.fixture
def temp_dir():
    d = tempfile.mkdtemp()
    yield Path(d)
    try:
        shutil.rmtree(d)
    except:
        pass


# 1. Test CalamineReader iterator usage
def test_calamine_reader_uses_iterator(mocker):
    mock_wb = mocker.patch("core.infra.ingestion_reader.CalamineWorkbook.from_path")
    mock_instance = mock_wb.return_value
    mock_instance.sheet_names = ["01.01.2023"]
    mock_sheet = MagicMock()
    mock_instance.get_sheet_by_name.return_value = mock_sheet

    # Simulate rows with to_python and iter_rows()
    data = [["Header1", "Header2"], ["Val1", "Val2"]]
    mock_sheet.to_python.return_value = data
    mock_sheet.iter_rows.return_value = iter(data)

    reader = CalamineReader(
        markers={"amount": "Header1", "customer": "Header2"}, aliases={}
    )
    reader.read(Path("dummy.xlsx"))

    # The new implementation uses iter_rows for header detection
    assert mock_sheet.iter_rows.call_count >= 1


# 2. Test Config Schema Fragility
def test_config_bootstrap_graceful_fail(temp_dir):
    config_path = temp_dir / "config.yaml"
    with open(config_path, "w") as f:
        f.write("invalid: yaml: content:")

    with patch("tkinter.messagebox.showerror"):
        cfg_ctl, app_ctl, db = Bootstrap.setup(temp_dir, str(config_path))

    assert cfg_ctl is not None
    assert "paths" in cfg_ctl.config
    assert "sh1" in cfg_ctl.config
    assert "logic" in cfg_ctl.config


# 3. Test GUI Logging batch processing
def test_logging_handler_batch_processing():
    mock_widget = MagicMock()
    handler = TextHandler(mock_widget)

    for i in range(100):
        record = logging.LogRecord(
            "test", logging.INFO, "test.py", 10, f"msg {i}", None, None
        )
        handler.emit(record)

    # We call _process_queue. It should insert 50 and schedule another.
    handler._process_queue()

    assert mock_widget.insert.call_count == 50
    assert mock_widget.after_idle.call_count == 1  # From initial emit
    assert mock_widget.after.call_count == 1  # From _process_queue rescheduling


# 4. Test Pre-flight Lock Check
def test_pre_flight_lock_check(temp_dir, mocker):
    master_file = temp_dir / "Master.xlsx"
    master_file.touch()

    config_ctl = MagicMock()
    config_ctl.config = {"paths": {"master_file": str(master_file)}}
    config_ctl.resolve_path = MagicMock(return_value=master_file)

    app_ctl = AppController(
        config_ctl, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock()
    )

    on_complete = MagicMock()
    mocker.patch("core.app_controller.check_master_lock", return_value=False)

    original_open = open

    def mock_open(file, mode="r", *args, **kwargs):
        if str(file) == str(master_file) and any(m in mode for m in "awx+"):
            raise PermissionError("File is locked")
        return original_open(file, mode, *args, **kwargs)

    with patch("builtins.open", side_effect=mock_open):
        with patch("threading.Thread") as mock_thread:

            def run_sync(target, daemon=False):
                target()

            mock_thread.return_value.start.side_effect = lambda: run_sync(
                mock_thread.call_args[1]["target"]
            )
            app_ctl.run_consolidation(MagicMock(), MagicMock(), on_complete)

    on_complete.assert_called_once()
    success, msg, path = on_complete.call_args[0]
    assert success is False
    assert any(x in msg.lower() for x in ["занят", "locked", "permission"])


# 5. Test Transaction Integrity
def test_transaction_integrity(temp_dir):
    db_path = temp_dir / "test.db"
    schema_path = Path("E:/Dlia Dashi/Version5/APP/db_schema.sql")
    manager = SQLiteManager(str(db_path), str(schema_path), {})

    # Mock sqlite3.connect to return a mock connection
    with patch("sqlite3.connect") as mock_connect:
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn

        manager.save_file_cache("path", 1.0, 100, ["2023"])
        manager.wait_for_writes()

    # Check if BEGIN TRANSACTION was called and commit was called
    calls = [
        call[0][0].upper()
        for call in mock_conn.execute.call_args_list
        if isinstance(call[0][0], str)
    ]
    assert any("BEGIN TRANSACTION" in c for c in calls)
    assert mock_conn.commit.call_count > 0
    manager.close()


# 6. Test MAX_PATH handling (forcing failure or checking implementation)
def test_max_path_save_force_long(temp_dir, mocker):
    # To really test MAX_PATH we'd need a deep directory structure exceeding 260 chars.
    # But we can also just verify that it uses the \\?\ prefix on Windows if path is long.

    # Let's mock os.replace and openpyxl.Workbook.save to see what paths they get.
    long_path_str = "C:\\" + "a" * 250 + "\\Master.xlsx"
    config = {"paths": {"master_file": long_path_str}}
    writer = MasterWriter(config)

    mock_wb = MagicMock()
    with patch("os.path.abspath", return_value=long_path_str):
        with patch("os.path.exists", return_value=True):
            with patch("os.replace") as mock_replace:
                with patch("os.remove"):
                    writer._save_workbook(mock_wb)

    # Check if save was called with a path starting with \\?\
    save_path = mock_wb.save.call_args[0][0]
    # In my implementation I should probably ensure it's handled.
    # For now it will probably fail this test because it doesn't do it yet.
    assert save_path.startswith("\\\\?\\")
