
from __future__ import annotations

import logging
from copy import copy
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import openpyxl
from openpyxl import Workbook
from openpyxl.cell.cell import Cell, MergedCell
from openpyxl.styles import Alignment, Border, Font, PatternFill, Protection, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from core.infra.excel_hyperlinks import apply_cell_hyperlink
from core.infra.excel_backup import backup_existing_excel_output
from core.infra.utils import atomic_save_workbook

from ._format import _display_len, _excel_safe_text, _is_problem_row
from ._collect import _collect_rows_from_workbook, _copy_style, _normalize_source_paths
from ._template import _create_builtin_template_workbook, _find_total_row, _resolve_template_style_layout

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

RSCH_TABLE_HEADERS = [
    "Дата",
    "ИСПОЛНИТЕЛЬ",
    "ЗАКАЗЧИК",
    "Контрагент",
    "Комментарий",
    "Приход",
    "Расход",
    "р/с",
    "Источник",
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
    "% по выплате",
    "комиссия",
    "налог",
    "взносы",
)
_NO_ACCOUNT_MARKERS = (
    "факторинг",
    "факторнинг",
    "вф",
    "вафт фокс",
    "гетворк",
)


# Snapshot of a cell's six style attributes, captured once as plain (hashable)
# openpyxl style objects. ``src_cell.font`` returns a ``StyleProxy`` that is
# *unhashable*, so it cannot be assigned to another cell directly — but it can
# be ``copy()``-ed once into a regular Font/Fill/... object, which openpyxl's
# ``Styleable.__set__`` then deduplicates through its ``IndexedList``. Taking
# the snapshot once per template column and reusing it for every data row is
# what makes this ~2x faster than calling ``_copy_style`` per cell (which
# re-copies the same StyleProxy thousands of times, producing identical
# objects that immediately get deduplicated anyway).
_StyleSnapshot = Tuple[
    "Font",
    "PatternFill",
    "Border",
    "Alignment",
    str,  # number_format
    "Protection",
]


def _snapshot_style(src_cell: Any) -> _StyleSnapshot:
    """Capture a cell's style into hashable, reusable objects (one-time copy)."""
    return (
        copy(src_cell.font),
        copy(src_cell.fill),
        copy(src_cell.border),
        copy(src_cell.alignment),
        src_cell.number_format,
        copy(src_cell.protection),
    )


def _apply_style_snapshot(dst_cell: Any, snapshot: _StyleSnapshot) -> None:
    """Apply a previously captured style snapshot to a cell (no per-call copy)."""
    font, fill, border, align, number_format, protection = snapshot
    dst_cell.font = font
    dst_cell.fill = fill
    dst_cell.border = border
    dst_cell.alignment = align
    dst_cell.number_format = number_format
    dst_cell.protection = protection


def _ensure_header_style(ws: Worksheet, force_normalize: bool, is_table: bool = False) -> None:
    if not force_normalize:
        return
    headers = RSCH_TABLE_HEADERS if is_table else RSCH_HEADERS
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(1, col_idx)
        cell.fill = copy(_HEADER_FILL)
        cell.font = copy(_HEADER_FONT)
        cell.alignment = copy(_HEADER_ALIGNMENT)
        cell.border = copy(_THIN_BORDER)


def _ensure_comment_cell_style(cell: Cell | MergedCell) -> None:
    cell.number_format = "General"
    cell.alignment = copy(_TEXT_ALIGNMENT)
    cell.border = copy(_THIN_BORDER)


def _ensure_account_cell_style(cell: Cell | MergedCell) -> None:
    cell.number_format = "General"
    cell.alignment = copy(_ACCOUNT_ALIGNMENT)
    cell.border = copy(_THIN_BORDER)


def _ensure_amount_cell_style(cell: Cell | MergedCell, number_format: str) -> None:
    cell.number_format = number_format
    cell.alignment = copy(_AMOUNT_ALIGNMENT)
    cell.border = copy(_THIN_BORDER)


def _ensure_date_cell_style(cell: Cell | MergedCell) -> None:
    cell.alignment = copy(_DATE_ALIGNMENT)
    cell.border = copy(_THIN_BORDER)


