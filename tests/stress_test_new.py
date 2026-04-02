import os
import pytest
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pandas as pd
from datetime import datetime
import sqlite3
import json

from core.app_controller import AppController
from core.infra.persistence_manager import SQLiteManager
from core.infra.ingestion_engine import IngestionEngine

@pytest.fixture
def temp_db(tmp_path):
    db_path = tmp_path / "test_stress.db"
    # Find schema path relative to project root
    schema_path = Path("APP/db_schema.sql")
    if not schema_path.exists():
        # Try to find it from current file location
        schema_path = Path(__file__).parent.parent / "APP" / "db_schema.sql"
    
    config = {
        "database": {"use_wal": True, "timeout": 30.0},
        "locking": {"retry_count": 10, "retry_backoff": 0.1}
    }
    
    manager = SQLiteManager(str(db_path), str(schema_path), config)
    yield manager
    manager.close()

@pytest.fixture
def stress_files(tmp_path):
    files_dir = tmp_path / "stress_files"
    files_dir.mkdir()
    file_paths = []
    for i in range(30):
        p = files_dir / f"employee_{i}.xlsx"
        # Create a simple XLSX file with a date in a sheet name
        # CalamineReader and IngestionEngine look for dates in sheet names
        with pd.ExcelWriter(p, engine='openpyxl') as writer:
            df = pd.DataFrame({"Сумма": [100], "Дата": ["01.01.2024"]})
            df.to_excel(writer, sheet_name="01.01.2024", index=False)
        file_paths.append(p)
    return file_paths

def test_parallel_refresh_stress(temp_db, stress_files):
    # Setup dependencies
    config_controller = MagicMock()
    config_controller.config = {"employees": [], "employee_paths": {}, "paths": {}}
    
    ingestion = IngestionEngine({})
    validator = MagicMock()
    logic_service = MagicMock()
    writer = MagicMock()
    
    controller = AppController(config_controller, ingestion, temp_db, validator, logic_service, writer)
    
    # Mock DiscoveryService to return our 30 files
    employees_map = {f"Emp_{i}": [{"path": str(p)}] for i, p in enumerate(stress_files)}
    controller.discovery.get_employees_map = MagicMock(return_value=employees_map)
    
    selected_date = datetime(2024, 1, 1)
    
    completion_event = threading.Event()
    results = []
    
    def on_progress(p):
        pass
        
    def on_complete(data, emp_map, rename):
        results.extend(data)
        completion_event.set()
        
    # Act
    controller.refresh_status(selected_date, on_progress, on_complete)
    
    # Wait for completion (with timeout)
    assert completion_event.wait(timeout=60), "Refresh status timed out"
    
    # Assert
    assert len(results) == 30
    for name, status, path_str, tag in results:
        assert status == "🟢 ГОТОВО", f"Employee {name} failed with status {status}"
        assert tag == "ready"
        
    # Verify SQLite file_cache
    with temp_db._get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM file_cache").fetchone()[0]
        assert count == 30
        
        # Check one entry
        row = conn.execute("SELECT * FROM file_cache LIMIT 1").fetchone()
        assert row['file_path'].endswith(".xlsx")
        dates = json.loads(row['dates_json'])
        assert "01.01.2024" in dates

def test_sqlite_concurrent_writes_direct(temp_db):
    # Directly test concurrent writes to file_cache to ensure WAL and retries work
    num_threads = 16
    num_writes_per_thread = 20
    
    def write_task(thread_id):
        for i in range(num_writes_per_thread):
            file_path = f"file_{thread_id}_{i}.xlsx"
            temp_db.save_file_cache(file_path, 123.456, 1000, ["01.01.2024"])
            
    threads = []
    for i in range(num_threads):
        t = threading.Thread(target=write_task, args=(i,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    with temp_db._get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM file_cache").fetchone()[0]
        assert count == num_threads * num_writes_per_thread
