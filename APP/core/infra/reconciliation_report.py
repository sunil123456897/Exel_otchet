from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Optional

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from core.infra.excel_hyperlinks import (
    apply_cell_hyperlink,
    extract_hyperlink_formula_parts,
)

MASTER_HEADERS = [
    "Источник",
    "ЗАКАЗЧИК",
    "ИСПОЛНИТЕЛЬ",
    "Приход",
    "Расход",
    "Комиссия",
    "ИТОГ",
    "% посредника",
    "посредник 1(кэш)",
    "посредник 2",
]
_MASTER_HEADER_ALIASES = {
    "Источник": ("Источник", "Сотрудник"),
    "% посредника": ("% посредника", "% посредник 1", "% посредника 1"),
    "посредник 1(кэш)": ("посредник 1(кэш)", "посредник 1"),
}
RSCH_HEADERS = [
    "ИСПОЛНИТЕЛЬ",
    "ЗАКАЗЧИК",
    "Контрагент",
    "Комментарий",
    "Приход",
    "Расход",
]
RECONCILIATION_HEADERS = [*MASTER_HEADERS, "ИТОГ", *RSCH_HEADERS]
REASON_NO_CURATOR = "ОШИБКА НЕТУ У КУРАТОРОВ"
REASON_NO_RSCH = "НЕТ В РСЧ"
REASON_AMOUNT_MISMATCH = "НЕ СОВПАЛА СУММА"
REASON_EXECUTOR_MISMATCH = "НЕ СОВПАЛ ИСПОЛНИТЕЛЬ"
_SUMMARY_REASON_LABELS = {
    REASON_NO_CURATOR: "Нет у кураторов",
    REASON_NO_RSCH: "Нет в РСЧ",
    REASON_AMOUNT_MISMATCH: "Не совпала сумма",
    REASON_EXECUTOR_MISMATCH: "Не совпал исполнитель",
}

_HEADER_FILL = PatternFill("solid", fgColor="FF1F4E79")
_STATUS_OK_FILL = PatternFill("solid", fgColor="FF00B050")
_STATUS_ERROR_FILL = PatternFill("solid", fgColor="FFFF0000")
_MASTER_EXPENSE_FILL = PatternFill("solid", fgColor="FFFFC7CE")
_TOTAL_FILL = PatternFill("solid", fgColor="FFD9E1F2")
_HEADER_FONT = Font(color="FFFFFFFF", bold=True)
_STATUS_FONT = Font(color="FF000000", bold=True)
_TOTAL_FONT = Font(bold=True)
_THIN_SIDE = Side(style="thin", color="FF000000")
_MEDIUM_SIDE = Side(style="medium", color="FF000000")
_THIN_BORDER = Border(
    left=_THIN_SIDE,
    right=_THIN_SIDE,
    top=_THIN_SIDE,
    bottom=_THIN_SIDE,
)
_TOTAL_BORDER = Border(
    left=_MEDIUM_SIDE,
    right=_MEDIUM_SIDE,
    top=_MEDIUM_SIDE,
    bottom=_MEDIUM_SIDE,
)


@dataclass(frozen=True)
class MasterReconciliationRow:
    values: list[Any]
    source: Any
    source_link: str | None
    customer: str
    executor: str
    income: Decimal
    expense: Decimal


@dataclass(frozen=True)
class RschReconciliationRow:
    executor: str
    customer: str
    contractor: str
    comment: str
    income: Decimal
    expense: Decimal
    source_link: str | None


@dataclass(frozen=True)
class ReconciliationRow:
    master: Optional[MasterReconciliationRow]
    rsch: Optional[RschReconciliationRow]
    status: str
    reason: str = ""


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").replace("ё", "е").lower().split())


def _is_filter_header(value: Any) -> bool:
    return _normalize_text(value) in {"фильтр", "фильтры", "filter", "filters"}


def _is_numeric_header(value: Any) -> bool:
    normalized = _normalize_text(value)
    return any(
        keyword in normalized
        for keyword in (
            "приход",
            "расход",
            "комиссия",
            "итог",
            "посредник",
            "транзит",
            "сумма",
        )
    )


