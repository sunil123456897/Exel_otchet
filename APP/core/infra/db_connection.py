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

        def _convert_timestamp(v: bytes) -> str:
            try:
                return v.decode("utf-8")
            except UnicodeDecodeError:
                return ""

        sqlite3.register_converter("TIMESTAMP", _convert_timestamp)

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
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA temp_store = MEMORY;")
            conn.execute("PRAGMA cache_size = -64000;")
            conn.execute("PRAGMA mmap_size = 268435456;")
            conn.execute("PRAGMA busy_timeout = 5000;")
            return conn
        except sqlite3.Error:
            conn.close()
            raise

    def check_integrity(self) -> tuple[bool, str | None]:
        """Run a quick PRAGMA integrity_check and return (ok, error_message).

        Called at application startup; skips if no prior unclean-shutdown
        flag is found.  Returns (True, None) when the database is healthy.
        """
        conn = self.get_connection()
        try:
            row = conn.execute("PRAGMA integrity_check").fetchone()
            msg = row[0] if row else "unknown"
            return (msg == "ok", None if msg == "ok" else msg)
        except Exception as exc:
            return (False, str(exc))
        finally:
            conn.close()

    def init_db(self, schema_path: Path) -> None:
        if schema_path.exists():
            conn = self.get_connection()
            try:
                with open(schema_path, "r", encoding="utf-8") as f:
                    conn.executescript(f.read())
            finally:
                conn.close()
        self._run_migrations()

    def _run_migrations(self) -> None:
        migrations_dir = Path(__file__).resolve().parents[
            2
        ] / "migrations"
        if not migrations_dir.is_dir():
            return
        pending = sorted(
            p for p in migrations_dir.glob("*.sql") if p.is_file()
        )
        conn = self.get_connection()
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS _migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            if not pending:
                return
            applied = {
                row[0]
                for row in conn.execute(
                    "SELECT filename FROM _migrations"
                ).fetchall()
            }
            for migration_path in pending:
                name = migration_path.name
                if name in applied:
                    continue
                with open(migration_path, "r", encoding="utf-8") as f:
                    conn.executescript(f.read())
                conn.execute(
                    "INSERT INTO _migrations (filename) VALUES (?)",
                    (name,),
                )
                conn.commit()
                self.logger.info("Applied migration: %s", name)
        finally:
            conn.close()

    def execute_with_retry(self, func, *args, **kwargs):
        """Execute a function with exponential backoff on transient SQLite errors."""
        last_err = None
        attempt_count = max(1, int(self.retry_count))
        for attempt in range(attempt_count):
            try:
                return func(*args, **kwargs)
            except sqlite3.OperationalError as e:
                if any(x in str(e).lower() for x in ["locked", "busy"]):
                    last_err = e
                    delay = self.retry_backoff * (2**attempt)
                    self.logger.warning(
                        f"SQLite retry {attempt + 1}/{attempt_count}: {e}, "
                        f"waiting {delay:.1f}s"
                    )
                    if attempt < attempt_count - 1:
                        time.sleep(delay)
                else:
                    raise
        if last_err is None:
            raise sqlite3.OperationalError("SQLite operation failed before execution")
        raise last_err
