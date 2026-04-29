from datetime import date, datetime
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from core.infra.rsch_report import build_rsch_report


_SOURCE_HEADERS = [
    "дата",
    "ост на нач",
    "коммент",
    "проект",
    "контрагент",
    "приход на рсч, су",
    "расход с рсч, су",
    "проект",
    "контрагент",
    "коммент",
    "ост на конец",
    "р/с",
]


def _create_source_book_with_rows(
    path: Path,
    rows: list[list[object]],
    sheet_title: str = "сти рсч",
) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title
    ws.append(["мс"])
    ws.append(_SOURCE_HEADERS)
    for row in rows:
        ws.append(row)
    wb.save(path)


def _cell_fill_rgb(ws, row_idx: int, col_idx: int) -> str:
    return str(ws.cell(row_idx, col_idx).fill.fgColor.rgb or "")


def _assert_warning_fill(ws, row_idx: int, columns: tuple[int, ...]) -> None:
    for col_idx in columns:
        assert "FFFF00" in _cell_fill_rgb(ws, row_idx, col_idx)


def _create_source_book(path: Path) -> None:
    _create_source_book_with_rows(
        path,
        [
            [
                datetime(2026, 4, 13),
                None,
                "Комментарий приход 1",
                "Проект Приход 1",
                "Контрагент Приход 1",
                100,
                0,
                "Проект Расход 1",
                "Контрагент Расход 1",
                "Комментарий расход 1",
                None,
                "40702810",
            ],
            [
                datetime(2026, 4, 13),
                None,
                None,
                "Проект Приход 2",
                "Контрагент Приход 2",
                0,
                200,
                "Проект Расход 2",
                "Контрагент Расход 2",
                "Комментарий расход 2",
                None,
                "40702811",
            ],
            [
                datetime(2026, 4, 13),
                None,
                None,
                "Проект Приход 3",
                "Контрагент Приход 3",
                -30,
                -40,
                "Проект Расход 3",
                "Контрагент Расход 3",
                "Комментарий оба 3",
                None,
                "40702812",
            ],
            [
                datetime(2026, 4, 14),
                None,
                None,
                "Проект Вне Даты",
                "Контрагент Вне Даты",
                999,
                0,
                "",
                "",
                None,
                None,
                "40702813",
            ],
        ],
    )


