
from __future__ import annotations

import logging
from copy import copy
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import openpyxl
from python_calamine import CalamineWorkbook

from core.domain.data_loss_log import record_loss
from core.infra.utils import get_local_copy

from ._format import (_normalize_text, _to_decimal, _as_date, _clean_executor_name,
    _cell_text_from_row, _pick_text, _format_source_label, _is_rsch_sheet_title)

logger = logging.getLogger(__name__)


def _to_decimal_soft(
    value: Any,
    *,
    sheet: str,
    row_index: int,
    field: str,
    source: str,
) -> Decimal:
    """Fail-soft amount parsing for РСЧ row collection.

    Mirrors :func:`_to_decimal` but, instead of raising on a dirty cell,
    logs the loss to ``data_loss.log`` and returns ``Decimal("0")`` so a
    single bad amount never aborts the whole executor sheet. Previously the
    ``ValueError`` propagated to the per-sheet ``except`` in the workbook
    collectors and silently dropped EVERY row of the sheet (hundreds of valid
    transactions lost for one corrupt cell). Matches reconciliation's
    ``_to_decimal_soft``.
    """
    try:
        return _to_decimal(value)
    except (ValueError, ArithmeticError):
        record_loss(
            source=f"rsch:{source}",
            kind="rsch_amount_parse",
            reason="Некорректное числовое значение в РСЧ; ячейка обнулена",
            row_index=row_index,
            sheet=sheet,
            field=field,
            original_value=value,
        )
        return Decimal("0")


def _copy_style(src_cell: Any, dst_cell: Any) -> None:
    dst_cell.font = copy(src_cell.font)
    dst_cell.fill = copy(src_cell.fill)
    dst_cell.border = copy(src_cell.border)
    dst_cell.alignment = copy(src_cell.alignment)
    dst_cell.number_format = src_cell.number_format
    dst_cell.protection = copy(src_cell.protection)


def _find_header_row(sheet_data: List[tuple[Any, ...]]) -> Optional[int]:
    max_scan = min(len(sheet_data), 30)
    for row_idx_0 in range(max_scan):
        row_values = sheet_data[row_idx_0]
        values = []
        for col_idx_0 in range(32):
            val = row_values[col_idx_0] if col_idx_0 < len(row_values) else None
            values.append(_normalize_text(val))
        has_date = any(v == "дата" for v in values)
        has_income = any("приход" in v and "рсч" in v for v in values)
        has_expense = any("расход" in v and "рсч" in v for v in values)
        if has_date and has_income and has_expense:
            return row_idx_0 + 1
    return None


def _detect_columns(sheet_data: List[tuple[Any, ...]], header_row_idx: int, sheet_title: str) -> Dict[str, Optional[int]]:
    row_values = sheet_data[header_row_idx - 1]
    max_scan = min(len(row_values), 128)
    header_values = [
        _normalize_text(row_values[col_idx_0])
        for col_idx_0 in range(max_scan)
    ]
    if len(header_values) < 128:
        header_values.extend([""] * (128 - len(header_values)))

    project_cols = [i + 1 for i, v in enumerate(header_values) if "проект" in v]
    contractor_cols = [i + 1 for i, v in enumerate(header_values) if "контрагент" in v]

    def first_index(predicate: Callable[[str], bool]) -> Optional[int]:
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
        "project_left",
        "contractor_left",
    )
    missing = [key for key in required if not col_map.get(key)]
    if missing:
        raise ValueError(
            f"Header columns not found in sheet '{sheet_title}': {', '.join(missing)}"
        )
    return col_map



def _build_row(
    row_date: date,
    executor: str,
    account: str,
    source: str,
    source_path: Path,
    source_sheet: str,
    source_row: int,
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
        "source_path": str(source_path),
        "source_sheet": source_sheet,
        "source_row": source_row,
    }



