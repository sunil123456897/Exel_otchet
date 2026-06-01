from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from openpyxl import Workbook, load_workbook

from core.infra.reconciliation_report import (
    REASON_AMOUNT_MISMATCH,
    REASON_CUSTOMER_MISMATCH,
    REASON_EXECUTOR_MISMATCH,
    STATUS_REVIEW,
    STATUS_VERIFIED,
    MasterReconciliationRow,
    RschReconciliationRow,
    _build_reconciliation_rows,
    build_combined_reconciliation_report,
    build_reconciliation_report,
)


def _find_status_col(ws) -> int:
    return max(
        range(1, ws.max_column + 1),
        key=lambda col: sum(
            1
            for row in range(2, ws.max_row + 1)
            if ws.cell(row, col).value in {"СВЕРЕНО", "ПРОВЕРИТЬ", "ОШИБКА"}
        ),
    )


def _find_header_col(ws, header: str) -> int:
    for col in range(1, ws.max_column + 1):
        if ws.cell(1, col).value == header:
            return col
    raise AssertionError(f"Header not found: {header}")


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


def _create_empty_master_book(path: Path) -> None:
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
        ]
    )
    wb.save(path)


def _create_single_master_book(
    path: Path,
    *,
    source: str = "master row",
    customer: str = "Илон",
    executor: str = "СТИНГ",
    income: int = 0,
    expense: int = 500000,
) -> None:
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
        ]
    )
    ws.append([source, customer, executor, income, expense, 0, income - expense])
    wb.save(path)


def _create_single_rsch_book(path: Path, *, duplicate: bool = False) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "21.04"
    ws.append(["ИСПОЛНИТЕЛЬ", "ЗАКАЗЧИК", "Контрагент", "Комментарий", "Приход", "Расход", "Источник"])
    ws.append(["СТИНГ", "илон", "реестр зп", "", 0, 500000, "rsch row 1"])
    if duplicate:
        ws.append(["СТИНГ", "илон", "реестр зп", "", 0, 500000, "rsch row 2"])
    wb.save(path)


def _master_row(customer: str, executor: str, expense: int) -> MasterReconciliationRow:
    expense_decimal = Decimal(str(expense))
    return MasterReconciliationRow(
        values=["source", customer, executor, 0, expense, 0, -expense],
        source="source",
        source_link=None,
        customer=customer,
        executor=executor,
        income=Decimal("0"),
        expense=expense_decimal,
    )


def _rsch_row(row_id: str, customer: str, executor: str, expense: int) -> RschReconciliationRow:
    expense_decimal = Decimal(str(expense))
    return RschReconciliationRow(
        row_id=row_id,
        executor=executor,
        customer=customer,
        contractor="",
        comment="",
        income=Decimal("0"),
        expense=expense_decimal,
        source_link=None,
    )


def test_build_reconciliation_rows_preserves_matching_semantics_guard() -> None:
    rows = _build_reconciliation_rows(
        [
            _master_row("Илон", "СТИНГ", 100),
            _master_row("Илон", "СТИНГ", 100),
            _master_row("Геометрия", "СТИ", 200),
            _master_row("Умка", "СТИ", 300),
            _master_row("Гетворк Проктер", "ВБ Альфа", 400),
        ],
        [
            _rsch_row("exact-1", "илон", "стинг", 100),
            _rsch_row("exact-2", "илон", "стинг", 100),
            _rsch_row("amount", "геометрия", "сти", 250),
            _rsch_row("executor", "умка", "сби", 300),
            _rsch_row("weak", "гетворк м", "вб альфа", 400),
        ],
    )

    assert [(row.status, row.reason, row.rsch.row_id if row.rsch else None) for row in rows] == [
        (STATUS_VERIFIED, "", "exact-1"),
        (STATUS_VERIFIED, "", "exact-2"),
        (STATUS_REVIEW, REASON_AMOUNT_MISMATCH, "amount"),
        (STATUS_REVIEW, REASON_EXECUTOR_MISMATCH, "executor"),
        (STATUS_REVIEW, REASON_CUSTOMER_MISMATCH, "weak"),
    ]


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

    assert [ws.cell(1, col).value for col in range(1, 19)] == [
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
        "Статус",
        "ИСПОЛНИТЕЛЬ",
        "ЗАКАЗЧИК",
        "Контрагент",
        "Комментарий",
        "Приход",
        "Расход",
        "Причина",
    ]

    assert wb.sheetnames == ["21.04.2026"]

    assert ws.cell(2, 1).value == "Отчет Марго.xlsx : Строка 58"
    assert ws.cell(2, 1).hyperlink.target.endswith("master.xlsx")
    assert ws.cell(2, 11).value == "СВЕРЕНО"
    assert ws.cell(2, 12).value == "СТИ"
    assert ws.cell(2, 13).value == "карат"
    assert ws.cell(2, 17).value == 1407

    assert ws.cell(3, 1).value == "Отчет Марго.xlsx : Строка 65"
    assert ws.cell(3, 1).hyperlink.target.endswith("master.xlsx")
    assert ws.cell(3, 11).value == "ПРОВЕРИТЬ"
    assert ws.cell(3, 12).value == "СБИ"
    assert ws.cell(3, 17).value == 1930
    assert ws.cell(3, 18).value == "Не совпал исполнитель"

    assert ws.cell(4, 1).value == "ОШИБКА НЕТУ У КУРАТОРОВ"
    assert ws.cell(4, 1).hyperlink.target.endswith("rsch.xlsx")
    assert ws.cell(4, 11).value == "ОШИБКА"
    assert ws.cell(4, 12).value == "СТИ"
    assert ws.cell(4, 16).value == 6000000
    assert ws.cell(4, 18).value == "Нет у кураторов"

    assert ws.max_row == 4
    assert ws.cell(5, 18).value is None

    assert ws.cell(2, 11).fill.fgColor.rgb == "FF00B050"
    assert ws.cell(3, 11).fill.fgColor.rgb == "FFFFEB9C"
    assert ws.cell(4, 11).fill.fgColor.rgb == "FFFFC7CE"
    assert ws.cell(2, 11).comment is None
    assert ws.cell(2, 1).hyperlink.target.endswith("master.xlsx")
    assert ws.cell(3, 11).comment.text == "Не совпал исполнитель"
    assert ws.cell(3, 1).hyperlink.target.endswith("master.xlsx")
    assert ws.cell(4, 11).comment.text == "Нет у кураторов"
    assert ws.cell(4, 1).hyperlink.target.endswith("rsch.xlsx")
    assert ws.auto_filter.ref == "A1:R4"


