from __future__ import annotations

import logging
from copy import copy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import openpyxl
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

logger = logging.getLogger(__name__)

RSCH_HEADERS = [
    "Дата",
    "ИСПОЛНИТЕЛЬ",
    "ЗАКАЗЧИК",
    "Контрагент",
    "Комментарий",
    "Приход",
    "Расход",
    "р/с",
]

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
    }


def _collect_rows_from_sheet(
    ws: Worksheet,
    target_date: Optional[date],
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

        income = _to_decimal(ws.cell(row_idx, col_map["income"]).value)
        expense = _to_decimal(ws.cell(row_idx, col_map["expense"]).value)
        if income == 0 and expense == 0:
            continue

        account = _cell_text(ws, row_idx, col_map["account"])
        expense_comment = _cell_text(ws, row_idx, 10)

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
) -> tuple[Workbook, Worksheet]:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name

    headers = [template_ws.cell(1, i).value for i in range(1, 9)]
    if any(h is None for h in headers):
        headers = RSCH_HEADERS
    ws.append(headers)

    for col_idx in range(1, 9):
        _copy_style(template_ws.cell(1, col_idx), ws.cell(1, col_idx))
        col = get_column_letter(col_idx)
        src_dim = template_ws.column_dimensions.get(col)
        if src_dim and src_dim.width:
            ws.column_dimensions[col].width = src_dim.width

    ws.freeze_panes = template_ws.freeze_panes
    return wb, ws


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

        if col_idx in (6, 7):
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
    income_cell = ws_out.cell(row_idx, 6)
    expense_cell = ws_out.cell(row_idx, 7)

    if income != 0:
        income_cell.fill = _INCOME_FILL
        income_cell.font = copy(_INCOME_FONT)

    if expense != 0:
        expense_cell.fill = _EXPENSE_FILL
        expense_cell.font = copy(_EXPENSE_FONT)


def _apply_warning_row_highlighting(ws_out: Worksheet, row_idx: int) -> None:
    for col_idx in range(1, 9):
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
                rows.extend(_collect_rows_from_sheet(ws, target_date))
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
    ws.append([datetime.now(), "", "", "", "", 0, 0, ""])
    ws.append(["ИТОГО:", None, None, None, None, "=SUM(F2:F2)", "=SUM(G2:G2)", None])
    ws["A1"].font = Font(bold=True)
    ws["B1"].font = Font(bold=True)
    ws["C1"].font = Font(bold=True)
    ws["D1"].font = Font(bold=True)
    ws["E1"].font = Font(bold=True)
    ws["F1"].font = Font(bold=True)
    ws["G1"].font = Font(bold=True)
    ws["F2"].number_format = "#,##0.00"
    ws["G2"].number_format = "#,##0.00"
    return wb


def build_rsch_report(
    source_path: Path | str | Sequence[Path | str],
    output_path: Path,
    *,
    target_date: Optional[date] = None,
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
        rows.extend(_collect_rows_from_workbook(src_path, target_date, issues))

    if issues_sink is not None:
        issues_sink.extend(issues)

    if issues:
        logger.warning(
            "РСЧ: обнаружены проблемы в листах (%s). Сборка продолжена по валидным листам.",
            len(issues),
        )

    sheet_name = target_date.strftime("%d.%m") if target_date else template_ws.title
    wb_out, ws_out = _prepare_output_sheet(template_ws, sheet_name)

    template_data_row_idx = 2 if template_ws.max_row >= 2 else 1
    for row in rows:
        ws_out.append(
            [
                datetime.combine(row["date"], datetime.min.time()),
                row["executor"],
                row["customer"],
                row["contractor"],
                row["comment"],
                row["income"],
                row["expense"],
                row["account"],
            ]
        )
        curr_idx = ws_out.max_row
        for col_idx in range(1, 9):
            _copy_style(
                template_ws.cell(template_data_row_idx, col_idx),
                ws_out.cell(curr_idx, col_idx),
            )
        if _is_problem_row(row):
            _apply_warning_row_highlighting(ws_out, curr_idx)
        _apply_amount_highlighting(ws_out, curr_idx, row["income"], row["expense"])

    _autosize_all_columns(ws_out)

    total_row_idx = ws_out.max_row + 1
    ws_out.cell(total_row_idx, 1, "ИТОГО:")
    if total_row_idx > 2:
        ws_out.cell(total_row_idx, 6, f"=SUM(F2:F{total_row_idx - 1})")
        ws_out.cell(total_row_idx, 7, f"=SUM(G2:G{total_row_idx - 1})")
    else:
        ws_out.cell(total_row_idx, 6, Decimal("0"))
        ws_out.cell(total_row_idx, 7, Decimal("0"))

    template_total_row_idx = _find_total_row(template_ws)
    if template_total_row_idx:
        for col_idx in range(1, 9):
            _copy_style(
                template_ws.cell(template_total_row_idx, col_idx),
                ws_out.cell(total_row_idx, col_idx),
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
