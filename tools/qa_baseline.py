#!/usr/bin/env python3
"""Generate a machine-readable, PII-free baseline report for Master-Report.

Produces ``baseline_report.json`` at the repo root by default. Used by the
Stage 0 gate (TZ MR-0002 + MR-0006) and as the reference point for Stage 8
performance SLA tracking.

Strict privacy rules — the report MUST NOT contain:

* real employee names or any string from ``APP/employees.yaml``;
* real amounts, account numbers, file paths under employees' folders;
* the GitHub token value or any ``ghp_``-shaped secret;
* contents of real Excel workbooks (``*.xlsx`` outside ``tests/``);
* full configuration dumps (only keys, value types, and availability flags).

Two modes:

* ``--quick`` (default): collect-only for test counts + mypy count. Fast
  (~5–10 s), suitable for repeated local runs.
* ``--full``: actually run pytest (with coverage) and timing harness.
  This is what the Stage 0 gate runs. Slow (~2–5 min).

Timing measurements (MR-0006):

* startup time — not measurable here (requires GUI); we record a marker;
* refresh / consolidation — only if a ``--with-timing`` flag is given and
  a fixture path is supplied. Otherwise we record ``"not_measured"`` with
  a reason. This keeps the baseline deterministic in environments without
  real data.

Token audit (MR-0006):

* checks that ``.github_token`` (if present locally) is gitignored;
* scans test fixtures and tools for accidental token-shaped strings;
* reports presence/absence — never the token value.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── path setup ──────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent

# Patterns that look like a leaked secret. We never capture the value — only
# the fact that a line matched, so the report stays PII-free.
_TOKEN_PATTERN = re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,}")


# ── helpers ─────────────────────────────────────────────────────────────
def _run(cmd: list[str], cwd: Path | None = None, timeout: int = 600) -> tuple[int, str, str]:
    """Run *cmd* and return ``(rc, stdout, stderr)`` as text."""
    try:
        r = subprocess.run(
            cmd, cwd=str(cwd or REPO_ROOT), capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        return 124, "", f"timeout after {timeout}s: {e}"
    return r.returncode, r.stdout, r.stderr


def _git_sha() -> dict[str, str]:
    rc, out, _ = _run(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"])
    rc_br, br, _ = _run(["git", "-C", str(REPO_ROOT), "rev-parse", "--abbrev-ref", "HEAD"])
    rc_dirty, dirty_out, _ = _run(["git", "-C", str(REPO_ROOT), "status", "--porcelain"])
    dirty_lines = [l for l in dirty_out.splitlines() if l.strip()]
    return {
        "sha": out.strip() if rc == 0 else "unknown",
        "branch": br.strip() if rc_br == 0 else "unknown",
        "dirty": bool(dirty_lines) if rc_dirty == 0 else None,
        "dirty_files": len(dirty_lines) if rc_dirty == 0 else None,
    }


def _app_version() -> str:
    init = REPO_ROOT / "APP" / "__init__.py"
    text = init.read_text(encoding="utf-8")
    m = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    return m.group(1) if m else "unknown"


def _python_versions(python_exe: str) -> dict[str, str]:
    out: dict[str, str] = {}
    rc, pyver, _ = _run([python_exe, "--version"])
    out["python"] = pyver.strip().split()[-1] if rc == 0 else "unknown"
    # Map our short name → pip distribution name (they sometimes differ).
    dist_name = {
        "pip": "pip",
        "pytest": "pytest",
        "ruff": "ruff",
        "mypy": "mypy",
        "openpyxl": "openpyxl",
        "calamine": "python-calamine",
        "pydantic": "pydantic",
    }
    for tool, dist in dist_name.items():
        rc, v, _ = _run([python_exe, "-m", "pip", "show", dist], timeout=60)
        if rc == 0:
            m = re.search(r"^Version:\s*(\S+)", v, re.MULTILINE)
            if m:
                out[tool] = m.group(1)
                continue
        out[tool] = "unknown"
    return out


def _platform_info() -> dict[str, str]:
    rc, out, _ = _run(["cmd.exe", "/c", "ver"], timeout=10)
    platform_str = out.strip() if rc == 0 else "unknown"
    return {
        "os_version_cmd": platform_str,
        "python_platform": sys.platform,
    }


def _ruff_check() -> dict[str, Any]:
    start = time.perf_counter()
    rc, out, err = _run([sys.executable, "-m", "ruff", "check", "APP", "tests"], timeout=120)
    return {
        "exit_code": rc,
        "clean": rc == 0,
        "duration_sec": round(time.perf_counter() - start, 2),
        "stderr_tail": err.strip().splitlines()[-5:] if err else [],
    }


def _compileall_check() -> dict[str, Any]:
    start = time.perf_counter()
    rc, out, err = _run([sys.executable, "-m", "compileall", "-q", "APP", "tests"], timeout=180)
    return {
        "exit_code": rc,
        "success": rc == 0,
        "duration_sec": round(time.perf_counter() - start, 2),
    }


def _mypy_strict() -> dict[str, Any]:
    """Run mypy and report counts (stdout = findings, stderr = tool errors)."""
    start = time.perf_counter()
    cmd = [sys.executable, "-m", "mypy", "APP",
           "--ignore-missing-imports", "--strict", "--no-error-summary"]
    rc, out, err = _run(cmd, timeout=300)
    findings = [l for l in out.splitlines() if l.strip()]
    # How many distinct normalized findings (matching ci_mypy_check.py logic).
    line_re = re.compile(r"(?P<prefix>^\S+?):(?P<lineno>\d+):(?P<rest>.*$)")
    normalized: set[str] = set()
    for line in findings:
        norm = line.replace("\\", "/").rstrip()
        m = line_re.match(norm)
        normalized.add(f"{m.group('prefix')}:LINE:{m.group('rest')}" if m else norm)
    return {
        "exit_code": rc,
        "raw_finding_lines": len(findings),
        "normalized_distinct": len(normalized),
        "duration_sec": round(time.perf_counter() - start, 2),
        "stderr_empty": not err.strip(),
    }


def _pytest_collect_only() -> dict[str, Any]:
    """Fast test count without running them."""
    start = time.perf_counter()
    rc, out, err = _run(
        [sys.executable, "-m", "pytest", "tests",
         "--collect-only", "-q", "-p", "no:cacheprovider", "--no-header"],
        timeout=120,
        cwd=REPO_ROOT,
    )
    # Pytest collect-only prints ``<tests>/<total> tests collected`` near the end,
    # plus ``error:`` lines on failure. Parse defensively.
    collected = None
    for line in (out + err).splitlines():
        m = re.search(r"(\d+) tests collected", line)
        if m:
            collected = int(m.group(1))
            break
    errors = [l for l in (out + err).splitlines() if "error" in l.lower()]
    return {
        "collected": collected,
        "exit_code": rc,
        "collection_errors": len(errors),
        "duration_sec": round(time.perf_counter() - start, 2),
    }


def _pytest_full() -> dict[str, Any]:
    """Run the suite with coverage if pytest-cov is available, else without.

    We refuse to silently install pytest-cov into the operator's venv. If
    it is missing we record the fact and run plain pytest so the test
    counts and skip-reason classification still work. The coverage
    percentage is reported as ``null`` with an explicit reason in that case.
    """
    start = time.perf_counter()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT / "APP")

    # Probe for pytest-cov without modifying the venv.
    probe = subprocess.run(
        [sys.executable, "-c", "import pytest_cov; print('ok')"],
        capture_output=True, text=True, timeout=15,
    )
    cov_available = probe.returncode == 0

    cmd = [sys.executable, "-m", "pytest", "tests",
           "-q", "--tb=short", "-p", "no:cacheprovider"]
    if cov_available:
        cmd += ["--cov=APP", "--cov-report=term-missing", "--cov-branch"]

    try:
        r = subprocess.run(
            cmd, cwd=str(REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=env, timeout=900,
        )
    except subprocess.TimeoutExpired:
        return {"timed_out": True, "duration_sec": 900, "pytest_cov_available": cov_available}
    out, err, rc = r.stdout, r.stderr, r.returncode

    def _grab(pattern: str, default: Any = None) -> Any:
        m = re.search(pattern, out)
        return m.group(1) if m else default

    summary: dict[str, Any] = {
        "exit_code": rc,
        "passed": int(_grab(r"(\d+) passed", 0)),
        "failed": int(_grab(r"(\d+) failed", 0)),
        "errors": int(_grab(r"(\d+) errors", 0)),
        "skipped": int(_grab(r"(\d+) skipped", 0)),
        "duration_sec": round(time.perf_counter() - start, 2),
        "pytest_cov_available": cov_available,
    }

    if cov_available:
        cov_match = re.search(r"^TOTAL\s+\d+\s+\d+\s+(\d+)%", out, re.MULTILINE)
        summary["coverage_total_pct"] = int(cov_match.group(1)) if cov_match else None
    else:
        summary["coverage_total_pct"] = None
        summary["coverage_missing_reason"] = (
            "pytest-cov is not installed in the active venv. Install "
            "requirements-dev.txt to capture coverage, or run "
            "`coverage run -m pytest && coverage report` manually."
        )

    # Skip-reason classification. Each skip line in pytest -v includes a
    # reason in parentheses. We tally the reasons.
    skip_reasons: dict[str, int] = {}
    for line in out.splitlines():
        m = re.search(r"SKIPPED.*?\(([^)]+)\)", line)
        if m:
            reason = m.group(1).strip()[:60]
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
    summary["skip_reasons_top"] = dict(sorted(skip_reasons.items(),
                                              key=lambda kv: -kv[1])[:10])
    return summary


def _timing_measurements(python_exe: str) -> dict[str, Any]:
    """MR-0006: timing baseline for key operations.

    Real-user-facing timings (app startup, refresh of 23 employees) need the
    GUI and real network paths — not safe to run here. We measure only what
    is deterministic and PII-free:

    * import time for ``APP`` (proxy for cold startup cost of the package);
    * mypy/ruff/pytest durations are recorded separately in their sections.

    The Stage 8 SLA discussion uses these numbers as floor estimates.
    """
    rc, out, err = _run(
        [python_exe, "-c",
         "import time, sys; sys.path.insert(0, '.'); "
         "t=time.perf_counter(); import APP; "
         "print(f'import_APP_ms={(time.perf_counter()-t)*1000:.1f}')"],
        cwd=str(REPO_ROOT), timeout=30,
    )
    m = re.search(r"import_APP_ms=([\d.]+)", out)
    return {
        "import_APP_ms": float(m.group(1)) if m else None,
        "note": (
            "Real SLA-relevant timings (GUI startup, 23-employee refresh, "
            "23-file consolidation) require GUI + real network paths and are "
            "not safe to measure here. They are measured manually in Stage 8 "
            "against a controlled fixture and recorded in the stage report."
        ),
        "raw_exit_code": rc,
    }


def _token_audit() -> dict[str, Any]:
    """MR-0006: confirm .github_token is gitignored and absent from fixtures."""
    audit: dict[str, Any] = {}

    # 1) Is .github_token present locally? (allowed — it's gitignored)
    token_path = REPO_ROOT / ".github_token"
    audit["local_github_token_present"] = token_path.exists()
    if token_path.exists():
        rc, out, _ = _run(["git", "-C", str(REPO_ROOT), "check-ignore", "-v",
                           str(token_path)])
        audit["github_token_gitignored"] = rc == 0
        audit["github_token_ignore_rule"] = out.strip() if rc == 0 else "NOT IGNORED"

    # 2) Scan test fixtures + tools for token-shaped strings.
    scan_dirs = [REPO_ROOT / "tests", REPO_ROOT / "tools"]
    hits: list[str] = []
    for d in scan_dirs:
        if not d.is_dir():
            continue
        for path in d.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in {".pyc", ".png", ".jpg", ".jpeg", ".xlsx",
                                       ".xls", ".db", ".sqlite"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except (OSError, UnicodeDecodeError):
                continue
            for line in text.splitlines():
                if _TOKEN_PATTERN.search(line):
                    rel = path.relative_to(REPO_ROOT).as_posix()
                    hits.append(f"{rel}: token-shaped string on a line")
                    break  # one hit per file is enough
    audit["token_shaped_strings_in_fixtures_or_tools"] = hits
    audit["token_shaped_string_count"] = len(hits)
    return audit


def build_report(python_exe: str, full: bool) -> dict[str, Any]:
    """Assemble the full baseline report dict."""
    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tool": "tools/qa_baseline.py",
        "tool_version": "1.0",
        "mode": "full" if full else "quick",
    }

    report["git"] = _git_sha()
    report["app_version"] = _app_version()
    report["platform"] = _platform_info()
    report["python_and_deps"] = _python_versions(python_exe)
    report["compileall"] = _compileall_check()
    report["ruff"] = _ruff_check()
    report["mypy_strict"] = _mypy_strict()

    if full:
        report["pytest"] = _pytest_full()
    else:
        report["pytest_collect_only"] = _pytest_collect_only()

    report["timing"] = _timing_measurements(python_exe)
    report["token_audit"] = _token_audit()

    return report


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--python", default=sys.executable,
                   help="python interpreter to run sub-tools with")
    p.add_argument("--full", action="store_true",
                   help="run the full pytest suite with coverage (slow)")
    p.add_argument("--out", default=str(REPO_ROOT / "baseline_report.json"),
                   help="output JSON path (default: ./baseline_report.json)")
    p.add_argument("--pretty", action="store_true",
                   help="pretty-print JSON")
    args = p.parse_args()

    start = time.perf_counter()
    print(f"[baseline] mode={'full' if args.full else 'quick'} "
          f"python={args.python}", file=sys.stderr)
    report = build_report(args.python, full=args.full)
    report["total_duration_sec"] = round(time.perf_counter() - start, 2)

    out_path = Path(args.out)
    out_path.write_text(
        json.dumps(report, indent=2 if args.pretty else None, ensure_ascii=False,
                   sort_keys=True),
        encoding="utf-8",
    )
    print(f"[baseline] wrote {out_path} ({out_path.stat().st_size} bytes)")
    print(f"[baseline] total duration: {report['total_duration_sec']}s")

    # Surface key facts for the human reader without dumping the JSON.
    print(f"[baseline] app_version={report['app_version']}")
    print(f"[baseline] git sha={report['git']['sha'][:12]} "
          f"branch={report['git']['branch']}")
    if args.full and "pytest" in report:
        pt = report["pytest"]
        print(f"[baseline] pytest: passed={pt.get('passed')} "
              f"failed={pt.get('failed')} skipped={pt.get('skipped')} "
              f"coverage={pt.get('coverage_total_pct')}%")
    print(f"[baseline] mypy normalized findings: "
          f"{report['mypy_strict']['normalized_distinct']}")
    print(f"[baseline] ruff clean: {report['ruff']['clean']}")
    print(f"[baseline] compileall success: {report['compileall']['success']}")
    ta = report["token_audit"]
    print(f"[baseline] token audit: local_token_present="
          f"{ta['local_github_token_present']} "
          f"gitignored={ta.get('github_token_gitignored')} "
          f"fixture_hits={ta['token_shaped_string_count']}")

    # Non-zero exit only if a hard gate fails. The caller (CI) decides what
    # to do with the report; this tool is descriptive, not a gate.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