def _normalize_legacy_data_row(
    ws_out: Worksheet, row_idx: int, amount_formats: Dict[int, str], is_table: bool = False
) -> None:
    if is_table:
        _ensure_date_cell_style(ws_out.cell(row_idx, 1))
        _ensure_comment_cell_style(ws_out.cell(row_idx, 5))
        _ensure_amount_cell_style(ws_out.cell(row_idx, 6), amount_formats[6])
        _ensure_amount_cell_style(ws_out.cell(row_idx, 7), amount_formats[7])
        _ensure_account_cell_style(ws_out.cell(row_idx, 8))
        _ensure_comment_cell_style(ws_out.cell(row_idx, 9))
    else:
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
    is_table: bool = False,
) -> None:
    if not force_normalize:
        return

    headers = RSCH_TABLE_HEADERS if is_table else RSCH_HEADERS
    income_col = 6 if is_table else 5
    expense_col = 7 if is_table else 6

    label = ws_out.cell(row_idx, 1)
    label.fill = copy(_TOTAL_FILL)
    label.font = Font(bold=True)
    label.border = copy(_TOTAL_BORDER)

    non_amount_cols = [c for c in range(2, len(headers) + 1) if c not in (income_col, expense_col)]
    for col_idx in non_amount_cols:
        cell = ws_out.cell(row_idx, col_idx)
        cell.fill = copy(_TOTAL_FILL)
        cell.font = Font(bold=True)
        cell.border = copy(_TOTAL_BORDER)
        cell.number_format = "General"

    for col_idx in (income_col, expense_col):
        cell = ws_out.cell(row_idx, col_idx)
        cell.fill = copy(_TOTAL_FILL)
        cell.font = Font(bold=True)
        cell.border = copy(_TOTAL_BORDER)
        cell.number_format = amount_formats[col_idx]
        cell.alignment = copy(_AMOUNT_ALIGNMENT)

def _update_column_widths(widths: dict[int, int], values: list[Any]) -> None:
    for col_idx, value in enumerate(values, start=1):
        widths[col_idx] = max(widths.get(col_idx, 0), _display_len(value))


def _apply_column_widths(
    ws_out: Worksheet,
    widths: dict[int, int],
    min_width: int = 10,
    max_width: int = 60,
) -> None:
    for col_idx in range(1, ws_out.max_column + 1):
        max_len = widths.get(col_idx, 0)
        if col_idx in (5, 6):
            max_len = max(max_len, 14)

        ws_out.column_dimensions[get_column_letter(col_idx)].width = max(
            min_width,
            min(max_width, max_len + 2),
        )


def _apply_amount_highlighting(
    ws_out: Worksheet,
    row_idx: int,
    income: Decimal,
    expense: Decimal,
    is_table: bool = False,
) -> None:
    income_col = 6 if is_table else 5
    expense_col = 7 if is_table else 6
    income_cell = ws_out.cell(row_idx, income_col)
    expense_cell = ws_out.cell(row_idx, expense_col)

    if income != 0:
        income_cell.fill = _INCOME_FILL
        income_cell.font = copy(_INCOME_FONT)

    if expense != 0:
        expense_cell.fill = _EXPENSE_FILL
        expense_cell.font = copy(_EXPENSE_FONT)


def _apply_warning_row_highlighting(ws_out: Worksheet, row_idx: int, is_table: bool = False) -> None:
    headers = RSCH_TABLE_HEADERS if is_table else RSCH_HEADERS
    for col_idx in range(1, len(headers) + 1):
        ws_out.cell(row_idx, col_idx).fill = copy(_WARNING_FILL)



