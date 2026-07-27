#!/usr/bin/env python3
"""Generate / refresh ``.mypy_baseline.txt`` from a fresh ``mypy --strict`` run.

Used by ``ci_mypy_check.py`` (the CI gate) and by maintainers to refresh the
baseline as a deliberate, reviewable action — never automatically inside CI.

Normalization applied so line shifts do not look like new errors:

* backslashes are converted to forward slashes (Windows / POSIX path variance);
* the ``:NN:`` column between path and message is replaced by ``:LINE:`` so
  adding/removing a line above the error does not look like a new finding;
* duplicate normalized lines are removed and the result sorted.

Output goes to ``.mypy_baseline.txt`` at the repository root by default.
Print a summary so the operator can see how many distinct findings were
captured.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# Matches the ``path:line:col? message`` shape produced by mypy. We only
# rewrite the first ``:digits:`` occurrence (the line number).
_LINE_NUM_RE = re.compile(r"(?P<prefix>^\S+?):(?P<lineno>\d+):(?P<rest>.*$)")


def normalize(raw_line: str) -> str:
    """Return a path/lineno-stable form of *raw_line*."""
    line = raw_line.replace("\\", "/").rstrip()
    m = _LINE_NUM_RE.match(line)
    if m:
        return f"{m.group('prefix')}:LINE:{m.group('rest')}"
    return line


def run_mypy(repo_root: Path, python_exe: str) -> str:
    """Run ``mypy --strict APP`` and return combined stdout output."""
    cmd = [python_exe, "-m", "mypy", "APP",
           "--ignore-missing-imports", "--strict", "--no-error-summary"]
    print(f"[baseline] running: {' '.join(cmd)}", file=sys.stderr)
    # mypy writes its findings to stdout. We capture both streams but use
    # stdout for the actual baseline content.
    result = subprocess.run(
        cmd, cwd=str(repo_root), capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode not in (0, 1):
        # mypy exits 1 on type errors (expected). Anything else is a tool failure.
        sys.stderr.write(result.stderr)
        raise SystemExit(f"mypy failed unexpectedly with exit code {result.returncode}")
    if result.stderr.strip():
        # surface any genuine diagnostic noise for the operator
        sys.stderr.write("[baseline] mypy stderr (not used for baseline):\n")
        sys.stderr.write(result.stderr)
    return result.stdout


def refresh(repo_root: Path, python_exe: str, out_path: Path) -> int:
    raw = run_mypy(repo_root, python_exe)
    raw_lines = [l for l in raw.splitlines() if l.strip()]
    normalized = sorted({normalize(l) for l in raw_lines})
    out_path.write_text("\n".join(normalized) + ("\n" if normalized else ""),
                        encoding="utf-8")
    print(f"[baseline] wrote {len(normalized)} normalized findings to {out_path}")
    print(f"[baseline] raw lines: {len(raw_lines)}")
    return len(normalized)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root", default=".",
                   help="repository root (default: current dir)")
    p.add_argument("--python", default=sys.executable,
                   help="python interpreter to run mypy with")
    p.add_argument("--out", default=".mypy_baseline.txt",
                   help="output baseline file (default: ./.mypy_baseline.txt)")
    args = p.parse_args()

    repo_root = Path(args.repo_root).resolve()
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = repo_root / out_path
    refresh(repo_root, args.python, out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
