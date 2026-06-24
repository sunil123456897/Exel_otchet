from __future__ import annotations
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.worksheet.worksheet import Worksheet
from core.infra.utils import get_local_copy
from ._types import MasterReconciliationRow, RschReconciliationRow
from ._utils import (
    _compact_text,
    _normalize_text,
    _canonical_match_text,
    _executor_alias_keys,
    _executor_tokens,
    _text_tokens,
    _weak_customer_tokens,
)


def _amount_equal(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) <= Decimal("0.01")


def _row_amount_matches(master: MasterReconciliationRow, rsch: RschReconciliationRow) -> bool:
    income_matches = master.income != 0 and _amount_equal(master.income, rsch.income)
    expense_matches = master.expense != 0 and _amount_equal(master.expense, rsch.expense)
    if income_matches or expense_matches:
        return True
    if master.income < 0 and _amount_equal(abs(master.income), rsch.expense):
        return True
    if master.expense < 0 and _amount_equal(abs(master.expense), rsch.income):
        return True
    if rsch.income < 0 and _amount_equal(master.income, abs(rsch.income)):
        return True
    if rsch.expense < 0 and _amount_equal(master.expense, abs(rsch.expense)):
        return True
    return False


def _executor_matches(master_executor: str, rsch_executor: str) -> bool:
    left = _canonical_match_text(master_executor)
    right = _canonical_match_text(rsch_executor)
    if not left or not right:
        return False
    if left == right or _compact_text(left) == _compact_text(right):
        return True
    if _executor_alias_keys(left) & _executor_alias_keys(right):
        return True
    left_tokens = {t for t in _executor_tokens(left) if len(t) >= 4}
    right_tokens = {t for t in _executor_tokens(right) if len(t) >= 4}
    if not left_tokens or not right_tokens:
        return False
    return left_tokens.issubset(right_tokens) or right_tokens.issubset(left_tokens)


def _customer_matches(master_customer: str, rsch_customer: str) -> bool:
    left = _normalize_text(master_customer)
    right = _normalize_text(rsch_customer)
    return bool(left and right and (left in right or right in left))


def _customer_matches_loose(left_value: str, right_value: str) -> bool:
    if _customer_matches(left_value, right_value):
        return True
    left = _compact_text(left_value)
    right = _compact_text(right_value)
    if len(left) >= 6 and len(right) >= 6 and (left in right or right in left):
        return True
    common_tokens = _text_tokens(left_value) & _text_tokens(right_value)
    return len(common_tokens) >= 2


def _rsch_customer_matches(master_customer: str, rsch_row: RschReconciliationRow) -> bool:
    return any(
        _customer_matches_loose(master_customer, candidate)
        for candidate in (rsch_row.customer, rsch_row.contractor, rsch_row.comment)
    )


def _customer_matches_weak(left_value: str, right_value: str) -> bool:
    if _customer_matches_loose(left_value, right_value):
        return False
    common_tokens = _weak_customer_tokens(left_value) & _weak_customer_tokens(right_value)
    return len(common_tokens) >= 2


def _rsch_customer_matches_weak(master_customer: str, rsch_row: RschReconciliationRow) -> bool:
    return any(
        _customer_matches_weak(master_customer, candidate)
        for candidate in (rsch_row.customer, rsch_row.contractor, rsch_row.comment)
    )


def _sheet_candidates(target_date: date) -> tuple[str, str]:
    return target_date.strftime("%d.%m.%Y"), target_date.strftime("%d.%m")


def _coerce_date(value: date) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


def _parse_full_sheet_date(sheet_title: str) -> date | None:
    try:
        return datetime.strptime(sheet_title, "%d.%m.%Y").date()
    except ValueError:
        return None


def _parse_day_month_sheet(sheet_title: str) -> tuple[int, int] | None:
    try:
        parsed = datetime.strptime(sheet_title, "%d.%m")
    except ValueError:
        return None
    return parsed.day, parsed.month


def _has_sheet_for_date(wb, target_date: date) -> bool:
    candidates = set(_sheet_candidates(target_date))
    return any(ws.title in candidates for ws in wb.worksheets)