def test_build_reconciliation_report_sets_readable_column_widths(tmp_path: Path) -> None:
    master_path = tmp_path / "master.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    output_path = tmp_path / "reconciliation.xlsx"
    _create_single_master_book(
        master_path,
        customer="Очень длинное название заказчика которое должно быть видно без ручного расширения",
        executor="СТИ",
        income=1234567890,
        expense=0,
    )
    _create_single_rsch_book(rsch_path)

    build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    wb = load_workbook(output_path)
    try:
        ws = wb["21.04.2026"]
        status_col = _find_header_col(ws, "Статус")
        income_col = _find_header_col(ws, "Приход")
        customer_col = _find_header_col(ws, "ЗАКАЗЧИК")

        assert ws.column_dimensions[ws.cell(1, status_col).column_letter].width >= 14
        assert ws.column_dimensions[ws.cell(1, income_col).column_letter].width >= 18
        assert ws.column_dimensions[ws.cell(1, customer_col).column_letter].width > 45
    finally:
        wb.close()


def test_build_reconciliation_report_sanitizes_formula_like_master_text(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    output_path = tmp_path / "reconciliation.xlsx"
    _create_single_master_book(
        master_path,
        source="+source",
        customer='=HYPERLINK("http://bad", "click")',
        executor="@executor",
    )
    _create_single_rsch_book(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 2
    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]
    assert ws.cell(2, 1).value == "'+source"
    assert ws.cell(2, 2).value == '\'=HYPERLINK("http://bad", "click")'
    assert ws.cell(2, 3).value == "'@executor"
    assert ws.cell(2, 5).value == 500000


def test_build_reconciliation_report_reads_via_local_copies(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    master_copy = tmp_path / "master-copy.xlsx"
    rsch_copy = tmp_path / "rsch-copy.xlsx"
    master_temp = tmp_path / "master-temp.xlsx"
    rsch_temp = tmp_path / "rsch-temp.xlsx"
    output_path = tmp_path / "reconciliation.xlsx"
    _create_master_book(master_path)
    _create_rsch_book(rsch_path)
    master_copy.write_bytes(master_path.read_bytes())
    rsch_copy.write_bytes(rsch_path.read_bytes())

    def fake_get_local_copy(path: str, drive_letters=("Q", "Z")):
        assert drive_letters == ("Q", "Z")
        if Path(path) == master_path:
            return str(master_copy), str(master_temp)
        if Path(path) == rsch_path:
            return str(rsch_copy), str(rsch_temp)
        raise AssertionError(path)

    with (
        patch(
            "core.infra.reconciliation_report.get_local_copy",
            side_effect=fake_get_local_copy,
        ) as copy_file,
        patch("core.infra.reconciliation_report.Path.unlink") as unlink,
    ):
        written = build_reconciliation_report(
            master_path,
            rsch_path,
            output_path,
            target_date=date(2026, 4, 21),
        )

    assert written == 3
    assert copy_file.call_count == 2
    assert unlink.call_count == 2
    assert all(call.kwargs == {"missing_ok": True} for call in unlink.call_args_list)


def test_build_combined_reconciliation_report_reads_via_local_copies(
    tmp_path: Path,
) -> None:
    general_path = tmp_path / "general.xlsx"
    boris_path = tmp_path / "boris.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    output_path = tmp_path / "combined.xlsx"
    _create_single_master_book(general_path)
    _create_single_master_book(boris_path, source="boris row")
    _create_single_rsch_book(rsch_path, duplicate=True)

    copy_map = {}
    for src in (general_path, boris_path, rsch_path):
        copy_path = tmp_path / f"{src.stem}-copy.xlsx"
        temp_path = tmp_path / f"{src.stem}-temp.xlsx"
        copy_path.write_bytes(src.read_bytes())
        copy_map[src] = (str(copy_path), str(temp_path))

    with (
        patch(
            "core.infra.reconciliation_report.get_local_copy",
            side_effect=lambda path, drive_letters=("Q", "Z"): copy_map[Path(path)],
        ) as copy_file,
        patch("core.infra.reconciliation_report.Path.unlink") as unlink,
    ):
        counts = build_combined_reconciliation_report(
            {"Общий": general_path, "Борис": boris_path},
            rsch_path,
            output_path,
            target_date=date(2026, 4, 21),
        )

    assert set(counts) == {"Общий", "Борис"}
    assert copy_file.call_count == 3
    assert unlink.call_count == 3
    assert all(call.kwargs == {"missing_ok": True} for call in unlink.call_args_list)


def test_build_combined_reconciliation_report_passes_custom_drive_letters(
    tmp_path: Path,
) -> None:
    general_path = tmp_path / "general.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    output_path = tmp_path / "combined.xlsx"
    _create_single_master_book(general_path)
    _create_single_rsch_book(rsch_path)

    def fake_get_local_copy(path: str, drive_letters=("Q", "Z")):
        assert drive_letters == ("R",)
        return path, None

    with patch(
        "core.infra.reconciliation_report.get_local_copy",
        side_effect=fake_get_local_copy,
    ) as copy_file:
        counts = build_combined_reconciliation_report(
            {"Общий": general_path},
            rsch_path,
            output_path,
            target_date=date(2026, 4, 21),
            drive_letters=("R",),
        )

    assert counts == {"Общий": 1}
    assert copy_file.call_count == 2


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


def test_build_reconciliation_report_falls_back_to_single_common_date_when_date_is_not_selected(
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
        target_date=None,
    )

    assert written == 3

    wb = load_workbook(output_path, data_only=False)
    assert wb.sheetnames == ["21.04.2026"]


def test_build_reconciliation_report_rejects_missing_selected_date_even_with_single_common_date(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    output_path = tmp_path / "reconciliation.xlsx"
    _create_master_book(master_path)
    _create_rsch_book(rsch_path)

    with pytest.raises(ValueError, match="Не найден лист за дату 01.05.2026"):
        build_reconciliation_report(
            master_path,
            rsch_path,
            output_path,
            target_date=date(2026, 5, 1),
        )


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
    assert [ws.cell(1, col).value for col in range(1, 20)] == [
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
        "Статус",
        "ИСПОЛНИТЕЛЬ",
        "ЗАКАЗЧИК",
        "Контрагент",
        "Комментарий",
        "Приход",
        "Расход",
        "Причина",
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
        "% посредника 1",
        "посредник 1(кэш)",
        "посредник 2",
        "Статус",
        "ИСПОЛНИТЕЛЬ",
        "ЗАКАЗЧИК",
        "Контрагент",
        "Комментарий",
        "Приход",
        "Расход",
        "Причина",
    ]
    assert "фильтры" not in headers
    assert "ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ" not in headers
    assert "курс" not in headers
    assert "сумма" not in headers
    assert "валюта" not in headers
    assert ws.cell(2, 1).value == "Иван"
    assert ws.cell(2, 11).value == "СВЕРЕНО"


def test_build_combined_reconciliation_report_writes_general_boris_ivan_sheets(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
    boris_path = tmp_path / "boris_report.xlsx"
    ivan_path = tmp_path / "ivan_report.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    output_path = tmp_path / "combined_reconciliation.xlsx"

    _create_master_book(master_path)

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
            "Борис",
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
    wb.save(boris_path)

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
    wb.save(ivan_path)
    _create_rsch_book(rsch_path)

    counts = build_combined_reconciliation_report(
        {
            "Общий": master_path,
            "Борис": boris_path,
            "Иван": ivan_path,
        },
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert counts == {"Общий": 3, "Борис": 1, "Иван": 1}

    wb = load_workbook(output_path, data_only=False)
    assert wb.sheetnames == ["Общий", "Борис", "Иван"]
    assert wb["Общий"].cell(1, 1).value == "Источник"
    assert wb["Борис"].cell(1, 10).value == "% посредник 2"
    assert wb["Борис"].cell(1, 12).value == "Статус"
    assert wb["Иван"].cell(1, 1).value == "Сотрудник"
    ivan_headers = [
        wb["Иван"].cell(1, col).value for col in range(1, wb["Иван"].max_column + 1)
    ]
    assert "фильтры" not in ivan_headers
    assert "ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ" not in ivan_headers
    assert "курс" not in ivan_headers
    assert "сумма" not in ivan_headers
    assert "валюта" not in ivan_headers
    assert ivan_headers[-1] == "Причина"


def test_combined_reconciliation_suppresses_rsch_only_rows_verified_in_prior_sheet(
    tmp_path: Path,
) -> None:
    general_path = tmp_path / "general.xlsx"
    boris_path = tmp_path / "boris.xlsx"
    ivan_path = tmp_path / "ivan.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    output_path = tmp_path / "combined.xlsx"
    _create_single_master_book(general_path)
    _create_empty_master_book(boris_path)
    _create_empty_master_book(ivan_path)
    _create_single_rsch_book(rsch_path)

    counts = build_combined_reconciliation_report(
        {"Общий": general_path, "Борис": boris_path, "Иван": ivan_path},
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert counts == {"Общий": 1, "Борис": 0, "Иван": 0}
    wb = load_workbook(output_path, data_only=False)
    assert wb["Общий"].cell(2, _find_status_col(wb["Общий"])).value == "СВЕРЕНО"
    assert wb["Борис"].max_row == 1
    assert wb["Иван"].max_row == 1


def test_combined_reconciliation_suppresses_rsch_only_rows_matched_in_later_sheet(
    tmp_path: Path,
) -> None:
    general_path = tmp_path / "general.xlsx"
    boris_path = tmp_path / "boris.xlsx"
    ivan_path = tmp_path / "ivan.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    output_path = tmp_path / "combined.xlsx"
    _create_empty_master_book(general_path)
    _create_single_master_book(boris_path)
    _create_empty_master_book(ivan_path)
    _create_single_rsch_book(rsch_path)

    counts = build_combined_reconciliation_report(
        {"Общий": general_path, "Борис": boris_path, "Иван": ivan_path},
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert counts == {"Общий": 0, "Борис": 1, "Иван": 0}
    wb = load_workbook(output_path, data_only=False)
    assert wb["Общий"].max_row == 1
    assert wb["Борис"].cell(2, _find_status_col(wb["Борис"])).value == "СВЕРЕНО"
    assert wb["Иван"].max_row == 1


def test_combined_reconciliation_keeps_unmatched_rsch_only_row_once(
    tmp_path: Path,
) -> None:
    general_path = tmp_path / "general.xlsx"
    boris_path = tmp_path / "boris.xlsx"
    ivan_path = tmp_path / "ivan.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    output_path = tmp_path / "combined.xlsx"
    _create_empty_master_book(general_path)
    _create_empty_master_book(boris_path)
    _create_empty_master_book(ivan_path)
    _create_single_rsch_book(rsch_path)

    counts = build_combined_reconciliation_report(
        {"Общий": general_path, "Борис": boris_path, "Иван": ivan_path},
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert counts == {"Общий": 1, "Борис": 0, "Иван": 0}
    wb = load_workbook(output_path, data_only=False)
    status_col = _find_status_col(wb["Общий"])
    assert wb["Общий"].cell(2, status_col).value == "ОШИБКА"
    assert wb["Общий"].cell(2, _find_header_col(wb["Общий"], "Причина")).value == "Нет у кураторов"
    assert wb["Борис"].max_row == 1
    assert wb["Иван"].max_row == 1


def test_combined_reconciliation_suppression_uses_physical_rsch_rows_not_values(
    tmp_path: Path,
) -> None:
    general_path = tmp_path / "general.xlsx"
    boris_path = tmp_path / "boris.xlsx"
    ivan_path = tmp_path / "ivan.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    output_path = tmp_path / "combined.xlsx"
    _create_single_master_book(general_path)
    _create_empty_master_book(boris_path)
    _create_empty_master_book(ivan_path)
    _create_single_rsch_book(rsch_path, duplicate=True)

    counts = build_combined_reconciliation_report(
        {"Общий": general_path, "Борис": boris_path, "Иван": ivan_path},
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert counts == {"Общий": 2, "Борис": 0, "Иван": 0}
    wb = load_workbook(output_path, data_only=False)
    general_ws = wb["Общий"]
    status_col = _find_status_col(general_ws)
    reason_col = _find_header_col(general_ws, "Причина")
    assert general_ws.cell(3, status_col).value == "ОШИБКА"
    assert general_ws.cell(3, status_col).comment.text == "Нет у кураторов"
    assert general_ws.cell(3, reason_col).value == "Нет у кураторов"
    assert wb["Борис"].max_row == 1
    assert wb["Иван"].max_row == 1


def test_combined_reconciliation_does_not_suppress_sheet_own_master_rows(
    tmp_path: Path,
) -> None:
    general_path = tmp_path / "general.xlsx"
    boris_path = tmp_path / "boris.xlsx"
    ivan_path = tmp_path / "ivan.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    output_path = tmp_path / "combined.xlsx"
    _create_single_master_book(general_path, source="general row")
    _create_single_master_book(boris_path, source="boris row")
    _create_empty_master_book(ivan_path)
    _create_single_rsch_book(rsch_path)

    counts = build_combined_reconciliation_report(
        {"Общий": general_path, "Борис": boris_path, "Иван": ivan_path},
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert counts == {"Общий": 1, "Борис": 1, "Иван": 0}
    wb = load_workbook(output_path, data_only=False)
    assert wb["Общий"].cell(2, _find_status_col(wb["Общий"])).value == "СВЕРЕНО"
    assert wb["Борис"].cell(2, _find_status_col(wb["Борис"])).value == "СВЕРЕНО"


def test_combined_reconciliation_uses_stable_sheet_priority_for_suppression(
    tmp_path: Path,
) -> None:
    general_path = tmp_path / "general.xlsx"
    boris_path = tmp_path / "boris.xlsx"
    ivan_path = tmp_path / "ivan.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    output_path = tmp_path / "combined.xlsx"
    _create_single_master_book(general_path)
    _create_empty_master_book(boris_path)
    _create_empty_master_book(ivan_path)
    _create_single_rsch_book(rsch_path)

    counts = build_combined_reconciliation_report(
        {"Борис": boris_path, "Иван": ivan_path, "Общий": general_path},
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert counts == {"Общий": 1, "Борис": 0, "Иван": 0}
    wb = load_workbook(output_path, data_only=False)
    assert wb.sheetnames == ["Общий", "Борис", "Иван"]


def test_combined_reconciliation_requires_date_when_candidate_dates_differ(
    tmp_path: Path,
) -> None:
    general_path = tmp_path / "general.xlsx"
    boris_path = tmp_path / "boris.xlsx"
    ivan_path = tmp_path / "ivan.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    output_path = tmp_path / "combined.xlsx"

    _create_single_master_book(general_path)
    _create_single_master_book(ivan_path)

    wb = Workbook()
    ws = wb.active
    ws.title = "22.04.2026"
    ws.append(["Источник", "ЗАКАЗЧИК", "ИСПОЛНИТЕЛЬ", "Приход", "Расход", "Комиссия", "ИТОГ"])
    ws.append(["boris row", "Илон", "СТИНГ", 0, 500000, 0, -500000])
    wb.save(boris_path)

    wb = Workbook()
    ws = wb.active
    ws.title = "21.04"
    ws.append(["ИСПОЛНИТЕЛЬ", "ЗАКАЗЧИК", "Контрагент", "Комментарий", "Приход", "Расход", "Источник"])
    ws.append(["СТИНГ", "илон", "реестр зп", "", 0, 500000, "rsch row 21"])
    ws = wb.create_sheet("22.04")
    ws.append(["ИСПОЛНИТЕЛЬ", "ЗАКАЗЧИК", "Контрагент", "Комментарий", "Приход", "Расход", "Источник"])
    ws.append(["СТИНГ", "илон", "реестр зп", "", 0, 500000, "rsch row 22"])
    wb.save(rsch_path)

    with pytest.raises(ValueError, match="несколько общих дат"):
        build_combined_reconciliation_report(
            {"Общий": general_path, "Борис": boris_path, "Иван": ivan_path},
            rsch_path,
            output_path,
            target_date=None,
        )


def test_combined_reconciliation_reports_missing_master_label_when_date_is_not_selected(
    tmp_path: Path,
) -> None:
    general_path = tmp_path / "general.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    output_path = tmp_path / "combined.xlsx"
    _create_single_master_book(general_path)
    _create_single_rsch_book(rsch_path)

    with pytest.raises(FileNotFoundError, match="Не найден мастер-отчет Борис"):
        build_combined_reconciliation_report(
            {
                "Общий": general_path,
                "Борис": tmp_path / "missing_boris.xlsx",
                "Иван": general_path,
            },
            rsch_path,
            output_path,
            target_date=None,
        )


def test_build_reconciliation_report_matches_rsch_comment_when_customer_is_short(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
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
            "% посредника",
            "посредник 1(кэш)",
            "посредник 2",
        ]
    )
    ws.append(
        [
            "Отчет Надежда Р.xlsx : Строка 31",
            "ОперационкаGabriel_СТИНГ",
            "СТИНГ СБ",
            0,
            143031,
            0,
            -143031,
            0,
            0,
            0,
        ]
    )
    wb.save(master_path)

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
            "Источник",
        ]
    )
    ws.append(
        [
            "СТИНГ",
            "операционка габриэль",
            "реестр зп",
            "НадеждаР_ОперационкаGabriel_Стинг_Сбер_РН_21.04.2026_143031",
            0,
            143031,
            "rsch | row 10",
        ]
    )
    wb.save(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 1
    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]
    assert ws.cell(2, 11).value == "СВЕРЕНО"


def test_build_reconciliation_report_matches_rsch_comment_with_extra_master_prefix(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
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
            "% посредника",
            "посредник 1(кэш)",
            "посредник 2",
        ]
    )
    ws.append(
        [
            "Отчет Надежда Р.xlsx : Строка 31",
            "Готово_ч9_НадеждаР_ОперационкаGabriel_Стинг_Сбер_НН_21.04.2026_143031.0",
            "стинг сб",
            0,
            143031,
            0,
            -143031,
            0,
            0,
            0,
        ]
    )
    wb.save(master_path)

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
            "Источник",
        ]
    )
    ws.append(
        [
            "СТИНГ",
            "операционка габриель",
            "реестр зп",
            "НадеждаР_ОперационкаGabriel_Стинг_Сбер_НН_21.04.2026_143031.0 (143 031,00)",
            0,
            143031,
            "rsch | row 441",
        ]
    )
    wb.save(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 1
    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]
    assert ws.cell(2, 1).value == "Отчет Надежда Р.xlsx : Строка 31"
    assert ws.cell(2, 11).value == "СВЕРЕНО"
    assert ws.cell(2, 15).value.startswith("НадеждаР_ОперационкаGabriel")


def test_build_reconciliation_report_does_not_match_customer_by_amount_date_executor_tokens(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    output_path = tmp_path / "reconciliation.xlsx"

    _create_single_master_book(
        master_path,
        customer="Аэрофлот_стинг сбер_НН_21.04.2026_500000.0",
        executor="стинг сбер",
        expense=500000,
    )

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
            "Источник",
        ]
    )
    ws.append(
        [
            "СТИНГ",
            "илон",
            "реестр зп",
            "БорисЖ_ИЛОН_Стинг_Сбер_РН_21.04.2026_500000.0 (500 000,00)",
            0,
            500000,
            "rsch row",
        ]
    )
    wb.save(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 2
    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]
    status_col = _find_status_col(ws)
    comments = sorted(
        ws.cell(row, status_col).comment.text
        for row in range(2, 4)
        if ws.cell(row, status_col).comment is not None
    )
    assert comments == ["Нет в РСЧ", "Нет у кураторов"]


def test_build_reconciliation_report_matches_rsch_contractor_by_two_strong_tokens(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
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
            "% посредника",
            "посредник 1(кэш)",
            "посредник 2",
        ]
    )
    ws.append(
        [
            "отчет кира стафф1.xlsx : Строка 34",
            "Пипл крафт альфа  (Статус-Независимость)",
            "Пипл крафт альфа",
            496800,
            0,
            0,
            496800,
            0,
            0,
            0,
        ]
    )
    wb.save(master_path)

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
            "Источник",
        ]
    )
    ws.append(
        [
            "ПИПЛ КРАФТ",
            "чоп-1",
            'ООО ЧОП"СТАТУС-НЕЗАВИСИМОСТЬ" Р/С 40702810429170008197',
            None,
            496800,
            0,
            "rsch | row 2",
        ]
    )
    wb.save(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 1
    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]
    assert ws.cell(2, 11).value == "СВЕРЕНО"


def test_build_reconciliation_report_matches_uk_allyans_alias_to_uk_a(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
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
        ]
    )
    ws.append(
        [
            "Отчет Надежда Р.xlsx : Строка 16",
            "Готово_НадеждаР_ОперационкаGabriel_УК АЛЬЯНС АЛЬФА_РН_21.04.2026_158350.0",
            "ук альфа",
            0,
            158350,
            0,
            -158350,
        ]
    )
    wb.save(master_path)

    wb = Workbook()
    ws = wb.active
    ws.title = "21.04"
    ws.append(["ИСПОЛНИТЕЛЬ", "ЗАКАЗЧИК", "Контрагент", "Комментарий", "Приход", "Расход", "Источник"])
    ws.append(["УК А", "операционка габриэль", "реестр зп", "", 0, 158350, "rsch row"])
    wb.save(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 1
    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]
    status_col = _find_status_col(ws)
    assert ws.cell(2, status_col).value == "СВЕРЕНО"


