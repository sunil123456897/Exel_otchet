
import os
import sys
import time
import unittest
import threading
import decimal
import logging
import sqlite3
import pandas as pd
from pathlib import Path

# Add APP to sys.path to allow imports like 'core.infra.persistence_manager'
APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'APP'))
sys.path.append(APP_ROOT)

try:
    import psutil
except ImportError:
    psutil = None

from core.infra.ingestion_core import CalamineReader
from core.infra.persistence_manager import SQLiteManager
from core.domain.data_schemas import FinancialRowSchema

# Mock markers for CalamineReader
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

class TestStressSQLiteWAL(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Base path for DB and schema
        cls.test_db = os.path.abspath(os.path.join(os.path.dirname(__file__), 'stress_test_db.sqlite'))
        cls.schema_path = os.path.join(APP_ROOT, 'db_schema.sql')
        
        # Consistent config with app
        cls.config = {
            'database': {'timeout': 60.0, 'use_wal': True},
            'locking': {'retry_count': 15, 'retry_backoff': 0.2}
        }
        
        if os.path.exists(cls.test_db):
            try: os.remove(cls.test_db)
            except: pass
            
        cls.db_manager = SQLiteManager(cls.test_db, cls.schema_path, cls.config)
        
        cls.large_file = os.path.abspath('ultra_large_150k.xlsx')
        if not os.path.exists(cls.large_file):
            print(f'Generating {cls.large_file} with 150,000 rows...')
            start_gen = time.time()
            data = {
                'дата': ['01.01.2024'] * 150000,
                'клиент': ['Client_' + str(i % 100) for i in range(150000)],
                'сумма': [100.50 + i for i in range(150000)],
                'приход': [50.0] * 150000,
                'расход': [20.0] * 150000,
                'комиссия': [5.0] * 150000
            }
            df = pd.DataFrame(data)
            # Use xlsxwriter for speed
            with pd.ExcelWriter(cls.large_file, engine='xlsxwriter') as writer:
                df.to_excel(writer, sheet_name='01.01.2024', index=False)
            print(f'Generation complete in {time.time() - start_gen:.2f} seconds.')

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'db_manager'):
            cls.db_manager.close()
        
        # Cleanup DB
        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'stress_test_db.sqlite'))
        for suffix in ['', '-wal', '-shm']:
            f = db_path + suffix
            if os.path.exists(f):
                try: os.remove(f)
                except: pass
        
        # Cleanup large file
        large_file = os.path.abspath('ultra_large_150k.xlsx')
        if os.path.exists(large_file):
            try: os.remove(large_file)
            except: pass

    def test_ultra_large_file(self):
        print('\n--- [KPI] Testing Ultra Large File Parsing (150,000 rows) ---')
        reader = CalamineReader(MARKERS, ALIASES)
        start_time = time.time()
        rows = reader.read(Path(self.large_file))
        duration = time.time() - start_time
        
        print(f'Parsed rows count: {len(rows)}')
        print(f'Execution time: {duration:.4f} seconds.')
        
        # KPI: < 5 seconds
        self.assertLess(duration, 5.0, f'KPI Failed: Parsing took {duration:.2f}s (limit: 5s)')
        # Rows should be >= 150,000
        self.assertGreaterEqual(len(rows), 150000, 'Should find all rows')

    def test_sqlite_wal_stress(self):
        print('\n--- [Stress] Testing SQLite WAL (16 threads concurrent writes) ---')
        num_threads = 16
        rows_per_thread = 500
        errors = []

        def worker(thread_id):
            session_id = f'stress_session_{thread_id}'
            try:
                # 1. Save Session
                self.db_manager.save_session(session_id, {'thread': thread_id, 'timestamp': time.time()})
                
                # 2. Save File Metadata
                file_ids = self.db_manager.save_file_metadata(session_id, [{'path': f'stress_file_{thread_id}.xlsx', 'status': 'pending'}])
                file_id = file_ids[0]
                
                # 3. Save Staging Data in chunks
                test_rows = [
                    {
                        '_row_index': i, 
                        'date': '01.01.2024', 
                        'amount': 100.0, 
                        'employee_name': f'Worker_{thread_id}', 
                        'source_type': 'stress_test',
                        'customer': f'Cust_{i}'
                    }
                    for i in range(rows_per_thread)
                ]
                self.db_manager.save_staging_data(file_id, test_rows[:250])
                self.db_manager.save_staging_data(file_id, test_rows[250:])
                
            except Exception as e:
                errors.append(f'Thread {thread_id} error: {e}')

        threads = []
        for i in range(num_threads):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        if errors:
            for err in errors:
                print(err)
        
        self.assertEqual(len(errors), 0, f'Found {len(errors)} locked or other errors during concurrent write stress.')
        print(f'Successfully performed {num_threads} concurrent sessions/writes with WAL.')

    def test_memory_efficiency(self):
        if not psutil:
            self.skipTest('psutil not installed')
            
        print('\n--- [Memory] Testing Memory Efficiency ---')
        process = psutil.Process(os.getpid())
        mem_before = process.memory_info().rss / (1024 * 1024)
        print(f'Base Memory usage: {mem_before:.2f} MB')
        
        reader = CalamineReader(MARKERS, ALIASES)
        rows = reader.read(Path(self.large_file))
        
        mem_after = process.memory_info().rss / (1024 * 1024)
        print(f'Memory usage after parsing 150k rows: {mem_after:.2f} MB')
        print(f'Total delta: {mem_after - mem_before:.2f} MB')
        
        # 1.2GB threshold is safe for 150k rows
        self.assertLess(mem_after - mem_before, 1200, 'Memory footprint exceeded 1.2GB delta')

if __name__ == '__main__':
    unittest.main()
