"""Stage 9 / MR-0901 — backup/restore verification.

The TZ demands that backups are *tested by restoration*, not just
created. A backup that has never been restored from is unproven — it
might be silently corrupt, half-written, or in a format the restore
path can't read.

These tests build a backup of each artefact type (Excel output, SQLite
cache, config.yaml, employees.yaml), then verify restoration works and
produces a byte-identical or semantically-identical result.
"""
from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path

import openpyxl
from ruamel.yaml import YAML

from core.infra.excel_backup import backup_existing_excel_output


# ── 1) Excel backup → restore is byte-identical ────────────────────────


def test_excel_backup_can_be_restored_byte_for_byte(tmp_path: Path) -> None:
    """A backed-up Excel file must restore to a byte-identical copy.

    The backup uses ``shutil.copy2`` which preserves content + metadata.
    We verify by hash, not by content-equality, so the test gives a
    useful diff if it fails.
    """
    import hashlib

    src = tmp_path / "report.xlsx"
    wb = openpyxl.Workbook()
    wb.active["A1"] = "preserve me"
    wb.save(src)
    src_hash = hashlib.sha256(src.read_bytes()).hexdigest()

    # Create backup.
    backup = backup_existing_excel_output(src, tmp_path / "backups", keep=3)
    assert backup is not None and backup.exists()

    # Simulate disaster: original is damaged.
    src.write_bytes(b"corrupted")

    # Restore from backup.
    shutil.copy2(backup, src)
    restored_hash = hashlib.sha256(src.read_bytes()).hexdigest()
    assert restored_hash == src_hash, (
        "restored file differs from original — backup is not byte-safe"
    )

    # And it still loads as a valid workbook.
    wb2 = openpyxl.load_workbook(src)
    assert wb2.active["A1"].value == "preserve me"
    wb2.close()


def test_excel_backup_rotation_keeps_latest(tmp_path: Path) -> None:
    """After multiple backup cycles, the most recent backup is always retained.

    A buggy rotation could delete the wrong end of the sorted list and
    drop the latest backup — leaving the operator with stale history.
    """
    src = tmp_path / "report.xlsx"
    openpyxl.Workbook().save(src)

    # Write distinct content per cycle so we can identify the latest.
    backups: list[Path] = []
    for i in range(5):
        wb = openpyxl.load_workbook(src)
        wb.active["A1"] = f"version-{i}"
        wb.save(src)
        wb.close()
        time.sleep(0.05)  # distinct mtimes
        b = backup_existing_excel_output(src, tmp_path / "backups", keep=3)
        if b:
            backups.append(b)

    # Only the 3 newest should survive.
    surviving = sorted(
        (tmp_path / "backups").rglob("*.xlsx"),
        key=lambda p: p.stat().st_mtime,
    )
    assert len(surviving) <= 3

    # The latest backup must contain the most-recent content.
    latest_backup = surviving[-1]
    wb = openpyxl.load_workbook(latest_backup)
    assert wb.active["A1"].value == "version-4"
    wb.close()


# ── 2) SQLite backup → restore preserves schema + data ────────────────


def test_sqlite_backup_can_be_restored(tmp_path: Path) -> None:
    """A SQLite backup (file copy) must restore to a working DB.

    This mirrors what ``DatabaseConnection._backup_db`` does. The
    restored DB must have the same schema and rows.
    """
    src_db = tmp_path / "cache.db"
    conn = sqlite3.connect(src_db)
    conn.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, status TEXT)")
    conn.execute("INSERT INTO sessions (id, status) VALUES ('s1', 'completed')")
    conn.commit()
    conn.close()

    # Backup.
    backup_path = src_db.parent / f"{src_db.name}.backup_test"
    shutil.copy2(src_db, backup_path)

    # Simulate corruption.
    src_db.unlink()
    assert not src_db.exists()

    # Restore.
    shutil.copy2(backup_path, src_db)

    # Verify restoration produced a usable database.
    conn = sqlite3.connect(src_db)
    rows = conn.execute("SELECT id, status FROM sessions").fetchall()
    conn.close()
    assert rows == [("s1", "completed")]


def test_sqlite_backup_survives_wal_mode(tmp_path: Path) -> None:
    """A DB in WAL mode must backup consistently.

    WAL mode is the project default. A naive copy that misses the
    ``-wal`` sidecar would lose uncommitted data. The project's
    ``_backup_db`` does a plain ``shutil.copy2`` of the main file — we
    document that this snapshots the last-committed state, which is the
    correct semantic for a pre-migration backup.
    """
    db = tmp_path / "cache.db"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (1)")
    conn.commit()
    conn.close()

    # Snapshot the main DB file only (matches project behaviour).
    shutil.copy2(db, tmp_path / "cache.db.snap")

    # The snapshot must contain the committed row.
    snap_conn = sqlite3.connect(tmp_path / "cache.db.snap")
    rows = snap_conn.execute("SELECT x FROM t").fetchall()
    snap_conn.close()
    assert rows == [(1,)]


