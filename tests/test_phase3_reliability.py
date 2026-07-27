"""Phase 3 — reliability: EventBus singleton race, migration atomicity,
and SourceFileRepository write-error propagation.

Three independent regressions guards:

- EventBus.get() must return the same instance under concurrent first
  calls (double-checked locking). The unlocked version could build two
  buses if two workers raced the init branch.
- A migration that raises mid-apply must leave the DB consistent: the
  _migrations row is written only when the DDL commits, so a crashed
  migration re-runs cleanly instead of being skipped.
- SourceFileRepository must surface writer-thread errors instead of
  silently swallowing them, mirroring StagingDataRepository.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "APP"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


# ── EventBus singleton race ───────────────────────────────────────────
# NOTE: event_bus.py was removed as dead code in Phase 3.2 (FIX-004).
# The three EventBus tests below were testing the removed module and
# have been deleted. See docs/fixes/fix-plan.md for details.


# ── Migration atomicity ───────────────────────────────────────────────


def _write_migration(name: str, sql: str) -> Path:
    mig_dir = APP_DIR / "migrations"
    mig_dir.mkdir(exist_ok=True)
    p = mig_dir / name
    p.write_text(sql, encoding="utf-8")
    return p


def test_migration_atomicity_partial_ddl_rolls_back():
    """If a migration contains two statements and the second raises, the
    first must be rolled back too AND the migration must not be recorded
    as applied — so a later retry starts clean."""
    from core.infra.db_connection import SQLiteConnectionManager

    mig = _write_migration(
        "997_atomic_test.sql",
        "CREATE TABLE __atomic_a (x INTEGER);\n"
        "CREATE TABLE __atomic_a (x INTEGER);\n",  # duplicate → error
    )
    try:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "t.db"
            mgr = SQLiteConnectionManager(db_path, {})
            with pytest.raises(Exception):
                mgr._run_migrations()
            conn = mgr.get_connection()
            try:
                tables = [
                    r[0] for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                ]
                # __atomic_a must NOT exist (rolled back with the failed
                # duplicate CREATE).
                assert "__atomic_a" not in tables
                applied = [
                    r[0] for r in conn.execute(
                        "SELECT filename FROM _migrations"
                    ).fetchall()
                ]
                # The migration must not be recorded as applied.
                assert "997_atomic_test.sql" not in applied
            finally:
                conn.close()
    finally:
        mig.unlink(missing_ok=True)


def test_migration_with_comments_is_parsed():
    """The statement splitter must tolerate '--' comment lines."""
    from core.infra.db_connection import SQLiteConnectionManager

    mig = _write_migration(
        "996_comment_test.sql",
        "-- This is a comment\n"
        "CREATE TABLE __comment_ok (x INTEGER);\n"
        "-- trailing comment\n",
    )
    try:
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "t.db"
            mgr = SQLiteConnectionManager(db_path, {})
            mgr.init_db(APP_DIR / "db_schema.sql")
            conn = mgr.get_connection()
            try:
                tables = [
                    r[0] for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                ]
                assert "__comment_ok" in tables
            finally:
                conn.close()
    finally:
        mig.unlink(missing_ok=True)


# ── SourceFileRepository error propagation ────────────────────────────


def test_source_file_repo_records_write_error(tmp_path):
    """When the writer thread's _save raises, the error must be surfaced
    via the write_error property instead of being swallowed."""
    from core.infra.session_repo import SessionRepository

    schema = APP_DIR / "db_schema.sql"
    repo = SessionRepository(str(tmp_path / "t.db"), str(schema), config={})
    try:
        sfr = repo.source_file_repo
        # Inject a _save closure that always raises.
        def boom(*args, **kwargs):
            raise RuntimeError("disk full")

        sfr.write_queue.put((boom, ()))
        sfr.wait_for_writes()
        # The error must be visible on the property.
        err = sfr.write_error
        assert err is not None
        assert "disk full" in str(err)
    finally:
        repo.close()


def test_source_file_repo_keeps_first_error_only(tmp_path):
    """Repeated failures must not overwrite the first error (keeps the
    root cause visible)."""
    from core.infra.session_repo import SessionRepository

    schema = APP_DIR / "db_schema.sql"
    repo = SessionRepository(str(tmp_path / "t.db"), str(schema), config={})
    try:
        sfr = repo.source_file_repo

        def first(*args, **kwargs):
            raise RuntimeError("first failure")

        def second(*args, **kwargs):
            raise RuntimeError("second failure")

        sfr.write_queue.put((first, ()))
        sfr.wait_for_writes()
        sfr.write_queue.put((second, ()))
        sfr.wait_for_writes()
        err = sfr.write_error
        assert err is not None
        assert "first failure" in str(err)
    finally:
        repo.close()
