"""Регрессионный тест: purge_old_sessions не должен падать на FK-constraint.

Реальный кейс заказчицы (лог 01.07.2026): purge_old_sessions падал с
``sqlite3.IntegrityError: FOREIGN KEY constraint failed`` при каждом
запуске, потому что db_schema.sql объявляет FK без ``ON DELETE CASCADE``,
а код рассчитывал на каскад. cache.db монотонно рос (200 МБ).

После фикса код удаляет зависимые строки (template_errors → staging_data
→ source_files → consolidated_results → sessions) вручную в одной
транзакции. Этот тест воспроизводит orphan-состояние и проверяет, что
purge проходит чисто.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "APP"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


def _make_db_with_orphans(db_path: Path) -> None:
    """Создать БД по схеме проекта + заполнить orphan-состоянием.

    Имитирует накопление у заказчицы: старая завершённая сессия с
    зависимыми source_files/staging_data/template_errors, плюс текущая
    in_progress-сессия (которую purge трогать не должен).
    """
    schema = (APP_DIR / "db_schema.sql").read_text(encoding="utf-8")
    conn = sqlite3.connect(str(db_path))
    conn.executescript(schema)

    old_ts = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO sessions(session_id, created_at, status) VALUES (?,?,?)",
        ("OLD_SESSION", old_ts, "completed"),
    )
    conn.execute(
        "INSERT INTO sessions(session_id, status) VALUES (?,?)",
        ("NEW_SESSION", "in_progress"),
    )
    # Зависимости старой сессии — без каскада они блокируют DELETE.
    conn.execute(
        "INSERT INTO source_files(session_id, file_path) VALUES (?,?)",
        ("OLD_SESSION", "old_report.xlsx"),
    )
    conn.execute(
        "INSERT INTO source_files(session_id, file_path) VALUES (?,?)",
        ("NEW_SESSION", "new_report.xlsx"),
    )
    conn.execute("INSERT INTO staging_data(file_id) VALUES (1)")  # → old source
    conn.execute("INSERT INTO staging_data(file_id) VALUES (2)")  # → new source
    conn.execute(
        "INSERT INTO template_errors(session_id) VALUES (?)", ("OLD_SESSION",)
    )
    conn.commit()
    conn.close()


def test_purge_old_sessions_removes_orphans_without_fk_error(tmp_path):
    """Корневой кейс: purge не падает, удаляет старую сессию с зависимостями."""
    from core.infra.session_repo import SessionRepository

    db_path = tmp_path / "cache.db"
    _make_db_with_orphans(db_path)

    repo = SessionRepository(
        str(db_path),
        str(APP_DIR / "db_schema.sql"),
        {"database": {"use_wal": False}},
    )
    try:
        deleted = repo.purge_old_sessions(max_age_days=30)
    finally:
        repo.close()

    assert deleted == 1, f"Должна удалиться 1 старая сессия, удалено {deleted}"

    # Проверяем, что orphan-зависимости старой сессии ушли вместе с ней,
    # а новая сессия и её данные на месте.
    conn = sqlite3.connect(str(db_path))
    try:
        sessions = conn.execute("SELECT session_id FROM sessions").fetchall()
        sources = conn.execute(
            "SELECT session_id, file_path FROM source_files"
        ).fetchall()
        staging_files = conn.execute("SELECT file_id FROM staging_data").fetchall()
    finally:
        conn.close()

    assert sessions == [("NEW_SESSION",)], "Новая сессия должна остаться"
    assert sources == [("NEW_SESSION", "new_report.xlsx")], (
        "Один source_file новой сессии должен остаться, старый — удалён"
    )
    # staging_data новой сессии (file_id=2) остаётся; старая (file_id=1) — удаляется
    assert staging_files == [(2,)], "staging старой сессии должен удалиться"


def test_purge_keeps_recent_sessions(tmp_path):
    """Свежие завершённые сессии (моложе max_age_days) не трогаются."""
    from core.infra.session_repo import SessionRepository

    db_path = tmp_path / "cache.db"
    schema = (APP_DIR / "db_schema.sql").read_text(encoding="utf-8")
    conn = sqlite3.connect(str(db_path))
    conn.executescript(schema)
    recent = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "INSERT INTO sessions(session_id, created_at, status) VALUES (?,?,?)",
        ("RECENT", recent, "completed"),
    )
    conn.commit()
    conn.close()

    repo = SessionRepository(
        str(db_path),
        str(APP_DIR / "db_schema.sql"),
        {"database": {"use_wal": False}},
    )
    try:
        deleted = repo.purge_old_sessions(max_age_days=30)
    finally:
        repo.close()

    assert deleted == 0, "Свежая сессия не должна удалиться"


def test_purge_zero_max_age_is_noop(tmp_path):
    """max_age_days=0 — purge не запускается (защита от случайной очистки)."""
    from core.infra.session_repo import SessionRepository

    db_path = tmp_path / "cache.db"
    (APP_DIR / "db_schema.sql").read_text(encoding="utf-8")
    # Создаём минимальную БД
    conn = sqlite3.connect(str(db_path))
    conn.executescript((APP_DIR / "db_schema.sql").read_text(encoding="utf-8"))
    conn.close()

    repo = SessionRepository(
        str(db_path),
        str(APP_DIR / "db_schema.sql"),
        {"database": {"use_wal": False}},
    )
    try:
        assert repo.purge_old_sessions(max_age_days=0) == 0
    finally:
        repo.close()
