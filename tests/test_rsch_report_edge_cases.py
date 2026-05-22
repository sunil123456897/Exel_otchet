from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from openpyxl import Workbook, load_workbook

from core.infra.rsch_report import _collect_rows_from_workbook, build_rsch_report


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
            "Источник",
        ]
    )
    ws.append([datetime(2026, 4, 13), "", "", "", "", 0, 0, "", ""])
    ws.append(
        ["ИТОГО:", None, None, None, None, "=SUM(F2:F2)", "=SUM(G2:G2)", None, None]
    )
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


def test_collect_rows_from_workbook_uses_local_copy_and_preserves_source_link(
    tmp_path: Path,
) -> None:
    source = tmp_path / "network_source.xlsx"
    local_copy = tmp_path / "local_copy.xlsx"
    temp_copy = tmp_path / "temp_copy.xlsx"
    _make_source(source)
    wb = load_workbook(source)
    wb.active.cell(3, 6).value = 100
    wb.save(source)
    local_copy.write_bytes(source.read_bytes())
    temp_copy.write_bytes(source.read_bytes())

    with (
        patch(
            "core.infra.rsch_report.get_local_copy",
            return_value=(str(local_copy), str(temp_copy)),
        ) as copy_file,
        patch("core.infra.rsch_report.Path.unlink") as unlink,
    ):
        rows = _collect_rows_from_workbook(source, date(2026, 4, 13))

    assert len(rows) == 1
    assert {row["source_path"] for row in rows} == {str(source)}
    assert rows[0]["source"].startswith(f"{source.name} | ")
    copy_file.assert_called_once_with(str(source), ("Q", "Z"))
    unlink.assert_called_once_with(missing_ok=True)


def test_collect_rows_from_workbook_passes_custom_drive_letters(tmp_path: Path) -> None:
    source = tmp_path / "network_source.xlsx"
    local_copy = tmp_path / "local_copy.xlsx"
    _make_source(source)
    wb = load_workbook(source)
    wb.active.cell(3, 6).value = 100
    wb.save(source)
    local_copy.write_bytes(source.read_bytes())

    with patch(
        "core.infra.rsch_report.get_local_copy",
        return_value=(str(local_copy), None),
    ) as copy_file:
        rows = _collect_rows_from_workbook(
            source,
            date(2026, 4, 13),
            drive_letters=("R",),
        )

    assert len(rows) == 1
    copy_file.assert_called_once_with(str(source), ("R",))


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


def test_only_invalid_rsch_sheets_raise_instead_of_writing_empty_success(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source_only_invalid.xlsx"
    template = tmp_path / "template.xlsx"
    output = tmp_path / "out_only_invalid.xlsx"
    _make_template(template)

    wb = Workbook()
    ws_bad = wb.active
    ws_bad.title = "битый рсч"
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
    with pytest.raises(RuntimeError, match="РСЧ.*не удалось собрать строки"):
        build_rsch_report(
            source,
            output,
            target_date=date(2026, 4, 13),
            template_path=template,
            issues_sink=issues,
        )

    assert issues
    assert "битый рсч" in issues[0]
    assert not output.exists()


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
    assert out_ws.cell(2, 1).value == "ИСПОЛНИТЕЛЬ"
    assert out_ws.cell(2, 2).value == "Нужный проект"
    assert out_ws.cell(2, 3).value == "Нужный контрагент"
    assert out_ws.cell(2, 4).value in (None, "")
    assert out_ws.cell(2, 5).value == 100
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
    assert out_ws.cell(2, 2).value == "Рабочий проект"
    assert out_ws.cell(2, 3).value == "Рабочий контрагент"
    assert out_ws.cell(2, 5).value == 100


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

    out_wb = load_workbook(output, data_only=False)
    out_ws = out_wb[out_wb.sheetnames[0]]
    assert out_ws.cell(3, 1).fill.fgColor.rgb == "FFD9E1F2"
    assert out_ws.cell(3, 5).fill.fgColor.rgb == "FFD9E1F2"
    assert out_ws.cell(3, 6).fill.fgColor.rgb == "FFD9E1F2"
    assert out_ws.cell(3, 5).number_format == "#,##0.00"
    assert out_ws.cell(3, 6).number_format == "#,##0.00"


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


def test_zero_amount_business_row_is_kept_as_warning(tmp_path: Path) -> None:
    source = tmp_path / "source_zero_business_row.xlsx"
    template = tmp_path / "template.xlsx"
    output = tmp_path / "out_zero_business_row.xlsx"
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
            "Нулевой проект",
            "Нулевой контрагент",
            0,
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
    assert out_ws.cell(2, 2).value == "Нулевой проект"
    assert out_ws.cell(2, 3).value == "Нулевой контрагент"
    assert out_ws.cell(2, 5).value == 0
    assert out_ws.cell(2, 6).value == 0
    for col_idx in (1, 2, 3, 4, 8):
        assert _is_warning(out_ws, 2, col_idx) is True


def test_blank_zero_amount_row_is_still_skipped(tmp_path: Path) -> None:
    source = tmp_path / "source_blank_zero_row.xlsx"
    template = tmp_path / "template.xlsx"
    output = tmp_path / "out_blank_zero_row.xlsx"
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
    ws.append([datetime(2026, 4, 13), None, None, "", "", 0, 0, "", "", None, None, ""])
    wb.save(source)

    written = build_rsch_report(
        source,
        output,
        target_date=date(2026, 4, 13),
        template_path=template,
    )

    assert written == 0


def test_zero_amount_row_with_only_account_is_still_skipped(tmp_path: Path) -> None:
    source = tmp_path / "source_account_only_zero_row.xlsx"
    template = tmp_path / "template.xlsx"
    output = tmp_path / "out_account_only_zero_row.xlsx"
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
            "",
            "",
            0,
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

    assert written == 0


def test_invalid_numeric_amount_reports_sheet_issue_instead_of_zeroing(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source_invalid_amount.xlsx"
    template = tmp_path / "template.xlsx"
    output = tmp_path / "out_invalid_amount.xlsx"
    issues: list[str] = []
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
            "Проект",
            "Контрагент",
            "не число",
            0,
            "",
            "",
            None,
            None,
            "4070",
        ]
    )
    wb.save(source)

    with pytest.raises(RuntimeError, match="Некорректное числовое значение в РСЧ"):
        build_rsch_report(
            source,
            output,
            target_date=date(2026, 4, 13),
            template_path=template,
            issues_sink=issues,
        )

    assert output.exists() is False
    assert len(issues) == 1
    assert "тест рсч" in issues[0]
    assert "не число" in issues[0]


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
    assert widths["E"] >= 14
    assert widths["F"] >= 14


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
    assert out_ws.cell(2, 3).value is None
    assert _is_warning(out_ws, 2, 3) is False


