from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from openpyxl import Workbook, load_workbook

from core.infra.rsch_report import build_rsch_report


def _make_template(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "13.04"
    ws.append(
        ["Дата", "Контрагент", "ЗАКАЗЧИК", "ИСПОЛНИТЕЛЬ", "Приход", "Расход", "р/с"]
    )
    ws.append([datetime(2026, 4, 13), "", "", "", 0, 0, ""])
    ws.append(["ИТОГО:", None, None, None, "=SUM(E2:E2)", "=SUM(F2:F2)", None])
    wb.save(path)


def _make_source(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "тест рсч"
    ws.append(["x"])
    ws.append(
        [
            "дата",
            "b",
            "c",
            "проект",
            "контрагент",
            "приход на рсч, су",
            "расход с рсч, су",
            "проект",
            "контрагент",
            "j",
            "k",
            "р/с",
        ]
    )
    ws.append(
        [
            datetime(2026, 4, 13),
            None,
            None,
            "P1",
            "C1",
            0,
            0,
            "P2",
            "C2",
            None,
            None,
            "4070",
        ]
    )
    wb.save(path)


def test_missing_source_file_raises(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    _make_template(template)
    with pytest.raises(FileNotFoundError):
        build_rsch_report(
            tmp_path / "missing.xlsx",
            tmp_path / "out.xlsx",
            target_date=date(2026, 4, 13),
            template_path=template,
        )


def test_missing_template_file_raises(tmp_path: Path) -> None:
    source = tmp_path / "source.xlsx"
    _make_source(source)
    with pytest.raises(FileNotFoundError):
        build_rsch_report(
            source,
            tmp_path / "out.xlsx",
            target_date=date(2026, 4, 13),
            template_path=tmp_path / "missing_template.xlsx",
        )


def test_invalid_sheet_does_not_break_whole_report(tmp_path: Path) -> None:
    source = tmp_path / "source_mixed.xlsx"
    template = tmp_path / "template.xlsx"
    output = tmp_path / "out_mixed.xlsx"
    _make_template(template)

    wb = Workbook()

    ws_ok = wb.active
    ws_ok.title = "валидный рсч"
    ws_ok.append(["x"])
    ws_ok.append(
        [
            "дата",
            "b",
            "c",
            "проект",
            "контрагент",
            "приход на рсч, су",
            "расход с рсч, су",
            "проект",
            "контрагент",
            "j",
            "k",
            "р/с",
        ]
    )
    ws_ok.append(
        [
            datetime(2026, 4, 13),
            None,
            None,
            "P1",
            "C1",
            100,
            0,
            "",
            "",
            None,
            None,
            "4070",
        ]
    )

    ws_bad = wb.create_sheet("битый лист")
    ws_bad.append(["x"])
    ws_bad.append(
        [
            "дата",
            "b",
            "c",
            "проект",
            "контрагент",
            "приход на рсч, су",
            "расход с рсч, су",
            "проект",
            "контрагент",
            "j",
            "k",
            "нет нужной колонки",
        ]
    )
    ws_bad.append(
        [
            datetime(2026, 4, 13),
            None,
            None,
            "P2",
            "C2",
            0,
            50,
            "",
            "",
            None,
            None,
            "-",
        ]
    )

    wb.save(source)

    issues = []
    written = build_rsch_report(
        source,
        output,
        target_date=date(2026, 4, 13),
        template_path=template,
        issues_sink=issues,
    )

    assert written == 1
    assert len(issues) == 1
    assert "битый лист" in issues[0]
    assert "пропущен" in issues[0]


def test_missing_default_template_uses_builtin_fallback(tmp_path: Path) -> None:
    source = tmp_path / "source_valid.xlsx"
    output = tmp_path / "out_builtin.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "валидный рсч"
    ws.append(["x"])
    ws.append(
        [
            "дата",
            "b",
            "c",
            "проект",
            "контрагент",
            "приход на рсч, су",
            "расход с рсч, су",
            "проект",
            "контрагент",
            "j",
            "k",
            "р/с",
        ]
    )
    ws.append(
        [
            datetime(2026, 4, 13),
            None,
            None,
            "P1",
            "C1",
            120,
            0,
            "",
            "",
            None,
            None,
            "4070",
        ]
    )
    wb.save(source)

    missing_template = tmp_path / "absent_template.xlsx"
    issues = []
    with patch("core.infra.rsch_report.DEFAULT_RSCH_TEMPLATE_PATH", missing_template):
        written = build_rsch_report(
            source,
            output,
            target_date=date(2026, 4, 13),
            issues_sink=issues,
        )

    assert written == 1
    assert output.exists()
    assert any("Шаблон РСЧ не найден" in issue for issue in issues)


def test_zero_rows_still_writes_total(tmp_path: Path) -> None:
    source = tmp_path / "source.xlsx"
    template = tmp_path / "template.xlsx"
    output = tmp_path / "out.xlsx"
    _make_source(source)
    _make_template(template)

    written = build_rsch_report(
        source,
        output,
        target_date=date(2026, 4, 14),
        template_path=template,
    )

    assert written == 0


def test_empty_sources_raises_value_error(tmp_path: Path) -> None:
    template = tmp_path / "template.xlsx"
    _make_template(template)
    with pytest.raises(ValueError):
        build_rsch_report(
            [],
            tmp_path / "out.xlsx",
            target_date=date(2026, 4, 13),
            template_path=template,
        )


def test_autosize_all_columns(tmp_path: Path) -> None:
    source = tmp_path / "source_long.xlsx"
    template = tmp_path / "template.xlsx"
    output = tmp_path / "out_long.xlsx"
    _make_template(template)

    wb = Workbook()
    ws = wb.active
    ws.title = "тест рсч"
    ws.append(["x"])
    ws.append(
        [
            "дата",
            "b",
            "c",
            "проект",
            "контрагент",
            "приход на рсч, су",
            "расход с рсч, су",
            "проект",
            "контрагент",
            "j",
            "k",
            "р/с",
        ]
    )
    ws.append(
        [
            datetime(2026, 4, 13),
            None,
            None,
            "ОЧЕНЬ ДЛИННОЕ НАЗВАНИЕ ПРОЕКТА ДЛЯ ПРОВЕРКИ ШИРИНЫ",
            "КОНТРАГЕНТ С ОЧЕНЬ ДЛИННЫМ НАЗВАНИЕМ",
            123456789.12,
            987654321.99,
            "",
            "",
            None,
            None,
            "40702810238000415419",
        ]
    )
    wb.save(source)

    build_rsch_report(
        source,
        output,
        target_date=date(2026, 4, 13),
        template_path=template,
    )

    out_wb = load_workbook(output)
    out_ws = out_wb[out_wb.sheetnames[0]]
    widths = {c: out_ws.column_dimensions[c].width for c in "ABCDEFG"}

    assert all(widths[c] is not None and widths[c] >= 10 for c in widths)
    assert widths["B"] > 10
    assert widths["C"] > 10
    assert widths["E"] >= 14
    assert widths["F"] >= 14