def test_build_reconciliation_report_does_not_verify_on_text_and_amount_with_wrong_executor(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
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
        ]
    )
    ws.append(["master row", "Пипл крафт альфа Статус-Независимость", "ПИПЛ КРАФТ", 496800, 0, 0, 496800])
    wb.save(master_path)

    wb = Workbook()
    ws = wb.active
    ws.title = "21.04"
    ws.append(["ИСПОЛНИТЕЛЬ", "ЗАКАЗЧИК", "Контрагент", "Комментарий", "Приход", "Расход", "Источник"])
    ws.append(["СТИНГ", "чоп-1", "ООО СТАТУС-НЕЗАВИСИМОСТЬ", "", 496800, 0, "rsch row"])
    wb.save(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 1
    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]
    status_col = _find_status_col(ws)
    assert ws.cell(2, status_col).value == "ПРОВЕРИТЬ"
    assert ws.cell(2, status_col).comment.text == "Не совпал исполнитель"


def test_build_reconciliation_report_verifies_common_executor_abbreviations(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
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
        ]
    )
    ws.append(["mos row", "Дядя ООО Сибирская управляющая компания", "МосАльфа", 0, 30324, 0, -30324])
    ws.append(["people row", "Слот Готово ПиплКрафт Альфа", "ПК Альфа", 0, 2080, 0, -2080])
    ws.append(["press row", "Рубашка ПРЕССБУК Альфа", "ПБ АЛЬФА", 0, 130000, 0, -130000])
    ws.append(["sss row", "Очки Спецстаффсервис Сбер", "ССС Сбер", 0, 749800, 0, -749800])
    ws.append(["vb row", "Анастасия рекрутинг выход ВБ", "воркбрайт сбер", 0, 2907, 0, -2907])
    wb.save(master_path)

    wb = Workbook()
    ws = wb.active
    ws.title = "21.04"
    ws.append(["ИСПОЛНИТЕЛЬ", "ЗАКАЗЧИК", "Контрагент", "Комментарий", "Приход", "Расход", "Источник"])
    ws.append(["МОС", "дядя", "ООО Сибирская Управляющая Компания", "", 0, 30324, "rsch mos"])
    ws.append(["ПИПЛ КРАФТ", "Слот", "реестр зп", "", 0, 2080, "rsch people"])
    ws.append(["ПРЕССБУК", "Рубашка", "реестр зп", "", 0, 130000, "rsch press"])
    ws.append(["СПЕЦСТАФФСЕРВИС", "Очки", "реестр зп", "", 0, 749800, "rsch sss"])
    ws.append(["ВБ", "анастасия рекрутинг", "Интернет Решения", "", 0, 2907, "rsch vb"])
    wb.save(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 5
    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]
    status_col = _find_status_col(ws)
    statuses = [ws.cell(row, status_col).value for row in range(2, 7)]
    assert statuses == ["СВЕРЕНО"] * 5


