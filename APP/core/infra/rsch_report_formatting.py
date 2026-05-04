from __future__ import annotations

from copy import copy
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional, Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

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
_HEADER_FILL = PatternFill(
    start_color="FF1F4E79", end_color="FF1F4E79", fill_type="solid"
)
_TOTAL_FILL = PatternFill(
    start_color="FFD9E1F2", end_color="FFD9E1F2", fill_type="solid"
)
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


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").lower().split())


def copy_style(src_cell, dst_cell) -> None:
    dst_cell.font = copy(src_cell.font)
    dst_cell.fill = copy(src_cell.fill)
    dst_cell.border = copy(src_cell.border)
    dst_cell.alignment = copy(src_cell.alignment)
    dst_cell.number_format = src_cell.number_format
    dst_cell.protection = copy(src_cell.protection)


def find_total_row(template_ws: Worksheet) -> Optional[int]:
    for row_idx in range(1, template_ws.max_row + 1):
        label = _normalize_text(template_ws.cell(row_idx, 1).value)
        if label.startswith("итого"):
            return row_idx
    return None


def prepare_output_sheet(
    template_ws: Worksheet,
    sheet_name: str,
    headers: Sequence[str],
    template_headers: Sequence[str],
) -> tuple[Workbook, Worksheet, Dict[str, Any]]:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    style_layout = _resolve_template_style_layout(template_ws, template_headers)
    ws.append(list(headers))

    for col_idx, _ in enumerate(headers, start=1):
        header_source = template_ws.cell(1, style_layout["header_cols"][col_idx])
        copy_style(header_source, ws.cell(1, col_idx))
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

    _ensure_header_style(ws, len(headers), style_layout["legacy_template"])
    return wb, ws, style_layout


def _template_header_values(template_ws: Worksheet, max_scan: int) -> list[str]:
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


def _is_legacy_template(
    header_values: Sequence[str], template_headers: Sequence[str]
) -> bool:
    expected = [_normalize_text(value) for value in template_headers]
    return list(header_values[: len(expected)]) != expected


def _resolve_template_style_layout(
    template_ws: Worksheet, template_headers: Sequence[str]
) -> Dict[str, Any]:
    max_scan = max(8, min(template_ws.max_column, 32))
    header_values = _template_header_values(template_ws, max_scan)
    cols = _resolve_template_semantic_columns(header_values)
    total_row_idx = find_total_row(template_ws)
    blank_total_col = _find_blank_total_col(template_ws, max_scan, total_row_idx)
    data_cols = _build_data_style_columns(cols, blank_total_col)
    total_cols = _build_total_style_columns(cols, blank_total_col)

    return {
        "header_cols": _build_header_style_columns(cols),
        "width_cols": data_cols,
        "data_cols": data_cols,
        "total_cols": total_cols,
        "legacy_template": _is_legacy_template(header_values, template_headers),
        "detail_amount_formats": {
            5: _resolve_amount_number_format(
                template_ws, data_cols[5], 2, total_row_idx, 1
            ),
            6: _resolve_amount_number_format(
                template_ws, data_cols[6], 2, total_row_idx, 1
            ),
        },
        "total_amount_formats": {
            5: _resolve_amount_number_format(
                template_ws, total_cols[5], total_row_idx, 2, 1
            ),
            6: _resolve_amount_number_format(
                template_ws, total_cols[6], total_row_idx, 2, 1
            ),
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


def _ensure_header_style(
    ws: Worksheet, column_count: int, force_normalize: bool
) -> None:
    if not force_normalize:
        return
    for col_idx in range(1, column_count + 1):
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


def normalize_legacy_data_row(
    ws_out: Worksheet, row_idx: int, amount_formats: Dict[int, str]
) -> None:
    _ensure_comment_cell_style(ws_out.cell(row_idx, 4))
    _ensure_amount_cell_style(ws_out.cell(row_idx, 5), amount_formats[5])
    _ensure_amount_cell_style(ws_out.cell(row_idx, 6), amount_formats[6])
    _ensure_account_cell_style(ws_out.cell(row_idx, 7))
    _ensure_comment_cell_style(ws_out.cell(row_idx, 8))


def ensure_total_row_style(
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


def autosize_all_columns(
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


def apply_amount_highlighting(
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


def apply_warning_row_highlighting(
    ws_out: Worksheet, row_idx: int, column_count: int
) -> None:
    for col_idx in range(1, column_count + 1):
        ws_out.cell(row_idx, col_idx).fill = copy(_WARNING_FILL)


def create_builtin_template_workbook(headers: Sequence[str]) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "РСЧ"
    ws.append(list(headers))
    ws.append(["", "", "", "", 0, 0, "", ""])
    ws.append(["ИТОГО:", None, None, None, "=SUM(E2:E2)", "=SUM(F2:F2)", None, None])

    for col_idx in range(1, len(headers) + 1):
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

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(3, col_idx)
        cell.fill = copy(_TOTAL_FILL)
        cell.font = Font(bold=True)
        cell.border = copy(_TOTAL_BORDER)
    ws["B3"].number_format = "General"
    ws["C3"].number_format = "General"
    ws["D3"].number_format = "General"
    ws["G3"].number_format = "General"
    ws["H3"].number_format = "General"
    ws["E3"].number_format = _DEFAULT_AMOUNT_NUMBER_FORMAT
    ws["F3"].number_format = _DEFAULT_AMOUNT_NUMBER_FORMAT
    ws["E3"].alignment = copy(_AMOUNT_ALIGNMENT)
    ws["F3"].alignment = copy(_AMOUNT_ALIGNMENT)
    ws.freeze_panes = "A2"
    return wb