# ── 3) Config backup → restore preserves data ─────────────────────────


def test_config_backup_can_be_restored(tmp_path: Path) -> None:
    """A config.yaml backup must restore to a semantically-identical file."""
    yaml = YAML()
    cfg = tmp_path / "config.yaml"
    data = {
        "config_version": 1,
        "database": {"path": "cache.db", "use_wal": True},
        "logic": {"return_keywords": ["возврат"]},
        "operator_custom": {"firm_id": "test-firm"},
    }
    with cfg.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)

    # Backup.
    backup = tmp_path / "config.yaml.bak"
    shutil.copy2(cfg, backup)

    # Simulate disaster: corrupt the live config.
    cfg.write_text("not: valid yaml: [", encoding="utf-8")

    # Restore.
    shutil.copy2(backup, cfg)

    # The restored config must load to the same dict.
    with cfg.open("r", encoding="utf-8") as f:
        restored = yaml.load(f)
    assert restored["database"]["path"] == "cache.db"
    assert restored["operator_custom"]["firm_id"] == "test-firm"
    assert restored["config_version"] == 1


def test_config_backup_preserves_operator_custom_keys(tmp_path: Path) -> None:
    """Custom keys added by the operator must survive backup/restore."""
    yaml = YAML()
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "database: {path: cache.db}\n"
        "custom_integration: {endpoint: 'https://firm-internal.local/api'}\n",
        encoding="utf-8",
    )
    backup = tmp_path / "config.yaml.bak"
    shutil.copy2(cfg, backup)

    # Restore.
    shutil.copy2(backup, cfg)

    with cfg.open("r", encoding="utf-8") as f:
        restored = yaml.load(f)
    assert restored["custom_integration"]["endpoint"] == "https://firm-internal.local/api"


# ── 4) employees.yaml backup → restore ────────────────────────────────


def test_employees_backup_can_be_restored(tmp_path: Path) -> None:
    """A employees.yaml backup must restore without losing fingerprint data."""
    yaml = YAML()
    emp = tmp_path / "employees.yaml"
    emp.write_text(
        "Амалия:\n"
        "  - path: /reports/2026/book.xlsx\n"
        "    id: 12345\n"
        "    fp: abcdef1234567890\n",
        encoding="utf-8",
    )

    backup = tmp_path / "employees.yaml.bak"
    shutil.copy2(emp, backup)

    # Damage: wipe the live file.
    emp.write_text("{}", encoding="utf-8")

    # Restore.
    shutil.copy2(backup, emp)

    with emp.open("r", encoding="utf-8") as f:
        restored = yaml.load(f)
    assert "Амалия" in restored
    entry = restored["Амалия"][0]
    assert entry["path"] == "/reports/2026/book.xlsx"
    assert entry["id"] == 12345
    assert entry["fp"] == "abcdef1234567890"


# ── 5) Rotation never deletes the last good backup ────────────────────


def test_rotation_does_not_delete_only_backup(tmp_path: Path) -> None:
    """Even with keep=1, a single backup must not delete itself.

    A buggy prune could sort in the wrong order and unlink the only
    surviving backup. The operator would be left with nothing.
    """
    src = tmp_path / "report.xlsx"
    openpyxl.Workbook().save(src)

    # Run with keep=1.
    backup_existing_excel_output(src, tmp_path / "backups", keep=1)

    backups = list((tmp_path / "backups").rglob("*.xlsx"))
    assert len(backups) == 1, (
        f"keep=1 left {len(backups)} backups; expected exactly 1"
    )


# ── 6) Backup does not silently swallow source-file issues ────────────


def test_backup_of_nonexistent_source_returns_none(tmp_path: Path) -> None:
    """Backing up a missing source returns None — does not create an empty file."""
    result = backup_existing_excel_output(
        tmp_path / "missing.xlsx", tmp_path / "backups", keep=3,
    )
    assert result is None
    # And no backup file was created.
    assert not list((tmp_path / "backups").rglob("*.xlsx"))


def test_backup_skips_excel_lock_files(tmp_path: Path) -> None:
    """``~$`` lock files must never be backed up (they're not real workbooks)."""
    lock = tmp_path / "~$report.xlsx"
    lock.write_bytes(b"\xd0\xcf\x11\xe0" + b"\x00" * 50)

    result = backup_existing_excel_output(lock, tmp_path / "backups", keep=3)
    assert result is None
    assert not list((tmp_path / "backups").rglob("*.xlsx"))