def test_build_reconciliation_report_keeps_unapproved_executor_alias_for_review(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
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
        ]
    )
    ws.append(["master row", "свитер билл альфа оплата патентов", "БИЛЛ АЛЬФА", 0, 35808, 0, -35808])
    wb.save(master_path)

    wb = Workbook()
    ws = wb.active
    ws.title = "21.04"
    ws.append(["ИСПОЛНИТЕЛЬ", "ЗАКАЗЧИК", "Контрагент", "Комментарий", "Приход", "Расход", "Источник"])
    ws.append(["БИЛЛТРЕЙД", "свитер", "патент", "", 0, 35808, "rsch row"])
    wb.save(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 1
    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]
    status_col = _find_status_col(ws)
    assert ws.cell(2, status_col).value == "ПРОВЕРИТЬ"
    assert ws.cell(2, status_col).comment.text == "Не совпал исполнитель"


def test_build_reconciliation_report_prioritizes_full_match_over_earlier_executor_mismatch(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
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
        ]
    )
    ws.append(["boris row 146", 'УМКА ( ООО "Умма-Групп") Выплата ЗП реестра 4315', "ПиплКрафт, Альфа", 0, 90000, 27, -123287.67])
    ws.append(["boris row 148", 'УМКА ( ООО "Умма-Групп") Выплата ЗП реестра 4369', "УК Альянс, Альфа", 0, 90000, 27, -123287.67])
    wb.save(master_path)

    wb = Workbook()
    ws = wb.active
    ws.title = "21.04"
    ws.append(["ИСПОЛНИТЕЛЬ", "ЗАКАЗЧИК", "Контрагент", "Комментарий", "Приход", "Расход", "Источник"])
    ws.append(["УК А", "умка", "реестр зп", "", 0, 90000, "rsch row"])
    wb.save(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 2
    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]
    status_col = _find_status_col(ws)
    rows_by_source = {
        ws.cell(row, 1).value: row
        for row in range(2, ws.max_row + 1)
    }
    assert ws.cell(rows_by_source["boris row 148"], status_col).value == "СВЕРЕНО"
    assert ws.cell(rows_by_source["boris row 146"], status_col).value == "ОШИБКА"
    assert ws.cell(rows_by_source["boris row 146"], status_col).comment.text == "Нет в РСЧ"


