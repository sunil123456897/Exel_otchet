"""Stage 3 / MR-0303 — date validation and suspicious-date warnings.

The reader's ``extract_date_from_sheet`` already parses DD.MM.YYYY
formats and rejects garbage. What was missing: a flag for *valid* dates
that are still suspicious in context — e.g. a sheet named ``15.04.2029``
on a machine whose wall clock says 2026.

Three categories:

* ``FUTURE`` — sheet date more than ``FUTURE_DAYS`` (default 31) ahead
  of the reference date. Almost always a typo or a 1C-side bug.
* ``DISTANT_PAST`` — sheet date more than ``PAST_DAYS`` (default 365)
  behind. Usually a stale template someone forgot to rename.
* ``OK`` — within the plausible operating window.

The function is **pure**: no I/O, no logging side effects. Callers
decide whether to surface the warning to the UI, log it, or both. The
ingestion pipeline will record it via ``data_loss_log.record_loss`` so
the operator sees a trace without the process refusing the date.

Note: we deliberately do NOT drop future/past rows. The ``2029`` sheet
that prompted this contained real data; silently dropping it would have
been worse than reporting it. The job of this module is to *surface*,
not to *filter*.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import Enum


class DateWarningKind(str, Enum):
    OK = "ok"
    FUTURE = "future"
    DISTANT_PAST = "distant_past"


# Plausibility windows. Tunable so a long-running historical import does
# not generate a flood of DISTANT_PAST warnings.
FUTURE_DAYS = 31
PAST_DAYS = 365


@dataclass
class DateWarning:
    kind: DateWarningKind
    sheet_date: date
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind.value,
            "sheet_date": self.sheet_date.isoformat(),
            "detail": self.detail,
        }


def classify_sheet_date(
    sheet_date_str: str,
    *,
    reference: date | None = None,
    future_days: int = FUTURE_DAYS,
    past_days: int = PAST_DAYS,
) -> DateWarning:
    """Classify *sheet_date_str* (DD.MM.YYYY) against a reference date.

    Parameters
    ----------
    sheet_date_str
        Date as parsed from the sheet name. Must already be in
        ``DD.MM.YYYY`` form (i.e. the output of ``extract_date_from_sheet``).
    reference
        Date to compare against. Defaults to today (UTC). Tests inject
        a fixed value.
    future_days, past_days
        Plausibility window. Outside it → ``FUTURE`` or ``DISTANT_PAST``.
    """
    if reference is None:
        reference = datetime.now(timezone.utc).date()
    try:
        sheet_date = datetime.strptime(sheet_date_str, "%d.%m.%Y").date()
    except ValueError as e:
        # Non-date strings should never reach here — the caller filters
        # them via extract_date_from_sheet. But defend in depth.
        return DateWarning(
            DateWarningKind.OK, reference,
            f"unparseable sheet date {sheet_date_str!r}: {e}",
        )

    delta = (sheet_date - reference).days
    if delta > future_days:
        return DateWarning(
            DateWarningKind.FUTURE, sheet_date,
            f"sheet date is {delta} days in the future (>{future_days}). "
            "Typo in sheet name or upstream 1C bug; data preserved, flagged.",
        )
    if delta < -past_days:
        return DateWarning(
            DateWarningKind.DISTANT_PAST, sheet_date,
            f"sheet date is {abs(delta)} days in the past (>{past_days}). "
            "Stale template? Data preserved, flagged.",
        )
    return DateWarning(DateWarningKind.OK, sheet_date, "within plausibility window")
