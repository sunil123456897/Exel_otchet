"""Stage 1 / MR-0102 — control date regression.

The control date is the single sheet in the operator's ``Master_Report.xlsx``
that has been confirmed to consolidate byte-for-byte to exactly 4 906 cells
(446 rows × 11 columns) on every run. It is the most valuable correctness
anchor in the project: any refactor, dependency bump, or packaging change
that silently drifts this output is a release blocker.

This test does two things:

1. **Static artifact check (always runs in CI):** verifies that the
   committed ``tests/golden/control_date.json`` is internally consistent
   (rows × cols == total_cells, expected cell count is 4 906). This
   catches a tampered or corrupted artifact without needing the real
   workbook.

2. **Live verification (runs only when the real workbook is present
   locally):** recomputes the fingerprint from ``Master_Report.xlsx`` and
   compares it to the golden. The workbook is gitignored and not present
   in CI, so on CI this branch is skipped with an explicit reason. On
   the operator's machine it runs every time and fails loudly if the
   control date drifts.

Privacy: no financial value ever leaves the operator's machine. The
committed artifact contains only dimensions and a SHA-256 over a
type-tagged cell stream — it is one-way and reversible only by someone
who already has the workbook.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_JSON = REPO_ROOT / "tests" / "golden" / "control_date.json"
REAL_WORKBOOK = REPO_ROOT / "Master_Report.xlsx"

# The TZ section 2 baseline value. Hard-coded here so a tampered artifact
# cannot silently redefine what "the control date" means.
EXPECTED_TOTAL_CELLS = 4906
EXPECTED_ROWS = 446
EXPECTED_COLS = 11


# ── 1) static artifact consistency ──────────────────────────────────────

def test_control_date_artifact_consistency() -> None:
    """The committed artifact must match the TZ's stated dimensions."""
    assert GOLDEN_JSON.is_file(), (
        f"missing {GOLDEN_JSON}. Run "
        f"`python tools/control_date_fingerprint.py capture "
        f"--workbook Master_Report.xlsx --sheet 18.05.2026 "
        f"--out tests/golden/control_date.json` to create it."
    )
    data = json.loads(GOLDEN_JSON.read_text(encoding="utf-8"))

    assert data["rows"] == EXPECTED_ROWS
    assert data["cols"] == EXPECTED_COLS
    assert data["total_cells"] == EXPECTED_TOTAL_CELLS
    assert data["rows"] * data["cols"] == data["total_cells"], (
        "artifact rows × cols must equal total_cells"
    )
    assert len(data["content_sha256"]) == 64, "sha256 must be a 64-char hex digest"
    # The artifact must NEVER contain cell values — only the digest.
    forbidden_keys = {"values", "cells", "data", "raw", "content"}
    leaked = forbidden_keys & set(data.keys())
    assert not leaked, f"artifact leaked value-bearing keys: {leaked}"


# ── 2) live verification against the real workbook ──────────────────────

def test_control_date_reproduces_against_real_workbook() -> None:
    """Recompute the fingerprint and compare it to the committed one.

    Skipped on CI and on any machine where ``Master_Report.xlsx`` is not
    present at the repo root. The workbook is gitignored because it
    contains real financial data.
    """
    if not REAL_WORKBOOK.is_file():
        pytest.skip(
            f"{REAL_WORKBOOK} not present — live control-date verification "
            f"only runs where the real (gitignored) workbook exists. "
            f"Run this test on the operator's machine before any release."
        )

    rc = subprocess.run(
        [sys.executable, "tools/control_date_fingerprint.py", "verify",
         "--workbook", str(REAL_WORKBOOK),
         "--sheet", "18.05.2026",
         "--golden", str(GOLDEN_JSON)],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    if rc.returncode != 0:
        pytest.fail(
            f"control date verification failed (rc={rc.returncode}):\n"
            f"stdout:\n{rc.stdout}\n"
            f"stderr:\n{rc.stderr}\n"
            f"This is a regression — the consolidated output of the "
            f"control date has drifted from the committed golden."
        )


def test_control_date_workbook_not_committed() -> None:
    """The real workbook must never be tracked by git."""
    if not REAL_WORKBOOK.is_file():
        pytest.skip("workbook not present locally — nothing to check")
    r = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "check-ignore", str(REAL_WORKBOOK)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, (
        f"{REAL_WORKBOOK} is NOT gitignored. The real workbook contains "
        f"firm financial data and must never be committed. Add it to "
        f".gitignore."
    )
