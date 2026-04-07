import pytest
import sqlite3
import json
import decimal
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch
from core.infra.persistence_manager import (
    SQLiteConnectionManager, 
    SourceFileRepository, 
    StagingDataRepository, 
    SessionRepository,
    sanitize_data,
    DBWriterThread
)
from core.infra.config_controller import ConfigController

@pytest.fixture
def db_config():
    return {
        'locking': {'retry_count': 2, 'retry_backoff': 0.1},
        'database': {'timeout': 5.0}
    }

@pytest.fixture
def temp_db(tmp_path):
    return tmp_path / "test_v2.db"

@pytest.fixture
def schema_path():
    p = Path(__file__).parent.parent / "APP" / "db_schema.sql"
    return p

# --- SQLiteConnectionManager Tests ---
def test_connection_manager_init_and_get(temp_db, db_config):
    mgr = SQLiteConnectionManager(temp_db, db_config)
    conn = mgr.get_connection()
    assert isinstance(conn, sqlite3.Connection)
    # Check PRAGMAs
    row = conn.execute("PRAGMA journal_mode").fetchone()
    assert row['journal_mode'].lower() == 'wal'
    conn.close()

def test_connection_manager_init_db(temp_db, db_config, schema_path):
    mgr = SQLiteConnectionManager(temp_db, db_config)
    mgr.init_db(schema_path)
    with mgr.get_connection() as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r['name'] for r in cursor.fetchall()]
        assert "sessions" in tables
        assert "source_files" in tables
        assert "staging_data" in tables

def test_connection_manager_execute_with_retry_custom(temp_db, db_config, mocker):
    mgr = SQLiteConnectionManager(temp_db, db_config)
    mock_func = MagicMock(side_effect=[sqlite3.OperationalError("database is locked"), "done"])
    mocker.patch("time.sleep")
    res = mgr.execute_with_retry(mock_func)
    assert res == "done"
    assert mock_func.call_count == 2

# --- SourceFileRepository Tests ---
def test_source_file_repo_save_metadata(temp_db, db_config, schema_path):
    mgr = SQLiteConnectionManager(temp_db, db_config)
    mgr.init_db(schema_path)
    repo = SourceFileRepository(mgr)
    
    # Needs session first
    session_repo = SessionRepository(str(temp_db), str(schema_path), db_config)
    session_repo.save_session("s1", {})
    
    ids = repo.save_file_metadata("s1", [{"path": "p1", "hash": "h1", "inode": 1, "status": "pending"}])
    assert len(ids) == 1
    assert ids[0] is not None

def test_source_file_repo_cache(temp_db, db_config, schema_path):
    mgr = SQLiteConnectionManager(temp_db, db_config)
    mgr.init_db(schema_path)
    repo = SourceFileRepository(mgr)
    
    repo.save_file_cache("path1", 123.45, 1000, ["2023-01-01"])
    cache = repo.get_file_cache("path1")
    assert cache["mtime"] == 123.45
    assert cache["size"] == 1000
    assert cache["dates"] == ["2023-01-01"]
    
    assert repo.get_file_cache("nonexistent") is None

# --- StagingDataRepository Tests ---
def test_staging_data_repo_save_and_get(temp_db, db_config, schema_path):
    mgr = SQLiteConnectionManager(temp_db, db_config)
    mgr.init_db(schema_path)
    repo = StagingDataRepository(mgr)
    source_repo = SourceFileRepository(mgr)
    
    # Setup session and file
    session_repo = SessionRepository(str(temp_db), str(schema_path), db_config)
    session_repo.save_session("s1", {})
    file_ids = source_repo.save_file_metadata("s1", [{"path": "p1"}])
    
    rows = [{"_row_index": 1, "employee_name": "Emp1", "amount": 10.0, "date": "2023-01-01", "source_type": "T1"}]
    repo.save_staging_data(file_ids[0], rows)
    
    # Wait for writer thread by closing (it joins)
    repo.close() 
    
    consolidated = repo.get_consolidated_data("s1")
    assert len(consolidated) == 1
    assert consolidated[0]["employee_name"] == "Emp1"

# --- Atomicity and Rollback Tests ---
def test_rollback_on_save_metadata_failure(temp_db, db_config, schema_path, mocker):
    mgr = SQLiteConnectionManager(temp_db, db_config)
    mgr.init_db(schema_path)
    repo = SourceFileRepository(mgr)
    
    # Mock connection to fail during commit
    mock_conn = MagicMock()
    mock_conn.commit.side_effect = Exception("Crash")
    mocker.patch.object(mgr, 'get_connection', return_value=mock_conn)
    
    with pytest.raises(Exception, match="Crash"):
        repo.save_file_metadata("s1", [{"path": "p1"}])
    
    mock_conn.rollback.assert_called_once()
    mock_conn.close.assert_called_once()

