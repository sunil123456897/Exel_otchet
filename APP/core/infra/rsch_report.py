from __future__ import annotations

import logging
from copy import copy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

logger = logging.getLogger(__name__)

RSCH_HEADERS = [
    "ИСПОЛНИТЕЛЬ",
    "ЗАКАЗЧИК",
    "Контрагент",
    "Комментарий",
    "Приход",
    "Расход",
    "р/с",
    "Источник",
]
RSCH_TEMPLATE_HEADERS = RSCH_HEADERS

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RSCH_TEMPLATE_PATH = _REPO_ROOT / "РСЧ" / "шаблон отчета.xlsx"

_INCOME_FILL = PatternFill(
    start_color="FFC6EFCE", end_color="FFC6EFCE", fill_type="solid"
)
_EXPENSE_FILL = PatternFill(
    start_color="FFFFC7CE", end_color="FFFFC7CE", fill_type="solid"
)
_WARNING_FILL = PatternFill(
    start_color="FFFFFF00", end_color="FFFFFF00", fill_type="solid"
)
_INCOME_FONT = Font(color="FF006100", bold=True)
_EXPENSE_FONT = Font(color="FF9C0006", bold=True)
_HEADER_FILL = PatternFill(start_color="FF1F4E79", end_color="FF1F4E79", fill_type="solid")
_TOTAL_FILL = PatternFill(start_color="FFD9E1F2", end_color="FFD9E1F2", fill_type="solid")
_HEADER_FONT = Font(color="FFFFFFFF", bold=True)
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
_HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center", wrap_text=True)
_TEXT_ALIGNMENT = Alignment(horizontal="left", vertical="top", wrap_text=True)
_ACCOUNT_ALIGNMENT = Alignment(horizontal="left", vertical="center")
_AMOUNT_ALIGNMENT = Alignment(horizontal="right", vertical="center")
_DATE_ALIGNMENT = Alignment(horizontal="left", vertical="center")
_DEFAULT_AMOUNT_NUMBER_FORMAT = "#,##0.00"
_SPECIAL_CUSTOMER_MARKERS = (
    "% по депозиту",
    "комиссия",
    "налог",
)


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").lower().split())


def _is_rsch_sheet_title(sheet_title: str) -> bool:
    normalized = _normalize_text(sheet_title)
    return "рсч" in normalized and "шаблон" not in normalized


def _to_decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip().replace(" ", "").replace(",", ".")
    if not text:
        return Decimal("0")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _as_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
            try:
                return datetime.strptime(stripped, fmt).date()
            except ValueError:
                continue
    return None


def _clean_executor_name(sheet_name: str) -> str:
    tokens = [
        token for token in str(sheet_name).strip().split() if token.lower() != "рсч"
    ]
    cleaned = " ".join(tokens).strip()
    return (cleaned or str(sheet_name).strip()).upper()


def _copy_style(src_cell, dst_cell) -> None:
    dst_cell.font = copy(src_cell.font)
    dst_cell.fill = copy(src_cell.fill)
    dst_cell.border = copy(src_cell.border)
    dst_cell.alignment = copy(src_cell.alignment)
    dst_cell.number_format = src_cell.number_format
    dst_cell.protection = copy(src_cell.protection)


def _find_header_row(ws: Worksheet) -> Optional[int]:
    max_scan = min(ws.max_row, 30)
    for row_idx in range(1, max_scan + 1):
        values = [
            _normalize_text(ws.cell(row_idx, col_idx).value) for col_idx in range(1, 33)
        ]
        has_date = any(v == "дата" for v in values)
        has_income = any("приход" in v and "рсч" in v for v in values)
        has_expense = any("расход" in v and "рсч" in v for v in values)
        if has_date and has_income and has_expense:
            return row_idx
    return None


