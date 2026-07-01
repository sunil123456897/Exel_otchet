# -*- coding: utf-8 -*-
"""Полная диагностика программы Master-Report (запускать на ПК заказчика).

Лежит в корне проекта (рядом с ЗАПУСК.bat). Запускается:
  • двойным кликом по «ДИАГНОСТИКА.bat» (проще для заказчика), либо
  • вручную:  .venv\\Scripts\\python.exe Диагностика.py

Что делает (полная проверка всего):
  1. Система: Python, версия ОС, ключевые библиотеки (openpyxl, calamine).
  2. Версия программы: последний git-коммит / .update_state/last_sha.txt.
  3. Пути: APP, .venv, config, БД, schema, источники РСЧ, отчёты сотрудников.
  4. Config: source_roots, rsch.recent_sources, network.drive_letters.
  5. Данные: есть ли источники РСЧ, Master_Report, шаблон РСЧ.
  6. Сетевые диски: доступность Q: / Z: (если настроены).
  7. Состояние БД: размер, integrity_check, кол-во записей, orphan-сессии.
  8. Очистка БД: purge старых сессий (FK-фикс) + VACUUM, с backup.
  9. Smoke: чтение одного РСЧ-файла с таймингом.
 10. Smoke: сборка «РСЧ за период» с таймингом и прогрессом.
 11. Отчёт: ДИАГНОСТИКА_ОТЧЁТ.txt (для заказчика) + .json (для разработчика)
     создаются РЯДОМ с этим скриптом (в той же папке).

Ничего не удаляет без бэкапа; данные сотрудников и настройки не трогает.
Все тяжёлые операции — по подтверждению (по умолчанию YES = делать).
"""
from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
from datetime import date, datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("Diag")

ROOT = Path(__file__).resolve().parent
APP = ROOT / "APP"
REPORT_TXT = ROOT / "ДИАГНОСТИКА_ОТЧЁТ.txt"
REPORT_JSON = ROOT / "ДИАГНОСТИКА_ОТЧЁТ.json"

_lines: list[str] = []


def out(msg: str = "") -> None:
    """Печать + накопление для итогового .txt отчёта."""
    print(msg)
    _lines.append(msg)


def section(title: str) -> None:
    line = "=" * 64
    out("")
    out(line)
    out(f"  {title}")
    out(line)


def ok(label: str, value, good: bool | None = None) -> None:
    mark = "✓" if good is None or good else "✗"
    out(f"  {mark} {label}: {value}")


# ── 1. Система ───────────────────────────────────────────────────────


def check_system(rep: dict) -> None:
    section("1. СИСТЕМА")
    rep["system"] = {}
    rep["system"]["python"] = sys.version.split()[0]
    rep["system"]["platform"] = platform.platform()
    ok("Python", sys.version.split()[0])
    ok("ОС", platform.platform())
    # Ключевые библиотеки.
    libs = {}
    for mod in ("openpyxl", "python_calamine", "ruamel.yaml", "pydantic", "yaml"):
        try:
            m = __import__(mod)
            ver = getattr(m, "__version__", getattr(m, "VERSION", "?"))
            libs[mod] = ver
            ok(f"библиотека {mod}", ver)
        except Exception as e:
            libs[mod] = f"ОТСУТСТВУЕТ ({e})"
            ok(f"библиотека {mod}", f"ОТСУТСТВУЕТ — {e}", good=False)


# ── 2. Версия программы ──────────────────────────────────────────────


def check_version(rep: dict) -> None:
    section("2. ВЕРСИЯ ПРОГРАММЫ")
    rep["version"] = {}
    sha = None
    src = None
    # Сначала git.
    if (ROOT / ".git").exists():
        try:
            r = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(ROOT), capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0:
                sha = r.stdout.strip()[:12]
                src = "git"
        except Exception:
            pass
    # Потом .update_state.
    if not sha:
        state_file = ROOT / ".update_state" / "last_sha.txt"
        if state_file.exists():
            raw = state_file.read_text(encoding="utf-8", errors="ignore")
            # PS 5.1 мог записать файл с UTF-8 BOM — убираем.
            if raw.startswith("\ufeff"):
                raw = raw.lstrip("\ufeff")
            sha = raw.strip()[:12]
            src = ".update_state/last_sha.txt"
    ok("commit SHA", sha or "НЕ НАЙДЕН", good=bool(sha))
    ok("источник", src or "—")
    rep["version"]["sha"] = sha
    rep["version"]["source"] = src


