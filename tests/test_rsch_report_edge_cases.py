from datetime import date, datetime
from pathlib import Path

import pytest
from openpyxl import Workbook

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
