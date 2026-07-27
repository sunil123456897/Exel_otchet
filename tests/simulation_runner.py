"""Headless-драйвер для симуляций работы заказчика (QA-sweep Phase 4).

Прогоняет РЕАЛЬНЫЕ сценарии (консолидация/РСЧ/сверка) на настоящих файлах
заказчика через AppController, БЕЗ GUI. Каждый сценарий пишет отчёт во
временную папку и проверяет результат.

Запуск:
    cd APP && ../.venv/Scripts/python.exe ../tests/simulation_runner.py [--smoke]

--smoke = только быстрые S1/S4/S5 (минимум); иначе — полный набор.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import threading
import time
from datetime import date, datetime
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent / "APP"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("Sim")

# Реальные данные заказчика
PROJECT_ROOT = APP_ROOT.parent
RSCH_SOURCES = sorted((PROJECT_ROOT / "рсч всех").glob("*.xlsx"))
EMPLOYEE_ROOT = PROJECT_ROOT / "REPORTS" / "Отчет кураторов 3"


def _make_isolated_env(tmp_root: Path) -> tuple[Path, Path]:
    """Создаёт изолированную среду: временные config.yaml + БД, копия сотрудников.

    Важно: НЕ трогаем config.yaml / cache.db заказчика.
    """
    tmp_root.mkdir(parents=True, exist_ok=True)
    cfg_dst = tmp_root / "config.yaml"
    emp_dst = tmp_root / "employees.yaml"
    db_dst = tmp_root / "sim.db"
    schema_src = APP_ROOT / "db_schema.sql"

    # Минимальный config, ссылающийся на РЕАЛЬНЫЕ исходники заказчика,
    # но с временной БД и output во временную папку.
    cfg = {
        "database": {
            "path": str(db_dst),
            "schema_path": str(schema_src),
            "timeout": 30.0,
            "use_wal": True,
        },
        "network": {"drive_letters": ["Q", "Z"]},
        "logic": {"commission_is_percent": True, "income_overrides": [], "return_keywords": ["возврат"]},
        "paths": {
            "master_file": str(tmp_root / "Master_Report.xlsx"),
            "source_root": str(EMPLOYEE_ROOT),
            "source_roots": [str(EMPLOYEE_ROOT)],
            "archive_dir": str(tmp_root / "backups"),
            "output_root": "",
        },
        "performance": {"isolate_calamine": False, "max_workers": 0},
        "backup": {"excel_keep": 3},
    }
    import yaml  # PyYAML из requirements

    with open(cfg_dst, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True)

    # employees.yaml: каждый сотрудник → его реальная папка с отчётом
    employees = {}
    for emp_dir in sorted(EMPLOYEE_ROOT.iterdir()):
        if emp_dir.is_dir():
            xlsx_files = sorted(emp_dir.glob("*.xlsx"))
            if xlsx_files:
                employees[emp_dir.name] = [str(p) for p in xlsx_files]
    with open(emp_dst, "w", encoding="utf-8") as f:
        yaml.safe_dump(employees, f, allow_unicode=True)

    return cfg_dst, db_dst


def _bootstrap(cfg_path: Path):
    from core.bootstrap import Bootstrap

    cfg_ctl, app_ctl, db = Bootstrap.setup(APP_ROOT, cfg_path)
    return cfg_ctl, app_ctl, db


def _wait(on_complete_factory, timeout=180):
    """Оборачивает AppController-вызовы: ждёт on_complete(ok,msg,path)."""
    done = threading.Event()
    box: dict = {}

    def cb(ok, msg, path=None):
        box["ok"] = ok
        box["msg"] = msg
        box["path"] = path
        done.set()

    return cb, done, box, timeout


def _result(name, box, elapsed, done):
    ok = box.get("ok")
    status = "PASS" if ok else "FAIL"
    log.info(
        "%s [%s] %s  (%.1fs)  msg=%s",
        status,
        name,
        "✓" if ok else "✗",
        elapsed,
        str(box.get("msg"))[:160],
    )
    return {
        "name": name,
        "ok": bool(ok),
        "elapsed_s": round(elapsed, 2),
        "msg": str(box.get("msg"))[:300],
        "path": str(box.get("path")) if box.get("path") else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="только S1/S4/S5")
    parser.add_argument("--out", default=str(PROJECT_ROOT / "docs" / "qa" / "simulation_results.json"))
    args = parser.parse_args()

    log.info("=== QA Симуляции работы заказчика ===")
    log.info("RSCH источников: %d, папок сотрудников: %d", len(RSCH_SOURCES), len(list(EMPLOYEE_ROOT.iterdir())))

    tmp_root = Path(os.environ.get("TEMP", "/tmp")) / "qa_sim_env"
    if tmp_root.exists():
        shutil.rmtree(tmp_root, ignore_errors=True)
    cfg_path, db_path = _make_isolated_env(tmp_root)
    log.info("Изолированная среда: %s", tmp_root)

    cfg_ctl, app_ctl, db = _bootstrap(cfg_path)
    results: list[dict] = []

    try:
        # ---------- S5: РСЧ за период (БАГ ЗАКАЗЧИКА — критично) ----------
        out = tmp_root / "РСЧ_период.xlsx"
        cb, done, box, to = _wait(None)
        start = date(2026, 5, 12)
        end = date(2026, 5, 29)
        t0 = time.monotonic()
        prog = []
        app_ctl.run_rsch_report_period(
            RSCH_SOURCES, out, start, end, cb,
            on_progress=lambda p: prog.append(p),
            on_current_file=lambda n, d, t: None,
        )
        if not done.wait(timeout=to):
            log.error("S5 TIMEOUT")
            results.append({"name": "S5_rsch_period", "ok": False, "msg": "timeout"})
        else:
            r = _result("S5_rsch_period (БАГ)", box, time.monotonic() - t0, done)
            r["progress_reports"] = len(prog)
            r["file_exists"] = out.exists()
            results.append(r)

        if args.smoke:
            # smoke = S5 (уже выше) + S4 + S1
            pass

        # ---------- S4: РСЧ за один день ----------
        out2 = tmp_root / "РСЧ_день.xlsx"
        cb, done, box, to = _wait(None)
        t0 = time.monotonic()
        app_ctl.run_rsch_report(RSCH_SOURCES, out2, date(2026, 5, 26), cb)
        done.wait(timeout=to)
        results.append(_result("S4_rsch_day", box, time.monotonic() - t0, done))

        # ---------- S6: РСЧ за период batch (по файлам на дату) ----------
        outdir = tmp_root / "rsch_batch"
        cb, done, box, to = _wait(None)
        t0 = time.monotonic()
        app_ctl.run_rsch_report_period_batch(RSCH_SOURCES, outdir, date(2026, 5, 25), date(2026, 5, 27), cb)
        done.wait(timeout=to)
        results.append(_result("S6_rsch_period_batch", box, time.monotonic() - t0, done))

        # ---------- S1: Консолидация за день ----------
        cb, done, box, to = _wait(None)
        t0 = time.monotonic()
        app_ctl.run_consolidation(datetime(2026, 5, 26), lambda p: None, cb)
        done.wait(timeout=to)
        results.append(_result("S1_consolidation_day", box, time.monotonic() - t0, done))

        if args.smoke:
            _summarize(results, args.out)
            return

        # ---------- S2: Консолидация за все даты ----------
        cb, done, box, to = _wait(None)
        t0 = time.monotonic()
        app_ctl.run_consolidation_all_dates(lambda p: None, cb)
        done.wait(timeout=300)
        results.append(_result("S2_consolidation_all", box, time.monotonic() - t0, done))

        # ---------- S3: Консолидация за период ----------
        cb, done, box, to = _wait(None)
        t0 = time.monotonic()
        app_ctl.run_consolidation_month(date(2026, 5, 20), date(2026, 5, 29), lambda p: None, cb)
        done.wait(timeout=300)
        results.append(_result("S3_consolidation_period", box, time.monotonic() - t0, done))

        # ---------- S10: refresh_status ----------
        cb_err = []
        cb, done, box, to = _wait(None)

        def on_err(m):
            cb_err.append(m)

        t0 = time.monotonic()
        app_ctl.refresh_status(datetime(2026, 5, 26), lambda p: None, cb, on_error=on_err)
        done.wait(timeout=120)
        results.append(_result("S10_refresh_status", box, time.monotonic() - t0, done))

        # ---------- S8: Автосверка за день (master + rsch) ----------
        auto_out = tmp_root / "Автосверка.xlsx"
        cb, done, box, to = _wait(None)
        t0 = time.monotonic()
        app_ctl.run_auto_reconciliation_day(
            RSCH_SOURCES, auto_out, date(2026, 5, 26), cb
        )
        done.wait(timeout=300)
        results.append(_result("S8_auto_reconciliation", box, time.monotonic() - t0, done))

    finally:
        try:
            app_ctl.shutdown()
        except Exception as e:
            log.warning("shutdown error: %s", e)

    _summarize(results, args.out)


def _summarize(results, out_path):
    log.info("\n=== ИТОГ СИМУЛЯЦИЙ ===")
    passed = sum(1 for r in results if r["ok"])
    failed = len(results) - passed
    for r in results:
        mark = "✓ PASS" if r["ok"] else "✗ FAIL"
        extra = f"  progress_reports={r.get('progress_reports')}" if "progress_reports" in r else ""
        log.info("  %s  %-32s %.1fs%s", mark, r["name"], r.get("elapsed_s", 0), extra)
    log.info("---\nПройдено: %d/%d", passed, len(results))

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"passed": passed, "failed": failed, "results": results}, f, ensure_ascii=False, indent=2)
    log.info("Результаты: %s", out_path)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