# ── 3. Пути ──────────────────────────────────────────────────────────


def check_paths(rep: dict) -> None:
    section("3. ПУТИ И ФАЙЛЫ")
    rep["paths"] = {}
    checks = {
        "APP/": APP,
        "APP/main.py": APP / "main.py",
        ".venv/Scripts/python.exe": ROOT / ".venv" / "Scripts" / "python.exe",
        "APP/config.yaml": APP / "config.yaml",
        "APP/cache.db": APP / "cache.db",
        "APP/db_schema.sql": APP / "db_schema.sql",
        "ЗАПУСК.bat": ROOT / "ЗАПУСК.bat",
        "tools/update_from_github.ps1": ROOT / "tools" / "update_from_github.ps1",
    }
    for label, p in checks.items():
        exists = p.exists()
        rep["paths"][label] = {"path": str(p), "exists": exists}
        ok(label, ("есть" if exists else "НЕТ") + f" → {p}", good=exists)


# ── 4-5. Config + данные ────────────────────────────────────────────

# Кэш источников РСЧ, собранных как настоящее приложение: из
# config.yaml → rsch.recent_sources (с фильтром существующих) плюс
# fallback на папку «рсч всех/». Используется секциями 9 и 10.
RSCH_SOURCES: list[Path] = []


def check_config_and_data(rep: dict) -> None:
    global RSCH_SOURCES
    section("4. CONFIG И ДАННЫЕ")
    rep["config"] = {}
    rep["data"] = {}
    cfg_path = APP / "config.yaml"
    cfg = {}
    if cfg_path.exists():
        try:
            import yaml

            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        except Exception as e:
            ok("config.yaml", f"ошибка чтения: {e}", good=False)
    paths_cfg = cfg.get("paths", {}) or {}
    rsch_cfg = cfg.get("rsch", {}) or {}
    net_cfg = cfg.get("network", {}) or {}
    rep["config"]["source_roots"] = paths_cfg.get("source_roots")
    rep["config"]["master_file"] = paths_cfg.get("master_file")
    rep["config"]["rsch_recent_sources"] = rsch_cfg.get("recent_sources")
    rep["config"]["drive_letters"] = net_cfg.get("drive_letters")
    ok("source_roots", paths_cfg.get("source_roots"))
    ok("master_file", paths_cfg.get("master_file"))
    ok("rsch.recent_sources", f"{len(rsch_cfg.get('recent_sources') or [])} шт.")
    ok("network.drive_letters", net_cfg.get("drive_letters"))

    # Источники РСЧ. Берём из config.yaml → rsch.recent_sources — точно так
    # же, как настоящее приложение (см. _rsch.py:_get_saved_rsch_sources):
    # абсолютные пути как есть, относительные — от папки APP/. Фильтруем
    # существующие. Дополнительно показываем папку «рсч всех/» как
    # ориентир, но работаем именно с configured-источниками.
    section("5. ИСТОЧНИКИ ДАННЫХ")
    raw_sources = rsch_cfg.get("recent_sources") or []
    if isinstance(raw_sources, str):
        raw_sources = [raw_sources]
    configured: list[Path] = []
    for raw in raw_sources:
        if not raw:
            continue
        p = Path(str(raw))
        if not p.is_absolute():
            p = (APP / p).resolve()
        configured.append(p)

    existing_cfg = [p for p in configured if p.exists()]
    rep["data"]["rsch_configured_count"] = len(configured)
    rep["data"]["rsch_configured_existing"] = len(existing_cfg)
    ok("РСЧ в config (всего)", len(configured))
    ok("РСЧ в config (существуют)", len(existing_cfg),
       good=bool(existing_cfg))
    for p in configured:
        mark = "✓" if p.exists() else "✗"
        out(f"      {mark} {p}")
    # Папка «рсч всех» — только ориентир.
    rsch_dir = ROOT / "рсч всех"
    rsch_files = sorted(rsch_dir.glob("*.xlsx")) if rsch_dir.exists() else []
    rep["data"]["rsch_dir_count"] = len(rsch_files)
    ok("папка «рсч всех»", f"{len(rsch_files)} файлов (ориентир)",
       good=None)

    # Источники для smoke-тестов: сначала configured+existing, иначе папка.
    if existing_cfg:
        RSCH_SOURCES = existing_cfg
    elif rsch_files:
        RSCH_SOURCES = rsch_files
    else:
        RSCH_SOURCES = []
    rep["data"]["rsch_sources_for_smoke"] = [str(p) for p in RSCH_SOURCES]

    # Master + шаблон.
    master = ROOT / "Master_Report.xlsx"
    ok("Master_Report.xlsx", "есть" if master.exists() else "НЕТ", good=master.exists())
    rep["data"]["master_report"] = master.exists()
    rsch_tpl = APP / "РСЧ" / "шаблон отчета.xlsx"
    ok("шаблон РСЧ", "есть" if rsch_tpl.exists() else "НЕТ (исп. встроенный)",
       good=rsch_tpl.exists())
    rep["data"]["rsch_template"] = rsch_tpl.exists()


