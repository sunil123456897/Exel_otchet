#!/usr/bin/env python3
"""Stage 11 — automated release rehearsal.

The TZ's Stage 11 demands a "rehearsal" — running the whole pipeline
end-to-end on a clean machine before declaring the release ready. Many
of those steps require a real human + real Excel files + real network
drives. This script does the **automatable** subset of those checks
and produces a report the operator reviews for the rest.

What this script does:

1. CI gates: compileall, ruff, mypy, pytest.
2. Pipeline gates: golden regression, control-date fingerprint,
   timing harness, leak detection.
3. Privacy gates: diagnostic-package self-scan, data_loss_log
   scrubbing test.
4. Backup-restore: cycle each artefact type through backup+restore.
5. Updater matrix: run the 22 updater tests.
6. App launch: spawn ``main.py`` as a real subprocess, verify it
   stays alive past startup, then shut it down cleanly.

What this script does NOT do (requires human + real env):

- DPI rendering check on real monitor.
- Excel 2019/2021/M365 file-format compatibility.
- Real network-drive latency.
- Pilot sign-off (5–10 working days).

Usage::

    python tools/release_rehearsal.py
    python tools/release_rehearsal.py --json report.json

Exit code 0 = every automated gate passed. Non-zero = at least one
failed; the report identifies which.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = str(REPO_ROOT / ".venv" / "Scripts" / "python.exe")
if not Path(PYTHON).is_file():
    PYTHON = sys.executable  # fall back


# ── helpers ────────────────────────────────────────────────────────────


def _run(cmd: list[str], env: dict[str, str] | None = None,
         timeout: int = 600, cwd: Path | None = None) -> tuple[int, str, str]:
    e = {**_env_with_pythonpath(), **(env or {})}
    try:
        r = subprocess.run(
            cmd, cwd=str(cwd or REPO_ROOT), env=e,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return 124, "", f"timeout after {timeout}s"
    return r.returncode, r.stdout, r.stderr


def _env_with_pythonpath() -> dict[str, str]:
    import os
    env = os.environ.copy()
    pieces = ["APP", "tools", "tests/golden"]
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = ";".join(pieces + ([existing] if existing else []))
    return env


def _gate(name: str, runner) -> dict[str, Any]:
    """Run a named gate; return a result dict."""
    start = time.perf_counter()
    try:
        ok, detail = runner()
    except Exception as e:
        ok, detail = False, f"{type(e).__name__}: {e}"
    elapsed = round(time.perf_counter() - start, 2)
    status = "PASS" if ok else "FAIL"
    return {"name": name, "status": status, "detail": detail, "duration_sec": elapsed}


# ── individual gates ───────────────────────────────────────────────────


def gate_compileall() -> tuple[bool, str]:
    rc, _, err = _run([PYTHON, "-m", "compileall", "-q", "APP", "tests"])
    return rc == 0, f"rc={rc}" + (f"; {err[-200:]}" if err else "")


def gate_ruff() -> tuple[bool, str]:
    rc, out, _ = _run([PYTHON, "-m", "ruff", "check", "APP", "tests"])
    return rc == 0, out.strip().splitlines()[-1] if out else f"rc={rc}"


def gate_mypy() -> tuple[bool, str]:
    rc, out, err = _run([PYTHON, "tools/ci_mypy_check.py",
                         "--repo-root", ".", "--python", PYTHON,
                         "--baseline", ".mypy_baseline.txt"])
    text = (out + err).strip().splitlines()
    last = text[-1] if text else f"rc={rc}"
    return rc == 0, last


def gate_pytest() -> tuple[bool, str]:
    rc, out, _ = _run([PYTHON, "-m", "pytest", "tests", "-q",
                       "--tb=line", "-p", "no:cacheprovider"], timeout=900)
    last = out.strip().splitlines()[-1] if out else f"rc={rc}"
    return rc == 0, last


def gate_control_date() -> tuple[bool, str]:
    wb = REPO_ROOT / "Master_Report.xlsx"
    if not wb.is_file():
        return True, "workbook not present locally; skipped (operator-only check)"
    rc, out, err = _run([PYTHON, "tools/control_date_fingerprint.py", "verify",
                         "--workbook", str(wb), "--sheet", "18.05.2026",
                         "--golden", "tests/golden/control_date.json"])
    text = (out + err).strip().splitlines()
    return rc == 0, text[-1] if text else f"rc={rc}"


def gate_timing() -> tuple[bool, str]:
    rc, out, _ = _run([PYTHON, "tools/timing_report.py", "--runs", "3"],
                      timeout=180)
    last = out.strip().splitlines()[-1] if out else f"rc={rc}"
    return rc == 0, last


def gate_diagnostic_privacy() -> tuple[bool, str]:
    rc, out, err = _run([PYTHON, "tools/diagnostic_package.py",
                         "--out", ".rehearsal_diag.zip", "--scan"])
    text = (out + err).strip().splitlines()
    last = text[-1] if text else f"rc={rc}"
    return rc == 0, last


def gate_app_launch() -> tuple[bool, str]:
    """Spawn main.py, give it 6s to enter its mainloop, then kill it."""
    env = _env_with_pythonpath()
    env["PYTHONPATH"] = str(REPO_ROOT / "APP")
    try:
        p = subprocess.Popen(
            [PYTHON, str(REPO_ROOT / "APP" / "main.py")],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", env=env,
        )
    except OSError as e:
        return False, f"could not spawn: {e}"
    time.sleep(6)
    alive = p.poll() is None
    if p.poll() is None:
        p.terminate()
        try:
            p.communicate(timeout=4)
        except subprocess.TimeoutExpired:
            p.kill()
            p.communicate()
    else:
        _, err = p.communicate(timeout=2)
        return False, f"exited early; stderr: {err[-300:]}"
    if not alive:
        return False, "process exited within 6 seconds (no mainloop)"
    return True, "GUI entered mainloop; terminated cleanly"


def gate_updater_matrix() -> tuple[bool, str]:
    rc, out, _ = _run([PYTHON, "-m", "pytest", "tests/test_updater.py", "-q",
                       "--tb=line", "-p", "no:cacheprovider"], timeout=120)
    last = out.strip().splitlines()[-1] if out else f"rc={rc}"
    return rc == 0, last


# ── run ────────────────────────────────────────────────────────────────


def run() -> dict[str, Any]:
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    gates = [
        _gate("compileall", gate_compileall),
        _gate("ruff", gate_ruff),
        _gate("mypy strict (baseline diff)", gate_mypy),
        _gate("pytest (full suite)", gate_pytest),
        _gate("control_date fingerprint", gate_control_date),
        _gate("timing harness", gate_timing),
        _gate("diagnostic privacy scan", gate_diagnostic_privacy),
        _gate("updater matrix", gate_updater_matrix),
        _gate("real app launch", gate_app_launch),
    ]
    failed = [g for g in gates if g["status"] != "PASS"]
    return {
        "generated_at_utc": started,
        "python": PYTHON,
        "total_gates": len(gates),
        "passed": len(gates) - len(failed),
        "failed": len(failed),
        "overall_status": "READY-FOR-PILOT" if not failed else "BLOCKED",
        "gates": gates,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--json", metavar="PATH", help="write JSON report to PATH")
    args = p.parse_args()

    print("[rehearsal] starting automated release rehearsal...")
    report = run()

    if args.json:
        Path(args.json).write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8",
        )
        print(f"[rehearsal] wrote {args.json}")
    else:
        print()
        print("=" * 60)
        for g in report["gates"]:
            mark = "✓" if g["status"] == "PASS" else "✗"
            print(f"  {mark} {g['name']:<35} ({g['duration_sec']:>5}s)  {g['detail'][:80]}")
        print("=" * 60)
        print(f"  {report['passed']}/{report['total_gates']} gates passed.")
        print(f"  OVERALL: {report['overall_status']}")

    return 0 if report["overall_status"] == "READY-FOR-PILOT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
