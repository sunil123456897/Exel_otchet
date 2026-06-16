import sqlite3
import json
import time
import decimal
import datetime
import logging
import threading
from typing import Dict, Any
from pathlib import Path


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return str(obj)
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return super().default(obj)


def sanitize_data(data: Any) -> Any:
    if isinstance(data, dict):
        return {str(k): sanitize_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_data(i) for i in data]
    elif isinstance(data, (decimal.Decimal, datetime.date, datetime.datetime)):
        return str(data) if isinstance(data, decimal.Decimal) else data.isoformat()
    return data


# Module-level adapter/converter registration. sqlite3.register_adapter
# and register_converter mutate global process state, so they must run
# exactly once — calling them in SQLiteConnectionManager.__init__
# re-registered (and re-wrapped) them on every connection manager. A
# lock guards the once-flag for import-time thread safety.
_ADAPTERS_REGISTERED = False
_ADAPTERS_LOCK = threading.Lock()


def _register_sqlite_adapters_once() -> None:
    global _ADAPTERS_REGISTERED
    if _ADAPTERS_REGISTERED:
        return
    with _ADAPTERS_LOCK:
        if _ADAPTERS_REGISTERED:
            return

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
        _ADAPTERS_REGISTERED = True


# Register on import so the first SQLiteConnectionManager is unaffected.
_register_sqlite_adapters_once()


class SQLiteConnectionManager:
    def __init__(self, db_path: Path, config: Dict[str, Any]):
        self.db_path = db_path
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.retry_count = config.get("locking", {}).get("retry_count", 3)
        self.retry_backoff = config.get("locking", {}).get("retry_backoff", 1.0)

        # Adapters/converters are registered once at module import; the
        # per-instance registration that used to live here was redundant
        # and re-wrapped the globals on every connection manager.

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
            # Overwrite deleted content with zeros so that subsequent VACUUM
            # genuinely removes the bytes from the file (defense-in-depth
            # for PII retention; no business-logic change).
            conn.execute("PRAGMA secure_delete = ON;")
            return conn
        except sqlite3.Error:
            conn.close()
            raise

    def check_integrity(self) -> tuple[bool, str | None]:
        """Run a quick PRAGMA quick_check and return (ok, error_message).

        Called at application startup; skips if no prior unclean-shutdown
        flag is found.  Returns (True, None) when the database is healthy.
        """
        flag_file = self.db_path.with_name(self.db_path.name + ".unclean")
        if not flag_file.exists():
            try:
                flag_file.write_text("unclean", encoding="utf-8")
            except Exception as e:
                self.logger.warning("Could not create unclean shutdown flag file: %s", e)
            return (True, None)

        self.logger.warning("Unclean shutdown detected. Running PRAGMA quick_check...")
        conn = self.get_connection()
        try:
            row = conn.execute("PRAGMA quick_check").fetchone()
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
                # Apply each migration as one atomic unit: the DDL and the
                # _migrations row commit together. executescript() implicitly
                # commits any open transaction, so we drive the migration
                # statement-by-statement inside an explicit BEGIN IMMEDIATE
                # instead — that way a crash between 'DDL applied' and
                # 'migration recorded' can't leave a half-applied migration
                # that re-runs (and may fail) on the next start.
                sql_text = migration_path.read_text(encoding="utf-8")
                statements = self._split_sql_statements(sql_text)
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    try:
                        for stmt in statements:
                            if stmt.strip():
                                conn.execute(stmt)
                        conn.execute(
                            "INSERT INTO _migrations (filename) VALUES (?)",
                            (name,),
                        )
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        raise
                    self.logger.info("Applied migration: %s", name)
                except sqlite3.Error as exc:
                    # A failing migration must not prevent the rest of
                    # startup; surface it loudly but keep going so the
                    # app is at least usable for diagnosis.
                    self.logger.error(
                        "Migration %s failed and was rolled back: %s",
                        name, exc,
                    )
                    raise
        finally:
            conn.close()

    @staticmethod
    def _split_sql_statements(sql_text: str) -> list[str]:
        """Split a .sql script into individual statements.

        Keeps it simple: split on ';'. Multi-line DDL and comments are
        fine; the migration files in this project are plain CREATE
        TABLE / CREATE INDEX scripts without triggers or procedures, so
        a naive split is sufficient and avoids the implicit-commit
        behaviour of executescript().
        """
        statements: list[str] = []
        for raw in sql_text.split(";"):
            # Drop full-line and trailing comments so empty/comment-only
            # splits don't reach execute() as no-ops that some SQLite
            # builds reject.
            lines = [
                line for line in raw.splitlines()
                if not line.strip().startswith("--")
            ]
            stmt = "\n".join(lines).strip()
            if stmt:
                statements.append(stmt + ";")
        return statements

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