# ── 6. Сетевые диски ────────────────────────────────────────────────


def check_network(rep: dict) -> None:
    section("6. СЕТЕВЫЕ ДИСКИ")
    rep["network"] = {}
    letters = (cfg_get_drive_letters() or ["Q", "Z"])
    for letter in letters:
        drive = f"{letter}:\\"
        exists = os.path.exists(drive)
        rep["network"][drive] = exists
        ok(drive, "доступен" if exists else "НЕ доступен", good=exists)


def cfg_get_drive_letters():
    cfg_path = APP / "config.yaml"
    if not cfg_path.exists():
        return None
    try:
        import yaml

        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        return (cfg.get("network", {}) or {}).get("drive_letters")
    except Exception:
        return None


# ── 7-8. БД: состояние + очистка ────────────────────────────────────


def check_db(rep: dict, do_clean: bool) -> None:
    section("7. СОСТОЯНИЕ БАЗЫ ДАННЫХ (cache.db)")
    rep["db"] = {}
    db_path = APP / "cache.db"
    if not db_path.exists():
        ok("cache.db", "НЕТ", good=False)
        return
    size_before = db_path.stat().st_size
    ok("размер ДО", f"{size_before / 1024 / 1024:.1f} МБ")
    rep["db"]["size_before_mb"] = round(size_before / 1024 / 1024, 1)

    conn = sqlite3.connect(str(db_path))
    counts = {}
    integrity = None
    try:
        # integrity_check.
        row = conn.execute("PRAGMA integrity_check").fetchone()
        integrity = row[0] if row else "?"
        ok("integrity_check", integrity, good=(integrity == "ok"))
        rep["db"]["integrity"] = integrity
        # Кол-во записей.
        for t in ("sessions", "source_files", "staging_data", "template_errors",
                  "consolidated_results", "row_cache", "file_cache",
                  "discovery_cache", "customer_aliases"):
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                counts[t] = n
            except Exception:
                counts[t] = "—"
        for t, n in counts.items():
            out(f"      {t}: {n}")
        rep["db"]["counts"] = counts
        # Orphan-сессии (завершённые старше 30 дней) — те, что purge должен убрать.
        try:
            old = conn.execute(
                "SELECT COUNT(*) FROM sessions "
                "WHERE created_at < datetime('now','-30 days') "
                "AND status IN ('completed','failed','cancelled')"
            ).fetchone()[0]
            ok("старых сессий к удалению", old)
            rep["db"]["old_sessions"] = old
        except Exception:
            rep["db"]["old_sessions"] = None
    finally:
        conn.close()

    if do_clean:
        section("8. ОЧИСТКА БАЗЫ ДАННЫХ")
        backup = db_path.with_suffix(".db.diag_backup")
        try:
            shutil.copy2(db_path, backup)
            ok("backup", backup.name)
        except Exception as e:
            ok("backup", f"ошибка: {e}", good=False)
            return
        # Purge через исправленный репозиторий (FK-фикс).
        try:
            sys.path.insert(0, str(APP))
            from core.infra.session_repo import SessionRepository

            repo = SessionRepository(
                str(db_path), str(APP / "db_schema.sql"),
                {"database": {"use_wal": False}},
            )
            deleted = repo.purge_old_sessions(max_age_days=30)
            repo.close()
            ok("purge: удалено сессий", deleted)
            rep["db"]["purged"] = deleted
        except Exception as e:
            ok("purge", f"ошибка: {e}", good=False)
            rep["db"]["purge_error"] = str(e)
        # VACUUM.
        try:
            conn = sqlite3.connect(str(db_path))
            conn.execute("VACUUM")
            conn.close()
            size_after = db_path.stat().st_size
            ok("размер ПОСЛЕ VACUUM", f"{size_after / 1024 / 1024:.1f} МБ "
              f"(−{(size_before - size_after) / 1024 / 1024:.1f} МБ)")
            rep["db"]["size_after_mb"] = round(size_after / 1024 / 1024, 1)
        except Exception as e:
            ok("VACUUM", f"ошибка: {e}", good=False)
            rep["db"]["vacuum_error"] = str(e)
    else:
        out("")
        out("  (очистка пропущена — ответьте ДА при запуске, чтобы почистить)")