def _detect_columns(ws: Worksheet, header_row_idx: int) -> Dict[str, Optional[int]]:
    max_scan = min(ws.max_column, 128)
    header_values = [
        _normalize_text(ws.cell(header_row_idx, col_idx).value)
        for col_idx in range(1, max_scan + 1)
    ]

    project_cols = [i + 1 for i, v in enumerate(header_values) if "проект" in v]
    contractor_cols = [i + 1 for i, v in enumerate(header_values) if "контрагент" in v]

    def first_index(predicate) -> Optional[int]:
        for i, v in enumerate(header_values, start=1):
            if predicate(v):
                return i
        return None

    col_map = {
        "date": first_index(lambda v: v == "дата"),
        "income": first_index(lambda v: "приход" in v and "рсч" in v),
        "expense": first_index(lambda v: "расход" in v and "рсч" in v),
        "account": first_index(lambda v: "р/с" in v),
        "project_left": project_cols[0] if project_cols else None,
        "project_right": project_cols[1]
        if len(project_cols) > 1
        else (project_cols[0] if project_cols else None),
        "contractor_left": contractor_cols[0] if contractor_cols else None,
        "contractor_right": contractor_cols[1]
        if len(contractor_cols) > 1
        else (contractor_cols[0] if contractor_cols else None),
    }

    required = (
        "date",
        "income",
        "expense",
        "account",
        "project_left",
        "contractor_left",
    )
    missing = [key for key in required if not col_map.get(key)]
    if missing:
        raise ValueError(
            f"Header columns not found in sheet '{ws.title}': {', '.join(missing)}"
        )
    return col_map


def _cell_text(ws: Worksheet, row_idx: int, col_idx: Optional[int]) -> str:
    if not col_idx:
        return ""
    value = ws.cell(row_idx, col_idx).value
    return "" if value is None else str(value).strip()


def _pick_text(primary: str, secondary: str) -> str:
    return primary if primary else secondary


def _is_special_customer_label(customer: str) -> bool:
    normalized = _normalize_text(customer)
    return any(marker in normalized for marker in _SPECIAL_CUSTOMER_MARKERS)


def _is_problem_row(row: Dict[str, Any]) -> bool:
    income = row["income"]
    expense = row["expense"]
    contractor = str(row["contractor"] or "").strip()
    customer = str(row["customer"] or "").strip()
    executor = str(row["executor"] or "").strip()
    account = str(row["account"] or "").strip()

    if income != 0 and expense != 0:
        return True

    if not contractor and customer and not _is_special_customer_label(customer):
        return True

    if not customer or not executor or not account:
        return True

    return income == 0 and expense == 0


def _build_row(
    row_date: date,
    executor: str,
    account: str,
    source: str,
    customer_primary: str,
    customer_secondary: str,
    contractor_primary: str,
    contractor_secondary: str,
    comment: str,
    income: Decimal,
    expense: Decimal,
) -> Dict[str, Any]:
    return {
        "date": row_date,
        "contractor": _pick_text(contractor_primary, contractor_secondary),
        "customer": _pick_text(customer_primary, customer_secondary),
        "executor": executor,
        "comment": comment,
        "income": income,
        "expense": expense,
        "account": account,
        "source": source,
    }


def _format_source_label(source_name: str, sheet_name: str, row_idx: int) -> str:
    return f"{source_name} | {sheet_name} | строка {row_idx}"


