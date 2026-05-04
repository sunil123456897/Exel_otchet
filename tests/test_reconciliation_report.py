from datetime import date
from pathlib import Path

from openpyxl import Workbook, load_workbook

from core.infra.reconciliation_report import build_reconciliation_report


def _create_master_book(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "21.04.2026"
    ws.append(
        [
            "Источник",
            "ЗАКАЗЧИК",
            "ИСПОЛНИТЕЛЬ",
            "Приход",
            "Расход",
            "Комиссия",
            "ИТОГ",
            "% посредника",
            "посредник 1(кэш)",
            "посредник 2",
            "Фильтры",
        ]
    )
    ws.append(
        [
            "Отчет Марго.xlsx : Строка 58",
            "Карат ИП Михальчук А. С., ИНН 504700521754",
            "СТИ Альфа",
            0,
            1407,
            16,
            -1181.88,
            0,
            0,
            0,
            "транзит",
        ]
    )
    ws.cell(2, 1).hyperlink = f"{path}#'21.04.2026'!A2"
    ws.append(
        [
            "Отчет Марго.xlsx : Строка 65",
            "Карат Принцев И.О ИП, ИНН 501300220789",
            "СТИ Альфа",
            0,
            1930,
            16,
            -1621.2,
            0,
            0,
            0,
            "транзит",
        ]
    )
    ws.cell(3, 1).hyperlink = f"{path}#'21.04.2026'!A3"
    ws.append(
        [
            "ИТОГО:",
            None,
            None,
            "=SUM(D2:D3)",
            "=SUM(E2:E3)",
            None,
            "=SUM(G2:G3)",
            None,
            "=SUM(I2:I3)",
            "=SUM(J2:J3)",
            None,
        ]
    )
    wb.save(path)


def _create_rsch_book(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "21.04"
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
    ws.append(
        [
            "СТИ",
            None,
            'ООО "Союз"',
            None,
            6000000,
            None,
            "407",
            "source | row 10",
        ]
    )
    ws.cell(2, 8).hyperlink = f"{path}#'21.04'!A2"
    ws.append(
        [
            "СТИ",
            "карат",
            "ИП Михальчук Александр Сергеевич",
            "Карат ИП Михальчук А. С., ИНН 504700521754",
            None,
            1407,
            "407",
            "source | row 11",
        ]
    )
    ws.cell(3, 8).hyperlink = f"{path}#'21.04'!A3"
    ws.append(
        [
            "СБИ",
            "карат",
            "ИП Принцев Игорь Олегович",
            "Карат Принцев И.О ИП, ИНН 501300220789",
            None,
            1930,
            "407",
            "source | row 12",
        ]
    )
    ws.append(["ИТОГО:", None, None, None, "=SUM(E2:E4)", "=SUM(F2:F4)", None, None])
    wb.save(path)


def test_build_reconciliation_report_matches_rows_and_places_missing_curator_first(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    output_path = tmp_path / "reconciliation.xlsx"
    _create_master_book(master_path)
    _create_rsch_book(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 3

    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]

    assert [ws.cell(1, col).value for col in range(1, 18)] == [
        "Источник",
        "ЗАКАЗЧИК",
        "ИСПОЛНИТЕЛЬ",
        "Приход",
        "Расход",
        "Комиссия",
        "ИТОГ",
        "% посредника",
        "посредник 1(кэш)",
        "посредник 2",
        "ИТОГ",
        "ИСПОЛНИТЕЛЬ",
        "ЗАКАЗЧИК",
        "Контрагент",
        "Комментарий",
        "Приход",
        "Расход",
    ]

    assert wb.sheetnames == ["21.04.2026"]

    assert ws.cell(2, 1).value == "Отчет Марго.xlsx : Строка 58"
    assert ws.cell(2, 1).hyperlink.target.endswith("master.xlsx")
    assert ws.cell(2, 11).value == "СВЕРЕНО"
    assert ws.cell(2, 12).value == "СТИ"
    assert ws.cell(2, 13).value == "карат"
    assert ws.cell(2, 17).value == 1407

    assert ws.cell(3, 1).value == "ОШИБКА НЕТУ У КУРАТОРОВ"
    assert ws.cell(3, 1).hyperlink.target.endswith("rsch.xlsx")
    assert ws.cell(3, 11).value == "ОШИБКА"
    assert ws.cell(3, 12).value == "СТИ"
    assert ws.cell(3, 16).value == 6000000

    assert ws.cell(4, 1).value == "Отчет Марго.xlsx : Строка 65"
    assert ws.cell(4, 1).hyperlink.target.endswith("master.xlsx")
    assert ws.cell(4, 11).value == "ОШИБКА"
    assert ws.cell(4, 12).value == "СБИ"
    assert ws.cell(4, 17).value == 1930

    assert ws.cell(5, 1).value == "ИТОГО:"
    assert ws.cell(5, 4).value == "=SUM(D2:D4)"
    assert ws.cell(5, 5).value == "=SUM(E2:E4)"
    assert ws.cell(5, 7).value == "=SUM(G2:G4)"
    assert ws.cell(5, 17).value == "=SUM(Q2:Q4)"

    assert ws.cell(2, 11).fill.fgColor.rgb == "FF00B050"
    assert ws.cell(3, 11).fill.fgColor.rgb == "FFFF0000"
    assert ws.cell(4, 11).fill.fgColor.rgb == "FFFF0000"
    assert ws.cell(2, 11).comment is None
    assert ws.cell(2, 1).hyperlink.target.endswith("master.xlsx")
    assert ws.cell(3, 11).comment.text == "Нет у кураторов"
    assert ws.cell(3, 1).hyperlink.target.endswith("rsch.xlsx")
    assert ws.cell(4, 11).comment.text == "Не совпал исполнитель"
    assert ws.auto_filter.ref == "A1:Q5"


def test_build_reconciliation_report_preserves_later_exact_amount_match(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    output_path = tmp_path / "reconciliation.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "13.04.2026"
    ws.append(
        [
            "Источник",
            "ЗАКАЗЧИК",
            "ИСПОЛНИТЕЛЬ",
            "Приход",
            "Расход",
            "Комиссия",
            "ИТОГ",
            "% посредника",
            "посредник 1(кэш)",
            "посредник 2",
            "Фильтры",
        ]
    )
    ws.append(["source 1", "Карат первый", "СТИ Альфа", 0, 100, 0, -100, 0, 0, 0, None])
    ws.append(["source 2", "Карат второй", "СТИ Альфа", 0, 1407, 0, -1407, 0, 0, 0, None])
    ws.append(["source 3", "Карат третий", "сти альфа ", 0, 200, 0, -200, 0, 0, 0, None])
    wb.save(master_path)

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
    ws.append(["СТИ", "Карат", "контрагент", None, 0, 1407, "407", "source | row 1"])
    wb.save(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 13),
    )

    assert written == 3

    wb = load_workbook(output_path, data_only=False)
    ws = wb["13.04.2026"]

    assert wb.sheetnames == ["13.04.2026"]

    assert ws.cell(2, 1).value == "source 2"
    assert ws.cell(2, 11).value == "СВЕРЕНО"
    assert ws.cell(2, 12).value == "СТИ"
    assert ws.cell(2, 17).value == 1407

    assert ws.cell(3, 1).value == "source 1"
    assert ws.cell(3, 11).value == "ОШИБКА"
    assert ws.cell(3, 12).value is None


def test_build_reconciliation_report_falls_back_to_single_common_date(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    output_path = tmp_path / "reconciliation.xlsx"
    _create_master_book(master_path)
    _create_rsch_book(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 5, 1),
    )

    assert written == 3

    wb = load_workbook(output_path, data_only=False)
    assert wb.sheetnames == ["21.04.2026"]


def test_build_reconciliation_report_accepts_boris_master_headers(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "boris_report.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    output_path = tmp_path / "reconciliation.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "21.04.2026"
    ws.append(
        [
            "Источник",
            "ЗАКАЗЧИК",
            "ИСПОЛНИТЕЛЬ",
            "Приход",
            "Расход",
            "Комиссия",
            "ИТОГ",
            "% посредник 1",
            "посредник 1(кэш)",
            "% посредник 2",
            "посредник 2",
            "Фильтры",
        ]
    )
    ws.append(
        [
            "Отчёт Борис Ж.xlsx : Строка 10",
            "Карат ИП Михальчук А. С., ИНН 504700521754",
            "СТИ Альфа",
            0,
            1407,
            16,
            -1181.88,
            0,
            0,
            0,
            0,
            "ЗП",
        ]
    )
    wb.save(master_path)
    _create_rsch_book(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 3

    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]
    assert [ws.cell(1, col).value for col in range(1, 19)] == [
        "Источник",
        "ЗАКАЗЧИК",
        "ИСПОЛНИТЕЛЬ",
        "Приход",
        "Расход",
        "Комиссия",
        "ИТОГ",
        "% посредник 1",
        "посредник 1(кэш)",
        "% посредник 2",
        "посредник 2",
        "ИТОГ",
        "ИСПОЛНИТЕЛЬ",
        "ЗАКАЗЧИК",
        "Контрагент",
        "Комментарий",
        "Приход",
        "Расход",
    ]
    assert ws.cell(2, 1).value == "Отчёт Борис Ж.xlsx : Строка 10"
    assert ws.cell(2, 8).value == 0
    assert ws.cell(2, 10).value == 0
    assert ws.cell(2, 12).value == "СВЕРЕНО"


def test_build_reconciliation_report_accepts_ivan_master_headers_without_filters(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "ivan_report.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    output_path = tmp_path / "reconciliation.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "21.04.2026"
    ws.append(
        [
            "Сотрудник",
            "ЗАКАЗЧИК",
            "ИСПОЛНИТЕЛЬ",
            "Приход",
            "Расход",
            "Комиссия",
            "ИТОГ",
            "ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ",
            "% посредника 1",
            "посредник 1(кэш)",
            "посредник 2",
            "курс",
            "сумма",
            "валюта",
            "фильтры",
        ]
    )
    ws.append(
        [
            "Иван",
            "Карат ИП Михальчук А. С., ИНН 504700521754",
            "СТИ Альфа",
            0,
            1407,
            16,
            -1181.88,
            335936,
            0,
            0,
            0,
            "",
            "",
            "",
            "ЗП",
        ]
    )
    wb.save(master_path)
    _create_rsch_book(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 3

    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]
    headers = [ws.cell(1, col).value for col in range(1, ws.max_column + 1)]
    assert headers == [
        "Сотрудник",
        "ЗАКАЗЧИК",
        "ИСПОЛНИТЕЛЬ",
        "Приход",
        "Расход",
        "Комиссия",
        "ИТОГ",
        "ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ",
        "% посредника 1",
        "посредник 1(кэш)",
        "посредник 2",
        "курс",
        "сумма",
        "валюта",
        "ИТОГ",
        "ИСПОЛНИТЕЛЬ",
        "ЗАКАЗЧИК",
        "Контрагент",
        "Комментарий",
        "Приход",
        "Расход",
    ]
    assert "фильтры" not in headers
    assert ws.cell(2, 1).value == "Иван"
    assert ws.cell(2, 8).value == 335936
    assert ws.cell(2, 15).value == "СВЕРЕНО"