# ── 9-10. Smoke-тесты РСЧ ────────────────────────────────────────────


def smoke_read_one_rsch(rep: dict) -> None:
    section("9. ЧТЕНИЕ ОДНОГО РСЧ-ФАЙЛА (тайминг сети/парсинга)")
    rep["smoke_read"] = {}
    if not RSCH_SOURCES:
        ok("источники РСЧ", "НЕТ — пропускаю", good=False)
        return
    sys.path.insert(0, str(APP))
    try:
        from core.infra.rsch._collect import _collect_rows_from_workbook

        f = RSCH_SOURCES[0]
        t0 = time.monotonic()
        rows = _collect_rows_from_workbook(f, None)
        elapsed = time.monotonic() - t0
        ok(f"{f.name}", f"{len(rows)} строк за {elapsed:.1f} с")
        rep["smoke_read"] = {"file": f.name, "rows": len(rows), "seconds": round(elapsed, 1)}
    except Exception as e:
        ok("чтение", f"ошибка: {e}", good=False)
        rep["smoke_read"]["error"] = str(e)


def smoke_rsch_period(rep: dict, do_period: bool) -> None:
    section("10. СБОРКА «РСЧ ЗА ПЕРИОД» (тайминг + прогресс)")
    rep["smoke_period"] = {}
    if not do_period:
        out("  (пропущено — ответьте ДА при запуске, чтобы прогнать)")
        rep["smoke_period"]["skipped"] = True
        return
    try:
        sys.path.insert(0, str(APP))
        from core.bootstrap import Bootstrap

        cfg_ctl, app_ctl, db = Bootstrap.setup(APP, APP / "config.yaml")
        rsch_sources = list(RSCH_SOURCES)
        out_path = ROOT / "ДИАГ_РСЧ_период.xlsx"
        start = date(2026, 6, 1)
        end = date(2026, 6, 30)

        done = threading.Event()
        box: dict = {}
        marks: list = []

        def on_progress(p):
            marks.append((round(time.monotonic() - t0, 1), round(p, 1)))

        def on_current_file(name, d, total):
            marks.append((round(time.monotonic() - t0, 1), f"{d}/{total} {name}"))

        def on_complete(ok_flag, msg, path):
            box.update(ok=ok_flag, msg=msg, path=path)
            done.set()

        out(f"  Запускаю РСЧ за период {start}..{end} ({len(rsch_sources)} источников)...")
        out("  ⏳ ждите до 10 минут (сборка по сети идёт долго)...")
        t0 = time.monotonic()
        app_ctl.run_rsch_report_period(
            rsch_sources, out_path, start, end, on_complete,
            on_progress=on_progress, on_current_file=on_current_file,
        )
        deadline = time.monotonic() + 600
        while not done.is_set() and time.monotonic() < deadline:
            time.sleep(0.5)
        elapsed = time.monotonic() - t0
        try:
            app_ctl.shutdown()
        except Exception:
            pass
        ok("полное время", f"{elapsed:.1f} с ({elapsed/60:.1f} мин)")
        ok("результат", "УСПЕХ" if box.get("ok") else
           ("ТАЙМАУТ (не дождались)" if not done.is_set() else "ОШИБКА"),
           good=bool(box.get("ok")))
        ok("сообщение", str(box.get("msg", ""))[:200])
        ok("файл создан", out_path.exists(), good=out_path.exists())
        ok("прогресс-меток", len(marks))
        if marks:
            out(f"      первые: {marks[:5]}")
            out(f"      последние: {marks[-5:]}")
        rep["smoke_period"] = {
            "elapsed_s": round(elapsed, 1),
            "ok": bool(box.get("ok")),
            "msg": str(box.get("msg", ""))[:300],
            "file_created": out_path.exists(),
            "timed_out": not done.is_set(),
            "progress_count": len(marks),
            "progress_first": marks[:5],
            "progress_last": marks[-5:],
        }
    except Exception:
        err = traceback.format_exc()
        out("  ОШИБКА прогона:")
        out(err)
        rep["smoke_period"]["error"] = err


