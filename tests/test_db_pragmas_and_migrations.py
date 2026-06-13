"""Verify PRAGMAs applied on connect, BEGIN IMMEDIATE usage, and migration system.

Ref: notebooklm recommendations for SQLite tuning.
"""
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "APP"
sys.path.insert(0, str(APP_DIR))


def _fresh_connection(db_path: Path):
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


# ── PRAGMA tests ────────────────────────────────────────────────────

def test_pragma_journal_mode_is_wal():
    from core.infra.db_connection import SQLiteConnectionManager

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        mgr = SQLiteConnectionManager(db_path, {})
        conn = mgr.get_connection()
        try:
            row = conn.execute("PRAGMA journal_mode").fetchone()
            assert row[0].upper() == "WAL"
        finally:
            conn.close()


def test_pragma_synchronous_is_normal():
    from core.infra.db_connection import SQLiteConnectionManager

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        mgr = SQLiteConnectionManager(db_path, {})
        conn = mgr.get_connection()
        try:
            # synchronous returns 0=OFF, 1=NORMAL, 2=FULL, 3=EXTRA
            row = conn.execute("PRAGMA synchronous").fetchone()
            assert row[0] == 1  # 1 = NORMAL
        finally:
            conn.close()


def test_pragma_mmap_size_is_set():
    from core.infra.db_connection import SQLiteConnectionManager

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        mgr = SQLiteConnectionManager(db_path, {})
        conn = mgr.get_connection()
        try:
            row = conn.execute("PRAGMA mmap_size").fetchone()
            assert row[0] == 268435456  # 256 MB
        finally:
            conn.close()


def test_pragma_busy_timeout_is_set():
    from core.infra.db_connection import SQLiteConnectionManager

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        mgr = SQLiteConnectionManager(db_path, {})
        conn = mgr.get_connection()
        try:
            row = conn.execute("PRAGMA busy_timeout").fetchone()
            assert row[0] == 5000  # 5 seconds
        finally:
            conn.close()


def test_pragma_cache_size_and_temp_store():
    from core.infra.db_connection import SQLiteConnectionManager

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        mgr = SQLiteConnectionManager(db_path, {})
        conn = mgr.get_connection()
        try:
            cache = conn.execute("PRAGMA cache_size").fetchone()
            assert cache[0] == -64000
            temp = conn.execute("PRAGMA temp_store").fetchone()
            assert temp[0] == 2  # 2 = MEMORY
        finally:
            conn.close()


# ── BEGIN IMMEDIATE tests ────────────────────────────────────────────

def _find_begin_immediate_calls(file_path: Path):
    """Return count of BEGIN IMMEDIATE and BEGIN TRANSACTION in a .py file."""
    text = file_path.read_text(encoding="utf-8")
    immediate = text.count("BEGIN IMMEDIATE")
    transaction = text.count("BEGIN TRANSACTION")
    return immediate, transaction


def test_begin_immediate_replaces_begin_transaction_in_session_repo():
    immediate, transaction = _find_begin_immediate_calls(
        APP_DIR / "core" / "infra" / "session_repo.py"
    )
    assert immediate >= 5, f"Expected ≥5 BEGIN IMMEDIATE, got {immediate}"
    assert transaction == 0, f"BEGIN TRANSACTION still present ({transaction} occurrences)"


def test_begin_immediate_replaces_begin_transaction_in_source_file_repo():
    immediate, transaction = _find_begin_immediate_calls(
        APP_DIR / "core" / "infra" / "source_file_repo.py"
    )
    assert immediate >= 4, f"Expected ≥4 BEGIN IMMEDIATE, got {immediate}"
    assert transaction == 0, f"BEGIN TRANSACTION still present ({transaction} occurrences)"


def test_begin_immediate_replaces_begin_transaction_in_staging_repo():
    immediate, transaction = _find_begin_immediate_calls(
        APP_DIR / "core" / "infra" / "staging_repo.py"
    )
    assert immediate >= 1, f"Expected ≥1 BEGIN IMMEDIATE, got {immediate}"
    assert transaction == 0, f"BEGIN TRANSACTION still present ({transaction} occurrences)"


# ── Migration system tests ───────────────────────────────────────────

def test_migration_table_is_created():
    from core.infra.db_connection import SQLiteConnectionManager

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "test.db"
        mgr = SQLiteConnectionManager(db_path, {})
        mgr._run_migrations()
        conn = mgr.get_connection()
        try:
            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
            assert "_migrations" in tables
        finally:
            conn.close()


def test_migration_applies_missing_files(tmp_path):
    """When a .sql migration file exists but hasn't been applied, it gets executed."""
    from core.infra.db_connection import SQLiteConnectionManager

    mig_dir = APP_DIR / "migrations"
    mig_dir.mkdir(exist_ok=True)
    mig_file = mig_dir / "999_test_table.sql"
    mig_file.write_text(
        "CREATE TABLE IF NOT EXISTS __test_auto (x INTEGER);\n",
        encoding="utf-8",
    )
    try:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "test.db"
            mgr = SQLiteConnectionManager(db_path, {})
            mgr._run_migrations()
            conn = mgr.get_connection()
            try:
                tables = [
                    r[0]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                ]
                assert "__test_auto" in tables, (
                    "Migration file 999_test_table.sql was not applied. "
                    f"Tables present: {tables}"
                )
                # Verify the migration was recorded
                applied = [
                    r[0]
                    for r in conn.execute(
                        "SELECT filename FROM _migrations"
                    ).fetchall()
                ]
                assert "999_test_table.sql" in applied
            finally:
                conn.close()
    finally:
        mig_file.unlink(missing_ok=True)


def test_migration_skips_already_applied(tmp_path):
    """Already-applied migrations must not be re-executed."""
    from core.infra.db_connection import SQLiteConnectionManager

    mig_dir = APP_DIR / "migrations"
    mig_dir.mkdir(exist_ok=True)
    mig_file = mig_dir / "998_skip_test.sql"
    mig_file.write_text(
        "CREATE TABLE IF NOT EXISTS __double_run (y INTEGER);\n",
        encoding="utf-8",
    )
    try:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "test.db"
            mgr = SQLiteConnectionManager(db_path, {})
            mgr._run_migrations()
            mgr._run_migrations()  # second call must be a no-op
            conn = mgr.get_connection()
            try:
                count = conn.execute(
                    "SELECT COUNT(*) FROM _migrations "
                    "WHERE filename = '998_skip_test.sql'"
                ).fetchone()[0]
                assert count == 1, (
                    f"Migration 998_skip_test.sql recorded {count} times "
                    "— should be 1 (duplicate prevention failed)."
                )
            finally:
                conn.close()
    finally:
        mig_file.unlink(missing_ok=True)
