from __future__ import annotations
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, PatternFill
from openpyxl.comments import Comment
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from core.infra.excel_hyperlinks import apply_cell_hyperlink
from core.infra.excel_backup import backup_existing_excel_output
from core.infra.utils import atomic_save_workbook
from ._types import RschReconciliationRow, ReconciliationRow
from ._utils import (
    _COMBINED_SHEET_PRIORITY,
    _is_numeric_header,
    _is_percent_header,
    _normalize_text,
    _HEADER_FILL,
    _HEADER_FONT,
    _THIN_BORDER,
    _STATUS_OK_FILL,
    _STATUS_REVIEW_FILL,
    _STATUS_ERROR_FILL,
    _STATUS_FONT,
    _MASTER_EXPENSE_FILL,
    STATUS_VERIFIED,
    STATUS_REVIEW,
    REASON_HEADER,
    STATUS_HEADER,
    REASON_NO_CURATOR,
    RSCH_HEADERS,
    _SUMMARY_REASON_LABELS,
)
from ._resolve import (
    _resolve_target_date,
    _resolve_combined_target_date,
    _find_sheet,
    _local_read_path,
)
from ._collect import (
    _collect_master_rows,
    _collect_rsch_rows,
    _master_values,
    _rsch_values,
    _build_reconciliation_rows,
    _suppress_rsch_rows_matched_by_excluded_master_filters,
    _cooccurrence_upgrade,
)


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


def _update_column_widths(widths: dict[int, int], values: list[Any]) -> None:
    for col_idx, value in enumerate(values, start=1):
        widths[col_idx] = max(
            widths.get(col_idx, 0),
            len(str(value)) if value is not None else 0,
        )


def _apply_column_widths(ws: Worksheet, widths: dict[int, int]) -> None:
    wide_text_headers = ("заказчик", "исполнитель", "контрагент", "комментар", "источник")
    compact_min_widths = {
        "статус": 14,
        "причина": 18,
    }
    for col_idx in range(1, ws.max_column + 1):
        header = _normalize_text(ws.cell(1, col_idx).value)
        max_len = widths.get(col_idx, 0)
        min_width = 18 if _is_numeric_header(header) else 10
        for key, width in compact_min_widths.items():
            if key in header:
                min_width = max(min_width, width)
        max_width = 70 if any(key in header for key in wide_text_headers) else 45
        ws.column_dimensions[get_column_letter(col_idx)].width = max(
            min_width,
            min(max_width, max_len + 2),
        )


def _append_reconciliation_row(
    ws: Worksheet,
    row: ReconciliationRow,
    master_headers: list[str],
    column_widths: dict[int, int] | None = None,
) -> None:
    headers = [*master_headers, STATUS_HEADER, *RSCH_HEADERS, REASON_HEADER]
    status_col = len(master_headers) + 1
    reason = _reason_label(row.reason) if row.reason else None
    values = [
        *_master_values(row, master_headers),
        row.status,
        *_rsch_values(row.rsch),
        reason,
    ]
    if column_widths is not None:
        _update_column_widths(column_widths, values)
    ws.append(values)
    row_idx = ws.max_row
    is_even = row_idx % 2 == 0
    row_fill = (
        PatternFill("solid", fgColor="FFF2F2F2")
        if is_even
        else PatternFill("solid", fgColor="FFFFFFFF")
    )
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
        if col_idx != status_col:
            cell.fill = row_fill
    status_cell = ws.cell(row_idx, status_col)
    status_cell.fill = {
        STATUS_VERIFIED: _STATUS_OK_FILL,
        STATUS_REVIEW: _STATUS_REVIEW_FILL,
    }.get(row.status, _STATUS_ERROR_FILL)
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


def _build_workbook(
    target_date: date,
    rows: Iterable[ReconciliationRow],
    master_headers: list[str],
) -> Workbook:
    wb = Workbook()
    ws = wb.active
    assert ws is not None  # a fresh Workbook always has an active sheet
    ws.title = target_date.strftime("%d.%m.%Y")
    _write_reconciliation_sheet(ws, rows, master_headers)
    return wb


def _reconciliation_sort_key(row: ReconciliationRow) -> tuple[int, str, str, str]:
    status_order = {STATUS_VERIFIED: 0, STATUS_REVIEW: 1}
    source = ""
    customer = ""
    executor = ""
    if row.master is not None:
        source = _normalize_text(row.master.source)
        customer = _normalize_text(row.master.customer)
        executor = _normalize_text(row.master.executor)
    elif row.rsch is not None:
        source = _normalize_text(row.rsch.executor)
        customer = _normalize_text(row.rsch.customer)
        executor = _normalize_text(row.rsch.executor)
    return (status_order.get(row.status, 2), source, customer, executor)