# ── main ─────────────────────────────────────────────────────────────


def ask(prompt: str, default_yes: bool = True) -> bool:
    """Спросить да/нет (через консоль). По умолчанию — да."""
    if "-y" in sys.argv or "--yes" in sys.argv:
        return True
    suffix = " [Y/n]" if default_yes else " [y/N]"
    try:
        ans = input(prompt + suffix).strip().lower()
    except EOFError:
        return default_yes
    if not ans:
        return default_yes
    return ans in ("y", "да", "yes", "д")


def main() -> int:
    out("=" * 64)
    out("  ПОЛНАЯ ДИАГНОСТИКА Master-Report")
    out(f"  Папка: {ROOT}")
    out(f"  Время: {datetime.now():%Y-%m-%d %H:%M:%S}")
    out("=" * 64)

    rep: dict = {"started_at": datetime.now().isoformat()}

    do_clean = ask("Почистить БД (purge + VACUUM)?", default_yes=True)
    do_period = ask("Прогнать «РСЧ за период» с таймингом (до 10 мин)?", default_yes=True)

    try:
        check_system(rep)
        check_version(rep)
        check_paths(rep)
        check_config_and_data(rep)
        check_network(rep)
        check_db(rep, do_clean=do_clean)
        smoke_read_one_rsch(rep)
        smoke_rsch_period(rep, do_period=do_period)
    except Exception:
        out("")
        out("НЕПРЕДВИДЕННАЯ ОШИБКА ДИАГНОСТИКИ:")
        out(traceback.format_exc())
        rep["fatal_error"] = traceback.format_exc()

    rep["finished_at"] = datetime.now().isoformat()

    section("ИТОГ")
    out("Отчёты сохранены:")
    out(f"  • {REPORT_TXT.name}  — для заказчика (прочитать / скинуть)")
    out(f"  • {REPORT_JSON.name} — для разработчика")
    if (ROOT / "ДИАГ_РСЧ_период.xlsx").exists():
        out("  • ДИАГ_РСЧ_период.xlsx — собранный РСЧ (если прогон был)")

    # Запись отчётов.
    REPORT_TXT.write_text("\n".join(_lines), encoding="utf-8")
    REPORT_JSON.write_text(
        json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    out("")
    out("Сделано. Можете закрыть это окно.")
    if "-y" not in sys.argv and "--yes" not in sys.argv:
        try:
            input("\nНажмите Enter, чтобы закрыть окно...")
        except EOFError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
