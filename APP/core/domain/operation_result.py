"""Stage 3 / MR-0305 — formal operation result with classified status.

Existing ingestion code returns ``List[Dict]`` and silently swallows
errors via ``return []``. That makes it impossible for the caller (UI,
controller, tests) to tell apart three very different situations:

* the file genuinely had no rows for this date (correct empty result);
* the file failed to parse (silent drop, user thinks data is missing);
* the user cancelled (legitimate empty, but should not look like a fail).

``OperationResult`` is the canonical envelope future code should use. It
carries:

* a ``status`` from a closed enum (``COMPLETED``, ``COMPLETED_WITH_WARNINGS``,
  ``FAILED``, ``CANCELLED``);
* a per-source breakdown (ok / skipped / failed counts);
* a list of classified issues (no PII — reuses ``data_loss_log`` shape);
* the partial data, so a failed source does not throw away the rest.

This is a *model only*; wiring it into the running controller is Stage 7
(UI). At Stage 3 we just establish the type and prove the invariants
hold under fault injection.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class OperationStatus(str, Enum):
    """Closed enum of terminal operation states.

    The order in which these are checked matters: a CANCELLED operation
    that also produced warnings is still CANCELLED, not COMPLETED_WITH_WARNINGS.
    """
    COMPLETED = "completed"
    COMPLETED_WITH_WARNINGS = "completed_with_warnings"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SourceOutcome:
    """Per-source breakdown — one row per file/employee processed."""
    source: str           # anonymised identifier (file name or employee label)
    rows_read: int = 0
    rows_dropped: int = 0
    rows_emitted: int = 0
    issues: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """A source is "ok" if it produced rows and had no hard issues."""
        return self.rows_emitted > 0 and not any(
            i.get("severity") == "critical" for i in self.issues
        )


@dataclass
class OperationResult:
    """Envelope around an operation that touched multiple sources."""
    status: OperationStatus = OperationStatus.COMPLETED
    outcomes: list[SourceOutcome] = field(default_factory=list)
    global_issues: list[dict[str, Any]] = field(default_factory=list)
    data: list[dict[str, Any]] = field(default_factory=list)
    cancel_reason: str | None = None

    # ── derived counts ────────────────────────────────────────────────

    @property
    def total_sources(self) -> int:
        return len(self.outcomes)

    @property
    def sources_ok(self) -> int:
        return sum(1 for o in self.outcomes if o.ok and not o.issues)

    @property
    def sources_with_warnings(self) -> int:
        return sum(1 for o in self.outcomes if o.issues and o.ok)

    @property
    def sources_failed(self) -> int:
        return sum(1 for o in self.outcomes if not o.ok)

    @property
    def rows_emitted(self) -> int:
        return sum(o.rows_emitted for o in self.outcomes)

    @property
    def rows_dropped(self) -> int:
        return sum(o.rows_dropped for o in self.outcomes)

    # ── mutation helpers ──────────────────────────────────────────────

    def add_outcome(self, outcome: SourceOutcome) -> None:
        self.outcomes.append(outcome)
        # Promote status if any source had issues.
        if outcome.issues and self.status == OperationStatus.COMPLETED:
            self.status = OperationStatus.COMPLETED_WITH_WARNINGS
        if not outcome.ok and self.status == OperationStatus.COMPLETED:
            self.status = OperationStatus.COMPLETED_WITH_WARNINGS

    def mark_failed(self, reason: str) -> None:
        """Mark the whole operation as FAILED (overrides warnings)."""
        self.status = OperationStatus.FAILED
        self.global_issues.append({"severity": "critical", "reason": reason})

    def mark_cancelled(self, reason: str = "cancelled by user") -> None:
        """Mark as CANCELLED. Overrides warnings, but not FAILED if already set."""
        if self.status != OperationStatus.FAILED:
            self.status = OperationStatus.CANCELLED
            self.cancel_reason = reason

    # ── summary for UI / logs ─────────────────────────────────────────

    def summary(self) -> dict[str, Any]:
        """PII-free summary suitable for UI display and diagnostic dumps."""
        return {
            "status": self.status.value,
            "sources": {
                "total": self.total_sources,
                "ok": self.sources_ok,
                "warnings": self.sources_with_warnings,
                "failed": self.sources_failed,
            },
            "rows": {
                "emitted": self.rows_emitted,
                "dropped": self.rows_dropped,
            },
            "global_issues": len(self.global_issues),
            "cancel_reason": self.cancel_reason,
        }
