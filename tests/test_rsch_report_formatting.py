from datetime import datetime
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from core.infra.rsch_report_formatting import (
    apply_amount_highlighting,
    apply_warning_row_highlighting,
    autosize_all_columns,
    copy_style,
    create_builtin_template_workbook,
    ensure_total_row_style,
    find_total_row,
    normalize_legacy_data_row,
    prepare_output_sheet,
)


HEADERS = [
    "ИСПОЛНИТЕЛЬ",
    "ЗАКАЗЧИК",
    "Контрагент",
    "Комментарий",
    "Приход",
    "Расход",
    "р/с",
    "Источник",
]


def _modern_template():
    wb = Workbook()
    ws = wb.active
    ws.title = "13.04"
    ws.append(HEADERS)
    ws.append(["СТИ", "МРВ", "ООО", "Комм", 100, 50, "4070", "src"])
    ws.append(["ИТОГО:", None, None, None, "=SUM(E2:E2)", "=SUM(F2:F2)", None, None])
    ws.freeze_panes = "A2"
    ws.sheet_view.zoomScale = 85
    ws.sheet_view.showGridLines = False
    ws.sheet_format.defaultRowHeight = 22
    ws.row_dimensions[1].height = 33
    for col_idx in range(1, 9):
        cell = ws.cell(1, col_idx)
        cell.fill = PatternFill(fill_type="solid", fgColor="FF7030A0")
        cell.font = Font(color="FFFFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[cell.column_letter].width = 9 + col_idx
    ws["E2"].number_format = "#,##0.0000"
    ws["F2"].number_format = "#,##0.0000"
    ws["E3"].number_format = "0.0"
    ws["F3"].number_format = "0.0"
    return ws


def _legacy_template():
    wb = Workbook()
    ws = wb.active
    ws.title = "13.04"
    ws.append(["Дата", "Контрагент", "ЗАКАЗЧИК", "ИСПОЛНИТЕЛЬ", "Приход", "Расход", "р/с"])
    ws.append([datetime(2026, 4, 13), "ООО", "МРВ", "СТИ", 100, 50, "4070"])
    ws.append(["ИТОГО:", None, None, None, "=SUM(E2:E2)", "=SUM(F2:F2)", None])
    ws["E2"].number_format = "#,##0.00"
    ws["F2"].number_format = "#,##0.00"
    ws["E3"].number_format = "0.0"
    ws["F3"].number_format = "0.0"
    return ws


def test_find_total_row_handles_text_variants_and_missing() -> None:
    ws = _modern_template()

    assert find_total_row(ws) == 3

    ws.cell(3, 1).value = "Всего"
    assert find_total_row(ws) is None


def test_copy_style_copies_visual_cell_attributes() -> None:
    wb = Workbook()
    ws = wb.active
    src = ws["A1"]
    dst = ws["B1"]
    src.font = Font(color="FFFF0000", bold=True)
    src.fill = PatternFill(fill_type="solid", fgColor="FF00FF00")
    src.alignment = Alignment(horizontal="right")
    src.number_format = "#,##0.00"

    copy_style(src, dst)

    assert dst.font.color.rgb == "FFFF0000"
    assert dst.font.bold is True
    assert dst.fill.fgColor.rgb == "FF00FF00"
    assert dst.alignment.horizontal == "right"
    assert dst.number_format == "#,##0.00"


def test_prepare_output_sheet_preserves_modern_template_layout() -> None:
    template = _modern_template()

    wb, ws, layout = prepare_output_sheet(template, "13.04", HEADERS, HEADERS)

    assert wb.active is ws
    assert ws.title == "13.04"
    assert [ws.cell(1, col).value for col in range(1, 9)] == HEADERS
    assert ws.freeze_panes == "A2"
    assert ws.sheet_view.zoomScale == 85
    assert ws.sheet_view.showGridLines is False
    assert ws.row_dimensions[1].height == 33
    assert ws.column_dimensions["E"].width == template.column_dimensions["E"].width
    assert layout["legacy_template"] is False
    assert layout["detail_amount_formats"] == {5: "#,##0.0000", 6: "#,##0.0000"}
    assert layout["total_amount_formats"] == {5: "0.0", 6: "0.0"}


def test_prepare_output_sheet_normalizes_legacy_template_styles() -> None:
    template = _legacy_template()

    _, ws, layout = prepare_output_sheet(template, "13.04", HEADERS, HEADERS)

    assert layout["legacy_template"] is True
    assert ws.cell(1, 1).fill.fgColor.rgb == "FF1F4E79"
    assert ws.cell(1, 1).font.color.rgb == "FFFFFFFF"
    assert ws.cell(1, 1).alignment.wrap_text is True
    assert layout["data_cols"][3] == 2
    assert layout["data_cols"][5] == 5
    assert layout["data_cols"][6] == 6


def test_legacy_row_total_autosize_and_highlighting_helpers() -> None:
    template = _legacy_template()
    _, ws, layout = prepare_output_sheet(template, "13.04", HEADERS, HEADERS)
    ws.append(["СТИ", "МРВ", "ООО", "Комментарий", 100, 50, "4070", "src"])
    ws.append(["ИТОГО:", None, None, None, "=SUM(E2:E2)", "=SUM(F2:F2)", None, None])

    normalize_legacy_data_row(ws, 2, layout["detail_amount_formats"])
    apply_amount_highlighting(ws, 2, Decimal("100"), Decimal("50"))
    apply_warning_row_highlighting(ws, 2, 9)
    ensure_total_row_style(ws, 3, layout["total_amount_formats"], force_normalize=True)
    autosize_all_columns(ws)

    assert ws.cell(2, 4).number_format == "General"
    assert ws.cell(2, 5).number_format == "#,##0.00"
    assert ws.cell(2, 6).number_format == "#,##0.00"
    assert ws.cell(2, 7).number_format == "General"
    assert ws.cell(2, 1).fill.fgColor.rgb == "FFFFFF00"
    assert ws.cell(3, 1).fill.fgColor.rgb == "FFD9E1F2"
    assert ws.cell(3, 5).number_format == "0.0"
    assert ws.column_dimensions["E"].width >= 14


def test_total_row_style_is_noop_for_modern_template() -> None:
    ws = _modern_template()
    original_fill = ws.cell(3, 1).fill.fgColor.rgb

    ensure_total_row_style(ws, 3, {5: "0.0", 6: "0.0"}, force_normalize=False)

    assert ws.cell(3, 1).fill.fgColor.rgb == original_fill


def test_create_builtin_template_workbook_has_dynamic_totals_and_styles() -> None:
    wb = create_builtin_template_workbook(HEADERS)
    ws = wb.active

    assert ws.title == "РСЧ"
    assert [ws.cell(1, col).value for col in range(1, 9)] == HEADERS
    assert ws.freeze_panes == "A2"
    assert ws["E3"].value == "=SUM(E2:E2)"
    assert ws["F3"].value == "=SUM(F2:F2)"
    assert ws["E2"].number_format == "#,##0.00"
    assert ws["A2"].number_format == "General"
    assert ws["A1"].fill.fgColor.rgb == "FF1F4E79"
    assert ws["A3"].fill.fgColor.rgb == "FFD9E1F2"
