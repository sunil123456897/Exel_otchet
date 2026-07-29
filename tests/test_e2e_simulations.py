"""Opt-in end-to-end wrapper for the customer-workflow simulation runners.

``tests/simulation_runner.py`` and ``tests/simulation_runner_real.py`` are the
ONLY place the full pipeline (read real employee Excel → AppController
consolidation → Master_Report / РСЧ / reconciliation) is exercised end to end
against the operator's actual network files. But they are plain scripts — not
collected by pytest, not gated by CI — so a regression in the integration seam
can break them silently. Indeed one of their committed result JSONs recorded a
scenario as FAILED and nobody noticed (see the QA audit).

This wrapper makes that regression visible without forcing CI to run it:
  * marked ``e2e`` (registered in pyproject.toml);
  * SKIPPED unless the operator's real data dirs are present AND the run is
    explicitly requested via ``--run-e2e`` (so a clean checkout / CI never
    blocks, and a maintainer opts in only when the data is local);
  * when it runs, it launches the runner as a subprocess and asserts that
    every scenario reports ``ok=True`` — a regression that previously hid in a
    JSON file now fails the test.

Run explicitly (requires the real data files locally):
    .venv/Scripts/python.exe -m pytest tests/test_e2e_simulations.py --run-e2e
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"

# The real customer data these simulations depend on. Absent on CI / a clean
# checkout → the whole test is skipped (never a hard failure).
_REQUIRED_DATA_DIRS = [
    PROJECT_ROOT / "рсч всех",
    PROJECT_ROOT / "REPORTS" / "Отчет кураторов 3",
]


def _data_available() -> bool:
    return all(d.is_dir() and any(d.iterdir()) for d in _REQUIRED_DATA_DIRS)


@pytest.mark.e2e
def test_simulation_runner_smoke_scenarios_pass(tmp_path):
    """The smoke scenario set (РСЧ period/day + consolidation day) must all
    complete successfully against the real data. A failure here is a real
    regression in the integration seam that the unit suite cannot see."""
    if not _data_available():
        pytest.skip(
            "operator's real data dirs not found (рсч всех/, "
            "REPORTS/Отчет кураторов 3/) — run on the operator's machine"
        )

    runner = PROJECT_ROOT / "tests" / "simulation_runner.py"
    out_json = tmp_path / "sim_results.json"
    # --smoke runs the fast subset (S5/S4/S1); full set takes minutes and is
    # not what a regression gate should block on.
    cmd = [
        sys.executable if not VENV_PYTHON.exists() else str(VENV_PYTHON),
        str(runner),
        "--smoke",
        "--out",
        str(out_json),
    ]
    # The runner drives a real AppController with network timeouts; give it
    # generous headroom but still bounded so a hang surfaces as a failure.
    completed = subprocess.run(
        cmd, cwd=str(PROJECT_ROOT / "APP"),
        capture_output=True, text=True, timeout=900,
    )
    # The runner exits rc=1 when a scenario fails (which is exactly what we
    # assert on below via the JSON) — so returncode is NOT a reliable signal.
    # What matters is that it actually ran to completion and wrote results.
    if not out_json.is_file():
        pytest.fail(
            f"simulation_runner crashed before writing results "
            f"(rc={completed.returncode}):\n--- stdout ---\n"
            f"{completed.stdout[-3000:]}\n--- stderr ---\n{completed.stderr[-2000:]}"
        )

    results = json.loads(out_json.read_text(encoding="utf-8"))
    # ``results`` is a list of {"name", "ok", "msg", ...}.
    assert isinstance(results, list) and results, (
        f"no scenarios recorded in {out_json}: {results!r}"
    )
    failed = [r.get("name", "?") for r in results if not r.get("ok")]
    assert not failed, (
        f"{len(failed)} simulation scenario(s) regressed: {failed}. "
        "This is the integration seam (real AppController pipeline) the unit "
        "suite does not cover. Runner tail:\n" + completed.stdout[-2000:]
    )
