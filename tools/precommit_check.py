#!/usr/bin/env python3
"""Pre-commit quality gate for Master-Report.

Cross-platform replacement for the old bash hook. Invoked by
.git/hooks/pre-commit (a thin sh wrapper). Does three things:

1. ruff --select F401 --fix  : auto-remove unused imports, re-staged by caller
2. ruff full check           : blocks on lint errors
3. mypy baseline mode        : blocks only NEW errors (line numbers
                               normalised, so pure line-shifts don't count)

The baseline file is .mypy_baseline.txt at the repo root. If it is
missing the first run captures it and allows the commit.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "APP"
TEST_DIR = REPO_ROOT / "tests"
BASELINE = REPO_ROOT / ".mypy_baseline.txt"


def _python() -> str:
    """Prefer the project venv python; fall back to the invoking python."""
    venv_py = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_py.exists():
        return str(venv_py)
    return sys.executable


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")


def _normalise(text: str) -> set[str]:
    """Strip line numbers so a pure shift from editing nearby code is
    not counted as a new error."""
    import re

    out = set()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        line = re.sub(r":\d+:", ":N:", line)
        out.add(line)
    return out


def main() -> int:
    py = _python()

    print("=== [1/3] ruff: auto-fix unused imports ===")
    _run([py, "-m", "ruff", "check", "--select", "F401", "--fix",
          str(APP_DIR), str(TEST_DIR)])
    # The caller re-stages; we don't touch git here to stay testable.

    print("=== [2/3] ruff: full check ===")
    ruff = _run([py, "-m", "ruff", "check", str(APP_DIR), str(TEST_DIR)])
    print(ruff.stdout, end="")
    print(ruff.stderr, end="", file=sys.stderr)
    if ruff.returncode != 0:
        print("[pre-commit] ruff failed.")
        return ruff.returncode

    print("=== [3/3] mypy: baseline mode ===")
    mypy = _run([py, "-m", "mypy", str(APP_DIR),
                 "--ignore-missing-imports", "--strict", "--no-error-summary"])
    current_lines = _normalise(mypy.stdout + mypy.stderr)

    if not BASELINE.exists():
        BASELINE.write_text(
            mypy.stdout + mypy.stderr, encoding="utf-8"
        )
        print(f"Baseline created: {BASELINE} ({len(current_lines)} issues)")
        print("No errors blocked — baseline captured.")
        print("\n=== All pre-commit checks passed ===")
        return 0

    baseline_lines = _normalise(BASELINE.read_text(encoding="utf-8"))
    new = sorted(current_lines - baseline_lines)
    if new:
        print("=== BLOCKED: new mypy errors (line numbers normalised) ===")
        for line in new:
            print(line)
        print(
            "\nFix the above, or refresh the baseline if intentional:\n"
            f"  {py} -m mypy APP --strict --ignore-missing-imports "
            "--no-error-summary > .mypy_baseline.txt"
        )
        return 1

    print(f"mypy: no new errors (baseline: {len(baseline_lines)} lines)")
    print("\n=== All pre-commit checks passed ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
