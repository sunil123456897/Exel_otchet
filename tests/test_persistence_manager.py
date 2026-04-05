import pytest
import sqlite3
import json
import decimal
import datetime
from pathlib import Path
from core.infra.persistence_manager import SQLiteManager, DecimalEncoder, sanitize_data

@pytest.fixture
def db_setup(tmp_path):
    db_path = tmp_path / "test.db"
    # Use the project schema file
    project_root = Path(__file__).parent.parent / "APP"
    schema_path = project_root / "db_schema.sql"
    config = {
        'locking': {'retry_count': 2, 'retry_backoff': 0.1},
        'database': {'timeout': 5.0, 'use_wal': False}
    }
    # Copy schema to tmp_path so SQLite can find it
    if schema_path.exists():
        import shutil
        local_schema = tmp_path / "schema.sql"
        shutil.copy2(schema_path, local_schema)
        schema_path = local_schema
    return db_path, schema_path, config

def test_sqlite_manager_init(db_setup):
    db_path, schema_path, config = db_setup
    manager = SQLiteManager(str(db_path), str(schema_path), config)
    assert db_path.exists()
    
    # Check if tables were created
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'")
        assert cursor.fetchone() is not None

def test_save_session(db_setup):
    db_path, schema_path, config = db_setup
    manager = SQLiteManager(str(db_path), str(schema_path), config)
    session_id = "test_session"
    metadata = {"key": "value", "amount": decimal.Decimal("10.50")}
    manager.save_session(session_id, metadata)
    
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        assert row['session_id'] == session_id
        saved_metadata = json.loads(row['metadata'])
        assert saved_metadata['key'] == "value"
        assert saved_metadata['amount'] == "10.50"

def test_save_file_metadata(db_setup):
    db_path, schema_path, config = db_setup
    manager = SQLiteManager(str(db_path), str(schema_path), config)
    session_id = "test_session"
    manager.save_session(session_id, {})
    
    files = [
        {'path': 'file1.xlsx', 'hash': 'h1', 'inode': 123, 'status': 'pending'},
        {'path': 'file2.xlsx', 'hash': 'h2', 'inode': 456}
    ]
    ids = manager.save_file_metadata(session_id, files)
    assert len(ids) == 2
    
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM source_files WHERE session_id = ?", (session_id,)).fetchall()
        assert len(rows) == 2

def test_save_staging_data(db_setup):
    import time
    db_path, schema_path, config = db_setup
    manager = SQLiteManager(str(db_path), str(schema_path), config)
    session_id = "test_session"
    manager.save_session(session_id, {})
    file_ids = manager.save_file_metadata(session_id, [{'path': 'f1'}])
    file_id = file_ids[0]

    rows = [
        {'_row_index': 1, 'date': '2023-01-01', 'amount': 100.0, 'employee_name': 'John', 'source_type': 'Staff'},
        {'_row_index': 2, 'date': '2023-01-02', 'amount': 200.0, 'employee_name': 'Jane', 'source_type': 'OPT'}
    ]
    manager.save_staging_data(file_id, rows)

    # Wait for async writer thread
    time.sleep(0.3)

    with sqlite3.connect(db_path) as conn:
        db_rows = conn.execute("SELECT * FROM staging_data WHERE file_id = ?", (file_id,)).fetchall()
        assert len(db_rows) == 2

    manager.close()

def test_save_staging_data_empty(db_setup):
    db_path, schema_path, config = db_setup
    manager = SQLiteManager(str(db_path), str(schema_path), config)
    manager.save_staging_data(1, []) # Should return early

def test_save_template_error(db_setup):
    db_path, schema_path, config = db_setup
    manager = SQLiteManager(str(db_path), str(schema_path), config)
    session_id = "test_session"
    manager.save_session(session_id, {})
    
    error_info = {
        'file_path': 'f1.xlsx',
        'sheet_name': 'Sheet1',
        'row_index': 5,
        'error_type': 'ValueMismatch',
        'details': 'Error details',
        'raw_data': {'col1': 'val1'}
    }
    manager.save_template_error(session_id, error_info)
    
    errors = manager.get_template_errors(session_id)
    assert len(errors) == 1
    assert errors[0]['error_type'] == 'ValueMismatch'