def _write_reconciliation_sheet(
    ws: Worksheet,
    rows: Iterable[ReconciliationRow],
    master_headers: list[str],
) -> None:
    row_list = sorted(rows, key=_reconciliation_sort_key)
    headers = [*master_headers, STATUS_HEADER, *RSCH_HEADERS, REASON_HEADER]
    _write_headers(ws, headers)

    column_widths: dict[int, int] = {}
    _update_column_widths(column_widths, headers)
    for row in row_list:
        _append_reconciliation_row(ws, row, master_headers, column_widths)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{ws.max_row}"
    _apply_column_widths(ws, column_widths)


def _build_reconciliation_sheet_data(
    master_wb: Workbook,
    rsch_wb: Workbook,
    target_date: date | None,
    alias_repo: Optional[Any] = None,
) -> tuple[date, list[str], list[ReconciliationRow]]:
    effective_date = _resolve_target_date(master_wb, rsch_wb, target_date)
    master_ws = _find_sheet(master_wb, effective_date)
    rsch_ws = _find_sheet(rsch_wb, effective_date)
    master_headers, master_rows, excluded_master_rows = _collect_master_rows(master_ws)
    rsch_rows = _suppress_rsch_rows_matched_by_excluded_master_filters(
        _collect_rsch_rows(rsch_ws),
        excluded_master_rows,
    )
    rows = _build_reconciliation_rows(master_rows, rsch_rows, alias_repo=alias_repo)
    rows = _cooccurrence_upgrade(rows)
    return effective_date, master_headers, rows


def _matched_rsch_row_ids(rows: Iterable[ReconciliationRow]) -> set[str]:
    return {
        row.rsch.row_id
        for row in rows
        if row.status in {STATUS_VERIFIED, STATUS_REVIEW}
        and row.master is not None
        and row.rsch is not None
    }


def _is_rsch_only_no_curator_row(row: ReconciliationRow) -> bool:
    return row.master is None and row.rsch is not None and row.reason == REASON_NO_CURATOR


def _build_curator_routing(sheet_names: Iterable[str]) -> dict[str, str]:
    routing: dict[str, str] = {}
    for name in sheet_names:
        norm = _normalize_text(name)
        if norm and norm not in ("общий", "general", "all"):
            routing[norm] = name
    return routing


def _infer_rsch_row_owner(
    rsch_row: RschReconciliationRow,
    curator_routing: dict[str, str],
) -> str | None:
    comment_norm = _normalize_text(rsch_row.comment or "")
    if not comment_norm:
        return None
    for key, sheet in curator_routing.items():
        if key in comment_norm:
            return sheet
    return None


def _suppress_combined_rsch_only_rows(
    rows: Iterable[ReconciliationRow],
    matched_rsch_ids: set[str],
    seen_unmatched_rsch_ids: set[str],
    current_sheet: str,
    rsch_only_owners: dict[str, str],
) -> list[ReconciliationRow]:
    filtered = []
    for row in rows:
        if not _is_rsch_only_no_curator_row(row):
            filtered.append(row)
            continue
        assert row.rsch is not None
        row_id = row.rsch.row_id
        if row_id in matched_rsch_ids or row_id in seen_unmatched_rsch_ids:
            continue
        owner = rsch_only_owners.get(row_id)
        if owner is not None and owner != current_sheet:
            continue
        seen_unmatched_rsch_ids.add(row_id)
        filtered.append(row)
    return filtered


def _ordered_combined_master_items(
    master_paths: Mapping[str, Path | str],
) -> list[tuple[str, Path | str]]:
    original_order = {name: idx for idx, name in enumerate(master_paths)}
    return sorted(
        master_paths.items(),
        key=lambda item: (
            _COMBINED_SHEET_PRIORITY.get(item[0], len(_COMBINED_SHEET_PRIORITY)),
            original_order[item[0]],
        ),
    )


def build_reconciliation_report(
    master_path: Path | str,
    rsch_path: Path | str,
    output_path: Path | str,
    *,
    target_date: date | None = None,
    drive_letters: tuple[str, ...] = ("Q", "Z"),
    alias_repo: Optional[Any] = None,
) -> int:
    master_path = Path(master_path)
    rsch_path = Path(rsch_path)
    output_path = Path(output_path)

    if not master_path.exists():
        raise FileNotFoundError(f"Не найден мастер-отчет: {master_path}")
    if not rsch_path.exists():
        raise FileNotFoundError(f"Не найден РСЧ-отчет: {rsch_path}")

    with (
        _local_read_path(master_path, drive_letters) as master_read_path,
        _local_read_path(rsch_path, drive_letters) as rsch_read_path,
    ):
        master_wb = None
        rsch_wb = None
        wb_out = None
        try:
            master_wb = load_workbook(master_read_path, data_only=True)
            rsch_wb = load_workbook(rsch_read_path, data_only=True)
            effective_date, master_headers, rows = _build_reconciliation_sheet_data(
                master_wb,
                rsch_wb,
                target_date,
                alias_repo=alias_repo,
            )
            wb_out = _build_workbook(effective_date, rows, master_headers)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            backup_existing_excel_output(output_path)
            atomic_save_workbook(wb_out, output_path)
            return len(rows)
        finally:
            if master_wb is not None:
                master_wb.close()
            if rsch_wb is not None:
                rsch_wb.close()
            if wb_out is not None:
                wb_out.close()