def _workbook_sheet_dates(wb) -> tuple[set[date], set[tuple[int, int]]]:
    full_dates: set[date] = set()
    day_months: set[tuple[int, int]] = set()
    for ws in wb.worksheets:
        full_date = _parse_full_sheet_date(ws.title)
        if full_date is not None:
            full_dates.add(full_date)
            continue
        day_month = _parse_day_month_sheet(ws.title)
        if day_month is not None:
            day_months.add(day_month)
    return full_dates, day_months


def _common_sheet_dates(master_wb, rsch_wb) -> list[date]:
    master_dates, master_day_months = _workbook_sheet_dates(master_wb)
    rsch_dates, rsch_day_months = _workbook_sheet_dates(rsch_wb)
    common = set(master_dates & rsch_dates)
    common.update(d for d in master_dates if (d.day, d.month) in rsch_day_months)
    common.update(d for d in rsch_dates if (d.day, d.month) in master_day_months)
    return sorted(common)


def _format_dates(dates: list[date]) -> str:
    return ", ".join(d.strftime("%d.%m.%Y") for d in dates)


def _resolve_target_date(master_wb, rsch_wb, target_date: date | None) -> date:
    if target_date is not None:
        target_date = _coerce_date(target_date)
        if _has_sheet_for_date(master_wb, target_date) and _has_sheet_for_date(
            rsch_wb,
            target_date,
        ):
            return target_date
        raise ValueError(
            f"Не найден лист за дату {target_date.strftime('%d.%m.%Y')} "
            "в выбранной паре мастер- и РСЧ-файлов"
        )

    common_dates = _common_sheet_dates(master_wb, rsch_wb)
    if len(common_dates) == 1:
        return common_dates[0]

    if not common_dates:
        raise ValueError("Не найдена общая дата в выбранных мастер- и РСЧ-файлах")

    raise ValueError(
        "В выбранных файлах найдено несколько общих дат: "
        f"{_format_dates(common_dates)}. Выберите нужную дату в панели слева."
    )


def _find_sheet(wb, target_date: date) -> Worksheet:
    target_date = _coerce_date(target_date)
    candidates = set(_sheet_candidates(target_date))
    for ws in wb.worksheets:
        if ws.title in candidates:
            return ws
    raise ValueError(f"Не найден лист за дату {target_date.strftime('%d.%m.%Y')}")


def _resolve_combined_target_date(
    master_paths: list[tuple[str, Path | str]],
    rsch_wb,
    target_date: date | None,
    drive_letters: tuple[str, ...],
) -> date | None:
    if target_date is not None:
        return _coerce_date(target_date)

    common_dates: set[date] | None = None
    for sheet_name, master_path_value in master_paths:
        master_path = Path(master_path_value)
        if not master_path.exists():
            raise FileNotFoundError(f"Не найден мастер-отчет {sheet_name}: {master_path}")
        with _local_read_path(master_path, drive_letters) as master_read_path:
            master_wb = None
            try:
                master_wb = load_workbook(master_read_path, data_only=True)
                master_dates = _common_sheet_dates(master_wb, rsch_wb)
                if common_dates is None:
                    common_dates = set(master_dates)
                else:
                    common_dates &= set(master_dates)
            finally:
                if master_wb is not None:
                    master_wb.close()

    if common_dates and len(common_dates) == 1:
        return next(iter(common_dates))
    if not common_dates:
        raise ValueError("Не найдена общая дата в выбранных мастер- и РСЧ-файлах")
    raise ValueError(
        "В выбранных файлах найдено несколько общих дат: "
        f"{_format_dates(sorted(common_dates))}. Выберите нужную дату в панели слева."
    )


@contextmanager
def _local_read_path(path: Path, drive_letters: tuple[str, ...] = ("Q", "Z")):
    target_path, temp_file = get_local_copy(str(path), drive_letters)
    try:
        yield target_path
    finally:
        if temp_file:
            Path(temp_file).unlink(missing_ok=True)