def test_get_consolidated_data(db_setup):
    import time
    db_path, schema_path, config = db_setup
    manager = SQLiteManager(str(db_path), str(schema_path), config)
    session_id = "test_session"
    manager.save_session(session_id, {})
    file_ids = manager.save_file_metadata(session_id, [{'path': 'f1.xlsx'}])
    file_id = file_ids[0]

    rows = [{'_row_index': 1, 'date': '2023-01-01', 'amount': 100.0, 'employee_name': 'John', 'source_type': 'Staff'}]
    manager.save_staging_data(file_id, rows)

    # Wait for async writer
    time.sleep(0.3)

    consolidated = manager.get_consolidated_data(session_id)
    assert len(consolidated) == 1
    assert consolidated[0]['employee_name'] == 'John'
    assert '_source_info' in consolidated[0]

    manager.close()

def test_get_session_status(db_setup):
    db_path, schema_path, config = db_setup
    manager = SQLiteManager(str(db_path), str(schema_path), config)
    session_id = "test_session"
    manager.save_session(session_id, {})
    manager.save_file_metadata(session_id, [{'path': 'f1', 'status': 'processed'}, {'path': 'f2', 'status': 'pending'}])

    status = manager.get_session_status(session_id)
    assert status['session_id'] == session_id
    assert status['file_stats']['processed'] == 1
    assert status['file_stats']['pending'] == 1
    manager.close()

def test_get_session_status_not_found(db_setup):
    db_path, schema_path, config = db_setup
    manager = SQLiteManager(str(db_path), str(schema_path), config)
    assert manager.get_session_status("non_existent") == {}
    manager.close()

def test_execute_with_retry_locked(db_setup, mocker):
    db_path, schema_path, config = db_setup
    manager = SQLiteManager(str(db_path), str(schema_path), config)
    
    mock_func = mocker.Mock(side_effect=[sqlite3.OperationalError("database is locked"), "success"])
    mocker.patch("time.sleep") # Don't actually sleep
    
    result = manager._execute_with_retry(mock_func)
    assert result == "success"
    assert mock_func.call_count == 2

def test_execute_with_retry_fail(db_setup, mocker):
    db_path, schema_path, config = db_setup
    manager = SQLiteManager(str(db_path), str(schema_path), config)
    
    mock_func = mocker.Mock(side_effect=sqlite3.OperationalError("database is locked"))
    mocker.patch("time.sleep")
    
    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        manager._execute_with_retry(mock_func)
    assert mock_func.call_count == config['locking']['retry_count']

def test_execute_with_retry_other_error(db_setup, mocker):
    db_path, schema_path, config = db_setup
    manager = SQLiteManager(str(db_path), str(schema_path), config)
    
    mock_func = mocker.Mock(side_effect=sqlite3.OperationalError("other error"))
    
    with pytest.raises(sqlite3.OperationalError, match="other error"):
        manager._execute_with_retry(mock_func)
    assert mock_func.call_count == 1

def test_sanitize_data():
    data = {
        'd': decimal.Decimal('1.23'),
        'l': [decimal.Decimal('4.56')],
        'dt': datetime.date(2023, 1, 1),
        'nested': {'a': 1}
    }
    sanitized = sanitize_data(data)
    assert sanitized['d'] == '1.23'
    assert sanitized['l'] == ['4.56']
    assert sanitized['dt'] == '2023-01-01'
    assert sanitized['nested']['a'] == 1

def test_decimal_encoder():
    encoder = DecimalEncoder()
    assert encoder.default(decimal.Decimal('1.23')) == '1.23'
    assert encoder.default(datetime.date(2023, 1, 1)) == '2023-01-01'
    with pytest.raises(TypeError):
        encoder.default(object())

def test_rollback_on_error(db_setup, mocker):
    db_path, schema_path, config = db_setup
    manager = SQLiteManager(str(db_path), str(schema_path), config)
    session_id = "test_session"
    
    # Mock connection to fail during commit
    mock_conn = mocker.Mock()
    mock_conn.execute.return_value = mocker.Mock()
    mock_conn.commit.side_effect = Exception("Commit failed")
    mocker.patch.object(manager, '_get_connection', return_value=mock_conn)
    
    with pytest.raises(Exception, match="Commit failed"):
        manager.save_session(session_id, {})
    
    mock_conn.rollback.assert_called_once()
    mock_conn.close.assert_called_once()

def test_close(db_setup, caplog):
    db_path, schema_path, config = db_setup
    manager = SQLiteManager(str(db_path), str(schema_path), config)
    with caplog.at_level("INFO"):
        manager.close()
    assert "Closing database manager." in caplog.text
