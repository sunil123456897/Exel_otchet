import os
import sys
import time
import threading
import pandas as pd
import sqlite3
import decimal
from pathlib import Path
import logging

# Add APP to sys.path
APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'APP'))
sys.path.append(APP_ROOT)

from core.infra.ingestion_reader import CalamineReader
from core.infra.session_repo import SQLiteManager

# Configure logging to be less noisy
logging.basicConfig(level=logging.ERROR)

# App markers and aliases
MARKERS = {
    'date': 'дата',
    'customer': 'клиент',
    'contractor': 'контрагент',
    'amount': 'сумма',
    'income': 'приход',
    'expense': 'расход',
    'commission': 'комиссия'
}
ALIASES = {
    'amount': ['выплата', 'всего'],
    'customer': ['фио', 'сотрудник']
}

def generate_150k_data(file_path):
    if os.path.exists(file_path):
        return
    print(f"Generating benchmark data (150,000 rows)...")
    data = {
        'дата': ['01.01.2024'] * 150000,
        'клиент': [f'Client_{i % 100}' for i in range(150000)],
        'сумма': [100.50 + i for i in range(150000)],
        'приход': [50.0] * 150000,
        'расход': [20.0] * 150000,
        'комиссия': [5.0] * 150000
    }
    df = pd.DataFrame(data)
    with pd.ExcelWriter(file_path, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='01.01.2024', index=False)

def run_parsing_benchmark():
    file_path = Path("benchmark_150k.xlsx")
    generate_150k_data(file_path)
    
    reader = CalamineReader(MARKERS, ALIASES)
    
    # 1. Cold Start
    start = time.time()
    rows = reader.read(file_path)
    cold_duration = time.time() - start
    
    # 2. Hot Start (same process, OS cache, pre-loaded structures)
    start = time.time()
    rows = reader.read(file_path)
    hot_duration = time.time() - start
    
    if os.path.exists(file_path):
        os.remove(file_path)
        
    return cold_duration, hot_duration

def run_concurrency_audit():
    db_path = "benchmark_concurrency.sqlite"
    schema_path = os.path.join(APP_ROOT, "db_schema.sql")
    config = {
        'database': {'timeout': 60.0, 'use_wal': True},
        'locking': {'retry_count': 30, 'retry_backoff': 0.1}
    }
    
    if os.path.exists(db_path):
        try: os.remove(db_path)
        except: pass
        
    manager = SQLiteManager(db_path, schema_path, config)
    num_threads = 16
    errors = []
    
    def worker(tid):
        session_id = f"bench_session_{tid}"
        try:
            manager.save_session(session_id, {"thread": tid})
            for f_idx in range(5):
                file_ids = manager.save_file_metadata(session_id, [{"path": f"fake_{tid}_{f_idx}.xlsx"}])
                file_id = file_ids[0]
                for chunk in range(3):
                    rows = [{"_row_index": i, "date": "01.01.2024", "amount": 100.0, "employee_name": f"W_{tid}", "source_type": "b"} for i in range(100)]
                    manager.save_staging_data(file_id, rows)
        except Exception as e:
            errors.append(f"Thread {tid} error: {e}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
    for t in threads: t.start()
    for t in threads: t.join()
    manager.close()
    
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            for suffix in ['-wal', '-shm']:
                if os.path.exists(db_path + suffix): os.remove(db_path + suffix)
        except: pass
            
    return errors

if __name__ == "__main__":
    cold, hot = run_parsing_benchmark()
    errors = run_concurrency_audit()
    
    print("## PERFORMANCE BENCHMARK RESULTS")
    print(f"- Cold Start: {cold:.4f}s")
    print(f"- Hot Start:  {hot:.4f}s")
    print(f"- Database Locks: {len(errors)} errors")
    print(f"- KPI Status: {'PASSED' if hot < 2.0 else 'FAILED (Previous: 3.72s, Goal: 2.0s, Current: ' + str(round(hot, 2)) + 's)'}")
    print(f"- Concurrency Status: {'PASSED' if len(errors) == 0 else 'FAILED'}")