def test_empty_contractor_is_allowed_for_getwork_customer(tmp_path: Path) -> None:
    source = tmp_path / "getwork_empty_contractor.xlsx"
    template = tmp_path / "template.xlsx"
    output = tmp_path / "out_getwork_empty_contractor.xlsx"
    _make_template(template)

    wb = Workbook()
    ws = wb.active
    ws.title = "Моника рсч"
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
            "ООО Гетворк",
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
    assert out_ws.cell(2, 3).value is None
    assert _is_warning(out_ws, 2, 3) is False


@pytest.mark.parametrize("customer", ["ООО ГЕТВОРК комиссия", "ООО ГЕТВОРК налог", "ООО ГЕТВОРК % по депозиту"])
def test_empty_account_is_allowed_for_getwork_special_customer_rows(
    tmp_path: Path,
    customer: str,
) -> None:
    source = tmp_path / "getwork_without_account.xlsx"
    template = tmp_path / "template.xlsx"
    output = tmp_path / "out_getwork_without_account.xlsx"
    _make_template(template)

    wb = Workbook()
    ws = wb.active
    ws.title = "Моника рсч"
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
            "ООО ГЕТВОРК",
            0,
            115000,
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
    assert _is_warning(out_ws, 2, 7) is False
    assert out_ws.cell(2, 6).fill.fgColor.rgb == "FFFFC7CE"


@pytest.mark.parametrize("customer", ["% по депозиту", "комиссия", "налог"])
def test_empty_account_is_marked_for_regular_special_customer_rows(
    tmp_path: Path,
    customer: str,
) -> None:
    source = tmp_path / "regular_special_without_account.xlsx"
    template = tmp_path / "template.xlsx"
    output = tmp_path / "out_regular_special_without_account.xlsx"
    _make_template(template)

    wb = Workbook()
    ws = wb.active
    ws.title = "СБИ рсч"
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
            datetime(2026, 5, 5),
            None,
            None,
            customer,
            "служебный платеж",
            0,
            21950.87,
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
        target_date=date(2026, 5, 5),
        template_path=template,
    )

    assert written == 1

    out_wb = load_workbook(output)
    out_ws = out_wb[out_wb.sheetnames[0]]
    assert _is_warning(out_ws, 2, 7) is True
    assert out_ws.cell(2, 6).fill.fgColor.rgb == "FFFFC7CE"


@pytest.mark.parametrize("executor", ["Факторинг рсч", "ВФ рсч", "Вафт Фокс рсч"])
def test_empty_account_is_allowed_for_known_no_account_executors(
    tmp_path: Path,
    executor: str,
) -> None:
    source = tmp_path / "known_executor_without_account.xlsx"
    template = tmp_path / "template.xlsx"
    output = tmp_path / "out_known_executor_without_account.xlsx"
    _make_template(template)

    wb = Workbook()
    ws = wb.active
    ws.title = executor
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
            "Карат",
            "Розетта",
            5000,
            0,
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
    assert _is_warning(out_ws, 2, 7) is False
    assert out_ws.cell(2, 5).fill.fgColor.rgb == "FFC6EFCE"


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
    for col_idx in (1, 2, 3, 4, 8):
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
    for col_idx in (1, 2, 3, 4, 8):
        assert _is_warning(out_ws, 2, col_idx) is True
    assert out_ws.cell(2, 6).fill.fgColor.rgb == "FFFFC7CE"