def test_build_reconciliation_report_does_not_verify_on_text_and_executor_with_wrong_amount(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
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
        ]
    )
    ws.append(["master row", "Пипл крафт альфа Статус-Независимость", "ПИПЛ КРАФТ", 496800, 0, 0, 496800])
    wb.save(master_path)

    wb = Workbook()
    ws = wb.active
    ws.title = "21.04"
    ws.append(["ИСПОЛНИТЕЛЬ", "ЗАКАЗЧИК", "Контрагент", "Комментарий", "Приход", "Расход", "Источник"])
    ws.append(["ПИПЛ КРАФТ", "чоп-1", "ООО СТАТУС-НЕЗАВИСИМОСТЬ", "", 100, 0, "rsch row"])
    wb.save(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 1
    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]
    status_col = _find_status_col(ws)
    assert ws.cell(2, status_col).value == "ПРОВЕРИТЬ"
    assert ws.cell(2, status_col).comment.text == "Не совпала сумма"


def test_build_reconciliation_report_does_not_pair_weak_text_without_executor_or_amount(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
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
        ]
    )
    ws.append(["master row", "ПАТЕНТ СПЕЦСТАФФСЕРВИС Альфа", "ВБ АЛЬФА", 0, 100, 0, -100])
    wb.save(master_path)

    wb = Workbook()
    ws = wb.active
    ws.title = "21.04"
    ws.append(["ИСПОЛНИТЕЛЬ", "ЗАКАЗЧИК", "Контрагент", "Комментарий", "Приход", "Расход", "Источник"])
    ws.append(["СТИ", "ПАТЕНТ СПЕЦСТАФФСЕРВИС", "", "", 0, 80000, "rsch row"])
    wb.save(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 2
    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]
    status_col = _find_status_col(ws)
    comments = sorted(
        ws.cell(row, status_col).comment.text
        for row in range(2, 4)
        if ws.cell(row, status_col).comment is not None
    )
    assert comments == ["Нет в РСЧ", "Нет у кураторов"]