def _collect_rows_from_sheet(
    ws: Worksheet,
    target_date: Optional[date],
    source_name: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    header_row_idx = _find_header_row(ws)
    if header_row_idx is None:
        return []
    col_map = _detect_columns(ws, header_row_idx)
    executor = _clean_executor_name(ws.title)
    rows: List[Dict[str, Any]] = []

    for row_idx in range(header_row_idx + 1, ws.max_row + 1):
        row_date = _as_date(ws.cell(row_idx, col_map["date"]).value)
        if row_date is None:
            continue
        if target_date and row_date != target_date:
            continue
        if start_date and end_date and not (start_date <= row_date <= end_date):
            continue

        income = _to_decimal(ws.cell(row_idx, col_map["income"]).value)
        expense = _to_decimal(ws.cell(row_idx, col_map["expense"]).value)
        if income == 0 and expense == 0:
            continue

        account = _cell_text(ws, row_idx, col_map["account"])
        expense_comment = _cell_text(ws, row_idx, 10)
        source = _format_source_label(source_name, ws.title, row_idx)

        customer_left = _cell_text(ws, row_idx, col_map["project_left"])
        customer_right = _cell_text(ws, row_idx, col_map["project_right"])
        contractor_left = _cell_text(ws, row_idx, col_map["contractor_left"])
        contractor_right = _cell_text(ws, row_idx, col_map["contractor_right"])

        if income != 0 and expense != 0:
            rows.append(
                _build_row(
                    row_date,
                    executor,
                    account,
                    source,
                    customer_left,
                    customer_right,
                    contractor_left,
                    contractor_right,
                    expense_comment,
                    income,
                    expense,
                )
            )
        elif income != 0:
            rows.append(
                _build_row(
                    row_date,
                    executor,
                    account,
                    source,
                    customer_left,
                    customer_right,
                    contractor_left,
                    contractor_right,
                    "",
                    income,
                    Decimal("0"),
                )
            )
        elif expense != 0:
            rows.append(
                _build_row(
                    row_date,
                    executor,
                    account,
                    source,
                    customer_right,
                    customer_left,
                    contractor_right,
                    contractor_left,
                    expense_comment,
                    Decimal("0"),
                    expense,
                )
            )

    return rows


def _find_total_row(template_ws: Worksheet) -> Optional[int]:
    for row_idx in range(1, template_ws.max_row + 1):
        label = _normalize_text(template_ws.cell(row_idx, 1).value)
        if label.startswith("итого"):
            return row_idx
    return None


def _prepare_output_sheet(
    template_ws: Worksheet, sheet_name: str
) -> tuple[Workbook, Worksheet, Dict[str, Any]]:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    style_layout = _resolve_template_style_layout(template_ws)

    ws.append(RSCH_HEADERS)

    for col_idx, _ in enumerate(RSCH_HEADERS, start=1):
        header_source = template_ws.cell(1, style_layout["header_cols"][col_idx])
        _copy_style(header_source, ws.cell(1, col_idx))
        col = get_column_letter(col_idx)
        source_col = get_column_letter(style_layout["width_cols"][col_idx])
        src_dim = template_ws.column_dimensions.get(source_col)
        if src_dim and src_dim.width:
            ws.column_dimensions[col].width = src_dim.width

    ws.freeze_panes = template_ws.freeze_panes
    ws.sheet_view.zoomScale = template_ws.sheet_view.zoomScale
    ws.sheet_view.showGridLines = template_ws.sheet_view.showGridLines
    ws.sheet_format.defaultRowHeight = template_ws.sheet_format.defaultRowHeight
    header_height = template_ws.row_dimensions[1].height
    if header_height:
        ws.row_dimensions[1].height = header_height

    _ensure_header_style(ws, style_layout["legacy_template"])
    return wb, ws, style_layout


def _template_header_values(template_ws: Worksheet, max_scan: int) -> List[str]:
    return [
        _normalize_text(template_ws.cell(1, col_idx).value)
        for col_idx in range(1, max_scan + 1)
    ]


def _first_matching_column(header_values: Sequence[str], predicate) -> Optional[int]:
    for idx, value in enumerate(header_values, start=1):
        if predicate(value):
            return idx
    return None


def _resolve_template_semantic_columns(header_values: Sequence[str]) -> Dict[str, int]:
    fallback_col = _first_matching_column(header_values, lambda v: bool(v)) or 1
    date_col = _first_matching_column(header_values, lambda v: v == "дата") or 1
    executor_col = _first_matching_column(header_values, lambda v: "исполнитель" in v)
    customer_col = _first_matching_column(header_values, lambda v: "заказчик" in v)
    contractor_col = _first_matching_column(header_values, lambda v: "контрагент" in v)
    comment_col = _first_matching_column(header_values, lambda v: "комментар" in v)
    income_col = _first_matching_column(header_values, lambda v: "приход" in v)
    expense_col = _first_matching_column(header_values, lambda v: "расход" in v)
    account_col = _first_matching_column(header_values, lambda v: "р/с" in v)
    text_col = contractor_col or executor_col or customer_col or fallback_col
    comment_style_col = comment_col or contractor_col or customer_col or text_col

    return {
        "fallback": fallback_col,
        "date": date_col,
        "executor": executor_col or text_col,
        "customer": customer_col or text_col,
        "contractor": contractor_col or text_col,
        "comment_style": comment_style_col,
        "income": income_col or fallback_col,
        "expense": expense_col or fallback_col,
        "account": account_col or text_col,
        "text": text_col,
    }


def _find_blank_total_col(
    template_ws: Worksheet, max_scan: int, total_row_idx: Optional[int]
) -> int:
    default_col = 2 if template_ws.max_column >= 2 else 1
    if total_row_idx is None:
        return default_col
    for col_idx in range(1, max_scan + 1):
        if template_ws.cell(total_row_idx, col_idx).value in (None, ""):
            return col_idx
    return default_col


def _build_header_style_columns(cols: Dict[str, int]) -> Dict[int, int]:
    return {
        1: cols["executor"],
        2: cols["customer"],
        3: cols["contractor"],
        4: cols["comment_style"],
        5: cols["income"],
        6: cols["expense"],
        7: cols["account"],
        8: cols["comment_style"],
    }


def _build_data_style_columns(cols: Dict[str, int], blank_total_col: int) -> Dict[int, int]:
    return {
        1: cols["executor"],
        2: cols["customer"],
        3: cols["contractor"],
        4: cols["comment_style"],
        5: cols["income"] or blank_total_col,
        6: cols["expense"] or blank_total_col,
        7: cols["account"],
        8: cols["comment_style"],
    }


def _build_total_style_columns(cols: Dict[str, int], blank_total_col: int) -> Dict[int, int]:
    return {
        1: 1,
        2: blank_total_col,
        3: blank_total_col,
        4: blank_total_col,
        5: cols["income"] or blank_total_col,
        6: cols["expense"] or blank_total_col,
        7: blank_total_col,
        8: blank_total_col,
    }


def _is_legacy_template(header_values: Sequence[str]) -> bool:
    expected = [_normalize_text(value) for value in RSCH_TEMPLATE_HEADERS]
    expected_with_date = ["дата", *expected]
    prefix = list(header_values)
    return not (
        prefix[: len(expected)] == expected
        or prefix[: len(expected_with_date)] == expected_with_date
    )


def _resolve_template_style_layout(template_ws: Worksheet) -> Dict[str, Any]:
    max_scan = max(8, min(template_ws.max_column, 32))
    header_values = _template_header_values(template_ws, max_scan)
    cols = _resolve_template_semantic_columns(header_values)
    total_row_idx = _find_total_row(template_ws)
    blank_total_col = _find_blank_total_col(template_ws, max_scan, total_row_idx)
    data_cols = _build_data_style_columns(cols, blank_total_col)
    total_cols = _build_total_style_columns(cols, blank_total_col)

    return {
        "header_cols": _build_header_style_columns(cols),
        "width_cols": data_cols,
        "data_cols": data_cols,
        "total_cols": total_cols,
        "legacy_template": _is_legacy_template(header_values),
        "detail_amount_formats": {
            5: _resolve_amount_number_format(template_ws, data_cols[5], 2, total_row_idx, 1),
            6: _resolve_amount_number_format(template_ws, data_cols[6], 2, total_row_idx, 1),
        },
        "total_amount_formats": {
            5: _resolve_amount_number_format(template_ws, total_cols[5], total_row_idx, 2, 1),
            6: _resolve_amount_number_format(template_ws, total_cols[6], total_row_idx, 2, 1),
        },
    }


def _resolve_amount_number_format(
    template_ws: Worksheet, col_idx: int, *row_indexes: Optional[int]
) -> str:
    for row_idx in row_indexes:
        if row_idx is None or row_idx > template_ws.max_row:
            continue
        fmt = template_ws.cell(row_idx, col_idx).number_format
        if fmt and fmt != "General":
            return fmt
    return _DEFAULT_AMOUNT_NUMBER_FORMAT


def _ensure_header_style(ws: Worksheet, force_normalize: bool) -> None:
    if not force_normalize:
        return
    for col_idx in range(1, len(RSCH_HEADERS) + 1):
        cell = ws.cell(1, col_idx)
        cell.fill = copy(_HEADER_FILL)
        cell.font = copy(_HEADER_FONT)
        cell.alignment = copy(_HEADER_ALIGNMENT)
        cell.border = copy(_THIN_BORDER)


def _ensure_comment_cell_style(cell) -> None:
    cell.number_format = "General"
    cell.alignment = copy(_TEXT_ALIGNMENT)
    cell.border = copy(_THIN_BORDER)


def _ensure_account_cell_style(cell) -> None:
    cell.number_format = "General"
    cell.alignment = copy(_ACCOUNT_ALIGNMENT)
    cell.border = copy(_THIN_BORDER)


def _ensure_amount_cell_style(cell, number_format: str) -> None:
    cell.number_format = number_format
    cell.alignment = copy(_AMOUNT_ALIGNMENT)
    cell.border = copy(_THIN_BORDER)


def _ensure_date_cell_style(cell) -> None:
    cell.alignment = copy(_DATE_ALIGNMENT)
    cell.border = copy(_THIN_BORDER)


def _normalize_legacy_data_row(
    ws_out: Worksheet, row_idx: int, amount_formats: Dict[int, str]
) -> None:
    _ensure_comment_cell_style(ws_out.cell(row_idx, 4))
    _ensure_amount_cell_style(ws_out.cell(row_idx, 5), amount_formats[5])
    _ensure_amount_cell_style(ws_out.cell(row_idx, 6), amount_formats[6])
    _ensure_account_cell_style(ws_out.cell(row_idx, 7))
    _ensure_comment_cell_style(ws_out.cell(row_idx, 8))


def _ensure_total_row_style(
    ws_out: Worksheet,
    row_idx: int,
    amount_formats: Dict[int, str],
    *,
    force_normalize: bool,
) -> None:
    if not force_normalize:
        return

    label = ws_out.cell(row_idx, 1)
    label.fill = copy(_TOTAL_FILL)
    label.font = Font(bold=True)
    label.border = copy(_TOTAL_BORDER)

    for col_idx in (2, 3, 4, 7, 8):
        cell = ws_out.cell(row_idx, col_idx)
        cell.fill = copy(_TOTAL_FILL)
        cell.font = Font(bold=True)
        cell.border = copy(_TOTAL_BORDER)
        cell.number_format = "General"

    for col_idx in (5, 6):
        cell = ws_out.cell(row_idx, col_idx)
        cell.fill = copy(_TOTAL_FILL)
        cell.font = Font(bold=True)
        cell.border = copy(_TOTAL_BORDER)
        cell.number_format = amount_formats[col_idx]
        cell.alignment = copy(_AMOUNT_ALIGNMENT)
def _display_len(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, datetime):
        return 10
    if isinstance(value, Decimal):
        return len(f"{value:,.2f}")
    if isinstance(value, (int, float)):
        return len(f"{value:,.2f}")
    return len(str(value))


def _autosize_all_columns(
    ws_out: Worksheet, min_width: int = 10, max_width: int = 60
) -> None:
    for col_idx in range(1, ws_out.max_column + 1):
        col_letter = get_column_letter(col_idx)
        max_len = 0
        for row_idx in range(1, ws_out.max_row + 1):
            max_len = max(max_len, _display_len(ws_out.cell(row_idx, col_idx).value))

        if col_idx in (5, 6):
            max_len = max(max_len, 14)

        ws_out.column_dimensions[col_letter].width = max(
            min_width,
            min(max_width, max_len + 2),
        )


def _apply_amount_highlighting(
    ws_out: Worksheet,
    row_idx: int,
    income: Decimal,
    expense: Decimal,
) -> None:
    income_cell = ws_out.cell(row_idx, 5)
    expense_cell = ws_out.cell(row_idx, 6)

    if income != 0:
        income_cell.fill = _INCOME_FILL
        income_cell.font = copy(_INCOME_FONT)

    if expense != 0:
        expense_cell.fill = _EXPENSE_FILL
        expense_cell.font = copy(_EXPENSE_FONT)


def _apply_warning_row_highlighting(ws_out: Worksheet, row_idx: int) -> None:
    for col_idx in range(1, len(RSCH_HEADERS) + 1):
        ws_out.cell(row_idx, col_idx).fill = copy(_WARNING_FILL)


def _normalize_source_paths(source_paths: Any) -> List[Path]:
    if isinstance(source_paths, (str, Path)):
        raw_paths = [source_paths]
    else:
        raw_paths = list(source_paths or [])

    normalized: List[Path] = []
    seen: set[str] = set()
    for raw_path in raw_paths:
        if raw_path is None:
            continue
        path = Path(raw_path)
        key = str(path)
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(path)
    return normalized


def _collect_rows_from_workbook(
    source_path: Path,
    target_date: Optional[date],
    issues_sink: Optional[List[str]] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    wb_source = openpyxl.load_workbook(source_path, data_only=True)
    try:
        rows: List[Dict[str, Any]] = []
        for ws in wb_source.worksheets:
            if ws.title.startswith("_"):
                continue
            if not _is_rsch_sheet_title(ws.title):
                continue
            try:
                rows.extend(
                    _collect_rows_from_sheet(
                        ws,
                        target_date,
                        source_path.name,
                        start_date=start_date,
                        end_date=end_date,
                    )
                )
            except Exception as e:
                issue = (
                    f"Лист '{ws.title}' в файле '{source_path.name}' пропущен: {e}"
                )
                logger.warning(issue)
                if issues_sink is not None:
                    issues_sink.append(issue)
        return rows
    finally:
        wb_source.close()


def _create_builtin_template_workbook() -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "РСЧ"
    ws.append(RSCH_HEADERS)
    ws.append(["", "", "", "", 0, 0, "", ""])
    ws.append(["ИТОГО:", None, None, None, "=SUM(E2:E2)", "=SUM(F2:F2)", None, None])

    for col_idx in range(1, len(RSCH_HEADERS) + 1):
        cell = ws.cell(1, col_idx)
        cell.fill = copy(_HEADER_FILL)
        cell.font = copy(_HEADER_FONT)
        cell.alignment = copy(_HEADER_ALIGNMENT)
        cell.border = copy(_THIN_BORDER)

    for ref in ("A2", "B2", "C2", "D2", "H2"):
        ws[ref].alignment = copy(_TEXT_ALIGNMENT)
        ws[ref].border = copy(_THIN_BORDER)
        ws[ref].number_format = "General"
    ws["G2"].alignment = copy(_ACCOUNT_ALIGNMENT)
    ws["G2"].border = copy(_THIN_BORDER)
    ws["G2"].number_format = "General"
    for ref in ("E2", "F2"):
        ws[ref].number_format = _DEFAULT_AMOUNT_NUMBER_FORMAT
        ws[ref].alignment = copy(_AMOUNT_ALIGNMENT)
        ws[ref].border = copy(_THIN_BORDER)

    for col_idx in range(1, len(RSCH_HEADERS) + 1):
        cell = ws.cell(3, col_idx)
        cell.fill = copy(_TOTAL_FILL)
        cell.font = Font(bold=True)
        cell.border = copy(_TOTAL_BORDER)
    for ref in ("B3", "C3", "D3", "G3", "H3"):
        ws[ref].number_format = "General"
    ws["E3"].number_format = _DEFAULT_AMOUNT_NUMBER_FORMAT
    ws["F3"].number_format = _DEFAULT_AMOUNT_NUMBER_FORMAT
    ws["E3"].alignment = copy(_AMOUNT_ALIGNMENT)
    ws["F3"].alignment = copy(_AMOUNT_ALIGNMENT)
    ws.freeze_panes = "A2"
    return wb


def _write_rsch_sheet(
    wb_out: Workbook,
    template_ws: Worksheet,
    sheet_name: str,
    rows: List[Dict[str, Any]],
    *,
    first_sheet: bool,
) -> None:
    ws_out = wb_out.active if first_sheet else wb_out.create_sheet()
    ws_out.title = sheet_name

    style_layout = _resolve_template_style_layout(template_ws)
    ws_out.append(RSCH_HEADERS)

    for col_idx, _ in enumerate(RSCH_HEADERS, start=1):
        header_source = template_ws.cell(1, style_layout["header_cols"][col_idx])
        _copy_style(header_source, ws_out.cell(1, col_idx))
        col = get_column_letter(col_idx)
        source_col = get_column_letter(style_layout["width_cols"][col_idx])
        src_dim = template_ws.column_dimensions.get(source_col)
        if src_dim and src_dim.width:
            ws_out.column_dimensions[col].width = src_dim.width

    ws_out.freeze_panes = template_ws.freeze_panes
    ws_out.sheet_view.zoomScale = template_ws.sheet_view.zoomScale
    ws_out.sheet_view.showGridLines = template_ws.sheet_view.showGridLines
    ws_out.sheet_format.defaultRowHeight = template_ws.sheet_format.defaultRowHeight
    header_height = template_ws.row_dimensions[1].height
    if header_height:
        ws_out.row_dimensions[1].height = header_height

    _ensure_header_style(ws_out, style_layout["legacy_template"])

    template_data_row_idx = 2 if template_ws.max_row >= 2 else 1
    for row in rows:
        ws_out.append(
            [
                row["executor"],
                row["customer"],
                row["contractor"],
                row["comment"],
                row["income"],
                row["expense"],
                row["account"],
                row["source"],
            ]
        )
        curr_idx = ws_out.max_row
        for col_idx in range(1, len(RSCH_HEADERS) + 1):
            _copy_style(
                template_ws.cell(template_data_row_idx, style_layout["data_cols"][col_idx]),
                ws_out.cell(curr_idx, col_idx),
            )
        if style_layout["legacy_template"]:
            _normalize_legacy_data_row(
                ws_out, curr_idx, style_layout["detail_amount_formats"]
            )
        if _is_problem_row(row):
            _apply_warning_row_highlighting(ws_out, curr_idx)
        _apply_amount_highlighting(ws_out, curr_idx, row["income"], row["expense"])

    _autosize_all_columns(ws_out)

    total_row_idx = ws_out.max_row + 1
    ws_out.cell(total_row_idx, 1, "ИТОГО:")
    if total_row_idx > 2:
        ws_out.cell(total_row_idx, 5, f"=SUM(E2:E{total_row_idx - 1})")
        ws_out.cell(total_row_idx, 6, f"=SUM(F2:F{total_row_idx - 1})")
    else:
        ws_out.cell(total_row_idx, 5, Decimal("0"))
        ws_out.cell(total_row_idx, 6, Decimal("0"))

    template_total_row_idx = _find_total_row(template_ws)
    if template_total_row_idx:
        for col_idx in range(1, len(RSCH_HEADERS) + 1):
            _copy_style(
                template_ws.cell(
                    template_total_row_idx,
                    style_layout["total_cols"][col_idx],
                ),
                ws_out.cell(total_row_idx, col_idx),
            )
    _ensure_total_row_style(
        ws_out,
        total_row_idx,
        style_layout["total_amount_formats"],
        force_normalize=style_layout["legacy_template"],
    )
    ws_out.auto_filter.ref = (
        f"A1:{get_column_letter(len(RSCH_HEADERS))}{max(1, total_row_idx - 1)}"
    )


def build_rsch_report(
    source_path: Path | str | Sequence[Path | str],
    output_path: Path,
    *,
    target_date: Optional[date] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    template_path: Optional[Path] = None,
    issues_sink: Optional[List[str]] = None,
) -> int:
    source_paths = _normalize_source_paths(source_path)
    output_path = Path(output_path)
    template_to_use = (
        Path(template_path) if template_path else DEFAULT_RSCH_TEMPLATE_PATH
    )

    if not source_paths:
        raise ValueError("Не выбраны файлы РСЧ")
    for src_path in source_paths:
        if not src_path.exists():
            raise FileNotFoundError(f"Не найден файл РСЧ: {src_path}")
    if template_to_use.exists():
        wb_template = openpyxl.load_workbook(template_to_use)
    elif template_path is not None:
        raise FileNotFoundError(f"Не найден шаблон РСЧ: {template_to_use}")
    else:
        warning = (
            f"Шаблон РСЧ не найден: {template_to_use}. "
            "Используется встроенный шаблон."
        )
        logger.warning(warning)
        if issues_sink is not None:
            issues_sink.append(warning)
        wb_template = _create_builtin_template_workbook()

    template_ws = wb_template[wb_template.sheetnames[0]]

    rows: List[Dict[str, Any]] = []
    issues: List[str] = []
    for src_path in source_paths:
        rows.extend(
            _collect_rows_from_workbook(
                src_path,
                target_date,
                issues,
                start_date=start_date,
                end_date=end_date,
            )
        )

    if issues_sink is not None:
        issues_sink.extend(issues)

    if issues:
        logger.warning(
            "РСЧ: обнаружены проблемы в листах (%s). Сборка продолжена по валидным листам.",
            len(issues),
        )

    use_period = start_date is not None and end_date is not None
    wb_out = Workbook()
    if use_period and rows:
        rows_by_date: Dict[date, List[Dict[str, Any]]] = {}
        for row in rows:
            rows_by_date.setdefault(row["date"], []).append(row)
        for idx, row_date in enumerate(sorted(rows_by_date), start=1):
            _write_rsch_sheet(
                wb_out,
                template_ws,
                row_date.strftime("%d.%m"),
                rows_by_date[row_date],
                first_sheet=idx == 1,
            )
    else:
        sheet_date = target_date or start_date
        sheet_name = sheet_date.strftime("%d.%m") if sheet_date else template_ws.title
        _write_rsch_sheet(
            wb_out,
            template_ws,
            sheet_name,
            rows,
            first_sheet=True,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb_out.save(output_path)
    wb_template.close()
    logger.info(
        "RSC report generated: %s (rows=%s, sources=%s)",
        output_path,
        len(rows),
        len(source_paths),
    )
    return len(rows)
