"""Stage 3 / MR-0305 — OperationResult status + per-source breakdown.

The status enum is the public contract callers depend on. The test
suite pins the rules that make it safe to consume:

* COMPLETED is the default and the lowest status.
* Adding an outcome with issues promotes to COMPLETED_WITH_WARNINGS.
* mark_failed overrides warnings (a failure is not a warning).
* mark_cancelled overrides warnings but not a failure.
* Counts (ok / warnings / failed) match the outcomes list.
* summary() is JSON-serialisable and free of PII by construction.
"""
from __future__ import annotations

import json

from core.domain.operation_result import (
    OperationResult,
    OperationStatus,
    SourceOutcome,
)

# ── default status ─────────────────────────────────────────────────────

def test_default_status_is_completed() -> None:
    r = OperationResult()
    assert r.status == OperationStatus.COMPLETED
    assert r.total_sources == 0


def test_empty_result_summary() -> None:
    r = OperationResult()
    s = r.summary()
    assert s == {
        "status": "completed",
        "sources": {"total": 0, "ok": 0, "warnings": 0, "failed": 0},
        "rows": {"emitted": 0, "dropped": 0},
        "global_issues": 0,
        "cancel_reason": None,
    }


# ── status promotion ───────────────────────────────────────────────────

def test_adding_outcome_with_issues_promotes_to_warnings() -> None:
    r = OperationResult()
    r.add_outcome(SourceOutcome(source="emp1", rows_emitted=10,
                                issues=[{"severity": "warning", "reason": "x"}]))
    assert r.status == OperationStatus.COMPLETED_WITH_WARNINGS
    assert r.sources_with_warnings == 1


def test_adding_clean_outcome_keeps_completed() -> None:
    r = OperationResult()
    r.add_outcome(SourceOutcome(source="emp1", rows_emitted=10))
    assert r.status == OperationStatus.COMPLETED
    assert r.sources_ok == 1


def test_failed_source_promotes_to_warnings() -> None:
    """A source with zero emitted rows and no issues is a soft failure.

    It does not fail the whole operation — the operator may still get
    useful data from the other sources. The status becomes
    COMPLETED_WITH_WARNINGS so the UI shows the partial-success state.
    """
    r = OperationResult()
    r.add_outcome(SourceOutcome(source="emp1", rows_emitted=0))
    assert r.status == OperationStatus.COMPLETED_WITH_WARNINGS
    assert r.sources_failed == 1


def test_mark_failed_overrides_warnings() -> None:
    r = OperationResult()
    r.add_outcome(SourceOutcome(source="emp1", rows_emitted=0))
    r.mark_failed("catastrophic error")
    assert r.status == OperationStatus.FAILED
    assert r.global_issues[-1]["severity"] == "critical"


def test_mark_cancelled_overrides_warnings_but_not_failure() -> None:
    r = OperationResult()
    r.add_outcome(SourceOutcome(source="emp1", rows_emitted=0))
    r.mark_cancelled("user pressed cancel")
    assert r.status == OperationStatus.CANCELLED
    assert r.cancel_reason == "user pressed cancel"


def test_mark_cancelled_does_not_override_failure() -> None:
    r = OperationResult()
    r.mark_failed("hard error")
    r.mark_cancelled("user pressed cancel")
    assert r.status == OperationStatus.FAILED


# ── counts ─────────────────────────────────────────────────────────────

def test_counts_match_outcomes() -> None:
    r = OperationResult()
    r.add_outcome(SourceOutcome(source="ok1", rows_emitted=10))
    r.add_outcome(SourceOutcome(source="warn1", rows_emitted=5,
                                issues=[{"severity": "warning"}]))
    r.add_outcome(SourceOutcome(source="fail1", rows_emitted=0,
                                issues=[{"severity": "critical"}]))
    assert r.total_sources == 3
    assert r.sources_ok == 1
    assert r.sources_with_warnings == 1
    assert r.sources_failed == 1
    assert r.rows_emitted == 15


def test_rows_dropped_accumulates() -> None:
    r = OperationResult()
    r.add_outcome(SourceOutcome(source="emp1", rows_emitted=8, rows_dropped=2))
    r.add_outcome(SourceOutcome(source="emp2", rows_emitted=10, rows_dropped=5))
    assert r.rows_dropped == 7


# ── SourceOutcome.ok semantics ─────────────────────────────────────────

def test_source_with_critical_issue_is_not_ok() -> None:
    o = SourceOutcome(source="emp1", rows_emitted=10,
                      issues=[{"severity": "critical"}])
    assert not o.ok


def test_source_with_zero_rows_is_not_ok() -> None:
    o = SourceOutcome(source="emp1", rows_emitted=0)
    assert not o.ok


def test_source_with_only_warnings_is_ok() -> None:
    o = SourceOutcome(source="emp1", rows_emitted=10,
                      issues=[{"severity": "warning"}])
    assert o.ok


# ── summary is JSON-serialisable & PII-free ────────────────────────────

def test_summary_is_json_serialisable() -> None:
    r = OperationResult()
    r.add_outcome(SourceOutcome(source="emp1", rows_emitted=10,
                                issues=[{"severity": "warning", "reason": "x"}]))
    r.mark_cancelled("user cancelled")
    s = r.summary()
    # Round-trips through JSON.
    assert json.loads(json.dumps(s)) == s


def test_summary_does_not_leak_source_names() -> None:
    """Summary must contain only counts, never source identifiers."""
    r = OperationResult()
    r.add_outcome(SourceOutcome(source="Амалия Иванова", rows_emitted=10))
    r.add_outcome(SourceOutcome(source="secret_firm_name", rows_emitted=5))
    s = r.summary()
    serialised = json.dumps(s, ensure_ascii=False)
    assert "Амалия" not in serialised
    assert "secret_firm_name" not in serialised