def _is_percent_header(value: Any) -> bool:
    return "%" in str(value or "")


def _should_total_header(value: Any) -> bool:
    return _is_numeric_header(value) and not _is_percent_header(value)


def _to_decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).replace(" ", "").replace(",", ".").strip()
    if not text or text.startswith("="):
        return Decimal("0")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _amount_equal(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) <= Decimal("0.01")


def _row_amount_matches(master: MasterReconciliationRow, rsch: RschReconciliationRow) -> bool:
    income_matches = master.income != 0 and _amount_equal(master.income, rsch.income)
    expense_matches = master.expense != 0 and _amount_equal(master.expense, rsch.expense)
    return income_matches or expense_matches


def _executor_matches(master_executor: str, rsch_executor: str) -> bool:
    left = _normalize_text(master_executor)
    right = _normalize_text(rsch_executor)
    return bool(left and right and (left in right or right in left))


def _customer_matches(master_customer: str, rsch_customer: str) -> bool:
    left = _normalize_text(master_customer)
    right = _normalize_text(rsch_customer)
    return bool(left and right and (left in right or right in left))


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
    common.update(
        d for d in master_dates if (d.day, d.month) in rsch_day_months
    )
    common.update(
        d for d in rsch_dates if (d.day, d.month) in master_day_months
    )
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

    common_dates = _common_sheet_dates(master_wb, rsch_wb)
    if len(common_dates) == 1:
        return common_dates[0]

    if not common_dates:
        if target_date is None:
            raise ValueError("Не найдена общая дата в выбранных мастер- и РСЧ-файлах")
        raise ValueError(
            f"Не найден лист за дату {target_date.strftime('%d.%m.%Y')} "
            "в выбранной паре мастер- и РСЧ-файлов"
        )

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
    raise ValueError(
        f"Не найден лист за дату {target_date.strftime('%d.%m.%Y')}"
    )


def _header_map(ws: Worksheet, *, prefer_last: bool = False) -> dict[str, int]:
    headers: dict[str, int] = {}
    for col_idx in range(1, ws.max_column + 1):
        value = ws.cell(1, col_idx).value
        if value in (None, ""):
            continue
        header = str(value).strip()
        if prefer_last or header not in headers:
            headers[header] = col_idx
    return headers


def _master_output_headers(ws: Worksheet) -> list[str]:
    headers: list[str] = []
    for col_idx in range(1, ws.max_column + 1):
        value = ws.cell(1, col_idx).value
        if value in (None, "") or _is_filter_header(value):
            continue
        headers.append(str(value).strip())
    return headers


def _header_index(
    headers: dict[str, int],
    header: str,
    *,
    required: bool = True,
) -> int | None:
    aliases = _MASTER_HEADER_ALIASES.get(header, (header,))
    for alias in aliases:
        if alias in headers:
            return headers[alias]

    normalized_headers = {_normalize_text(key): value for key, value in headers.items()}
    for alias in aliases:
        normalized_alias = _normalize_text(alias)
        if normalized_alias in normalized_headers:
            return normalized_headers[normalized_alias]

    if required:
        raise KeyError(header)
    return None


def _master_cell_value(
    ws: Worksheet,
    row_idx: int,
    headers: dict[str, int],
    header: str,
) -> Any:
    col_idx = _header_index(headers, header, required=False)
    if col_idx is None:
        return None
    return _cell_display_value(ws, row_idx, col_idx)


def _is_total_row(value: Any) -> bool:
    return _normalize_text(value).startswith("итого")


def _cell_hyperlink_target(ws: Worksheet, row_idx: int, col_idx: int) -> str | None:
    formula_parts = extract_hyperlink_formula_parts(ws.cell(row_idx, col_idx).value)
    if formula_parts is not None:
        return formula_parts[0]
    hyperlink = ws.cell(row_idx, col_idx).hyperlink
    if hyperlink is None:
        return None
    target = hyperlink.target or hyperlink.location
    if target is None:
        return None
    return target.split("#", 1)[0]


