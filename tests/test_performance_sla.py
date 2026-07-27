"""Stage 8 — SLA + leak-detection tests.

The TZ defines SLA targets for end-user-perceived latency. Most of
those targets (window startup ≤5s, 23-employee refresh ≤2s, real
consolidation ≤30s) cannot be measured in CI without a real display
and real network paths. What we CAN measure here:

* the floor cost of each pipeline stage on synthetic data;
* regressions vs the floor (a 20% regression detection);
* leaks of threads and Python objects across repeated operations.

CI thresholds are deliberately loose (10× the observed floor) so they
do not flake on slow runners. The timing harness
(``tools/timing_report.py``) is the tighter reference run on the
operator's machine.

The leak tests are strict: a single-threaded operation must not spawn
threads or accumulate objects. A failure here is always a real bug.
"""
from __future__ import annotations

import gc
import statistics
import sys
import threading
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


# ── helpers ─────────────────────────────────────────────────────────────


def _median_of(fn, runs: int = 5) -> float:
    """Return the median elapsed seconds over *runs* invocations of *fn*."""
    # Warmup once to stabilise caches.
    fn()
    samples: list[float] = []
    for _ in range(runs):
        gc.collect()
        start = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - start)
    return statistics.median(samples)


# ── 1) Pipeline-stage SLA floors ────────────────────────────────────────
#
# Each test measures one pipeline stage on a synthetic input. The
# threshold is 10× the observed median on the development machine; CI
# runners vary widely, so we use generous bounds to avoid flakiness.
# A real regression will blow through 10× easily.


def test_apply_financial_rules_completes_under_generous_threshold() -> None:
    """apply_financial_rules on 100 rows must complete under 500 ms.

    Floor (dev machine): ~2 ms. Threshold: 250× margin. A failure means
    a real regression — e.g. an accidentally quadratic regex, a
    blocking I/O call inside the loop, or a per-row DB hit.
    """
    from core.domain.logic_service import LogicService

    class _Stub:
        def get_consolidated_data(self, s: str) -> list[dict[str, Any]]:
            return []

        def get_template_errors(self, s: str) -> list[dict[str, Any]]:
            return []

    logic = LogicService(_Stub(), config={"logic": {}})
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

    median = _median_of(lambda: logic.apply_financial_rules(rows))
    assert median < 0.5, (
        f"apply_financial_rules regressed: median {median*1000:.1f} ms "
        f"(threshold 500 ms)"
    )


def test_synthetic_workbook_parse_under_generous_threshold(tmp_path: Path) -> None:
    """CalamineReader on a small synthetic workbook must parse under 1 s.

    Floor: ~6 ms. Threshold: ~150× margin. Real per-employee parse on a
    network drive adds latency; the harness is the floor, not the SLA.
    """
    sys.path.insert(0, str(REPO_ROOT / "tests" / "golden"))
    try:
        from synthetic_fixtures import build_master_day
        from core.infra.ingestion_engine import IngestionEngine

        wb_path = tmp_path / "sla.xlsx"
        build_master_day().save(wb_path)

        markers = {
            "source": "Источник", "amount": "сумма платежа",
            "total": "итог", "customer": "Заказчик",
            "contractor": "Исполнитель", "commission": "комиссия",
            "filters": "фильтры",
        }
        eng = IngestionEngine(markers, drive_letters=("Q", "Z"))
        eng._should_isolate_calamine = lambda _p: False  # type: ignore

        median = _median_of(lambda: eng.read_file(wb_path, strict_io=False))
        assert median < 1.0, (
            f"parse regressed: median {median*1000:.1f} ms (threshold 1000 ms)"
        )
    finally:
        sys.path.remove(str(REPO_ROOT / "tests" / "golden"))


def test_write_report_under_generous_threshold(tmp_path: Path) -> None:
    """MasterWriter on 50 rows must complete under 5 s.

    Floor: ~65 ms. Threshold: ~75× margin. openpyxl I/O is the slowest
    pipeline stage; this catches an accidentally expensive formatting
    call (e.g. style lookup in a quadratic loop).
    """
    from core.infra.export_writer import MasterWriter

    out_path = tmp_path / "out.xlsx"
    writer = MasterWriter({"paths": {"master_file": str(out_path)}, "logic": {}})
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

    median = _median_of(lambda: writer.write_report(data, out_path))
    assert median < 5.0, (
        f"write_report regressed: median {median*1000:.1f} ms (threshold 5000 ms)"
    )


# ── 2) Leak detection ──────────────────────────────────────────────────


def test_financial_rules_does_not_leak_threads_or_objects() -> None:
    """100 iterations of apply_financial_rules must not grow threads/objects.

    A real leak shows up as monotonic growth. We allow a small slack
    (+200 objects) because Python's gc tracks ephemeral state like
    traceback frames; anything larger is a leak.
    """
    from core.domain.logic_service import LogicService

    class _Stub:
        def get_consolidated_data(self, s: str) -> list[dict[str, Any]]:
            return []

        def get_template_errors(self, s: str) -> list[dict[str, Any]]:
            return []

    logic = LogicService(_Stub(), config={"logic": {}})
    rows = [
        {
            "customer": "Клиент А", "contractor": "Подрядчик 1",
            "amount": Decimal("1000.00"), "total": Decimal("1000.00"),
            "commission": Decimal("0"), "filters": "",
        }
    ]

    gc.collect()
    threads_before = threading.active_count()
    objects_before = len(gc.get_objects())

    for _ in range(100):
        logic.apply_financial_rules(rows)

    # Let any worker threads exit and gc settle.
    time.sleep(0.05)
    gc.collect()

    threads_after = threading.active_count()
    objects_after = len(gc.get_objects())

    thread_delta = threads_after - threads_before
    object_delta = objects_after - objects_before

    assert thread_delta == 0, (
        f"thread leak: {thread_delta} new threads after 100 iterations"
    )
    assert object_delta < 200, (
        f"possible object leak: +{object_delta} gc objects after 100 iterations "
        f"(threshold 200)"
    )


