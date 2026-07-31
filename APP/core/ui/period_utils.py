"""Pure date-range helpers for the sidebar period picker.

Extracted from ``core/ui/ui_sidebar.py`` (TD: god-widget decomposition).
No Tk dependencies — safe to unit test and reuse.
"""

from __future__ import annotations

from datetime import datetime, timedelta


def last_day_of_month(month_start: datetime) -> datetime:
    if month_start.month == 12:
        return month_start.replace(day=31)
    return (month_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(
        days=1
    )


def previous_month_start(today: datetime) -> datetime:
    if today.month == 1:
        return today.replace(year=today.year - 1, month=12, day=1)
    return today.replace(month=today.month - 1, day=1)


def get_default_period_range(today: datetime | None = None) -> tuple[datetime, datetime]:
    """Default (start, end) for the monthly-report picker.

    On the 1st of a month the default is the full previous month; otherwise
    the current month from its first day through today.
    """
    today = today or datetime.now()
    if today.day == 1:
        start = previous_month_start(today)
        return start, last_day_of_month(start)

    start = today.replace(day=1)
    return start, today
