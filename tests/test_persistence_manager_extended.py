"""Расширенные тесты для persistence_manager.py."""
import pytest
import sqlite3
import json
import decimal
import datetime
import queue
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
from core.infra.persistence_manager import (
    SQLiteManager, DecimalEncoder, sanitize_data, DBWriterThread
)


@pytest.fixture
def db_setup(tmp_path):
    db_path = tmp_path / "test.db"
    # Create schema file
    schema_path = tmp_path / "schema.sql"
    schema_path.write_text("""
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    metadata TEXT,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS source_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    file_path TEXT,
    file_hash TEXT,
    inode INTEGER,
    status TEXT DEFAULT 'pending',
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);
CREATE TABLE IF NOT EXISTS staging_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER,
    row_index INTEGER,
    raw_content_json TEXT,
    date_val TEXT,
    amount NUMERIC,
    employee_name TEXT,
    source_type TEXT,
    FOREIGN KEY (file_id) REFERENCES source_files(id)
);
CREATE TABLE IF NOT EXISTS file_cache (
    file_path TEXT PRIMARY KEY,
    mtime REAL,
    size INTEGER,
    dates_json TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS template_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    file_path TEXT,
    sheet_name TEXT,
    row_index INTEGER,
    error_type TEXT,
    details TEXT,
    raw_data TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);
""", encoding='utf-8')
    config = {
        'locking': {'retry_count': 2, 'retry_backoff': 0.05},
        'database': {'timeout': 5.0}
    }
    return SQLiteManager(str(db_path), str(schema_path), config)


class TestFileCache:
    """Тесты file_cache — кеширование дат файлов."""

    def test_save_and_get_cache(self, db_setup):
        db_setup.save_file_cache("/path/file.xlsx", 1000.0, 5000, ['01.04.2026', '02.04.2026'])
        result = db_setup.get_file_cache("/path/file.xlsx")

        assert result is not None
        assert result['mtime'] == 1000.0
        assert result['size'] == 5000
        assert '01.04.2026' in result['dates']
        assert '02.04.2026' in result['dates']

    def test_get_cache_missing(self, db_setup):
        assert db_setup.get_file_cache("/missing.xlsx") is None

    def test_cache_overwrite(self, db_setup):
        db_setup.save_file_cache("/path/f.xlsx", 1000.0, 100, ['01.04.2026'])
        db_setup.save_file_cache("/path/f.xlsx", 2000.0, 200, ['02.04.2026'])

        result = db_setup.get_file_cache("/path/f.xlsx")
        assert result['mtime'] == 2000.0
        assert result['size'] == 200
        assert result['dates'] == ['02.04.2026']


class TestDBWriterThread:
    """Тесты DBWriterThread — асинхронная запись."""

    def test_writer_thread_starts(self, db_setup):
        assert db_setup.writer_thread.is_alive()

    def test_writer_thread_processes_queue(self, db_setup):
        session_id = "session1"
        db_setup.save_session(session_id, {})
        file_ids = db_setup.save_file_metadata(session_id, [{'path': 'f.xlsx'}])
        file_id = file_ids[0]

        rows = [{'_row_index': 1, 'date': '01.04.2026', 'amount': 100, 'employee_name': 'Test', 'source_type': 'Staff'}]
        db_setup.save_staging_data(file_id, rows)

        # Подождать обработки
        time.sleep(0.2)

        # Проверить что данные записаны
        with sqlite3.connect(db_setup.db_path) as conn:
            conn.row_factory = sqlite3.Row
            count = conn.execute("SELECT COUNT(*) as cnt FROM staging_data WHERE file_id = ?", (file_id,)).fetchone()['cnt']
            assert count == 1

    def test_writer_thread_stop(self, db_setup):
        db_setup.writer_thread.stop()
        db_setup.writer_thread.join(timeout=2.0)
        assert not db_setup.writer_thread.is_alive()

    def test_writer_thread_handles_error(self, db_setup, caplog):
        """Ошибка в обработке — логирование без падения."""
        db_setup.write_queue.put(("bad", "invalid_data"))
        time.sleep(0.3)
        # Поток должен продолжать работать
        assert db_setup.writer_thread.is_alive()


class TestGetConnection:
    """Тесты _get_connection."""

    def test_connection_pragmas(self, db_setup):
        conn = db_setup._get_connection()
        try:
            # Проверить WAL mode
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode == 'wal'

            # Проверить synchronous
            sync = conn.execute("PRAGMA synchronous").fetchone()[0]
            assert sync == 0  # OFF

            # Проверить temp_store
            temp = conn.execute("PRAGMA temp_store").fetchone()[0]
            assert temp == 2  # MEMORY
        finally:
            conn.close()


