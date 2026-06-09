import pytest
from pathlib import Path
from core.infra.ingestion_reader import extract_date_from_sheet
from core.infra.ingestion_engine import IngestionEngine
from core.infra.source_file_repo import SourceFileRepository
from core.infra.db_connection import SQLiteConnectionManager
import threading
import sqlite3
import os

def test_extract_date_from_sheet_with_year_hint():
    date_str = extract_date_from_sheet("01.01", year_hint=2024)
    assert date_str == "01.01.2024", "Bug: extract_date_from_sheet ignores year_hint for missing year"

def test_extract_date_from_sheet_returns_dict():
    res = extract_date_from_sheet("01.01", with_year_hint=True, year_hint=2024)
    assert res is not None, "Bug: extract_date_from_sheet returns None when year is missing, even with year_hint"

def test_duplicate_metadata_read_bug(monkeypatch):
    calls = []
    def mock_try_get(path):
        calls.append(path)
        return None
        
    monkeypatch.setattr("core.infra.ingestion_engine._try_get_xlsx_sheet_dates_from_metadata", mock_try_get)
    monkeypatch.setattr("core.infra.ingestion_engine.get_local_copy", lambda p, d, remote_mtime=None, remote_size=None: ("dummy_local.xlsx", None))
    
    engine = IngestionEngine({})
    engine.config = {"performance": {"isolate_calamine": True}}
    
    engine.get_available_dates(Path("Z:\\reports\\dummy.xlsx"))
    
    assert len(calls) <= 1, f"Bug: _try_get_xlsx_sheet_dates_from_metadata called {len(calls)} times (duplicate code)"

def test_source_file_repo_duplicate_items(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE source_files (id INTEGER PRIMARY KEY, session_id TEXT, file_path TEXT, file_hash TEXT, inode INTEGER, status TEXT)")
    conn.commit()
    conn.close()
    
    manager = SQLiteConnectionManager(db_path, {})
    repo = SourceFileRepository(manager)
    
    session_id = "test-session"
    files = [{"path": "Z:\\reports\\data.xlsx", "hash": "abc", "id": 123}]
    
    repo.save_file_metadata(session_id, files)
    repo.save_file_metadata(session_id, files)
    
    conn = manager.get_connection()
    count = conn.execute("SELECT COUNT(*) FROM source_files WHERE session_id = ? AND file_path = ?", (session_id, "Z:\\reports\\data.xlsx")).fetchone()[0]
    conn.close()
    
    assert count == 1, "Bug: save_file_metadata creates duplicate entries in DB"

def test_get_local_copy_race_condition():
    import core.infra.utils
    from threading import Lock
    lock_type = type(Lock())
    assert not isinstance(core.infra.utils._CACHE_COPY_LOCK, lock_type), "Bug: get_local_copy uses threading.Lock which is not process-safe for calamine worker."

def test_read_file_bypasses_local_copy_for_worker(monkeypatch):
    calls = []
    def mock_worker(mode, target_path, *args, **kwargs):
        calls.append(target_path)
        return {"ok": True, "result": []}
        
    monkeypatch.setattr("core.infra.ingestion_engine._run_calamine_worker", mock_worker)
    monkeypatch.setattr(
        "core.infra.ingestion_engine.get_local_copy",
        lambda path, dest, remote_mtime=None, remote_size=None: ("/tmp/local_copy.xlsx", None),
    )

    engine = IngestionEngine({})
    engine.config = {"performance": {"isolate_calamine": True}}
    engine.read_file(Path("Z:\\reports\\remote_file.xlsx"))

    assert len(calls) == 1
    assert "remote_file.xlsx" not in calls[0], "Bug: read_file passes remote path directly to worker instead of local copy"
