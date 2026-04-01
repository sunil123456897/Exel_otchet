import sqlite3
import json
import logging
import time
import decimal
import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
from core.interfaces import IPersistence

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, decimal.Decimal): return str(obj)
        if hasattr(obj, 'isoformat'): return obj.isoformat()
        return super(DecimalEncoder, self).default(obj)

def sanitize_data(data: Any) -> Any:
    if isinstance(data, dict): return {str(k): sanitize_data(v) for k, v in data.items()}
    elif isinstance(data, list): return [sanitize_data(i) for i in data]
    elif isinstance(data, (decimal.Decimal, datetime.date, datetime.datetime)): return str(data) if isinstance(data, decimal.Decimal) else data.isoformat()
    return data

class SQLiteManager(IPersistence):
    def __init__(self, db_path: str, schema_path: str, config: Dict[str, Any]):
        self.db_path, self.schema_path, self.config = Path(db_path), Path(schema_path), config
        self.logger = logging.getLogger(__name__)
        self.retry_count = config.get('locking', {}).get('retry_count', 3)
        self.retry_backoff = config.get('locking', {}).get('retry_backoff', 1.0)
        sqlite3.register_adapter(decimal.Decimal, str)
        sqlite3.register_converter("NUMERIC", lambda v: decimal.Decimal(v.decode('utf-8')))
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, detect_types=sqlite3.PARSE_DECLTYPES, timeout=self.config.get('database', {}).get('timeout', 30.0))
        conn.row_factory = sqlite3.Row
        if self.config.get('database', {}).get('use_wal', True): conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def init_db(self) -> None:
        if not self.db_path.exists() and self.schema_path.exists():
            with self._get_connection() as conn:
                with open(self.schema_path, 'r', encoding='utf-8') as f: conn.executescript(f.read())

    def _execute_with_retry(self, func, *args, **kwargs):
        last_err = None
        for i in range(self.retry_count):
            try: return func(*args, **kwargs)
            except sqlite3.OperationalError as e:
                if any(x in str(e).lower() for x in ["locked", "busy"]): last_err = e; time.sleep(self.retry_backoff)
                else: raise
        raise last_err

    def save_session(self, session_id: str, metadata: Dict[str, Any]) -> None:
        def _save():
            conn = self._get_connection()
            try:
                conn.execute("BEGIN TRANSACTION")
                conn.execute("INSERT INTO sessions (session_id, metadata) VALUES (?, ?)", (session_id, json.dumps(metadata, ensure_ascii=False, cls=DecimalEncoder)))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        self._execute_with_retry(_save)

    def save_file_metadata(self, session_id: str, files: List[Dict[str, Any]]) -> List[int]:
        def _save():
            ids = []
            conn = self._get_connection()
            try:
                conn.execute("BEGIN TRANSACTION")
                for f in files: 
                    cur = conn.execute("INSERT INTO source_files (session_id, file_path, file_hash, inode, status) VALUES (?, ?, ?, ?, ?)", (session_id, f['path'], f.get('hash'), f.get('inode'), f.get('status', 'pending')))
                    ids.append(cur.lastrowid)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
            return ids
        return self._execute_with_retry(_save)

    def save_staging_data(self, file_id: int, rows: List[Dict[str, Any]]) -> None:
        if not rows: return
        def _save():
            sql = "INSERT INTO staging_data (file_id, row_index, raw_content_json, date_val, amount, employee_name, source_type) VALUES (?, ?, ?, ?, ?, ?, ?)"
            data = [(file_id, r.get('_row_index'), json.dumps(sanitize_data(r), ensure_ascii=False), r.get('date'), decimal.Decimal(str(r.get('amount', 0))), r.get('employee_name'), r.get('source_type')) for r in rows]
            conn = self._get_connection()
            try:
                conn.execute("BEGIN TRANSACTION")
                conn.executemany(sql, data)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        self._execute_with_retry(_save)

    def save_template_error(self, session_id: str, error_info: Dict[str, Any]) -> None:
        def _save():
            conn = self._get_connection()
            try:
                conn.execute("BEGIN TRANSACTION")
                conn.execute("INSERT INTO template_errors (session_id, file_path, sheet_name, row_index, error_type, details, raw_data) VALUES (?, ?, ?, ?, ?, ?, ?)", (session_id, error_info.get('file_path'), error_info.get('sheet_name'), error_info.get('row_index'), error_info.get('error_type'), error_info.get('details'), json.dumps(error_info.get('raw_data'), ensure_ascii=False, cls=DecimalEncoder)))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        self._execute_with_retry(_save)

    def get_template_errors(self, session_id: str) -> List[Dict[str, Any]]:
        with self._get_connection() as conn: return [dict(r) for r in conn.execute("SELECT * FROM template_errors WHERE session_id = ? ORDER BY file_path, row_index", (session_id,))]

    def get_consolidated_data(self, session_id: str) -> List[Dict[str, Any]]:
        sql = "SELECT staging_data.raw_content_json, staging_data.employee_name, staging_data.date_val, staging_data.row_index, source_files.file_path FROM staging_data JOIN source_files ON staging_data.file_id = source_files.id WHERE source_files.session_id = ? ORDER BY staging_data.employee_name, staging_data.date_val"
        results = []
        with self._get_connection() as conn:
            for row in conn.execute(sql, (session_id,)):
                data = json.loads(row['raw_content_json'])
                data.update({'employee_name': row['employee_name'], 'date': row['date_val'], '_source_info': f"{Path(row['file_path']).name} : Строка {row['row_index']}"})
                results.append(data)
        return results

    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
            if not row: return {}
            stats = conn.execute("SELECT status, COUNT(*) as cnt FROM source_files WHERE session_id = ? GROUP BY status", (session_id,)).fetchall()
            return {"session_id": row['session_id'], "status": row['status'], "created_at": row['created_at'], "file_stats": {s['status']: s['cnt'] for s in stats}}

    def close(self) -> None: self.logger.info("Closing database manager.")