def test_build_reconciliation_report_marks_unique_weak_customer_match_for_review(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
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
        ]
    )
    ws.append(
        [
            "matvey row 12",
            "Гетворк ВБ Альфа РТ 21.04 2 990 (4192) - Проктер 2_АТ_Труд._15.04.26",
            "ВБ Альфа",
            0,
            2990,
            20,
            -3737.5,
        ]
    )
    wb.save(master_path)

    wb = Workbook()
    ws = wb.active
    ws.title = "21.04"
    ws.append(["ИСПОЛНИТЕЛЬ", "ЗАКАЗЧИК", "Контрагент", "Комментарий", "Приход", "Расход", "Источник"])
    ws.append(["ВБ", "гетворк м", "реестр зп", "", 0, 2990, "rsch row"])
    wb.save(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 1
    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]
    status_col = _find_status_col(ws)
    assert ws.cell(2, status_col).value == "ПРОВЕРИТЬ"
    assert ws.cell(2, status_col).comment.text == "Похожий заказчик"


def test_build_reconciliation_report_does_not_pair_ambiguous_weak_customer_match(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
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
        ]
    )
    ws.append(["master row", "Гетворк ВБ Альфа Проктер", "ВБ Альфа", 0, 2990, 0, -2990])
    wb.save(master_path)

    wb = Workbook()
    ws = wb.active
    ws.title = "21.04"
    ws.append(["ИСПОЛНИТЕЛЬ", "ЗАКАЗЧИК", "Контрагент", "Комментарий", "Приход", "Расход", "Источник"])
    ws.append(["ВБ", "гетворк м", "реестр зп", "", 0, 2990, "rsch row 1"])
    ws.append(["ВБ", "гетворк алиса", "реестр зп", "", 0, 2990, "rsch row 2"])
    wb.save(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 3
    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]
    status_col = _find_status_col(ws)
    comments = sorted(
        ws.cell(row, status_col).comment.text
        for row in range(2, 5)
        if ws.cell(row, status_col).comment is not None
    )
    assert comments == ["Нет в РСЧ", "Нет у кураторов", "Нет у кураторов"]