def test_rollback_on_save_cache_failure(temp_db, db_config, schema_path, mocker):
    mgr = SQLiteConnectionManager(temp_db, db_config)
    mgr.init_db(schema_path)
    repo = SourceFileRepository(mgr)
    
    mock_conn = MagicMock()
    mock_conn.commit.side_effect = Exception("Crash")
    mocker.patch.object(mgr, 'get_connection', return_value=mock_conn)
    
    with pytest.raises(Exception, match="Crash"):
        repo.save_file_cache("p1", 1.0, 1, [])
    
    mock_conn.rollback.assert_called_once()
    mock_conn.close.assert_called_once()

# --- ConfigController Mutation and Error Coverage ---
def test_config_controller_metadata_error_coverage(tmp_path, caplog):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("employees: []\nemployee_paths: {}", encoding='utf-8')
    cc = ConfigController(str(cfg_file))
    
    f = tmp_path / "broken.xlsx"
    f.write_text("content")
    
    # Mock hashlib.md5 to fail to trigger the except block inside the loop
    with patch("hashlib.md5", side_effect=Exception("Hash failed")):
        cc.attach_files("Emp1", [str(f)])
    
    assert "Error generating metadata" in caplog.text
    paths = cc.config["employee_paths"]["Emp1"]
    assert len(paths) == 1
    assert paths[0]["path"] == str(f)
    assert "id" not in paths[0]  # Error block appends only 'path'

def test_config_controller_attach_files_merging(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("employee_paths: {Emp1: [{path: p1}]}", encoding='utf-8')
    cc = ConfigController(str(cfg_file))
    
    f2 = tmp_path / "p2.xlsx"
    f2.write_text("content")
    
    # Append mode
    cc.attach_files("Emp1", [str(f2)], append=True)
    assert len(cc.config["employee_paths"]["Emp1"]) == 2
    
    # Replace mode
    cc.attach_files("Emp1", [str(f2)], append=False)
    assert len(cc.config["employee_paths"]["Emp1"]) == 1
    assert cc.config["employee_paths"]["Emp1"][0]["path"] == str(f2)

def test_staging_data_repo_writer_thread_error_handling(temp_db, db_config, schema_path, mocker, caplog):
    # This tests lines 111-113 in persistence_manager.py
    mgr = SQLiteConnectionManager(temp_db, db_config)
    mgr.init_db(schema_path)
    
    # Mock connection to fail
    mock_conn = MagicMock()
    # Raise error during commit
    mock_conn.commit.side_effect = Exception("Writer Crash")
    mocker.patch.object(mgr, 'get_connection', return_value=mock_conn)
    
    import queue
    q = queue.Queue()
    writer = DBWriterThread(mgr, q)
    
    # Process one item, it re-raises Exception
    with pytest.raises(Exception, match="Writer Crash"):
        writer._process_item((1, [{"_row_index": 1, "amount": 10, "employee_name": "E1", "date": "2023-01-01", "source_type": "T"}]))
    
    mock_conn.rollback.assert_called_once()
    mock_conn.close.assert_called_once()

def test_session_repo_save_template_error_rollback(temp_db, db_config, schema_path, mocker):
    # Tests lines 273-275
    repo = SessionRepository(str(temp_db), str(schema_path), db_config)
    
    mock_conn = MagicMock()
    mock_conn.commit.side_effect = Exception("Template Error Crash")
    mocker.patch.object(repo, '_get_connection', return_value=mock_conn)
    
    with pytest.raises(Exception, match="Template Error Crash"):
        repo.save_template_error("s1", {"error_type": "E1"})
        
    mock_conn.rollback.assert_called_once()
    mock_conn.close.assert_called_once()

def test_sanitize_data_coverage():
    # Test decimal, date, datetime in sanitize_data
    import datetime
    from decimal import Decimal
    data = {
        "dec": Decimal("1.5"),
        "date": datetime.date(2023, 1, 1),
        "dt": datetime.datetime(2023, 1, 1, 12, 0, 0),
        "list": [Decimal("2.5")],
        "nested": {"a": Decimal("3.5")}
    }
    san = sanitize_data(data)
    assert san["dec"] == "1.5"
    assert san["date"] == "2023-01-01"
    assert san["dt"] == "2023-01-01T12:00:00"
    assert san["list"] == ["2.5"]
    assert san["nested"]["a"] == "3.5"