def _collect_rows_from_sheet(
    ws: Any,  # openpyxl Worksheet or _CalamineWorksheetAdapter (duck-typed)
    target_date: Optional[date],
    source_name: str,
    source_path: Path,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    sheet_data = list(ws.iter_rows(values_only=True))
    if not sheet_data:
        return []

    header_row_idx = _find_header_row(sheet_data)
    if header_row_idx is None:
        return []
    col_map = _detect_columns(sheet_data, header_row_idx, ws.title)
    executor = _clean_executor_name(ws.title)
    rows: List[Dict[str, Any]] = []
    current_row_date: Optional[date] = None

    for row_idx in range(header_row_idx + 1, len(sheet_data) + 1):
        row_values = sheet_data[row_idx - 1]

        date_col = col_map["date"]
        raw_date = row_values[date_col - 1] if date_col and date_col <= len(row_values) else None

        explicit_row_date = _as_date(raw_date)
        if explicit_row_date is not None:
            current_row_date = explicit_row_date
        elif raw_date not in (None, "") and str(raw_date).strip():
            current_row_date = None
        if current_row_date is None:
            continue
        row_date = current_row_date
        if target_date and row_date != target_date:
            continue
        if start_date and end_date and not (start_date <= row_date <= end_date):
            continue

        income_col = col_map["income"]
        raw_income = row_values[income_col - 1] if income_col and income_col <= len(row_values) else None
        income = _to_decimal_soft(
            raw_income, sheet=ws.title, row_index=row_idx, field="income",
            source=source_name,
        )

        expense_col = col_map["expense"]
        raw_expense = row_values[expense_col - 1] if expense_col and expense_col <= len(row_values) else None
        expense = _to_decimal_soft(
            raw_expense, sheet=ws.title, row_index=row_idx, field="expense",
            source=source_name,
        )

        account = _cell_text_from_row(row_values, col_map["account"])
        expense_comment = _cell_text_from_row(row_values, 10)
        source = _format_source_label(source_name, ws.title, row_idx)

        customer_left = _cell_text_from_row(row_values, col_map["project_left"])
        customer_right = _cell_text_from_row(row_values, col_map["project_right"])
        contractor_left = _cell_text_from_row(row_values, col_map["contractor_left"])
        contractor_right = _cell_text_from_row(row_values, col_map["contractor_right"])
        has_business_text = any(
            (
                expense_comment,
                customer_left,
                customer_right,
                contractor_left,
                contractor_right,
            )
        )
        if (
            income == 0
            and expense == 0
            and not has_business_text
        ):
            continue

        if income != 0 and expense != 0:
            rows.append(
                _build_row(
                    row_date,
                    executor,
                    account,
                    source,
                    source_path,
                    ws.title,
                    row_idx,
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
                    source_path,
                    ws.title,
                    row_idx,
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
                    source_path,
                    ws.title,
                    row_idx,
                    customer_right,
                    customer_left,
                    contractor_right,
                    contractor_left,
                    expense_comment,
                    Decimal("0"),
                    expense,
                )
            )
        else:
            rows.append(
                _build_row(
                    row_date,
                    executor,
                    account,
                    source,
                    source_path,
                    ws.title,
                    row_idx,
                    customer_left,
                    customer_right,
                    contractor_left,
                    contractor_right,
                    expense_comment,
                    Decimal("0"),
                    Decimal("0"),
                )
            )

    return rows



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


class _CalamineWorksheetAdapter:
    def __init__(self, title: str, sheet: Any) -> None:
        self.title = title
        self._sheet = sheet

    def iter_rows(self, values_only: bool = True) -> Any:
        return self._sheet.iter_rows()


def _collect_rows_from_openpyxl_workbook(
    target_path: str,
    source_path: Path,
    target_date: Optional[date],
    issues_sink: Optional[List[str]] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    wb_source = None
    try:
        wb_source = openpyxl.load_workbook(target_path, read_only=True, data_only=True)
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
                        source_path,
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
        if wb_source is not None:
            wb_source.close()


def _collect_rows_from_calamine_workbook(
    target_path: str,
    source_path: Path,
    target_date: Optional[date],
    issues_sink: Optional[List[str]] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> List[Dict[str, Any]]:
    wb_source = None
    try:
        wb_source = CalamineWorkbook.from_path(target_path)
        rows: List[Dict[str, Any]] = []
        for sheet_name in wb_source.sheet_names:
            if sheet_name.startswith("_"):
                continue
            if not _is_rsch_sheet_title(sheet_name):
                continue
            try:
                sheet = wb_source.get_sheet_by_name(sheet_name)
                rows.extend(
                    _collect_rows_from_sheet(
                        _CalamineWorksheetAdapter(sheet_name, sheet),
                        target_date,
                        source_path.name,
                        source_path,
                        start_date=start_date,
                        end_date=end_date,
                    )
                )
            except Exception as e:
                issue = f"Лист '{sheet_name}' в файле '{source_path.name}' пропущен: {e}"
                logger.warning(issue)
                if issues_sink is not None:
                    issues_sink.append(issue)
        return rows
    finally:
        # Guard: if CalamineWorkbook.from_path raised before assignment,
        # `wb_source` is still None — calling .close() here would raise
        # UnboundLocalError and mask the original cause.
        if wb_source is not None:
            wb_source.close()


def _collect_rows_from_workbook(
    source_path: Path,
    target_date: Optional[date],
    issues_sink: Optional[List[str]] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    drive_letters: tuple[str, ...] = ("Q", "Z"),
) -> List[Dict[str, Any]]:
    target_path, temp_file = get_local_copy(str(source_path), drive_letters)
    try:
        try:
            return _collect_rows_from_calamine_workbook(
                target_path,
                source_path,
                target_date,
                issues_sink=issues_sink,
                start_date=start_date,
                end_date=end_date,
            )
        except Exception as e:
            logger.warning(
                "Calamine failed for RSC source '%s', falling back to openpyxl: %s",
                source_path,
                e,
            )
            return _collect_rows_from_openpyxl_workbook(
                target_path,
                source_path,
                target_date,
                issues_sink=issues_sink,
                start_date=start_date,
                end_date=end_date,
            )
    finally:
        if temp_file:
            Path(temp_file).unlink(missing_ok=True)