def _cell_display_value(ws: Worksheet, row_idx: int, col_idx: int) -> Any:
    value = ws.cell(row_idx, col_idx).value
    formula_parts = extract_hyperlink_formula_parts(value)
    if formula_parts is not None:
        return formula_parts[1]
    return value


def _collect_master_rows(ws: Worksheet) -> tuple[list[str], list[MasterReconciliationRow]]:
    headers = _header_map(ws)
    output_headers = _master_output_headers(ws)
    source_col = _header_index(headers, "Источник")
    customer_col = _header_index(headers, "ЗАКАЗЧИК")
    executor_col = _header_index(headers, "ИСПОЛНИТЕЛЬ")
    income_col = _header_index(headers, "Приход")
    expense_col = _header_index(headers, "Расход")
    rows: list[MasterReconciliationRow] = []
    for row_idx in range(2, ws.max_row + 1):
        source = _cell_display_value(ws, row_idx, source_col)
        if _is_total_row(source):
            continue
        customer = str(ws.cell(row_idx, customer_col).value or "").strip()
        executor = str(ws.cell(row_idx, executor_col).value or "").strip()
        if not customer and not executor:
            continue
        values = [
            _master_cell_value(ws, row_idx, headers, header) for header in output_headers
        ]
        rows.append(
            MasterReconciliationRow(
                values=values,
                source=source,
                source_link=_cell_hyperlink_target(ws, row_idx, source_col),
                customer=customer,
                executor=executor,
                income=_to_decimal(ws.cell(row_idx, income_col).value),
                expense=_to_decimal(ws.cell(row_idx, expense_col).value),
            )
        )
    return output_headers, rows


def _collect_rsch_rows(ws: Worksheet) -> list[RschReconciliationRow]:
    headers = _header_map(ws, prefer_last=True)
    rows: list[RschReconciliationRow] = []
    for row_idx in range(2, ws.max_row + 1):
        first = ws.cell(row_idx, 1).value
        if _is_total_row(first):
            continue
        income = _to_decimal(ws.cell(row_idx, headers["Приход"]).value)
        expense = _to_decimal(ws.cell(row_idx, headers["Расход"]).value)
        if income == 0 and expense == 0:
            continue
        rows.append(
            RschReconciliationRow(
                executor=str(ws.cell(row_idx, headers["ИСПОЛНИТЕЛЬ"]).value or "").strip(),
                customer=str(ws.cell(row_idx, headers["ЗАКАЗЧИК"]).value or "").strip(),
                contractor=str(ws.cell(row_idx, headers["Контрагент"]).value or "").strip(),
                comment=str(ws.cell(row_idx, headers["Комментарий"]).value or "").strip(),
                income=income,
                expense=expense,
                source_link=_cell_hyperlink_target(ws, row_idx, headers.get("Источник", 1)),
            )
        )
    return rows


def _find_best_rsch_match(
    master_row: MasterReconciliationRow,
    rsch_rows: list[RschReconciliationRow],
    used_indexes: set[int],
) -> tuple[Optional[int], Optional[RschReconciliationRow]]:
    customer_candidates = [
        (idx, row)
        for idx, row in enumerate(rsch_rows)
        if idx not in used_indexes and _customer_matches(master_row.customer, row.customer)
    ]
    if not customer_candidates:
        return None, None
    amount_candidates = [
        (idx, row) for idx, row in customer_candidates if _row_amount_matches(master_row, row)
    ]
    for idx, row in amount_candidates:
        if _executor_matches(master_row.executor, row.executor):
            return idx, row
    if amount_candidates:
        return amount_candidates[0]
    return None, None


def _find_likely_rsch_mismatch(
    master_row: MasterReconciliationRow,
    rsch_rows: list[RschReconciliationRow],
    used_indexes: set[int],
) -> tuple[Optional[int], Optional[RschReconciliationRow]]:
    customer_candidates = [
        (idx, row)
        for idx, row in enumerate(rsch_rows)
        if idx not in used_indexes and _customer_matches(master_row.customer, row.customer)
    ]
    for idx, row in customer_candidates:
        if _executor_matches(master_row.executor, row.executor):
            return idx, row
    if customer_candidates:
        return customer_candidates[0]
    return None, None


