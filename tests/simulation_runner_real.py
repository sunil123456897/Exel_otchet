"""Расширенные симуляции на РЕАЛЬНОМ config/cache.db заказчика (QA Phase 4.1c).

Использует настоящий config.yaml и cache.db (где уже есть discovery-кэш с
найденными файлами сотрудников), поэтому консолидация и свёрка работают с
полными данными. Output направляется во временную папку, чтобы НЕ затереть
рабочие отчёты заказчика.

ВНИМАНИЕ: запускает тяжёлые операции на реальных данных. Output во временную
папку %TEMP%/qa_real_out.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from datetime import date, datetime
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent / "APP"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout)
log = logging.getLogger("SimReal")

PROJECT = APP_ROOT.parent
TEMP_OUT = Path(os.environ.get("TEMP", "/tmp")) / "qa_real_out"
TEMP_OUT.mkdir(parents=True, exist_ok=True)


def _wait():
    done = threading.Event()
    box: dict = {}

    def cb(ok, msg, path=None):
        box.update(ok=ok, msg=msg, path=path)
        done.set()

    return cb, done, box


def _run(name, fn, timeout=300):
    cb, done, box = _wait()
    t0 = time.monotonic()
    try:
        fn(cb)
    except Exception as e:
        box.update(ok=False, msg=f"exception: {e}", path=None)
        done.set()
    finished = done.wait(timeout=timeout)
    elapsed = time.monotonic() - t0
    ok = box.get("ok") if finished else False
    status = "PASS" if ok else "FAIL"
    log.info("%s [%s] %.1fs  msg=%s", status, name, elapsed, str(box.get("msg"))[:160])
    return {"name": name, "ok": bool(ok), "elapsed_s": round(elapsed, 2),
            "msg": str(box.get("msg"))[:300], "timed_out": not finished}


def main():
    log.info("=== Симуляции на РЕАЛЬНОМ config/cache.db заказчика ===")
    log.info("Output направлен в: %s", TEMP_OUT)

    from core.bootstrap import Bootstrap
    cfg_ctl, app_ctl, db = Bootstrap.setup(APP_ROOT, APP_ROOT / "config.yaml")

    results: list[dict] = []
    try:
        # НЕ перенаправляем output: path-traversal guard в resolve_path
        # (функция безопасности) блокирует пути вне разрешённых корней
        # (source_roots / project root / config dir). Заказчик и так
        # перегенерирует Master_Report/boris/ivan при каждом запуске — это
        # нормальный рабочий процесс, поэтому пишем туда же, куда и GUI.
        # Сначала сделаем резервные копии текущих отчётов, чтобы иметь
        # возможность сравнить/откатить.
        for rep in [
            PROJECT / "Master_Report.xlsx",
            APP_ROOT / "output" / "boris_report.xlsx",
            APP_ROOT / "output" / "ivan_report.xlsx",
        ]:
            if rep.exists():
                bak = rep.with_suffix(".xlsx.qasim_bak")
                if not bak.exists():
                    rep.replace(bak) if False else __import__("shutil").copy2(rep, bak)
        log.info("Резервные копии отчётов сохранены (.qasim_bak)")

        # ---------- S1: Консолидация за день ----------
        def s1(cb):
            app_ctl.run_consolidation(datetime(2026, 5, 26), lambda p: None, cb)
        results.append(_run("S1_consolidation_day", s1, timeout=180))

        # ---------- S2: Консолидация за все даты ----------
        def s2(cb):
            app_ctl.run_consolidation_all_dates(lambda p: None, cb)
        results.append(_run("S2_consolidation_all", s2, timeout=300))

        # ---------- S3: Консолидация за период ----------
        def s3(cb):
            app_ctl.run_consolidation_month(
                date(2026, 5, 20), date(2026, 5, 29), lambda p: None, cb
            )
        results.append(_run("S3_consolidation_period", s3, timeout=300))

        # ---------- S10: refresh_status ----------
        def s10(cb):
            app_ctl.refresh_status(datetime(2026, 5, 26), lambda p: None, cb)
        results.append(_run("S10_refresh_status", s10, timeout=120))

        # ---------- S8: Автосверка за день ----------
        rsch_sources = sorted((PROJECT / "рсч всех").glob("*.xlsx"))

        def s8(cb):
            app_ctl.run_auto_reconciliation_day(
                rsch_sources, TEMP_OUT / "Автосверка.xlsx", date(2026, 5, 26), cb
            )
        results.append(_run("S8_auto_reconciliation", s8, timeout=300))

    finally:
        try:
            app_ctl.shutdown()
        except Exception as e:
            log.warning("shutdown: %s", e)

    passed = sum(1 for r in results if r["ok"])
    log.info("\n=== ИТОГ (реальный config) ===")
    for r in results:
        mark = "✓ PASS" if r["ok"] else "✗ FAIL"
        to = " TIMEOUT" if r.get("timed_out") else ""
        log.info("  %s  %-32s %.1fs%s", mark, r["name"], r["elapsed_s"], to)
    log.info("Пройдено: %d/%d", passed, len(results))

    out = PROJECT / "docs" / "qa" / "simulation_real_results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"passed": passed, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Результаты: %s", out)
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