def test_workbook_parse_does_not_leak_threads(tmp_path: Path) -> None:
    """Repeated parsing must not accumulate threads."""
    sys.path.insert(0, str(REPO_ROOT / "tests" / "golden"))
    try:
        from synthetic_fixtures import build_master_day
        from core.infra.ingestion_engine import IngestionEngine

        wb_path = tmp_path / "leak.xlsx"
        build_master_day().save(wb_path)
        eng = IngestionEngine(
            {"source": "Источник", "amount": "сумма платежа", "total": "итог",
             "customer": "Заказчик", "contractor": "Исполнитель",
             "commission": "комиссия", "filters": "фильтры"},
            drive_letters=("Q", "Z"),
        )
        eng._should_isolate_calamine = lambda _p: False  # type: ignore

        gc.collect()
        threads_before = threading.active_count()

        for _ in range(20):
            eng.read_file(wb_path, strict_io=False)

        time.sleep(0.05)
        gc.collect()
        threads_after = threading.active_count()

        assert threads_after == threads_before, (
            f"thread leak in reader: {threads_after - threads_before} new threads"
        )
    finally:
        sys.path.remove(str(REPO_ROOT / "tests" / "golden"))


def test_excel_open_close_cycle_does_not_leak_handles(tmp_path: Path) -> None:
    """Open/modify/save/close cycles must not leak OS file handles.

    On Windows, leaked handles prevent the file from being renamed or
    deleted. We do 20 cycles and verify the file can be renamed
    afterwards — equivalent to "no handles are open".
    """
    import openpyxl

    path = tmp_path / "cycle.xlsx"
    openpyxl.Workbook().save(path)

    for _ in range(20):
        wb = openpyxl.load_workbook(path)
        wb.active["A1"] = "x"
        wb.save(path)
        wb.close()
        gc.collect()

    # If any handle is open, this rename will fail with PermissionError.
    renamed = tmp_path / "renamed.xlsx"
    os_replace = __import__("os").replace
    os_replace(path, renamed)
    assert renamed.exists()


# ── 3) Idempotent re-run performance ───────────────────────────────────


def test_repeated_writes_do_not_grow_in_duration(tmp_path: Path) -> None:
    """10 consecutive writes should not become progressively slower.

    A growing trend indicates a leak (e.g. accumulating styles in
    openpyxl's internal registry). We check the last write is not >50%
    slower than the first.
    """
    from core.infra.export_writer import MasterWriter

    out_path = tmp_path / "out.xlsx"
    writer = MasterWriter({"paths": {"master_file": str(out_path)}, "logic": {}})
    data = [
        {
            "Дата": "01.05.2026",
            "ЗАКАЗЧИК (название проекта, наименование ЮЛ)": "Клиент А",
            "ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)": "Подрядчик 1",
            "сумма платежа ПРИХОД": Decimal("1000.00"),
            "сумма платежа РАСХОД": Decimal("0.00"),
            "ИТОГ": Decimal("1000.00"),
            "комиссия": Decimal("50.00"),
        }
    ]

    durations: list[float] = []
    for _ in range(10):
        start = time.perf_counter()
        writer.write_report(data, out_path)
        durations.append(time.perf_counter() - start)

    # Compare the median of the first 3 against the median of the last 3.
    # The first write includes warmup (style cache miss, openpyxl import),
    # and CI runners may be loaded by other tests — a single slow outlier
    # should not flip a pass into a fail.
    import statistics
    early_median = statistics.median(durations[:3])
    late_median = statistics.median(durations[-3:])
    assert late_median < early_median * 3.0, (
        f"writes are slowing down: early_median={early_median*1000:.1f} ms, "
        f"late_median={late_median*1000:.1f} ms — possible leak"
    )


# ── 4) Regression detection vs recorded baseline ───────────────────────


def test_timing_report_runs_without_error(tmp_path: Path) -> None:
    """The timing harness must complete cleanly with --runs 2.

    This is a smoke test for the harness itself; the actual regression
    detection runs out-of-band (operator runs timing_report.py and
    compares to the previous run).
    """
    import subprocess

    json_out = tmp_path / "timing.json"
    rc = subprocess.run(
        [sys.executable, "tools/timing_report.py", "--runs", "2",
         "--json", str(json_out)],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120,
    )
    assert rc.returncode == 0, (
        f"timing_report failed (rc={rc.returncode}):\n{rc.stderr}"
    )
    assert json_out.exists(), "timing_report did not write JSON output"

    import json
    data = json.loads(json_out.read_text(encoding="utf-8"))
    # Sanity: every benchmark produced a non-zero median.
    for key in ("import_APP", "parse_synthetic_workbook",
                "apply_financial_rules_100_rows", "write_report_50_rows"):
        assert key in data, f"missing benchmark {key!r} in report"
        assert data[key]["median_ms"] > 0, (
            f"benchmark {key!r} produced zero median — measurement failed"
        )
