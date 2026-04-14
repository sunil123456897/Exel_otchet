import sqlite3
import json
import time
import decimal
import datetime
import logging
from typing import Dict, Any
from pathlib import Path


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return str(obj)
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return super(DecimalEncoder, self).default(obj)


def sanitize_data(data: Any) -> Any:
    if isinstance(data, dict):
        return {str(k): sanitize_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_data(i) for i in data]
    elif isinstance(data, (decimal.Decimal, datetime.date, datetime.datetime)):
        return str(data) if isinstance(data, decimal.Decimal) else data.isoformat()
    return data


class SQLiteConnectionManager:
    def __init__(self, db_path: Path, config: Dict[str, Any]):
        self.db_path = db_path
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.retry_count = config.get("locking", {}).get("retry_count", 3)
        self.retry_backoff = config.get("locking", {}).get("retry_backoff", 1.0)

        sqlite3.register_adapter(decimal.Decimal, str)

        def _convert_numeric(v: bytes) -> decimal.Decimal:
            try:
                s = v.decode("utf-8").strip()
                return decimal.Decimal(s) if s else decimal.Decimal("0")
            except (decimal.InvalidOperation, UnicodeDecodeError):
                return decimal.Decimal("0")

        sqlite3.register_converter("NUMERIC", _convert_numeric)

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=self.config.get("database", {}).get("timeout", 30.0),
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA temp_store = MEMORY;")
        conn.execute("PRAGMA cache_size = -64000;")
        return conn

    def init_db(self, schema_path: Path) -> None:
        if schema_path.exists():
            with self.get_connection() as conn:
                with open(schema_path, "r", encoding="utf-8") as f:
                    conn.executescript(f.read())

    def execute_with_retry(self, func, *args, **kwargs):
        """Execute a function with exponential backoff on transient SQLite errors."""
        last_err = None
        for attempt in range(self.retry_count):
            try:
                return func(*args, **kwargs)
            except sqlite3.OperationalError as e:
                if any(x in str(e).lower() for x in ["locked", "busy"]):
                    last_err = e
                    delay = self.retry_backoff * (2**attempt)
                    self.logger.warning(
                        f"SQLite retry {attempt + 1}/{self.retry_count}: {e}, "
                        f"waiting {delay:.1f}s"
                    )
                    time.sleep(delay)
                else:
                    raise
        raise last_err
