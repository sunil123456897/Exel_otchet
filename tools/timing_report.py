#!/usr/bin/env python3
"""Stage 8 — reproducible timing harness for SLA-relevant operations.

Measures the operations the TZ calls out as SLA-bearing:

* **import time** for ``APP`` (cold-start cost of the package).
* **single-file parse** through ``IngestionEngine.read_file`` on a
  synthetic workbook (proxy for refresh-per-employee).
* **LogicService.apply_financial_rules** on N rows (proxy for the
  consolidation engine's per-day work).
* **MasterWriter.write_report** to a temp file (proxy for the export
  step).
* **thread / handle baseline** before and after a burst of operations,
  to detect leaks without requiring psutil.

The harness is deterministic and PII-free: every input is built in
memory from ``tests/golden/synthetic_fixtures``. No real workbooks, no
network drives. The numbers it produces are **floor estimates** of the
real-machine SLA — they will be much faster than the operator's
23-employee refresh because there's no network round-trip. The TZ
accepts this; the harness's job is to detect *regressions*, not to
certify production SLA.

Usage::

    python tools/timing_report.py                  # quick mode, 3 runs
    python tools/timing_report.py --runs 10        # 10-run median + p95
    python tools/timing_report.py --json out.json  # machine-readable

Output is human-readable by default; JSON for CI consumption.
"""
from __future__ import annotations

import argparse
import gc
import json
import statistics
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "APP"))
sys.path.insert(0, str(REPO_ROOT / "tests" / "golden"))

from decimal import Decimal  # noqa: E402

from synthetic_fixtures import build_master_day  # noqa: E402


# ── helpers ────────────────────────────────────────────────────────────


def _median_p95(samples: list[float]) -> tuple[float, float]:
    """Return (median, p95) of *samples* in seconds."""
    if not samples:
        return 0.0, 0.0
    s = sorted(samples)
    median = statistics.median(s)
    # p95: index 0.95 * (n-1). For small n this is approximate.
    idx = int(0.95 * (len(s) - 1))
    p95 = s[idx]
    return median, p95


def _measure(fn: Callable[[], Any], runs: int) -> tuple[list[float], Any]:
    """Run *fn* *runs* times, returning (samples_sec, last_result).

    The first run is treated as warmup and discarded — Python's import
    cache and openpyxl's internal state make the very first call
    significantly slower than steady-state, which would skew the median.
    """
    # Warmup.
    warmup_result = fn()
    samples: list[float] = []
    last = warmup_result
    for _ in range(runs):
        gc.collect()
        gc.disable()  # avoid GC pauses skewing the measurement
        start = time.perf_counter()
        last = fn()
        elapsed = time.perf_counter() - start
        gc.enable()
        samples.append(elapsed)
    gc.enable()
    return samples, last


def _thread_handle_snapshot() -> dict[str, int]:
    """Best-effort thread/handle baseline without psutil.

    ``threading.active_count()`` counts live Thread objects. There is
    no portable Python API for OS-level handles; psutil gives it, but
    requiring psutil as a runtime dep is overkill for the timing tool.
    We track what we can and document the gap in the report.
    """
    return {
        "threads": threading.active_count(),
        # gc.get_objects() count is a weak proxy for retained memory;
        # useful for "did this operation leak 100k objects" detection.
        "gc_objects": len(gc.get_objects()),
    }


# ── the benchmarks ────────────────────────────────────────────────────


def bench_import_app() -> float:
    """Time to import the APP package."""
    # The repo layout puts APP/ on sys.path so ``core.*`` imports work,
    # but to import the ``APP`` package itself the repo root must be on
    # sys.path. We add it temporarily for the measurement.
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    # We measure fresh import by clearing sys.modules first.
    for key in list(sys.modules.keys()):
        if key == "APP" or key.startswith("APP."):
            del sys.modules[key]
    start = time.perf_counter()
    import APP  # noqa: F401
    return time.perf_counter() - start


def bench_parse_synthetic_workbook(tmp_dir: Path) -> float:
    """Time to parse a small synthetic workbook via CalamineReader.

    Uses the in-memory builder so no PII, no network. The number is a
    floor estimate: real per-employee parse includes network latency
    and larger files.
    """
    from core.infra.ingestion_engine import IngestionEngine

    wb_path = tmp_dir / "bench.xlsx"
    build_master_day().save(wb_path)

    markers = {
        "source": "Источник", "amount": "сумма платежа",
        "total": "итог", "customer": "Заказчик",
        "contractor": "Исполнитель", "commission": "комиссия",
        "filters": "фильтры",
    }
    eng = IngestionEngine(markers, drive_letters=("Q", "Z"))
    # Force non-isolated path so we measure parse directly.
    eng._should_isolate_calamine = lambda _p: False  # type: ignore

    start = time.perf_counter()
    rows = eng.read_file(wb_path, strict_io=False)
    elapsed = time.perf_counter() - start
    assert isinstance(rows, list)
    return elapsed


