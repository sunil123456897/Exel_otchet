import sqlite3
import decimal
import json
import logging
import time
from typing import List, Dict, Any, Optional
from pathlib import Path
from .interfaces import IPersistence

class DecimalEncoder(json.JSONEncoder):
    """Custom JSON encoder to handle Decimal objects for SQLite storage."""
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return str(obj)
        return super(DecimalEncoder, self).default(obj)

class SQLiteManager(IPersistence):
    """
    Manages SQLite persistence with Decimal support for financial precision and WAL mode for network reliability.
    Implements IPersistence interface.
    """
    def __init__(self, db_path: str, schema_path: str, config: Dict[str, Any]):
        self.db_path = Path(db_path)
        self.schema_path = Path(schema_path)
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Locking/Retry parameters from config
        locking_cfg = config.get('locking', {})
        self.retry_count = locking_cfg.get('retry_count', 3)
        self.retry_backoff = locking_cfg.get('retry_backoff', 1.0)
        
        # Register Decimal adapters/converters for NUMERIC affinity
        self._setup_decimal_handling()
        self.init_db()

    def _setup_decimal_handling(self):
        """Ensures Python Decimal objects are stored correctly in SQLite NUMERIC columns."""
        sqlite3.register_adapter(decimal.Decimal, str)
        sqlite3.register_converter("NUMERIC", lambda v: decimal.Decimal(v.decode('utf-8')))

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.db_path, 
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=self.config.get('database', {}).get('timeout', 30.0)
        )
        conn.row_factory = sqlite3.Row
        
        # Enable WAL mode for better concurrency in network environments
        if self.config.get('database', {}).get('use_wal', True):
            conn.execute("PRAGMA journal_mode=WAL;")
        
        return conn

    def init_db(self) -> None:
        """Initializes the database using the provided SQL schema."""
        self.logger.info(f"Checking database initialization at {self.db_path}")
        
        # If DB exists, we just check connection. If not, we create it.
        db_exists = self.db_path.exists()
        
        with self._get_connection() as conn:
            if not db_exists:
                self.logger.info(f"Initializing new database from schema: {self.schema_path}")
                if not self.schema_path.exists():
                     self.logger.error(f"Schema file missing: {self.schema_path}")
                     return
                with open(self.schema_path, 'r', encoding='utf-8') as f:
                    schema_sql = f.read()
                conn.executescript(schema_sql)
            else:
                self.logger.debug("Database already exists.")

    def _execute_with_retry(self, func, *args, **kwargs):
        """Executes a database function with retries on Busy/Locked errors."""
        last_err = None
        for i in range(self.retry_count):
            try:
                return func(*args, **kwargs)
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e).lower() or "busy" in str(e).lower():
                    last_err = e
                    self.logger.warning(f"Database locked. Retry {i+1}/{self.retry_count} after {self.retry_backoff}s...")
                    time.sleep(self.retry_backoff)
                else:
                    raise
        raise last_err

    def save_session(self, session_id: str, metadata: Dict[str, Any]) -> None:
        def _save():
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO sessions (session_id, metadata) VALUES (?, ?)",
                    (session_id, json.dumps(metadata, ensure_ascii=False, cls=DecimalEncoder))
                )
        self._execute_with_retry(_save)

    def save_file_metadata(self, session_id: str, files: List[Dict[str, Any]]) -> List[int]:
        """Saves file metadata and returns generated IDs."""
        def _save():
            ids = []
            with self._get_connection() as conn:
                for f in files:
                    cursor = conn.execute(
                        """INSERT INTO source_files (session_id, file_path, file_hash, inode, status) 
                           VALUES (?, ?, ?, ?, ?)""",
                        (session_id, f['path'], f.get('hash'), f.get('inode'), f.get('status', 'pending'))
                    )
                    ids.append(cursor.lastrowid)
            return ids
        return self._execute_with_retry(_save)

    def save_staging_data(self, file_id: int, rows: List[Dict[str, Any]]) -> None:
        """Bulk inserts raw data rows into staging_data table."""
        if not rows:
            return
        
        def _save():
            sql = """INSERT INTO staging_data (file_id, row_index, raw_content_json, date_val, amount, employee_name, source_type) 
                     VALUES (?, ?, ?, ?, ?, ?, ?)"""
            
            data_to_insert = []
            for row in rows:
                amt = row.get('amount', 0)
                if not isinstance(amt, decimal.Decimal):
                    amt = decimal.Decimal(str(amt))
                    
                data_to_insert.append((
                    file_id,
                    row.get('_row_index'), # Fixed: added underscore to match IngestionEngine
                    json.dumps(row, ensure_ascii=False, cls=DecimalEncoder),
                    row.get('date'),
                    amt,
                    row.get('employee_name'),
                    row.get('source_type')
                ))
                
            with self._get_connection() as conn:
                conn.executemany(sql, data_to_insert)
        
        self._execute_with_retry(_save)

    def save_template_error(self, session_id: str, error_info: Dict[str, Any]) -> None:
        def _save():
            with self._get_connection() as conn:
                conn.execute(
                    """INSERT INTO template_errors (session_id, file_path, sheet_name, row_index, error_type, details, raw_data) 
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        session_id,
                        error_info.get('file_path'),
                        error_info.get('sheet_name'),
                        error_info.get('row_index'),
                        error_info.get('error_type'),
                        error_info.get('details'),
                        json.dumps(error_info.get('raw_data'), ensure_ascii=False, cls=DecimalEncoder)
                    )
                )
        self._execute_with_retry(_save)

    def get_template_errors(self, session_id: str) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM template_errors WHERE session_id = ? ORDER BY file_path, row_index"
        results = []
        with self._get_connection() as conn:
            cursor = conn.execute(sql, (session_id,))
            for row in cursor:
                results.append(dict(row))
        return results

    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            
            if not row:
                return {}
            
            stats = conn.execute(
                "SELECT status, COUNT(*) as cnt FROM source_files WHERE session_id = ? GROUP BY status",
                (session_id,)
            ).fetchall()
            
            return {
                "session_id": row['session_id'],
                "status": row['status'],
                "created_at": row['created_at'],
                "file_stats": {s['status']: s['cnt'] for s in stats}
            }

    def close(self) -> None:
        """Closing handled per-connection in _get_connection context managers."""
        pass

    def get_consolidated_data(self, session_id: str) -> List[Dict[str, Any]]:
        """Retrieves all staging rows for a session, ordered by employee and date."""
        sql = """
            SELECT 
                staging_data.raw_content_json,
                staging_data.employee_name,
                staging_data.date_val,
                staging_data.row_index,
                source_files.file_path
            FROM staging_data
            JOIN source_files ON staging_data.file_id = source_files.id
            WHERE source_files.session_id = ?
            ORDER BY staging_data.employee_name, staging_data.date_val
        """
        results = []
        with self._get_connection() as conn:
            cursor = conn.execute(sql, (session_id,))
            for row in cursor:
                data = json.loads(row['raw_content_json'])
                # Ensure employee_name and date are present
                if 'employee_name' not in data:
                    data['employee_name'] = row['employee_name']
                if 'date' not in data:
                    data['date'] = row['date_val']
                
                # Metadata for "Source" column: "filename.xlsx : Строка 123"
                file_name = Path(row['file_path']).name
                data['_source_info'] = f"{file_name} : Строка {row['row_index']}"
                
                results.append(data)
        return results

    def close(self) -> None:
        """Closes database connections. For SQLite with context managers, this is often a no-op unless persistent connections are used."""
        self.logger.info("Closing database manager.")