def _create_template_book(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "13.04"
    ws.append(
        [
            "ИСПОЛНИТЕЛЬ",
            "ЗАКАЗЧИК",
            "Контрагент",
            "Комментарий",
            "Приход",
            "Расход",
            "р/с",
            "Источник",
        ]
    )
    ws.append([datetime(2026, 4, 13), "", "", "", "", 0, 0, "", ""])
    ws.append(
        ["ИТОГО:", None, None, None, None, "=SUM(F2:F2)", "=SUM(G2:G2)", None, None]
    )
    ws["F2"].number_format = "#,##0.00"
    ws["G2"].number_format = "#,##0.00"
    wb.save(path)


def _create_styled_modern_template_book(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "13.04"
    purple = "FF7030A0"
    peach = "FFFCE4D6"

    ws.append(
        [
            "ИСПОЛНИТЕЛЬ",
            "ЗАКАЗЧИК",
            "Контрагент",
            "Комментарий",
            "Приход",
            "Расход",
            "р/с",
            "Источник",
        ]
    )
    ws.append(["", "", "", "", 0, 0, "", ""])
    ws.append(["ИТОГО:", None, None, None, "=SUM(E2:E2)", "=SUM(F2:F2)", None, None])

    for col_idx in range(1, 9):
        cell = ws.cell(1, col_idx)
        cell.fill = PatternFill(fill_type="solid", fgColor=purple)
        cell.font = Font(color="FFFFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for ref in ("A3", "E3", "F3"):
        ws[ref].fill = PatternFill(fill_type="solid", fgColor=peach)
        ws[ref].font = Font(bold=True)

    ws["D2"].alignment = Alignment(horizontal="center", vertical="center")
    ws["G2"].alignment = Alignment(horizontal="center", vertical="center")

    ws["E2"].number_format = "#,##0.0000"
    ws["F2"].number_format = "#,##0.0000"
    ws["E3"].number_format = "0.0"
    ws["F3"].number_format = "0.0"
    ws.freeze_panes = "A2"
    wb.save(path)


def _create_legacy_template_book(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "13.04"

    dark_blue = "FF1F4E79"
    light_blue = "FFD9E1F2"
    green_fill = "FFC6EFCE"
    red_fill = "FFFFC7CE"
    green_font = "FF006100"
    red_font = "FF9C0006"
    white = "FFFFFFFF"
    black = "FF000000"

    thin = Side(style="thin", color=black)
    medium = Side(style="medium", color=black)

    header_font = Font(color=white, bold=True)
    header_fill = PatternFill(fill_type="solid", fgColor=dark_blue)
    header_alignment = Alignment(
        horizontal="center", vertical="center", wrap_text=True
    )
    data_border = Border(left=thin, right=thin, top=thin, bottom=thin)
    total_border = Border(left=medium, right=medium, top=medium, bottom=medium)

    ws.append(
        [
            "Дата",
            "Контрагент",
            "ЗАКАЗЧИК",
            "ИСПОЛНИТЕЛЬ",
            "Приход",
            "Расход",
            "р/с",
        ]
    )
    ws.append(
        [
            datetime(2026, 4, 13),
            'ООО "Манyфактура"',
            "МРВ",
            "СТИ",
            100,
            50,
            "40702810638000239606",
        ]
    )
    ws.append(["ИТОГО:", None, None, None, "=SUM(E2:E2)", "=SUM(F2:F2)", None])

    for col_idx in range(1, 8):
        cell = ws.cell(1, col_idx)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = data_border

    ws["A2"].number_format = "mm-dd-yy"
    ws["A2"].alignment = Alignment(horizontal="left", vertical="center")
    ws["A2"].border = data_border

    ws["B2"].alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
    ws["B2"].border = data_border
    ws["C2"].alignment = Alignment(horizontal="left", vertical="center")
    ws["C2"].border = data_border
    ws["D2"].alignment = Alignment(horizontal="left", vertical="center")
    ws["D2"].border = data_border

    ws["E2"].number_format = "#,##0.00"
    ws["E2"].font = Font(color=green_font, bold=True)
    ws["E2"].fill = PatternFill(fill_type="solid", fgColor=green_fill)
    ws["E2"].alignment = Alignment(horizontal="right", vertical="center")
    ws["E2"].border = data_border

    ws["F2"].number_format = "#,##0.00"
    ws["F2"].font = Font(color=red_font, bold=True)
    ws["F2"].fill = PatternFill(fill_type="solid", fgColor=red_fill)
    ws["F2"].alignment = Alignment(horizontal="right", vertical="center")
    ws["F2"].border = data_border

    ws["G2"].alignment = Alignment(horizontal="left", vertical="center")
    ws["G2"].border = data_border

    ws["A3"].font = Font(bold=True)
    ws["A3"].fill = PatternFill(fill_type="solid", fgColor=light_blue)
    ws["A3"].border = total_border
    ws["E3"].font = Font(bold=True)
    ws["E3"].fill = PatternFill(fill_type="solid", fgColor=light_blue)
    ws["E3"].border = total_border
    ws["E3"].number_format = "#,##0.00"
    ws["F3"].font = Font(bold=True)
    ws["F3"].fill = PatternFill(fill_type="solid", fgColor=light_blue)
    ws["F3"].border = total_border
    ws["F3"].number_format = "#,##0.00"

    ws.freeze_panes = "A2"
    wb.save(path)


def test_build_rsch_report_maps_and_splits_rows(tmp_path: Path) -> None:
    source = tmp_path / "source.xlsx"
    template = tmp_path / "template.xlsx"
    output = tmp_path / "report.xlsx"
    _create_source_book(source)
    _create_template_book(template)

    written = build_rsch_report(
        source,
        output,
        target_date=date(2026, 4, 13),
        template_path=template,
    )

    assert written == 3

    wb = load_workbook(output, data_only=False)
    ws = wb["13.04"]

    assert [ws.cell(1, c).value for c in range(1, 9)] == [
        "ИСПОЛНИТЕЛЬ",
        "ЗАКАЗЧИК",
        "Контрагент",
        "Комментарий",
        "Приход",
        "Расход",
        "р/с",
        "Источник",
    ]

    # income leg from left D/E, expense comment is ignored
    assert ws.cell(2, 1).value == "СТИ"
    assert ws.cell(2, 2).value == "Проект Приход 1"
    assert ws.cell(2, 3).value == "Контрагент Приход 1"
    assert ws.cell(2, 4).value in (None, "")
    assert ws.cell(2, 5).value == 100
    assert ws.cell(2, 6).value == 0
    assert ws.cell(2, 7).value == "40702810"
    assert ws.cell(2, 8).value == "source.xlsx | сти рсч | строка 3"

    # expense leg from right H/I and comment from J
    assert ws.cell(3, 1).value == "СТИ"
    assert ws.cell(3, 2).value == "Проект Расход 2"
    assert ws.cell(3, 3).value == "Контрагент Расход 2"
    assert ws.cell(3, 4).value == "Комментарий расход 2"
    assert ws.cell(3, 5).value == 0
    assert ws.cell(3, 6).value == 200
    assert ws.cell(3, 7).value == "40702811"
    assert ws.cell(3, 8).value == "source.xlsx | сти рсч | строка 4"

    # both-leg row stays as one operation, keeps both signs, and takes comment from J
    assert ws.cell(4, 1).value == "СТИ"
    assert ws.cell(4, 2).value == "Проект Приход 3"
    assert ws.cell(4, 3).value == "Контрагент Приход 3"
    assert ws.cell(4, 4).value == "Комментарий оба 3"
    assert ws.cell(4, 5).value == -30
    assert ws.cell(4, 6).value == -40
    assert ws.cell(4, 7).value == "40702812"
    assert ws.cell(4, 8).value == "source.xlsx | сти рсч | строка 5"

    assert ws.cell(5, 1).value == "ИТОГО:"
    assert ws.cell(5, 5).value == "=SUM(E2:E4)"
    assert ws.cell(5, 6).value == "=SUM(F2:F4)"

    # highlight colors for non-zero amounts
    assert ws.cell(2, 5).fill.fgColor.rgb == "FFC6EFCE"
    assert ws.cell(3, 6).fill.fgColor.rgb == "FFFFC7CE"
    assert ws.cell(4, 5).fill.fgColor.rgb == "FFC6EFCE"
    assert ws.cell(4, 6).fill.fgColor.rgb == "FFFFC7CE"


def test_build_rsch_report_real_fixture_for_13_04(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source = repo_root / "РСЧ" / "рсч для инструкции.xlsx"
    template = repo_root / "РСЧ" / "шаблон отчета.xlsx"
    if not source.exists() or not template.exists():
        pytest.skip("РСЧ fixture files not available")

    output = tmp_path / "rsch_fixture_report.xlsx"
    written = build_rsch_report(
        source,
        output,
        target_date=date(2026, 4, 13),
        template_path=template,
    )

    assert written == 75


def test_build_rsch_report_combines_multiple_sources(tmp_path: Path) -> None:
    source1 = tmp_path / "source1.xlsx"
    source2 = tmp_path / "source2.xlsx"
    template = tmp_path / "template.xlsx"
    output = tmp_path / "report_multi.xlsx"

    _create_source_book(source1)
    _create_source_book(source2)
    _create_template_book(template)

    written = build_rsch_report(
        [source1, source2],
        output,
        target_date=date(2026, 4, 13),
        template_path=template,
    )

    assert written == 6

    wb = load_workbook(output, data_only=False)
    ws = wb["13.04"]
    assert ws.cell(8, 1).value == "ИТОГО:"
    assert ws.cell(8, 5).value == "=SUM(E2:E7)"
    assert ws.cell(8, 6).value == "=SUM(F2:F7)"


def test_build_rsch_report_period_creates_one_sheet_per_row_date(tmp_path: Path) -> None:
    source = tmp_path / "source.xlsx"
    template = tmp_path / "template.xlsx"
    output = tmp_path / "report_period.xlsx"

    _create_source_book_with_rows(
        source,
        [
            [
                datetime(2026, 4, 12),
                None,
                None,
                "Before",
                "Before Contractor",
                1000,
                0,
                "",
                "",
                None,
                None,
                "40700000",
            ],
            [
                datetime(2026, 4, 13),
                None,
                "Комментарий 13",
                "Project 13",
                "Contractor 13",
                100,
                0,
                "",
                "",
                None,
                None,
                "40700013",
            ],
            [
                "14.04.2026",
                None,
                None,
                "Project 14 income",
                "Contractor 14 income",
                0,
                200,
                "Project 14 expense",
                "Contractor 14 expense",
                "Комментарий 14",
                None,
                "40700014",
            ],
            [
                "15.04",
                None,
                None,
                "No Year",
                "No Year Contractor",
                300,
                0,
                "",
                "",
                None,
                None,
                "40700015",
            ],
            [
                datetime(2026, 4, 16),
                None,
                None,
                "After",
                "After Contractor",
                400,
                0,
                "",
                "",
                None,
                None,
                "40700016",
            ],
        ],
    )
    _create_template_book(template)

    written = build_rsch_report(
        source,
        output,
        start_date=date(2026, 4, 13),
        end_date=date(2026, 4, 14),
        template_path=template,
    )

    assert written == 2

    wb = load_workbook(output, data_only=False)
    assert wb.sheetnames == ["13.04", "14.04"]

    ws_13 = wb["13.04"]
    assert ws_13.cell(2, 2).value == "Project 13"
    assert ws_13.cell(2, 8).value == "source.xlsx | сти рсч | строка 4"
    assert ws_13.cell(3, 1).value == "ИТОГО:"
    assert ws_13.cell(3, 5).value == "=SUM(E2:E2)"

    ws_14 = wb["14.04"]
    assert ws_14.cell(2, 2).value == "Project 14 expense"
    assert ws_14.cell(2, 4).value == "Комментарий 14"
    assert ws_14.cell(2, 6).value == 200
    assert ws_14.cell(3, 6).value == "=SUM(F2:F2)"


def test_build_rsch_report_normalizes_formatting_from_legacy_template(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.xlsx"
    template = tmp_path / "legacy_template.xlsx"
    output = tmp_path / "report_legacy_style.xlsx"

    _create_source_book(source)
    _create_legacy_template_book(template)

    written = build_rsch_report(
        source,
        output,
        target_date=date(2026, 4, 13),
        template_path=template,
    )

    assert written == 3

    wb = load_workbook(output, data_only=False)
    ws = wb["13.04"]

    assert ws.freeze_panes == "A2"
    assert ws.auto_filter.ref == "A1:H4"

    for col_idx in range(1, 9):
        cell = ws.cell(1, col_idx)
        assert cell.fill.fgColor.rgb == "FF1F4E79"
        assert cell.font.bold is True
        assert cell.font.color.rgb == "FFFFFFFF"
        assert cell.alignment.horizontal == "center"
        assert cell.alignment.vertical == "center"

    assert ws.cell(2, 4).number_format == "General"
    assert ws.cell(2, 4).fill.fill_type is None
    assert ws.cell(3, 4).alignment.wrap_text is True

    assert ws.cell(2, 5).number_format == "#,##0.00"
    assert ws.cell(3, 6).number_format == "#,##0.00"
    assert ws.cell(5, 5).number_format == "#,##0.00"
    assert ws.cell(5, 6).number_format == "#,##0.00"

    assert ws.cell(2, 7).border.left.style == "thin"
    assert ws.cell(2, 7).border.right.style == "thin"

    assert ws.cell(5, 1).fill.fgColor.rgb == "FFD9E1F2"
    assert ws.cell(5, 5).fill.fgColor.rgb == "FFD9E1F2"
    assert ws.cell(5, 6).fill.fgColor.rgb == "FFD9E1F2"
    assert ws.cell(5, 4).number_format == "General"
    assert ws.cell(5, 8).number_format == "General"


def test_build_rsch_report_preserves_modern_template_palette_and_data_formats(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.xlsx"
    template = tmp_path / "styled_modern_template.xlsx"
    output = tmp_path / "report_modern_style.xlsx"

    _create_source_book(source)
    _create_styled_modern_template_book(template)

    written = build_rsch_report(
        source,
        output,
        target_date=date(2026, 4, 13),
        template_path=template,
    )

    assert written == 3

    wb = load_workbook(output, data_only=False)
    ws = wb["13.04"]

    for col_idx in range(1, 9):
        assert ws.cell(1, col_idx).fill.fgColor.rgb == "FF7030A0"

    assert ws.cell(2, 5).number_format == "#,##0.0000"
    assert ws.cell(3, 6).number_format == "#,##0.0000"
    assert ws.cell(2, 4).alignment.horizontal == "center"
    assert ws.cell(2, 7).alignment.horizontal == "center"
    assert ws.cell(2, 7).border.left.style is None
    assert ws.cell(5, 1).fill.fgColor.rgb == "FFFCE4D6"
    assert ws.cell(5, 5).fill.fgColor.rgb == "FFFCE4D6"
    assert ws.cell(5, 6).fill.fgColor.rgb == "FFFCE4D6"


def test_combined_income_and_expense_row_is_marked_yellow_but_keeps_amount_colors(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source_warning.xlsx"
    template = tmp_path / "template.xlsx"
    output = tmp_path / "report_warning.xlsx"
    _create_template_book(template)
    _create_source_book_with_rows(
        source,
        [
            [
                datetime(2026, 4, 13),
                None,
                None,
                "Конструктор",
                "ООО СПК-ГРУПП",
                2000000,
                17441.93,
                "Розетта",
                "в-т Меликов В.П.",
                "Комментарий расход",
                None,
                "40702810238000415419",
            ]
        ],
    )

    written = build_rsch_report(
        source,
        output,
        target_date=date(2026, 4, 13),
        template_path=template,
    )

    assert written == 1

    wb = load_workbook(output, data_only=False)
    ws = wb["13.04"]
    assert ws.cell(2, 1).value == "СТИ"
    assert ws.cell(2, 2).value == "Конструктор"
    assert ws.cell(2, 3).value == "ООО СПК-ГРУПП"
    assert ws.cell(2, 4).value == "Комментарий расход"
    _assert_warning_fill(ws, 2, (1, 2, 3, 4, 8))
    assert ws.cell(2, 5).fill.fgColor.rgb == "FFC6EFCE"
    assert ws.cell(2, 6).fill.fgColor.rgb == "FFFFC7CE"


def test_build_rsch_report_combines_five_sources_with_expected_warning_rows(
    tmp_path: Path,
) -> None:
    template = tmp_path / "template.xlsx"
    output = tmp_path / "report_five.xlsx"
    _create_template_book(template)

    source1 = tmp_path / "source1.xlsx"
    source2 = tmp_path / "source2.xlsx"
    source3 = tmp_path / "source3.xlsx"
    source4 = tmp_path / "source4.xlsx"
    source5 = tmp_path / "source5.xlsx"

    _create_source_book_with_rows(
        source1,
        [
            [
                datetime(2026, 4, 13),
                None,
                None,
                "Проект 1",
                "Контрагент 1",
                100,
                0,
                "",
                "",
                None,
                None,
                "40702810",
            ]
        ],
        sheet_title="сти рсч 1",
    )
    _create_source_book_with_rows(
        source2,
        [
            [
                datetime(2026, 4, 13),
                None,
                None,
                "Конструктор",
                "ООО СПК-ГРУПП",
                2000000,
                17441.93,
                "Розетта",
                "в-т Меликов В.П.",
                "Комментарий расход 2",
                None,
                "40702810238000415419",
            ]
        ],
        sheet_title="сти рсч 2",
    )
    _create_source_book_with_rows(
        source3,
        [
            [
                datetime(2026, 4, 13),
                None,
                None,
                "% по депозиту",
                "",
                150,
                0,
                "",
                "",
                None,
                None,
                "40702811",
            ]
        ],
        sheet_title="сти рсч 3",
    )
    _create_source_book_with_rows(
        source4,
        [
            [
                datetime(2026, 4, 13),
                None,
                None,
                "Обычный заказчик",
                "",
                0,
                90,
                "",
                "",
                "Комментарий расход 4",
                None,
                "40702812",
            ]
        ],
        sheet_title="сти рсч 4",
    )
    _create_source_book_with_rows(
        source5,
        [
            [
                datetime(2026, 4, 13),
                None,
                None,
                "",
                "Контрагент 5",
                0,
                75,
                "",
                "",
                None,
                None,
                "",
            ]
        ],
        sheet_title="сти рсч 5",
    )

    written = build_rsch_report(
        [source1, source2, source3, source4, source5],
        output,
        target_date=date(2026, 4, 13),
        template_path=template,
    )

    assert written == 5

    wb = load_workbook(output, data_only=False)
    ws = wb["13.04"]

    assert "FFFF00" not in _cell_fill_rgb(ws, 2, 2)
    assert ws.cell(3, 4).value == "Комментарий расход 2"
    _assert_warning_fill(ws, 3, (1, 2, 3, 4, 8))
    assert ws.cell(4, 4).value in (None, "")
    assert "FFFF00" not in _cell_fill_rgb(ws, 4, 2)
    assert ws.cell(5, 4).value == "Комментарий расход 4"
    _assert_warning_fill(ws, 5, (1, 2, 3, 4, 8))
    _assert_warning_fill(ws, 6, (1, 2, 3, 4, 8))
    assert ws.cell(7, 1).value == "ИТОГО:"
    assert ws.cell(7, 5).value == "=SUM(E2:E6)"
    assert ws.cell(7, 6).value == "=SUM(F2:F6)"