def bench_apply_financial_rules() -> float:
    """Time to apply financial rules to a synthetic batch."""
    from core.domain.logic_service import LogicService

    class _Stub:
        def get_consolidated_data(self, s: str) -> list[dict[str, Any]]:
            return []

        def get_template_errors(self, s: str) -> list[dict[str, Any]]:
            return []

    logic = LogicService(_Stub(), config={"logic": {}})
    # 100 rows — realistic per-day per-employee volume.
    rows = [
        {
            "customer": f"Клиент {i % 5}",
            "contractor": "Подрядчик 1",
            "amount": Decimal(f"{1000 + i}.00"),
            "total": Decimal(f"{1000 + i}.00"),
            "commission": Decimal("50.00"),
            "filters": "",
        }
        for i in range(100)
    ]

    start = time.perf_counter()
    out = logic.apply_financial_rules(rows)
    elapsed = time.perf_counter() - start
    assert isinstance(out, list)
    return elapsed


def bench_write_report(tmp_dir: Path) -> float:
    """Time to write a small report via MasterWriter."""
    from core.infra.export_writer import MasterWriter

    out_path = tmp_dir / "out.xlsx"
    config = {
        "paths": {"master_file": str(out_path)},
        "logic": {},
    }
    writer = MasterWriter(config)

    data = [
        {
            "Дата": "01.05.2026",
            "ЗАКАЗЧИК (название проекта, наименование ЮЛ)": f"Клиент {i}",
            "ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)": "Подрядчик 1",
            "сумма платежа ПРИХОД": Decimal("1000.00"),
            "сумма платежа РАСХОД": Decimal("0.00"),
            "ИТОГ": Decimal("1000.00"),
            "комиссия": Decimal("50.00"),
        }
        for i in range(50)
    ]

    start = time.perf_counter()
    ok = writer.write_report(data, out_path)
    elapsed = time.perf_counter() - start
    assert ok, "write_report returned False"
    return elapsed


# ── leak detection ────────────────────────────────────────────────────


def detect_leak(operation: Callable[[], Any], iterations: int) -> dict[str, int]:
    """Run *operation* *iterations* times; report delta in threads / objects.

    A real leak shows up as steady growth: each iteration adds N to the
    thread count or M to the gc objects count, and the delta doesn't
    flatten out.
    """
    before = _thread_handle_snapshot()
    for _ in range(iterations):
        operation()
    # Give threads time to exit and gc a chance to collect.
    time.sleep(0.1)
    gc.collect()
    after = _thread_handle_snapshot()
    return {
        "iterations": iterations,
        "threads_before": before["threads"],
        "threads_after": after["threads"],
        "threads_delta": after["threads"] - before["threads"],
        "gc_objects_before": before["gc_objects"],
        "gc_objects_after": after["gc_objects"],
        "gc_objects_delta": after["gc_objects"] - before["gc_objects"],
    }


# ── main ──────────────────────────────────────────────────────────────


def run(runs: int) -> dict[str, Any]:
    """Run every benchmark and return a report dict."""
    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "runs_per_benchmark": runs,
        "platform_python": sys.version.split()[0],
    }

    # 1) import APP
    samples, _ = _measure(bench_import_app, runs)
    med, p95 = _median_p95(samples)
    report["import_APP"] = {
        "median_ms": round(med * 1000, 2),
        "p95_ms": round(p95 * 1000, 2),
        "samples_ms": [round(s * 1000, 2) for s in samples],
    }

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)

        # 2) parse synthetic workbook
        samples, _ = _measure(lambda: bench_parse_synthetic_workbook(tmp_dir), runs)
        med, p95 = _median_p95(samples)
        report["parse_synthetic_workbook"] = {
            "median_ms": round(med * 1000, 2),
            "p95_ms": round(p95 * 1000, 2),
            "samples_ms": [round(s * 1000, 2) for s in samples],
            "note": "floor estimate — real per-employee includes network I/O",
        }

        # 3) apply financial rules
        samples, _ = _measure(bench_apply_financial_rules, runs)
        med, p95 = _median_p95(samples)
        report["apply_financial_rules_100_rows"] = {
            "median_ms": round(med * 1000, 2),
            "p95_ms": round(p95 * 1000, 2),
            "samples_ms": [round(s * 1000, 2) for s in samples],
        }

        # 4) write report
        samples, _ = _measure(lambda: bench_write_report(tmp_dir), runs)
        med, p95 = _median_p95(samples)
        report["write_report_50_rows"] = {
            "median_ms": round(med * 1000, 2),
            "p95_ms": round(p95 * 1000, 2),
            "samples_ms": [round(s * 1000, 2) for s in samples],
        }

    # 5) leak detection: run financial-rules 100× and check for growth
    report["leak_after_100_iterations"] = detect_leak(bench_apply_financial_rules, 100)

    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runs", type=int, default=5,
                   help="measurements per benchmark (default 5; first is warmup)")
    p.add_argument("--json", metavar="PATH", help="write JSON to PATH instead of stdout")
    args = p.parse_args()

    report = run(runs=args.runs)

    if args.json:
        out = Path(args.json)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[timing] wrote {out}")
    else:
        print(json.dumps(report, indent=2, ensure_ascii=False))

    # Human summary.
    print()
    print("=== summary (median / p95 ms) ===")
    for key, val in report.items():
        if isinstance(val, dict) and "median_ms" in val:
            print(f"  {key}: {val['median_ms']} / {val['p95_ms']} ms")
    leak = report.get("leak_after_100_iterations", {})
    if leak:
        print(f"  leak: threads_delta={leak.get('threads_delta')} "
              f"gc_objects_delta={leak.get('gc_objects_delta')} "
              f"after {leak.get('iterations')} iters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