def test_build_reconciliation_report_skips_rsch_transfer_comments(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
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
        ]
    )
    wb.save(master_path)

    wb = Workbook()
    ws = wb.active
    ws.title = "21.04"
    ws.append(["ИСПОЛНИТЕЛЬ", "ЗАКАЗЧИК", "Контрагент", "Комментарий", "Приход", "Расход", "Источник"])
    ws.append(["ВБ", "внутренний", "", "ПЕРЕВОД между РСЧ", 0, 100, "transfer row"])
    ws.append(["ВБ", "переводстрой", "", "обычная операция", 0, 200, "normal row"])
    wb.save(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 1
    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]
    headers = [ws.cell(1, col_idx).value for col_idx in range(1, ws.max_column + 1)]
    rsch_customer_col = headers.index("ЗАКАЗЧИК", headers.index("ИТОГ") + 1) + 1
    assert ws.cell(2, rsch_customer_col).value == "переводстрой"
    status_col = _find_status_col(ws)
    assert ws.cell(2, status_col).comment.text == "Нет у кураторов"


def test_build_reconciliation_report_does_not_match_executor_by_inner_substring(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
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
        ]
    )
    ws.append(["master row", "Анастасия рекрутинг", "прессбук альфа", 0, 100, 0, -100])
    wb.save(master_path)

    wb = Workbook()
    ws = wb.active
    ws.title = "21.04"
    ws.append(["ИСПОЛНИТЕЛЬ", "ЗАКАЗЧИК", "Контрагент", "Комментарий", "Приход", "Расход", "Источник"])
    ws.append(["УК А", "Анастасия рекрутинг", "", "", 0, 200, "rsch row"])
    wb.save(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 2
    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]
    status_col = _find_status_col(ws)
    comments = sorted(
        ws.cell(row, status_col).comment.text
        for row in range(2, 4)
        if ws.cell(row, status_col).comment is not None
    )
    assert comments == ["Нет в РСЧ", "Нет у кураторов"]


def test_build_reconciliation_report_matches_uk_allyans_executor_to_uk_a(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
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
        ]
    )
    ws.append(["master row", "РЕТРО", "УК Альянс Сбер", 0, 29605, 0, -29605])
    wb.save(master_path)

    wb = Workbook()
    ws = wb.active
    ws.title = "21.04"
    ws.append(["ИСПОЛНИТЕЛЬ", "ЗАКАЗЧИК", "Контрагент", "Комментарий", "Приход", "Расход", "Источник"])
    ws.append(["УК А", "ретро", "", "", 0, 29605, "rsch row"])
    wb.save(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 1
    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]
    status_col = _find_status_col(ws)
    assert ws.cell(2, status_col).value == "СВЕРЕНО"


