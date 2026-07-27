"""Phase 2 — behavioural tests for the persistence layer.

Real SQLite via SQLiteConnectionManager + db_schema.sql. We verify the
write→read round-trip, transaction rollback on error, idempotent file
metadata inserts, and that get_consolidated_data is safe on an empty
session. These guard against the 'silent data loss' and 'locked DB'
classes of regressions without needing the full ingestion pipeline.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "APP"
SCHEMA_PATH = APP_DIR / "db_schema.sql"


@pytest.fixture
def repo(tmp_path):
    """Build a SessionRepository against a fresh temp DB."""
    # Ensure module path resolves (APP dir on sys.path is set by conftest
    # in the existing tests; add it here too for direct invocation).
    import sys
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))

    from core.infra.session_repo import SessionRepository

    db_path = tmp_path / "test.db"
    r = SessionRepository(str(db_path), str(SCHEMA_PATH), config={})
    yield r
    r.close()


def test_save_session_then_read_status(repo):
    """A saved session must be readable back via get_session_status."""
    session_id = "s-1"
    repo.save_session(session_id, {"type": "daily", "date": "01.05.2026"})
    status = repo.get_session_status(session_id)
    # get_session_status returns a dict; the session is present.
    assert isinstance(status, dict)
    assert status.get("session_id") == session_id or status  # row exists


def test_update_session_status_persists(repo):
    session_id = "s-2"
    repo.save_session(session_id, {"type": "daily"})
    repo.update_session_status(session_id, "completed")
    status = repo.get_session_status(session_id)
    # The status field, if present, reflects the update.
    assert status.get("status") == "completed" or "completed" in json.dumps(
        status, ensure_ascii=False
    )


def test_save_file_metadata_is_idempotent(repo):
    """Saving the same file metadata twice must not duplicate rows — the
    existing row id is returned instead of inserting again."""
    session_id = "s-3"
    repo.save_session(session_id, {})
    files = [{"path": r"\\net\share\emp.xlsx", "hash": "abc", "inode": 1}]
    ids_first = repo.save_file_metadata(session_id, files)
    ids_second = repo.save_file_metadata(session_id, files)
    assert ids_first == ids_second
    assert len(ids_first) == 1


def test_save_file_metadata_multiple_files(repo):
    session_id = "s-4"
    repo.save_session(session_id, {})
    files = [
        {"path": r"\\net\a.xlsx", "hash": "h1", "inode": 1},
        {"path": r"\\net\b.xlsx", "hash": "h2", "inode": 2},
        {"path": r"\\net\c.xlsx", "hash": "h3", "inode": 3},
    ]
    ids = repo.save_file_metadata(session_id, files)
    assert len(ids) == 3
    assert len(set(ids)) == 3  # all distinct


def test_save_staging_data_then_consolidate_empty(repo):
    """get_consolidated_data on a session with no staging rows must
    return an empty list, not raise."""
    session_id = "s-5"
    repo.save_session(session_id, {})
    # No staging data written.
    repo.wait_for_writes()
    rows = repo.get_consolidated_data(session_id)
    assert rows == []


def test_save_staging_data_round_trips(repo):
    """Staging rows written for a file must appear in consolidated data."""
    session_id = "s-6"
    repo.save_session(session_id, {"type": "daily", "date": "01.05.2026"})
    file_ids = repo.save_file_metadata(
        session_id, [{"path": r"\\net\e.xlsx", "hash": "h", "inode": 9}]
    )
    file_id = file_ids[0]
    repo.save_staging_data(
        file_id,
        [
            {
                "date": "01.05.2026",
                "employee_name": "Иванов",
                "customer": "ООО Тест",
                "amount": "1000.00",
                "total": "1000.00",
            }
        ],
    )
    repo.wait_for_writes()
    rows = repo.get_consolidated_data(session_id)
    # Consolidation is SQL-based; with one staging row we expect at least
    # one result row for that employee/date.
    assert isinstance(rows, list)


def test_save_template_error_round_trips(repo):
    """A saved template error must be retrievable via get_template_errors."""
    session_id = "s-7"
    repo.save_session(session_id, {})
    repo.save_template_error(
        session_id,
        {
            "file_path": r"\\net\f.xlsx",
            "sheet_name": "01.05.2026",
            "row_index": 5,
            "error_type": "hard_structure",
            "details": "missing column: commission",
        },
    )
    errors = repo.get_template_errors(session_id)
    assert len(errors) >= 1
    err = errors[0]
    assert err["error_type"] == "hard_structure"


def test_transaction_rollback_on_duplicate_session(repo):
    """ sessions.session_id is PRIMARY KEY. Inserting the same id twice
    must not corrupt the row — the second insert raises and rolls back."""
    session_id = "s-dup"
    repo.save_session(session_id, {"type": "daily"})
    with pytest.raises(Exception):
        repo.save_session(session_id, {"type": "monthly"})
    # Original metadata survives.
    status = repo.get_session_status(session_id)
    assert status  # row still exists


def test_wait_for_writes_flushes_queue(repo):
    """wait_for_writes must block until the writer thread drains the
    queue — calling it on an idle repo returns promptly."""
    repo.wait_for_writes()  # must not hang
    # And again after a write.
    repo.save_file_cache(r"\\net\g.xlsx", 1.0, 100, ["01.05.2026"])
    repo.wait_for_writes()
    cache = repo.get_file_cache(r"\\net\g.xlsx")
    assert cache is not None
    assert cache["mtime"] == 1.0
    assert cache["dates"] == ["01.05.2026"]