def _write_rsch_sheet(
    wb_out: Workbook,
    template_ws: Worksheet,
    sheet_name: str,
    rows: List[Dict[str, Any]],
    *,
    first_sheet: bool,
    is_table: bool = False,
) -> None:
    ws_out = wb_out.active if first_sheet else wb_out.create_sheet()
    assert ws_out is not None  # active sheet exists / create_sheet returns one
    ws_out.title = sheet_name

    style_layout = _resolve_template_style_layout(template_ws, is_table)
    headers = RSCH_TABLE_HEADERS if is_table else RSCH_HEADERS
    ws_out.append(headers)
    column_widths: dict[int, int] = {}
    _update_column_widths(column_widths, headers)

    for col_idx, _ in enumerate(headers, start=1):
        header_source = template_ws.cell(1, style_layout["header_cols"][col_idx])
        _copy_style(header_source, ws_out.cell(1, col_idx))
        col = get_column_letter(col_idx)
        width_source_col = get_column_letter(style_layout["width_cols"][col_idx])
        src_dim = template_ws.column_dimensions.get(width_source_col)
        if src_dim and src_dim.width:
            ws_out.column_dimensions[col].width = src_dim.width

    ws_out.freeze_panes = template_ws.freeze_panes
    ws_out.sheet_view.zoomScale = template_ws.sheet_view.zoomScale
    ws_out.sheet_view.showGridLines = template_ws.sheet_view.showGridLines
    ws_out.sheet_format.defaultRowHeight = template_ws.sheet_format.defaultRowHeight
    header_height = template_ws.row_dimensions[1].height
    if header_height:
        ws_out.row_dimensions[1].height = header_height

    _ensure_header_style(ws_out, style_layout["legacy_template"], is_table)

    template_data_row_idx = 2 if template_ws.max_row >= 2 else 1
    # Capture each column's style ONCE as plain hashable objects. Previously
    # this held live template cells and the loop below called ``_copy_style``
    # per cell, re-copying the same ``StyleProxy`` ~rows×cols times. Each copy
    # was byte-identical to the others (same source cell), so openpyxl's
    # ``IndexedList`` deduplicated them anyway — the work was pure waste on
    # large period reports (~2-4 s on a 6-day period). Snapshotting once and
    # reusing is ~2x faster with byte-identical output (verified on customer
    # files: styles.xml + sheetN.xml match exactly).
    data_style_snapshots: Dict[int, _StyleSnapshot] = {
        col_idx: _snapshot_style(
            template_ws.cell(template_data_row_idx, style_layout["data_cols"][col_idx])
        )
        for col_idx in range(1, len(headers) + 1)
    }

    income_col = 6 if is_table else 5
    expense_col = 7 if is_table else 6
    hyperlink_source_col = 9 if is_table else 8

    for row in rows:
        if is_table:
            values = [
                row["date"],
                _excel_safe_text(row["executor"]),
                _excel_safe_text(row["customer"]),
                _excel_safe_text(row["contractor"]),
                _excel_safe_text(row["comment"]),
                row["income"],
                row["expense"],
                _excel_safe_text(row["account"]),
                _excel_safe_text(row["source"]),
            ]
        else:
            values = [
                _excel_safe_text(row["executor"]),
                _excel_safe_text(row["customer"]),
                _excel_safe_text(row["contractor"]),
                _excel_safe_text(row["comment"]),
                row["income"],
                row["expense"],
                _excel_safe_text(row["account"]),
                _excel_safe_text(row["source"]),
            ]
        _update_column_widths(column_widths, values)
        ws_out.append(values)
        curr_idx = ws_out.max_row
        for col_idx in range(1, len(headers) + 1):
            _apply_style_snapshot(
                ws_out.cell(curr_idx, col_idx),
                data_style_snapshots[col_idx],
            )

        if is_table:
            ws_out.cell(curr_idx, 1).number_format = "dd.mm.yyyy"
            ws_out.cell(curr_idx, 1).alignment = copy(_DATE_ALIGNMENT)

        if style_layout["legacy_template"]:
            _normalize_legacy_data_row(
                ws_out, curr_idx, style_layout["detail_amount_formats"], is_table
            )
        if _is_problem_row(row):
            _apply_warning_row_highlighting(ws_out, curr_idx, is_table)
        _apply_amount_highlighting(ws_out, curr_idx, row["income"], row["expense"], is_table)
        apply_cell_hyperlink(
            ws_out.cell(curr_idx, hyperlink_source_col),
            row.get("source_path"),
            row.get("source_sheet"),
            row.get("source_row"),
        )

    _apply_column_widths(ws_out, column_widths)

    total_row_idx = ws_out.max_row + 1
    ws_out.cell(total_row_idx, 1, "ИТОГО:")

    income_letter = get_column_letter(income_col)
    expense_letter = get_column_letter(expense_col)

    if total_row_idx > 2:
        ws_out.cell(total_row_idx, income_col, f"=SUM({income_letter}2:{income_letter}{total_row_idx - 1})")
        ws_out.cell(total_row_idx, expense_col, f"=SUM({expense_letter}2:{expense_letter}{total_row_idx - 1})")
    else:
        ws_out.cell(total_row_idx, income_col, Decimal("0"))
        ws_out.cell(total_row_idx, expense_col, Decimal("0"))

    template_total_row_idx = _find_total_row(template_ws)
    if template_total_row_idx:
        for col_idx in range(1, len(headers) + 1):
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
        is_table=is_table,
    )
    ws_out.auto_filter.ref = (
        f"A1:{get_column_letter(len(headers))}{max(1, total_row_idx - 1)}"
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
    drive_letters: tuple[str, ...] = ("Q", "Z"),
    on_progress: Optional[Callable[[float], None]] = None,
    on_current_file: Optional[Callable[[str, int, int], None]] = None,
) -> int:
    source_paths = _normalize_source_paths(source_path)
    output_path = Path(output_path)

    # BUG 5 guard: without a date, the sheet-naming branch below would
    # try `None.strftime(...)` (AttributeError) or silently fall back to
    # the template sheet title. Fail fast with a clear message instead.
    if target_date is None and start_date is None:
        raise ValueError("build_rsch_report: требуется target_date или start_date")

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
    total_sources = len(source_paths)
    try:
        # Сбор строк по источникам — самая тяжёлая (сетевая) часть; именно
        # она отвечает за «грузит грузит». Колбэки двигают статус-бар и
        # показывают текущий файл, чтобы пользователь видел прогресс.
        if on_progress is not None:
            on_progress(0.0)
        for i, src_path in enumerate(source_paths):
            if on_current_file is not None:
                on_current_file(src_path.name, i, total_sources)
            rows.extend(
                _collect_rows_from_workbook(
                    src_path,
                    target_date,
                    issues,
                    start_date=start_date,
                    end_date=end_date,
                    drive_letters=drive_letters,
                )
            )
            # Сбор = ~80% работы (сеть + парсинг); запись листов — остаток.
            if on_progress is not None and total_sources:
                on_progress(((i + 1) / total_sources) * 80.0)
        if on_current_file is not None and total_sources:
            on_current_file("сборка листов", total_sources, total_sources)
        if on_progress is not None:
            on_progress(85.0)

        if issues_sink is not None:
            issues_sink.extend(issues)

        if issues:
            logger.warning(
                "РСЧ: обнаружены проблемы в листах (%s). Сборка продолжена по валидным листам.",
                len(issues),
            )
            if not rows:
                preview = "; ".join(issues[:3])
                if len(issues) > 3:
                    preview += " ..."
                raise RuntimeError(
                    "РСЧ: не удалось собрать строки из выбранных файлов. "
                    f"Проблемы: {preview}"
                )

        if not rows:
            logger.info(
                "RSC report skipped: no rows matched requested date/range (output=%s, sources=%s)",
                output_path,
                len(source_paths),
            )
            return 0

        use_period = start_date is not None and end_date is not None
        wb_out = Workbook()
        try:
            if use_period and rows:
                rows_by_date: Dict[date, List[Dict[str, Any]]] = {}
                for row in rows:
                    rows_by_date.setdefault(row["date"], []).append(row)
                sorted_dates = sorted(rows_by_date)
                # Имена листов всегда с годом (%d.%m.%Y) — совпадает с
                # форматом мастер-отчёта и исключает коллизию при периоде,
                # охватывающем январь двух лет (31.12.2024 + 01.01.2025).
                # Раньше был guard на %d.%m без года + ValueError при конфликте;
                # с годом конфликт невозможен, guard убран.
                for idx, row_date in enumerate(sorted_dates, start=1):
                    _write_rsch_sheet(
                        wb_out,
                        template_ws,
                        row_date.strftime("%d.%m.%Y"),
                        rows_by_date[row_date],
                        first_sheet=idx == 1,
                    )
                # Сводная таблица за весь период на последнем листе
                sorted_all_rows = sorted(rows, key=lambda r: r["date"])
                _write_rsch_sheet(
                    wb_out,
                    template_ws,
                    "Период",
                    sorted_all_rows,
                    first_sheet=False,
                    is_table=True,
                )
            else:
                sheet_date = target_date or start_date
                sheet_name = (
                    sheet_date.strftime("%d.%m.%Y") if sheet_date else template_ws.title
                )
                _write_rsch_sheet(
                    wb_out,
                    template_ws,
                    sheet_name,
                    rows,
                    first_sheet=True,
                )

            output_path.parent.mkdir(parents=True, exist_ok=True)
            backup_existing_excel_output(output_path)
            atomic_save_workbook(wb_out, output_path)
            if on_progress is not None:
                # 95% — финиш (100% выставит completion-хендлер в GUI,
                # чтобы статус-бар не отрисовал 100% до того, как файл
                # реально записан и тост показан).
                on_progress(95.0)
        finally:
            # Guarantee the output workbook handle is released even if
            # writing aborts mid-sheet, otherwise a retry on Windows
            # fails with a locked-file error.
            try:
                wb_out.close()
            except Exception:
                pass

        logger.info(
            "RSC report generated: %s (rows=%s, sources=%s)",
            output_path,
            len(rows),
            len(source_paths),
        )
        return len(rows)
    finally:
        # The template workbook is only needed during the build; close
        # it once the sheets are written so we never leak the handle
        # when an exception aborts the build early.
        try:
            wb_template.close()
        except Exception:
            pass
