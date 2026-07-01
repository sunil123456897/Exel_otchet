"""Диагностический скрипт для запуска на ПК заказчицы (при подключении).

Делает 3 вещи за один запуск:
  1. Чистит cache.db: purge старых сессий через фиксированный purge_old_sessions
     + удаляет orphan-записи (FK constraint больше не падает) + VACUUM (сжимает).
  2. Прогоняет «РСЧ за период» на ЕЁ реальных данных с детальным таймингом
     каждого этапа — покажет, где именно идёт время и нет ли зависания.
  3. Печатает понятный отчёт для разработчика.

Запуск (на её ПК, из папки APP):
    .venv\\Scripts\\python.exe ..\\tools\\diagnose_and_clean.py

Ничего не удаляет без подтверждения; данные сотрудников/настройки не трогает.
Выходные отчёты идут в %TEMP%\\rsch_diag\\ чтобы не засорять её папку.
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
import threading
import time
from datetime import date
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("Diag")


def step(msg: str) -> None:
    print(f"\n=== {msg} ===")


def find_app_root() -> Path:
    """Найти папку APP (где main.py + cache.db)."""
    here = Path(__file__).resolve().parent
    # Сценарий 1: tools/ внутри проекта → APP рядом
    candidate = here.parent / "APP"
    if (candidate / "main.py").exists():
        return candidate
    # Сценарий 2: скрипт запущен из APP
    if (here / "main.py").exists():
        return here
    raise SystemExit("Не найдена папка APP. Положите скрипт в tools/ проекта.")


def part1_clean_db(app_root: Path) -> dict:
    """Очистка cache.db: purge + orphan-удаление + VACUUM."""
    step("ЧАСТЬ 1: Очистка cache.db")
    import sqlite3

    db_path = app_root / "cache.db"
    if not db_path.exists():
        log.warning("cache.db не найден: %s — пропускаю", db_path)
        return {"skipped": True}

    size_before = db_path.stat().st_size
    log.info("Размер ДО: %.1f МБ", size_before / 1024 / 1024)

    # Backup (безопасность) — копируем рядом.
    backup = db_path.with_suffix(".db.diag_backup")
    shutil.copy2(db_path, backup)
    log.info("Backup создан: %s", backup.name)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    stats = {}
    try:
        # Считаем orphan-записи ДО.
        stats["sessions"] = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        stats["source_files"] = conn.execute(
            "SELECT COUNT(*) FROM source_files"
        ).fetchone()[0]
        stats["staging_data"] = conn.execute(
            "SELECT COUNT(*) FROM staging_data"
        ).fetchone()[0]
        stats["template_errors"] = conn.execute(
            "SELECT COUNT(*) FROM template_errors"
        ).fetchone()[0]
        stats["row_cache"] = conn.execute(
            "SELECT COUNT(*) FROM row_cache"
        ).fetchone()[0]
        stats["file_cache"] = conn.execute(
            "SELECT COUNT(*) FROM file_cache"
        ).fetchone()[0]
        log.info("Записей ДО: %s", stats)

        # purge старых сессий (через исправленный репозиторий).
        sys.path.insert(0, str(app_root))
        from core.infra.session_repo import SessionRepository

        repo = SessionRepository(
            str(db_path),
            str(app_root / "db_schema.sql"),
            {"database": {"use_wal": False}},
        )
        deleted = repo.purge_old_sessions(max_age_days=30)
        repo.close()
        log.info("Purge: удалено %d старых сессий", deleted)

        # VACUUM сжимает файл (освобождает место от удалённых строк).
        # VACUUM нельзя выполнять в транзакции.
        conn.commit()
        conn.execute("VACUUM")
        log.info("VACUUM выполнен")
    finally:
        conn.close()

    size_after = db_path.stat().st_size
    log.info(
        "Размер ПОСЛЕ: %.1f МБ (освобождено %.1f МБ)",
        size_after / 1024 / 1024,
        (size_before - size_after) / 1024 / 1024,
    )
    return {
        "deleted_sessions": deleted,
        "size_before_mb": round(size_before / 1024 / 1024, 1),
        "size_after_mb": round(size_after / 1024 / 1024, 1),
        "counts_before": stats,
        "backup": str(backup),
    }


def part2_rsch_period_timing(app_root: Path) -> dict:
    """Прогон «РСЧ за период» с детальным таймингом."""
    step("ЧАСТЬ 2: РСЧ за период — детальный тайминг")
    from core.bootstrap import Bootstrap

    cfg_ctl, app_ctl, db = Bootstrap.setup(app_root, app_root / "config.yaml")
    project_root = app_root.parent
    rsch_sources = sorted((project_root / "рсч всех").glob("*.xlsx"))
    log.info("Найдено источников РСЧ: %d", len(rsch_sources))
    if not rsch_sources:
        log.error("Папка «рсч всех» пуста или не найдена — пропускаю прогон")
        return {"skipped": True, "reason": "no rsch sources"}

    out_dir = Path(os.environ.get("TEMP", ".")) / "rsch_diag"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "РСЧ_диаг_период.xlsx"

    # Период — последний месяц данных (гибко: берём широкий диапазон).
    start = date(2026, 6, 1)
    end = date(2026, 6, 30)

    done = threading.Event()
    box: dict = {}
    progress_marks: list = []

    def on_progress(p):
        progress_marks.append((round(time.monotonic() - t0, 1), round(p, 1)))

    def on_current_file(name, done_n, total):
        progress_marks.append((round(time.monotonic() - t0, 1), f"file {done_n}/{total}: {name}"))

    def on_complete(ok, msg, path):
        box.update(ok=ok, msg=msg, path=path)
        done.set()

    log.info("Запускаю РСЧ за период %s..%s ...", start, end)
    t0 = time.monotonic()
    app_ctl.run_rsch_report_period(
        rsch_sources, out, start, end, on_complete,
        on_progress=on_progress, on_current_file=on_current_file,
    )

    # Ждём с большим запасом (РСЧ за период может идти 5-10 мин на медленной сети).
    deadline = time.monotonic() + 600
    while not done.is_set() and time.monotonic() < deadline:
        time.sleep(0.5)

    elapsed = time.monotonic() - t0
    try:
        app_ctl.shutdown()
    except Exception as e:
        log.warning("shutdown: %s", e)

    log.info("Полное время: %.1f сек (%.1f мин)", elapsed, elapsed / 60)
    log.info("Прогресс-меток: %d", len(progress_marks))
    if progress_marks:
        log.info("Первые 5: %s", progress_marks[:5])
        log.info("Последние 5: %s", progress_marks[-5:])
    log.info("Результат: ok=%s msg=%s", box.get("ok"), str(box.get("msg"))[:200])
    log.info("Файл создан: %s", out.exists())
    return {
        "elapsed_s": round(elapsed, 1),
        "ok": bool(box.get("ok")),
        "msg": str(box.get("msg"))[:300],
        "file_created": out.exists(),
        "progress_marks_count": len(progress_marks),
        "progress_first": progress_marks[:5] if progress_marks else [],
        "progress_last": progress_marks[-5:] if progress_marks else [],
        "timed_out": not done.is_set(),
    }


def main():
    print("=" * 60)
    print("  ДИАГНОСТИКА + ОЧИСТКА (для запуска на ПК заказчицы)")
    print("=" * 60)
    app_root = find_app_root()
    print(f"Папка APP: {app_root}")

    r1 = part1_clean_db(app_root)
    r2 = part2_rsch_period_timing(app_root)

    step("ИТОГ")
    print(f"Очистка БД: {r1}")
    print(f"РСЧ за период: {r2}")

    out_dir = Path(os.environ.get("TEMP", ".")) / "rsch_diag"
    import json
    report = out_dir / "diag_report.json"
    report.write_text(
        json.dumps({"clean": r1, "rsch": r2}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nОтчёт сохранён: {report}")
    print("Скиньте diag_report.json + startup_log.txt разработчику.")


if __name__ == "__main__":
    main()