def test_build_reconciliation_report_skips_service_rsch_customers_and_uses_soft_error_fill(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    output_path = tmp_path / "reconciliation.xlsx"
    _create_master_book(master_path)

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
            "Источник",
        ]
    )
    ws.append(["СБИ", "комиссия", "", "", 0, 100, "service | row 1"])
    ws.append(["СБИ", "налог", "", "", 0, 200, "service | row 2"])
    ws.append(["СБИ", "% по депозиту", "", "", 0, 300, "service | row 3"])
    wb.save(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 2
    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]
    values = [ws.cell(row, 13).value for row in range(2, ws.max_row + 1)]
    assert "комиссия" not in values
    assert "налог" not in values
    assert "% по депозиту" not in values
    assert ws.cell(2, 11).fill.fgColor.rgb != "FFFF0000"


def test_build_reconciliation_report_skips_master_rows_without_income_or_expense(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
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
        ]
    )
    ws.append(["Иван", "Бекхем", "Доха Катар", 0, 0, 0, 0])
    wb.save(master_path)

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
            "Источник",
        ]
    )
    wb.save(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 0
    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]
    assert ws.max_row == 1


@pytest.mark.parametrize(
    "filter_value",
    ["Доп сф", "Касса", "Зачет", "Посредник", "Корректировка"],
)
def test_build_reconciliation_report_skips_curator_rows_with_excluded_filters(
    tmp_path: Path,
    filter_value: str,
) -> None:
    master_path = tmp_path / "curator.xlsx"
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
            "Фильтры",
        ]
    )
    ws.append(
        [
            "Отчет Бориса.xlsx : Строка 10",
            "ООО Ромашка",
            "СТИ",
            0,
            500,
            0,
            -500,
            filter_value,
        ]
    )
    wb.save(master_path)

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
            "Источник",
        ]
    )
    ws.append(["СТИ", "ООО Ромашка", "", "", 0, 500, "rsch row 1"])
    wb.save(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    assert written == 0
    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]
    assert ws.max_row == 1


def test_build_reconciliation_report_suppresses_rsch_paired_with_excluded_filter_master(
    tmp_path: Path,
) -> None:
    """Rsch-строка, матчащаяся к мастеру с фильтром (доп.сф), не появляется как 'нет в РСЧ'."""
    master_path = tmp_path / "curator.xlsx"
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
            "Фильтры",
        ]
    )
    # Мастер-строка с фильтром "доп.сф" — должна быть подавлена и не светиться
    ws.append(
        [
            "Отчет Антон.xlsx : Строка 1",
            "Проект Геометрия",
            "МОСАЛЬФА",
            0,
            1000,
            0,
            -1000,
            "доп.сф",
        ]
    )
    # Контрольная мастер-строка без фильтра — попадёт в отчёт
    ws.append(
        [
            "Отчет Антон.xlsx : Строка 2",
            "Проект Атлант",
            "МОСАЛЬФА",
            0,
            2000,
            0,
            -2000,
            "",
        ]
    )
    wb.save(master_path)

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
            "Источник",
        ]
    )
    # Rsch-пара к фильтрованной строке — должна быть подавлена
    ws.append(["МОСАЛЬФА", "Проект Геометрия", "", "", 0, 1000, "rsch row 1"])
    # Rsch-only — не имеет пары, должна светиться как НЕТ В РСЧ
    ws.append(["МОСАЛЬФА", "Проект Гранит", "", "", 0, 2000, "rsch row 2"])
    wb.save(rsch_path)

    written = build_reconciliation_report(
        master_path,
        rsch_path,
        output_path,
        target_date=date(2026, 4, 21),
    )

    # В отчёте: 1 (Атлант - нет в РСЧ) + 1 (Гранит - rsch-only)
    assert written == 2
    wb = load_workbook(output_path, data_only=False)
    ws = wb["21.04.2026"]

    # Берём ОБЕ колонки "ЗАКАЗЧИК" (мастер-секция и rsch-секция)
    customer_cols = [
        cell.column for cell in ws[1] if cell.value == "ЗАКАЗЧИК"
    ]
    assert len(customer_cols) >= 2

    customers_in_report = set()
    for col in customer_cols:
        for row in range(2, ws.max_row + 1):
            val = str(ws.cell(row, col).value or "").strip()
            if val:
                customers_in_report.add(val)
    # Геометрия (мастер с фильтром) НЕ должна появиться
    assert "Проект Геометрия" not in customers_in_report
    # Атлант (без фильтра, нет пары) должна появиться
    assert "Проект Атлант" in customers_in_report
    # Гранит (rsch-only) должна появиться
    assert "Проект Гранит" in customers_in_report



def test_build_reconciliation_report_rejects_invalid_master_amount(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
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
        ]
    )
    ws.append(["master row", "Илон", "СТИНГ", 0, "не число", 0, 0])
    wb.save(master_path)
    _create_single_rsch_book(rsch_path)

    with pytest.raises(ValueError, match="Некорректное числовое значение"):
        build_reconciliation_report(
            master_path,
            rsch_path,
            output_path,
            target_date=date(2026, 4, 21),
        )

    assert not output_path.exists()


def test_build_reconciliation_report_rejects_invalid_rsch_amount(
    tmp_path: Path,
) -> None:
    master_path = tmp_path / "master.xlsx"
    rsch_path = tmp_path / "rsch.xlsx"
    output_path = tmp_path / "reconciliation.xlsx"
    _create_single_master_book(master_path)

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
            "Источник",
        ]
    )
    ws.append(["СТИНГ", "илон", "реестр зп", "", 0, "не число", "rsch row 1"])
    wb.save(rsch_path)

    with pytest.raises(ValueError, match="Некорректное числовое значение"):
        build_reconciliation_report(
            master_path,
            rsch_path,
            output_path,
            target_date=date(2026, 4, 21),
        )

    assert not output_path.exists()