def _build_reconciliation_rows(
    master_rows: list[MasterReconciliationRow],
    rsch_rows: list[RschReconciliationRow],
) -> list[ReconciliationRow]:
    result: list[ReconciliationRow] = []
    used_rsch_indexes: set[int] = set()
    exact_matches: dict[int, int] = {}

    for idx, row in enumerate(rsch_rows):
        if not row.customer:
            used_rsch_indexes.add(idx)
            result.append(
                ReconciliationRow(
                    master=None,
                    rsch=row,
                    status="ОШИБКА",
                    reason=REASON_NO_CURATOR,
                )
            )

    for master_idx, master_row in enumerate(master_rows):
        match_idx, rsch_row = _find_best_rsch_match(
            master_row, rsch_rows, used_rsch_indexes
        )
        if rsch_row is not None and match_idx is not None:
            used_rsch_indexes.add(match_idx)
            exact_matches[master_idx] = match_idx

    for master_idx, master_row in enumerate(master_rows):
        if master_idx in exact_matches:
            rsch_row = rsch_rows[exact_matches[master_idx]]
            ok = _executor_matches(master_row.executor, rsch_row.executor)
            result.append(
                ReconciliationRow(
                    master=master_row,
                    rsch=rsch_row,
                    status="СВЕРЕНО" if ok else "ОШИБКА",
                    reason="" if ok else REASON_EXECUTOR_MISMATCH,
                )
            )
            continue

        match_idx, rsch_row = _find_likely_rsch_mismatch(
            master_row, rsch_rows, used_rsch_indexes
        )
        if rsch_row is None or match_idx is None:
            result.append(
                ReconciliationRow(
                    master=master_row,
                    rsch=None,
                    status="ОШИБКА",
                    reason=REASON_NO_RSCH,
                )
            )
            continue
        used_rsch_indexes.add(match_idx)
        result.append(
            ReconciliationRow(
                master=master_row,
                rsch=rsch_row,
                status="ОШИБКА",
                reason=REASON_AMOUNT_MISMATCH,
            )
        )

    for idx, row in enumerate(rsch_rows):
        if idx in used_rsch_indexes:
            continue
        result.append(
            ReconciliationRow(
                master=None,
                rsch=row,
                status="ОШИБКА",
                reason=REASON_NO_CURATOR,
            )
        )
    return result


def _rsch_values(row: Optional[RschReconciliationRow]) -> list[Any]:
    if row is None:
        return [None, None, None, None, None, None]
    return [
        row.executor,
        row.customer,
        row.contractor,
        row.comment,
        row.income if row.income != 0 else None,
        row.expense if row.expense != 0 else None,
    ]


def _master_values(row: ReconciliationRow, master_headers: list[str]) -> list[Any]:
    if row.master is not None:
        return row.master.values
    values = [None for _ in master_headers]
    if values:
        values[0] = row.reason
    return values


def _reason_label(reason: str) -> str:
    return _SUMMARY_REASON_LABELS.get(reason, reason)


def _write_headers(ws: Worksheet, headers: list[str]) -> None:
    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(1, col_idx)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _THIN_BORDER


