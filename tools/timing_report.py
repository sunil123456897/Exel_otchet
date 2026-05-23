"""Headless timing report for real Master-Report scenarios.

The script measures existing production paths without changing business logic.
Excel outputs are redirected into a temporary benchmark directory.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = REPO_ROOT / "APP"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from core.bootstrap import Bootstrap  # noqa: E402
from core.infra.rsch_report import build_rsch_report  # noqa: E402


@dataclass
class StageTiming:
    stage: str
    location: str
    ok: bool = True
    message: str = ""
    files: int = 0
    rows: int = 0
    scan_s: float = 0.0
    read_s: float = 0.0
    sqlite_s: float = 0.0
    logic_s: float = 0.0
    excel_s: float = 0.0
    total_s: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


class TimingProbe:
    def __init__(self) -> None:
        self.current: StageTiming | None = None
        self._originals: list[tuple[Any, str, Any]] = []

    @contextmanager
    def stage(self, item: StageTiming):
        previous = self.current
        self.current = item
        started = time.perf_counter()
        try:
            yield item
        except Exception as exc:
            item.ok = False
            item.message = str(exc)
            raise
        finally:
            item.total_s = time.perf_counter() - started
            self.current = previous

    def add(self, field_name: str, seconds: float) -> None:
        if self.current is not None:
            setattr(
                self.current,
                field_name,
                getattr(self.current, field_name) + seconds,
            )

    def install_method_timer(
        self,
        obj: Any,
        name: str,
        field_name: str,
        *,
        rows_from_result: bool = False,
        sqlite_rows_arg: int | None = None,
    ) -> None:
        original = getattr(obj, name)

        def wrapper(*args, **kwargs):
            started = time.perf_counter()
            result = original(*args, **kwargs)
            elapsed = time.perf_counter() - started
            self.add(field_name, elapsed)
            if self.current is not None:
                if rows_from_result and isinstance(result, list):
                    self.current.rows += len(result)
                if sqlite_rows_arg is not None and len(args) > sqlite_rows_arg:
                    rows = args[sqlite_rows_arg]
                    if isinstance(rows, list):
                        self.current.details["sqlite_rows"] = (
                            self.current.details.get("sqlite_rows", 0) + len(rows)
                        )
            return result

        self._originals.append((obj, name, original))
        setattr(obj, name, wrapper)

    def restore(self) -> None:
        while self._originals:
            obj, name, original = self._originals.pop()
            setattr(obj, name, original)


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%d.%m.%Y")


def call_threaded(start: Callable[[Callable[..., None]], None], timeout: float) -> tuple:
    done = threading.Event()
    payload: dict[str, Any] = {}

    def on_complete(*args):
        payload["args"] = args
        done.set()

    start(on_complete)
    if not done.wait(timeout):
        raise TimeoutError(f"Timed out after {timeout:.0f}s")
    return payload.get("args", ())


def count_employee_files(employees_map: dict[str, list[Any]]) -> int:
    return sum(len(entries) for entries in employees_map.values())


def resolve_existing_paths(config_controller, values: list[str]) -> list[Path]:
    paths: list[Path] = []
    for value in values:
        path = config_controller.resolve_path(str(value))
        if path.exists():
            paths.append(path)
    return paths


def setup_app(temp_dir: Path, probe: TimingProbe):
    cfg_ctl, app_ctl, db = Bootstrap.setup(APP_ROOT, str(APP_ROOT / "config.yaml"))
    if cfg_ctl is None or app_ctl is None or db is None:
        raise RuntimeError("Bootstrap.setup returned empty components")

    cfg_ctl.save_config = lambda: None
    cfg = cfg_ctl.config
    cfg.setdefault("paths", {})["master_file"] = str(temp_dir / "Master_Report.xlsx")
    app_ctl.writer.master_path = str(temp_dir / "Master_Report.xlsx")

    curators = cfg.setdefault("curators", {})
    if isinstance(curators.get("boris"), dict):
        curators["boris"]["output_path"] = str(temp_dir / "boris_report.xlsx")
    if isinstance(curators.get("ivan"), dict):
        curators["ivan"]["output_path"] = str(temp_dir / "ivan_report.xlsx")

    probe.install_method_timer(app_ctl.discovery, "_scan_discovered_files", "scan_s")
    probe.install_method_timer(app_ctl.ingestion, "scan_directory", "scan_s")
    probe.install_method_timer(
        app_ctl.ingestion, "read_file", "read_s", rows_from_result=True
    )
    probe.install_method_timer(app_ctl.ingestion, "get_available_dates", "read_s")
    for method in (
        "save_session",
        "save_file_metadata",
        "save_staging_data",
        "save_template_errors_batch",
        "update_session_status",
        "update_file_status",
        "wait_for_writes",
        "get_consolidated_data",
        "get_template_errors",
    ):
        if hasattr(app_ctl.persistence, method):
            probe.install_method_timer(
                app_ctl.persistence,
                method,
                "sqlite_s",
                sqlite_rows_arg=1 if method == "save_staging_data" else None,
            )
    probe.install_method_timer(app_ctl.logic_service, "consolidate", "logic_s")
    probe.install_method_timer(app_ctl.writer, "write_report", "excel_s")
    probe.install_method_timer(app_ctl.writer, "write_empty_daily_report", "excel_s")
    return cfg_ctl, app_ctl, db


def run_refresh(app_ctl, selected_date: datetime) -> tuple[list[tuple], dict[str, list[Any]]]:
    result: dict[str, Any] = {}

    def on_complete(data, employees_map, rename_detected):
        result["data"] = data
        result["employees_map"] = employees_map
        result["rename_detected"] = rename_detected

    app_ctl._run_refresh_status(selected_date, lambda _p: None, on_complete)
    return result.get("data", []), result.get("employees_map", {})


def run_consolidation_direct(
    app_ctl,
    *,
    selected_date: datetime | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    curator: str | None = None,
    use_fresh_employees: bool = False,
) -> tuple[bool, str, Path | None]:
    result: dict[str, Any] = {}
    app_ctl._execute_consolidation(
        lambda _p: None,
        lambda ok, msg, path: result.update(ok=ok, msg=msg, path=path),
        selected_date.strftime("%d.%m.%Y") if selected_date else None,
        start_date.strftime("%d.%m.%Y") if start_date else None,
        end_date.strftime("%d.%m.%Y") if end_date else None,
        "monthly" if start_date and end_date else "daily",
        use_fresh_employees,
        curator,
    )
    return bool(result.get("ok")), str(result.get("msg", "")), result.get("path")


def run_report(args: argparse.Namespace) -> list[StageTiming]:
    temp_dir = REPO_ROOT / ".benchmark_tmp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir()

    probe = TimingProbe()
    timings: list[StageTiming] = []
    db = None
    try:
        startup = StageTiming("startup_to_gui_preflight", args.location)
        with probe.stage(startup):
            cfg_ctl, app_ctl, db = setup_app(temp_dir, probe)
            import tkinter as tk
            from core.ui.gui_master import GuiMaster

            root = tk.Tk()
            root.withdraw()
            GuiMaster(root, cfg_ctl, app_ctl)
            root.destroy()
        timings.append(startup)

        selected_date = parse_date(args.date)
        period_start = parse_date(args.period_start)
        period_end = parse_date(args.period_end)

        normal_refresh = StageTiming("refresh_status_cached", args.location)
        with probe.stage(normal_refresh):
            data, employees_map = run_refresh(app_ctl, selected_date)
            normal_refresh.files = count_employee_files(employees_map)
            normal_refresh.rows = len(data)
            normal_refresh.details["employees"] = len(employees_map)
        timings.append(normal_refresh)

        if "discovery_cache" in cfg_ctl.config:
            del cfg_ctl.config["discovery_cache"]
        app_ctl._cached_employees = None
        cleared_refresh = StageTiming("refresh_status_after_discovery_cache_clear", args.location)
        with probe.stage(cleared_refresh):
            data, employees_map = run_refresh(app_ctl, selected_date)
            cleared_refresh.files = count_employee_files(employees_map)
            cleared_refresh.rows = len(data)
            cleared_refresh.details["employees"] = len(employees_map)
        timings.append(cleared_refresh)

        for stage_name, kwargs in (
            ("master_single_date", {"selected_date": selected_date}),
            (
                "master_period",
                {"start_date": period_start, "end_date": period_end},
            ),
            ("boris_single_date", {"selected_date": selected_date, "curator": "boris"}),
            ("ivan_single_date", {"selected_date": selected_date, "curator": "ivan"}),
        ):
            item = StageTiming(stage_name, args.location)
            with probe.stage(item):
                ok, msg, path = run_consolidation_direct(app_ctl, **kwargs)
                item.ok = ok
                item.message = msg
                item.files = count_employee_files(app_ctl._cached_employees or {})
                item.details["output"] = str(path) if path else None
            timings.append(item)

        rsch_values = cfg_ctl.config.get("rsch", {}).get("recent_sources", [])
        rsch_sources = resolve_existing_paths(cfg_ctl, list(rsch_values))
        rsch_item = StageTiming("rsch_single_date", args.location)
        with probe.stage(rsch_item):
            if not rsch_sources:
                rsch_item.ok = False
                rsch_item.message = "No existing rsch.recent_sources"
            else:
                rsch_item.files = len(rsch_sources)
                issues: list[str] = []
                started = time.perf_counter()
                rows = build_rsch_report(
                    rsch_sources,
                    temp_dir / "РСЧ_отчет_benchmark.xlsx",
                    target_date=selected_date.date(),
                    issues_sink=issues,
                    drive_letters=tuple(cfg_ctl.config.get("network", {}).get("drive_letters", ["Q", "Z"])),
                )
                rsch_item.excel_s += time.perf_counter() - started
                rsch_item.rows = rows
                rsch_item.details["issues"] = len(issues)
        timings.append(rsch_item)

        auto_item = StageTiming("auto_reconciliation_full", args.location)
        with probe.stage(auto_item):
            if not rsch_sources:
                auto_item.ok = False
                auto_item.message = "No existing rsch.recent_sources"
            else:
                auto_item.files = count_employee_files(app_ctl._cached_employees or {}) + len(
                    rsch_sources
                )
                completed = call_threaded(
                    lambda cb: app_ctl.run_auto_reconciliation_day(
                        rsch_sources,
                        temp_dir / "Отчет_расхождений_benchmark.xlsx",
                        selected_date,
                        cb,
                    ),
                    args.timeout,
                )
                ok, msg, path = completed
                auto_item.ok = bool(ok)
                auto_item.message = str(msg)
                auto_item.details["output"] = str(path) if path else None
        timings.append(auto_item)

        network_item = StageTiming("qz_discovery_scan", "Q/Z")
        with probe.stage(network_item):
            roots = app_ctl.discovery._resolve_roots_to_scan(cfg_ctl.config)
            qz_roots = [root for root in roots if str(root).upper()[:2] in {"Q:", "Z:"}]
            existing = [root for root in qz_roots if root.exists()]
            network_item.details["configured_roots"] = [str(root) for root in qz_roots]
            network_item.details["existing_roots"] = [str(root) for root in existing]
            if not existing:
                network_item.ok = False
                network_item.message = "Q/Z roots are not available on this PC"
            else:
                files = app_ctl.discovery._scan_discovered_files(existing, all_have_custom=False)
                network_item.files = len(files)
        timings.append(network_item)
    finally:
        probe.restore()
        if db is not None:
            db.close()
        if temp_dir.exists() and not args.keep_outputs:
            shutil.rmtree(temp_dir)
    return timings


def timing_to_dict(item: StageTiming) -> dict[str, Any]:
    return {
        "stage": item.stage,
        "location": item.location,
        "ok": item.ok,
        "message": item.message,
        "files": item.files,
        "rows": item.rows,
        "scan_s": item.scan_s,
        "read_s": item.read_s,
        "sqlite_s": item.sqlite_s,
        "logic_s": item.logic_s,
        "excel_s": item.excel_s,
        "total_s": item.total_s,
        "details": item.details,
    }


def timings_to_markdown(
    timings: list[StageTiming],
    regressions: list[dict[str, Any]] | None = None,
) -> str:
    headers = [
        "stage",
        "location",
        "ok",
        "files",
        "rows",
        "scan_s",
        "read_s",
        "sqlite_s",
        "logic_s",
        "excel_s",
        "total_s",
        "message",
    ]
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(["---"] * len(headers)) + "|",
    ]
    for item in timings:
        values = [
            item.stage,
            item.location,
            str(item.ok),
            str(item.files),
            str(item.rows),
            f"{item.scan_s:.3f}",
            f"{item.read_s:.3f}",
            f"{item.sqlite_s:.3f}",
            f"{item.logic_s:.3f}",
            f"{item.excel_s:.3f}",
            f"{item.total_s:.3f}",
            item.message.replace("|", "/")[:180],
        ]
        lines.append("| " + " | ".join(values) + " |")
    if regressions:
        lines.append("")
        lines.append("## Regressions")
        lines.append("| stage | previous_total_s | current_total_s | change |")
        lines.append("|---|---:|---:|---:|")
        for item in regressions:
            lines.append(
                "| {stage} | {previous_total_s:.3f} | {current_total_s:.3f} | {change_pct:.1f}% |".format(
                    **item
                )
            )
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps([timing_to_dict(item) for item in timings], ensure_ascii=False, indent=2))
    lines.append("```")
    return "\n".join(lines)


def load_previous_benchmark(output_dir: Path, current_json: Path | None = None) -> list[dict[str, Any]]:
    candidates = sorted(output_dir.glob("timing_*.json"), key=lambda path: path.stat().st_mtime)
    if current_json is not None:
        candidates = [path for path in candidates if path.resolve() != current_json.resolve()]
    if not candidates:
        return []
    try:
        return json.loads(candidates[-1].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def compare_with_previous(
    timings: list[StageTiming],
    previous: list[dict[str, Any]],
    threshold: float,
) -> list[dict[str, Any]]:
    previous_by_stage = {
        str(item.get("stage")): item
        for item in previous
        if isinstance(item, dict) and item.get("ok", True)
    }
    regressions: list[dict[str, Any]] = []
    for item in timings:
        if not item.ok:
            continue
        prev = previous_by_stage.get(item.stage)
        if not prev:
            continue
        prev_total = float(prev.get("total_s") or 0)
        if prev_total <= 0:
            continue
        change = (item.total_s - prev_total) / prev_total
        if change >= threshold:
            regressions.append(
                {
                    "stage": item.stage,
                    "previous_total_s": prev_total,
                    "current_total_s": item.total_s,
                    "change_pct": change * 100,
                }
            )
    return regressions


def save_report(
    timings: list[StageTiming],
    output_dir: Path,
    threshold: float,
) -> tuple[Path, Path, list[dict[str, Any]]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"timing_{stamp}.json"
    md_path = output_dir / f"timing_{stamp}.md"
    previous = load_previous_benchmark(output_dir)
    regressions = compare_with_previous(timings, previous, threshold)
    payload = [timing_to_dict(item) for item in timings]
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(timings_to_markdown(timings, regressions), encoding="utf-8")
    return md_path, json_path, regressions


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Master-Report timing benchmark.")
    parser.add_argument("--date", default="12.05.2026")
    parser.add_argument("--period-start", default="01.05.2026")
    parser.add_argument("--period-end", default="22.05.2026")
    parser.add_argument("--location", default="local")
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--keep-outputs", action="store_true")
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "benchmarks"))
    parser.add_argument("--regression-threshold", type=float, default=0.20)
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    timings = run_report(args)
    regressions: list[dict[str, Any]] = []
    if not args.no_save:
        md_path, json_path, regressions = save_report(
            timings,
            Path(args.output_dir),
            args.regression_threshold,
        )
        print(f"Saved benchmark markdown: {md_path}")
        print(f"Saved benchmark json: {json_path}")
    print(timings_to_markdown(timings, regressions))
    return 1 if any(not item.ok for item in timings if item.stage != "qz_discovery_scan") else 0


if __name__ == "__main__":
    raise SystemExit(main())
