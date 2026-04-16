from datetime import date, datetime
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from core.infra.rsch_report import build_rsch_report


def _create_source_book(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "сти рсч"
    ws.append(["мс"])
    ws.append(
        [
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
    )
    ws.append(
        [
            datetime(2026, 4, 13),
            None,
            None,
            "Проект Приход 1",
            "Контрагент Приход 1",
            100,
            0,
            "Проект Расход 1",
            "Контрагент Расход 1",
            None,
            None,
            "40702810",
        ]
    )
    ws.append(
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
            None,
            None,
            "40702811",
        ]
    )
    ws.append(
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
            None,
            None,
            "40702812",
        ]
    )
    ws.append(
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
        ]
    )
    wb.save(path)


def _create_template_book(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "13.04"
    ws.append(
        ["Дата", "Контрагент", "ЗАКАЗЧИК", "ИСПОЛНИТЕЛЬ", "Приход", "Расход", "р/с"]
    )
    ws.append([datetime(2026, 4, 13), "", "", "", 0, 0, ""])
    ws.append(["ИТОГО:", None, None, None, "=SUM(E2:E2)", "=SUM(F2:F2)", None])
    ws["E2"].number_format = "#,##0.00"
    ws["F2"].number_format = "#,##0.00"
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

    assert [ws.cell(1, c).value for c in range(1, 8)] == [
        "Дата",
        "Контрагент",
        "ЗАКАЗЧИК",
        "ИСПОЛНИТЕЛЬ",
        "Приход",
        "Расход",
        "р/с",
    ]

    # income leg from left D/E
    assert ws.cell(2, 2).value == "Контрагент Приход 1"
    assert ws.cell(2, 3).value == "Проект Приход 1"
    assert ws.cell(2, 4).value == "СТИ"
    assert ws.cell(2, 5).value == 100
    assert ws.cell(2, 6).value == 0

    # expense leg from right H/I
    assert ws.cell(3, 2).value == "Контрагент Расход 2"
    assert ws.cell(3, 3).value == "Проект Расход 2"
    assert ws.cell(3, 5).value == 0
    assert ws.cell(3, 6).value == 200

    # both-leg row stays as one operation and keeps both signs
    assert ws.cell(4, 2).value == "Контрагент Приход 3"
    assert ws.cell(4, 3).value == "Проект Приход 3"
    assert ws.cell(4, 5).value == -30
    assert ws.cell(4, 6).value == -40

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

    assert written == 86