def build_combined_reconciliation_report(
    master_paths: Mapping[str, Path | str],
    rsch_path: Path | str,
    output_path: Path | str,
    *,
    target_date: date | None = None,
    drive_letters: tuple[str, ...] = ("Q", "Z"),
    alias_repo: Optional[Any] = None,
) -> dict[str, int]:
    rsch_path = Path(rsch_path)
    output_path = Path(output_path)
    if not master_paths:
        raise ValueError("Не выбраны мастер-отчеты для сверки")
    if not rsch_path.exists():
        raise FileNotFoundError(f"Не найден РСЧ-отчет: {rsch_path}")

    ordered_master_paths = _ordered_combined_master_items(master_paths)
    with _local_read_path(rsch_path, drive_letters) as rsch_read_path:
        rsch_wb = None
        wb_out = None
        try:
            wb_out = Workbook()
            default_ws = wb_out.active
            counts: dict[str, int] = {}
            sheet_rows: list[tuple[str, list[str], list[ReconciliationRow]]] = []
            rsch_wb = load_workbook(rsch_read_path, data_only=True)
            effective_target_date = _resolve_combined_target_date(
                ordered_master_paths,
                rsch_wb,
                target_date,
                drive_letters,
            )
            for sheet_name, master_path_value in ordered_master_paths:
                master_path = Path(master_path_value)
                if not master_path.exists():
                    raise FileNotFoundError(f"Не найден мастер-отчет {sheet_name}: {master_path}")
                with _local_read_path(master_path, drive_letters) as master_read_path:
                    master_wb = None
                    try:
                        master_wb = load_workbook(master_read_path, data_only=True)
                        (
                            _effective_date,
                            master_headers,
                            rows,
                        ) = _build_reconciliation_sheet_data(
                            master_wb,
                            rsch_wb,
                            effective_target_date,
                            alias_repo=alias_repo,
                        )
                    finally:
                        if master_wb is not None:
                            master_wb.close()
                sheet_rows.append((sheet_name, master_headers, rows))

            # Global co-occurrence upgrade across ALL sheets
            all_rows_flat: list[ReconciliationRow] = []
            for _sheet_name, _master_headers, _rows in sheet_rows:
                all_rows_flat.extend(_rows)
            upgraded_rows = _cooccurrence_upgrade(all_rows_flat)

            # Re-split upgraded rows back into sheets
            idx = 0
            new_sheet_rows: list[tuple[str, list[str], list[ReconciliationRow]]] = []
            for _sheet_name, _master_headers, _rows in sheet_rows:
                new_sheet_rows.append(
                    (
                        _sheet_name,
                        _master_headers,
                        upgraded_rows[idx : idx + len(_rows)],
                    )
                )
                idx += len(_rows)
            sheet_rows = new_sheet_rows

            matched_rsch_ids = {
                row_id
                for _sheet_name, _master_headers, rows in sheet_rows
                for row_id in _matched_rsch_row_ids(rows)
            }
            rsch_only_owners: dict[str, str] = {}
            curator_routing = _build_curator_routing(master_paths.keys())
            if curator_routing:
                for _sheet_name, _master_headers, rows in sheet_rows:
                    for row in rows:
                        if _is_rsch_only_no_curator_row(row) and row.rsch is not None:
                            owner = _infer_rsch_row_owner(row.rsch, curator_routing)
                            if owner:
                                rsch_only_owners[row.rsch.row_id] = owner
            seen_unmatched_rsch_ids: set[str] = set()
            for idx, (sheet_name, master_headers, rows) in enumerate(sheet_rows):
                rows = _suppress_combined_rsch_only_rows(
                    rows,
                    matched_rsch_ids,
                    seen_unmatched_rsch_ids,
                    sheet_name,
                    rsch_only_owners,
                )
                rows = sorted(rows, key=_reconciliation_sort_key)

                ws = default_ws if idx == 0 else wb_out.create_sheet()
                assert ws is not None  # active sheet / create_sheet always yield a sheet
                # Excel sheet names limited to 31 chars; deduplicate if truncated name collides
                truncated = sheet_name[:31]
                if truncated in wb_out.sheetnames:
                    n = 2
                    while True:
                        alt = f"{truncated[:28]}({n})"
                        if alt not in wb_out.sheetnames:
                            truncated = alt
                            break
                        n += 1
                ws.title = truncated
                _write_reconciliation_sheet(ws, rows, master_headers)
                counts[sheet_name] = len(rows)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            backup_existing_excel_output(output_path)
            atomic_save_workbook(wb_out, output_path)
            return counts
        finally:
            if rsch_wb is not None:
                rsch_wb.close()
            if wb_out is not None:
                wb_out.close()