class TestMultipleSessions:
    """Тесты множественных сессий."""

    def test_two_concurrent_sessions(self, db_setup):
        db_setup.save_session("session_a", {"type": "daily", "date": "01.04.2026"})
        db_setup.save_session("session_b", {"type": "all_dates"})

        status_a = db_setup.get_session_status("session_a")
        status_b = db_setup.get_session_status("session_b")

        assert status_a['session_id'] == "session_a"
        assert status_b['session_id'] == "session_b"

    def test_session_with_multiple_files(self, db_setup):
        session_id = "multi_file"
        db_setup.save_session(session_id, {})

        files = [
            {'path': '/path/f1.xlsx', 'hash': 'h1', 'inode': 1},
            {'path': '/path/f2.xlsx', 'hash': 'h2', 'inode': 2},
            {'path': '/path/f3.xlsx', 'hash': 'h3', 'inode': 3},
        ]
        ids = db_setup.save_file_metadata(session_id, files)
        assert len(ids) == 3

        status = db_setup.get_session_status(session_id)
        assert status['file_stats'].get('pending', 0) == 3


class TestTemplateErrors:
    """Тесты template_errors."""

    def test_multiple_errors(self, db_setup):
        session_id = "err_session"
        db_setup.save_session(session_id, {})

        db_setup.save_template_error(session_id, {
            'file_path': 'f1.xlsx', 'sheet_name': 'Sheet1', 'row_index': 5,
            'error_type': 'missing_column', 'details': 'No amount column', 'raw_data': {}
        })
        db_setup.save_template_error(session_id, {
            'file_path': 'f2.xlsx', 'sheet_name': 'Sheet2', 'row_index': 10,
            'error_type': 'value_error', 'details': 'Invalid value', 'raw_data': {'x': 1}
        })

        errors = db_setup.get_template_errors(session_id)
        assert len(errors) == 2
        assert errors[0]['error_type'] == 'missing_column'
        assert errors[1]['error_type'] == 'value_error'

    def test_errors_sorted_by_file(self, db_setup):
        session_id = "sort_session"
        db_setup.save_session(session_id, {})

        db_setup.save_template_error(session_id, {
            'file_path': 'z_file.xlsx', 'sheet_name': 'S', 'row_index': 1,
            'error_type': 'e', 'details': '', 'raw_data': {}
        })
        db_setup.save_template_error(session_id, {
            'file_path': 'a_file.xlsx', 'sheet_name': 'S', 'row_index': 1,
            'error_type': 'e', 'details': '', 'raw_data': {}
        })

        errors = db_setup.get_template_errors(session_id)
        assert errors[0]['file_path'] == 'a_file.xlsx'
        assert errors[1]['file_path'] == 'z_file.xlsx'

    def test_errors_different_sessions(self, db_setup):
        db_setup.save_session("s1", {})
        db_setup.save_session("s2", {})

        db_setup.save_template_error("s1", {
            'file_path': 'f1.xlsx', 'sheet_name': 'S', 'row_index': 1,
            'error_type': 'e', 'details': '', 'raw_data': {}
        })
        db_setup.save_template_error("s2", {
            'file_path': 'f2.xlsx', 'sheet_name': 'S', 'row_index': 1,
            'error_type': 'e', 'details': '', 'raw_data': {}
        })

        errors_s1 = db_setup.get_template_errors("s1")
        errors_s2 = db_setup.get_template_errors("s2")

        assert len(errors_s1) == 1
        assert len(errors_s2) == 1


class TestEdgeCases:
    """Крайние случаи."""

    def test_empty_staging_data(self, db_setup):
        """Пустые данные — возврат без записи."""
        db_setup.save_staging_data(1, [])
        # Не должно выбрасывать

    def test_decimal_in_metadata(self, db_setup):
        session_id = "decimal_meta"
        metadata = {'amount': decimal.Decimal('1234.56'), 'rate': decimal.Decimal('0.025')}
        db_setup.save_session(session_id, metadata)

        status = db_setup.get_session_status(session_id)
        assert status['session_id'] == session_id

    def test_unicode_in_error_details(self, db_setup):
        session_id = "unicode_session"
        db_setup.save_session(session_id, {})

        db_setup.save_template_error(session_id, {
            'file_path': 'файл.xlsx', 'sheet_name': 'Лист1', 'row_index': 5,
            'error_type': 'Ошибка', 'details': 'Неверное значение: данные', 'raw_data': {'ключ': 'значение'}
        })

        errors = db_setup.get_template_errors(session_id)
        assert 'Ошибка' in errors[0]['error_type']

    def test_large_batch_staging_data(self, db_setup):
        session_id = "large_session"
        db_setup.save_session(session_id, {})
        file_ids = db_setup.save_file_metadata(session_id, [{'path': 'large.xlsx'}])
        file_id = file_ids[0]

        rows = [
            {'_row_index': i, 'date': '01.04.2026', 'amount': i * 10, 'employee_name': 'Emp', 'source_type': 'Staff'}
            for i in range(100)
        ]
        db_setup.save_staging_data(file_id, rows)

        time.sleep(0.5)

        with sqlite3.connect(db_setup.db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM staging_data WHERE file_id = ?", (file_id,)).fetchone()[0]
            assert count == 100
