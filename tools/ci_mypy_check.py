#!/usr/bin/env python3
"""CI mypy gate: fail only on NEW strict errors not present in the baseline.

This script replaces the previous in-workflow inline Python that read only
``mypy``'s ``stderr``. mypy writes its actual findings to **stdout** (with
``stderr`` reserved for tool crashes / config errors), so the old gate saw
zero errors and was effectively a no-op.

Behaviour:

* Runs ``mypy --strict APP``.
* Captures **both** stdout and stderr; uses stdout for the actual findings.
* Normalizes each finding the same way ``qa_mypy_baseline.py`` does
  (``\\`` → ``/``, ``:NN:`` → ``:LINE:``) so adding/removing a line above
  an existing error is not mistaken for a new one.
* Compares the normalized set against ``.mypy_baseline.txt``.
* Exits 0 if no new findings, 1 if there are any.
* Never writes to the baseline file. Refreshing it is a separate, deliberate
  action via ``tools/qa_mypy_baseline.py`` and must be a reviewable commit.

This is a transitional gate while the codebase is being typed (Stage 5 of
the TZ). Once mypy strict is clean, the baseline file can be deleted and
this script replaced with a plain ``mypy --strict APP`` step.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_LINE_NUM_RE = re.compile(r"(?P<prefix>^\S+?):(?P<lineno>\d+):(?P<rest>.*$)")


def normalize(raw_line: str) -> str:
    line = raw_line.replace("\\", "/").rstrip()
    m = _LINE_NUM_RE.match(line)
    if m:
        return f"{m.group('prefix')}:LINE:{m.group('rest')}"
    return line


def run_mypy(repo_root: Path, python_exe: str) -> tuple[str, str, int]:
    cmd = [python_exe, "-m", "mypy", "APP",
           "--ignore-missing-imports", "--strict", "--no-error-summary"]
    result = subprocess.run(
        cmd, cwd=str(repo_root), capture_output=True, text=True, encoding="utf-8"
    )
    return result.stdout, result.stderr, result.returncode


def load_baseline(path: Path) -> set[str]:
    if not path.exists():
        # No baseline = every finding is new. Refuse to pass silently.
        sys.stderr.write(
            f"[mypy-gate] baseline file missing: {path}\n"
            "Run `python tools/qa_mypy_baseline.py` locally and commit the result.\n"
        )
        sys.exit(2)
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root", default=".")
    p.add_argument("--python", default=sys.executable)
    p.add_argument("--baseline", default=".mypy_baseline.txt")
    args = p.parse_args()

    repo_root = Path(args.repo_root).resolve()
    baseline_path = Path(args.baseline)
    if not baseline_path.is_absolute():
        baseline_path = repo_root / baseline_path

    baseline = load_baseline(baseline_path)

    stdout, stderr, rc = run_mypy(repo_root, args.python)
    if rc not in (0, 1):
        # Tool crash — surface the stderr and fail loudly.
        sys.stderr.write(stderr)
        print(f"[mypy-gate] mypy crashed with exit code {rc}", file=sys.stderr)
        return rc

    raw_lines = [l for l in stdout.splitlines() if l.strip()]
    current = {normalize(l) for l in raw_lines}

    new_findings = sorted(current - baseline)
    fixed_findings = sorted(baseline - current)

    print(f"[mypy-gate] baseline: {len(baseline)} normalized findings")
    print(f"[mypy-gate] current:  {len(current)} normalized findings")
    print(f"[mypy-gate] new:      {len(new_findings)}")
    print(f"[mypy-gate] fixed:    {len(fixed_findings)}")

    if new_findings:
        print("\n::error::NEW mypy --strict errors detected (not in baseline):")
        for line in new_findings[:50]:
            print(f"  + {line}")
        if len(new_findings) > 50:
            print(f"  ... and {len(new_findings) - 50} more")
        print(
            "\nFix the new errors, or if they are intentional, refresh the "
            "baseline with `python tools/qa_mypy_baseline.py` and explain why "
            "in the commit message.",
            file=sys.stderr,
        )
        return 1

    if fixed_findings:
        print("\n[mypy-gate] info: some baseline findings no longer reproduce. "
              "Consider trimming the baseline to keep it honest.")
        for line in fixed_findings[:10]:
            print(f"  - {line}")

    print("[mypy-gate] PASS — no new mypy --strict errors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
