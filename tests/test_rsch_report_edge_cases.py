from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from openpyxl import Workbook, load_workbook

from core.infra.rsch_report import build_rsch_report


def _fill_rgb(ws, row_idx: int, col_idx: int) -> str:
    return str(ws.cell(row_idx, col_idx).fill.fgColor.rgb or "")


def _is_warning(ws, row_idx: int, col_idx: int) -> bool:
    return "FFFF00" in _fill_rgb(ws, row_idx, col_idx)


def _make_template(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "13.04"
    ws.append(
        [
            "Дата",
            "ИСПОЛНИТЕЛЬ",
            "ЗАКАЗЧИК",
            "Контрагент",
            "Комментарий",
            "Приход",
            "Расход",
            "р/с",
        ]
    )
    ws.append([datetime(2026, 4, 13), "", "", "", "", 0, 0, ""])
    ws.append(["ИТОГО:", None, None, None, None, "=SUM(F2:F2)", "=SUM(G2:G2)", None])
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


def test_non_rsch_invalid_sheet_is_ignored_without_issue(tmp_path: Path) -> None:
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
    assert issues == []


def test_tagged_invalid_sheet_still_reports_issue(tmp_path: Path) -> None:
    source = tmp_path / "source_tagged_invalid.xlsx"
    template = tmp_path / "template.xlsx"
    output = tmp_path / "out_tagged_invalid.xlsx"
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

    ws_bad = wb.create_sheet("битый рсч")
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
    assert "битый рсч" in issues[0]
    assert "пропущен" in issues[0]


def test_non_rsch_valid_sheet_is_ignored(tmp_path: Path) -> None:
    source = tmp_path / "source_non_rsch_valid.xlsx"
    template = tmp_path / "template.xlsx"
    output = tmp_path / "out_non_rsch_valid.xlsx"
    _make_template(template)

    wb = Workbook()

    ws_tagged = wb.active
    ws_tagged.title = "исполнитель рсч"
    ws_tagged.append(["x"])
    ws_tagged.append(
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
    ws_tagged.append(
        [
            datetime(2026, 4, 13),
            None,
            None,
            "Нужный проект",
            "Нужный контрагент",
            100,
            0,
            "",
            "",
            None,
            None,
            "4070",
        ]
    )

    ws_untagged = wb.create_sheet("сверка проектов")
    ws_untagged.append(["x"])
    ws_untagged.append(
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
    ws_untagged.append(
        [
            datetime(2026, 4, 13),
            None,
            None,
            "Лишний проект",
            "Лишний контрагент",
            999,
            0,
            "",
            "",
            None,
            None,
            "4999",
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
    assert issues == []

    out_wb = load_workbook(output)
    out_ws = out_wb[out_wb.sheetnames[0]]
    assert out_ws.cell(2, 2).value == "ИСПОЛНИТЕЛЬ"
    assert out_ws.cell(2, 3).value == "Нужный проект"
    assert out_ws.cell(2, 4).value == "Нужный контрагент"
    assert out_ws.cell(2, 5).value in (None, "")
    assert out_ws.cell(2, 6).value == 100
    assert out_ws.cell(3, 1).value == "ИТОГО:"


def test_template_rsch_sheet_is_ignored(tmp_path: Path) -> None:
    source = tmp_path / "source_template_sheet.xlsx"
    template = tmp_path / "template.xlsx"
    output = tmp_path / "out_template_sheet.xlsx"
    _make_template(template)

    wb = Workbook()

    ws_real = wb.active
    ws_real.title = "рабочий рсч"
    ws_real.append(["x"])
    ws_real.append(
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
            "коммент",
            "k",
            "р/с",
        ]
    )
    ws_real.append(
        [
            datetime(2026, 4, 13),
            None,
            None,
            "Рабочий проект",
            "Рабочий контрагент",
            100,
            0,
            "",
            "",
            "Комментарий шаблон не нужен",
            None,
            "4070",
        ]
    )

    ws_template = wb.create_sheet("ШАБЛОН РСЧ")
    ws_template.append(["x"])
    ws_template.append(
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
            "коммент",
            "k",
            "р/с",
        ]
    )
    ws_template.append(
        [
            datetime(2026, 4, 13),
            None,
            None,
            "Шаблонный проект",
            "Шаблонный контрагент",
            999,
            0,
            "",
            "",
            "Шаблонный комментарий",
            None,
            "9999",
        ]
    )
    wb.save(source)

    written = build_rsch_report(
        source,
        output,
        target_date=date(2026, 4, 13),
        template_path=template,
    )

    assert written == 1

    out_wb = load_workbook(output)
    out_ws = out_wb[out_wb.sheetnames[0]]
    assert out_ws.cell(2, 3).value == "Рабочий проект"
    assert out_ws.cell(2, 4).value == "Рабочий контрагент"
    assert out_ws.cell(2, 6).value == 100


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
    widths = {c: out_ws.column_dimensions[c].width for c in "ABCDEFGH"}

    assert all(widths[c] is not None and widths[c] >= 10 for c in widths)
    assert widths["B"] > 10
    assert widths["C"] > 10
    assert widths["F"] >= 14
    assert widths["G"] >= 14


@pytest.mark.parametrize("customer", ["% по депозиту", "комиссия", "налог"])
def test_empty_contractor_is_allowed_for_special_customer_labels(
    tmp_path: Path,
    customer: str,
) -> None:
    source = tmp_path / f"special_{customer}.xlsx"
    template = tmp_path / "template.xlsx"
    output = tmp_path / f"out_{customer}.xlsx"
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
            customer,
            "",
            100,
            0,
            "",
            "",
            None,
            None,
            "4070",
        ]
    )
    wb.save(source)

    written = build_rsch_report(
        source,
        output,
        target_date=date(2026, 4, 13),
        template_path=template,
    )

    assert written == 1

    out_wb = load_workbook(output)
    out_ws = out_wb[out_wb.sheetnames[0]]
    assert out_ws.cell(2, 4).value is None
    assert _is_warning(out_ws, 2, 4) is False


def test_empty_contractor_is_marked_for_regular_customer(tmp_path: Path) -> None:
    source = tmp_path / "regular_customer.xlsx"
    template = tmp_path / "template.xlsx"
    output = tmp_path / "out_regular.xlsx"
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
            "Обычный заказчик",
            "",
            100,
            0,
            "",
            "",
            None,
            None,
            "4070",
        ]
    )
    wb.save(source)

    written = build_rsch_report(
        source,
        output,
        target_date=date(2026, 4, 13),
        template_path=template,
    )

    assert written == 1

    out_wb = load_workbook(output)
    out_ws = out_wb[out_wb.sheetnames[0]]
    for col_idx in (1, 2, 3, 4, 5, 8):
        assert _is_warning(out_ws, 2, col_idx) is True


def test_missing_customer_executor_and_account_marks_row_yellow(tmp_path: Path) -> None:
    source = tmp_path / "missing_fields.xlsx"
    template = tmp_path / "template.xlsx"
    output = tmp_path / "out_missing_fields.xlsx"
    _make_template(template)

    wb = Workbook()
    ws = wb.active
    ws.title = "рсч"
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
            "",
            "Контрагент",
            0,
            50,
            "",
            "",
            None,
            None,
            "",
        ]
    )
    wb.save(source)

    written = build_rsch_report(
        source,
        output,
        target_date=date(2026, 4, 13),
        template_path=template,
    )

    assert written == 1

    out_wb = load_workbook(output)
    out_ws = out_wb[out_wb.sheetnames[0]]
    for col_idx in (1, 2, 3, 4, 5, 8):
        assert _is_warning(out_ws, 2, col_idx) is True
    assert out_ws.cell(2, 7).fill.fgColor.rgb == "FFFFC7CE"