def _append_reconciliation_row(
    ws: Worksheet,
    row: ReconciliationRow,
    master_headers: list[str],
) -> None:
    headers = [*master_headers, "ИТОГ", *RSCH_HEADERS]
    status_col = len(master_headers) + 1
    ws.append([*_master_values(row, master_headers), row.status, *_rsch_values(row.rsch)])
    row_idx = ws.max_row
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row_idx, col_idx)
        cell.border = _THIN_BORDER
        cell.alignment = Alignment(
            horizontal="right" if _is_numeric_header(header) else "left",
            vertical="top",
            wrap_text=True,
        )
        if _is_numeric_header(header):
            cell.number_format = "#,##0.00"
        if _is_percent_header(header):
            cell.number_format = "0.##%"
    status_cell = ws.cell(row_idx, status_col)
    status_cell.fill = _STATUS_OK_FILL if row.status == "СВЕРЕНО" else _STATUS_ERROR_FILL
    status_cell.font = _STATUS_FONT
    status_cell.alignment = Alignment(horizontal="center", vertical="center")
    if row.reason:
        status_cell.comment = Comment(_reason_label(row.reason), "Master-Report")
    source_link = row.master.source_link if row.master is not None else None
    if source_link is None and row.rsch is not None:
        source_link = row.rsch.source_link
    if source_link:
        apply_cell_hyperlink(ws.cell(row_idx, 1), source_link)
    for col_idx, header in enumerate(headers, start=1):
        if _normalize_text(header) == "расход" and ws.cell(row_idx, col_idx).value not in (
            None,
            "",
            0,
        ):
            ws.cell(row_idx, col_idx).fill = _MASTER_EXPENSE_FILL


def _write_total_row(ws: Worksheet, headers: list[str]) -> None:
    row_idx = ws.max_row + 1
    ws.cell(row_idx, 1, "ИТОГО:")
    if row_idx > 2:
        for col_idx, header in enumerate(headers, start=1):
            if _should_total_header(header):
                letter = get_column_letter(col_idx)
                ws.cell(row_idx, col_idx, f"=SUM({letter}2:{letter}{row_idx - 1})")
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row_idx, col_idx)
        cell.fill = _TOTAL_FILL
        cell.font = _TOTAL_FONT
        cell.border = _TOTAL_BORDER
        if _is_numeric_header(header):
            cell.number_format = "#,##0.00"
        if _is_percent_header(header):
            cell.number_format = "0.##%"


def _autosize_columns(ws: Worksheet) -> None:
    for col_idx in range(1, ws.max_column + 1):
        max_len = 0
        for row in ws.iter_rows(min_col=col_idx, max_col=col_idx):
            value = row[0].value
            max_len = max(max_len, len(str(value)) if value is not None else 0)
        ws.column_dimensions[get_column_letter(col_idx)].width = max(
            10,
            min(45, max_len + 2),
        )


def _build_workbook(
    target_date: date,
    rows: Iterable[ReconciliationRow],
    master_headers: list[str],
) -> Workbook:
    row_list = sorted(rows, key=lambda row: 0 if row.status == "СВЕРЕНО" else 1)
    headers = [*master_headers, "ИТОГ", *RSCH_HEADERS]
    wb = Workbook()
    ws = wb.active
    ws.title = target_date.strftime("%d.%m.%Y")
    _write_headers(ws, headers)
    for row in row_list:
        _append_reconciliation_row(ws, row, master_headers)
    _write_total_row(ws, headers)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{ws.max_row}"
    _autosize_columns(ws)
    return wb


def build_reconciliation_report(
    master_path: Path | str,
    rsch_path: Path | str,
    output_path: Path | str,
    *,
    target_date: date | None = None,
) -> int:
    master_path = Path(master_path)
    rsch_path = Path(rsch_path)
    output_path = Path(output_path)

    if not master_path.exists():
        raise FileNotFoundError(f"Не найден мастер-отчет: {master_path}")
    if not rsch_path.exists():
        raise FileNotFoundError(f"Не найден РСЧ-отчет: {rsch_path}")

    master_wb = load_workbook(master_path, data_only=False)
    rsch_wb = load_workbook(rsch_path, data_only=True)
    try:
        effective_date = _resolve_target_date(master_wb, rsch_wb, target_date)
        master_ws = _find_sheet(master_wb, effective_date)
        rsch_ws = _find_sheet(rsch_wb, effective_date)
        master_headers, master_rows = _collect_master_rows(master_ws)
        rows = _build_reconciliation_rows(master_rows, _collect_rsch_rows(rsch_ws))
        wb_out = _build_workbook(effective_date, rows, master_headers)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        wb_out.save(output_path)
        return len(rows)
    finally:
        master_wb.close()
        rsch_wb.close()
