import pytest
import os
from pathlib import Path
from decimal import Decimal
from datetime import datetime
from unittest.mock import patch, MagicMock
from core.infra.ingestion_reader import extract_date_from_sheet
from core.infra.ingestion_reader import CalamineReader
from core.infra.ingestion_engine import IngestionEngine


def test_extract_date_from_sheet():
    assert extract_date_from_sheet("01.01.2026") == "01.01.2026"
    assert extract_date_from_sheet("01,01,2026") == "01.01.2026"
    assert extract_date_from_sheet("Sheet 01.01") is None
    assert extract_date_from_sheet("15.04.26") == "15.04.2026"
    assert extract_date_from_sheet("No date here") is None
    assert extract_date_from_sheet("32.01.2026") is None  # Invalid date
    assert extract_date_from_sheet("31.12") is None
    assert extract_date_from_sheet("05.01") is None


def test_ingestion_engine_scan_directory(tmp_path):
    engine = IngestionEngine({})

    # Create some files
    (tmp_path / "test1.xlsx").write_text("content")
    (tmp_path / "test2.xlsb").write_text("content")
    (tmp_path / "test3.txt").write_text("content")
    (tmp_path / "~$test4.xlsx").write_text("content")

    res = engine.scan_directory(tmp_path)
    assert len(res) == 2
    paths = [r["path"] for r in res]
    assert any("test1.xlsx" in p for p in paths)
    assert any("test2.xlsb" in p for p in paths)
    assert not any("test3.txt" in p for p in paths)
    assert not any("~$test4.xlsx" in p for p in paths)


def test_calamine_reader_map_columns():
    markers = {
        "amount": "сумма платежа",
        "customer": "заказчик",
        "commission": "комиссия",
    }
    aliases = {"amount": ["бн"], "customer": ["агент"]}
    reader = CalamineReader(markers, aliases)

    header = ["Дата", "Заказчик", "Сумма платежа", "Комиссия"]
    col_map, used_aliases = reader._map_columns(header)
    assert col_map["customer"] == 1
    assert col_map["amount"] == 2
    assert col_map["commission"] == 3
    assert not used_aliases

    header_aliases = ["Дата", "Агент", "БН", "Комиссия"]
    col_map, used_aliases = reader._map_columns(header_aliases)
    assert col_map["customer"] == 1
    assert col_map["amount"] == 2
    assert used_aliases


def test_calamine_reader_read_xlsx(tmp_path, create_temp_xlsx):
    markers = {
        "amount": "сумма",
        "customer": "заказчик",
        "income": "приход",
        "expense": "расход",
    }
    aliases = {
        "amount": ["сумма"],
        "income": ["приход"],
        "expense": ["расход"],
        "customer": ["заказчик"],
    }
    reader = CalamineReader(markers, aliases)

    data = [
        ["сумма", "заказчик", "приход", "расход"],
        [100, "Client A", 100, 0],
        [200, "Client B", 200, 0],
    ]
    file_path = tmp_path / "test.xlsx"
    create_temp_xlsx(file_path, data, sheet_name="01.01.2026")

    res = reader.read(file_path)
    assert len(res) == 2
    assert res[0]["amount"] == Decimal("100.00")
    assert res[0]["customer"] == "Client A"
    assert res[0]["date"] == "01.01.2026"


def test_calamine_reader_read_filters_target_date_sheets(tmp_path):
    import openpyxl

    markers = {
        "amount": "сумма",
        "customer": "заказчик",
        "income": "приход",
        "expense": "расход",
    }
    aliases = {
        "amount": ["сумма"],
        "income": ["приход"],
        "expense": ["расход"],
        "customer": ["заказчик"],
    }
    reader = CalamineReader(markers, aliases)

    file_path = tmp_path / "dated_sheets.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "12.04.2026"
    ws.append(["сумма", "заказчик", "приход", "расход"])
    ws.append([100, "Wrong Day", 100, 0])
    ws = wb.create_sheet("13.04.2026")
    ws.append(["сумма", "заказчик", "приход", "расход"])
    ws.append([200, "Right Day", 200, 0])
    wb.save(file_path)

    rows = reader.read(file_path, target_date_str="13.04.2026")

    assert [row["customer"] for row in rows] == ["Right Day"]


def test_calamine_reader_read_ignores_sheets_without_year(tmp_path):
    import openpyxl

    markers = {
        "amount": "сумма",
        "customer": "заказчик",
        "income": "приход",
        "expense": "расход",
    }
    aliases = {
        "amount": ["сумма"],
        "income": ["приход"],
        "expense": ["расход"],
        "customer": ["заказчик"],
    }
    reader = CalamineReader(markers, aliases)

    file_path = tmp_path / "year_required.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "13.04"
    ws.append(["сумма", "заказчик", "приход", "расход"])
    ws.append([100, "No Year", 100, 0])
    ws = wb.create_sheet("13.04.2026")
    ws.append(["сумма", "заказчик", "приход", "расход"])
    ws.append([200, "With Year", 200, 0])
    wb.save(file_path)

    rows = reader.read(file_path)

    assert [row["customer"] for row in rows] == ["With Year"]


def test_calamine_reader_read_filters_date_range_sheets(tmp_path):
    import openpyxl

    markers = {
        "amount": "сумма",
        "customer": "заказчик",
        "income": "приход",
        "expense": "расход",
    }
    aliases = {
        "amount": ["сумма"],
        "income": ["приход"],
        "expense": ["расход"],
        "customer": ["заказчик"],
    }
    reader = CalamineReader(markers, aliases)

    file_path = tmp_path / "range_sheets.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "31.03.2026"
    ws.append(["сумма", "заказчик", "приход", "расход"])
    ws.append([100, "Before", 100, 0])
    ws = wb.create_sheet("01.04.2026")
    ws.append(["сумма", "заказчик", "приход", "расход"])
    ws.append([200, "Inside Start", 200, 0])
    ws = wb.create_sheet("30.04.2026")
    ws.append(["сумма", "заказчик", "приход", "расход"])
    ws.append([300, "Inside End", 300, 0])
    ws = wb.create_sheet("01.05.2026")
    ws.append(["сумма", "заказчик", "приход", "расход"])
    ws.append([400, "After", 400, 0])
    wb.save(file_path)

    rows = reader.read(
        file_path,
        start_date_str="01.04.2026",
        end_date_str="30.04.2026",
    )

    assert [row["customer"] for row in rows] == ["Inside Start", "Inside End"]


def test_calamine_reader_two_pass_header_detection(tmp_path, create_temp_xlsx):
    markers = {
        "amount": "сумма",
        "customer": "заказчик",
        "income": "приход",
        "expense": "расход",
    }
    aliases = {
        "amount": ["сумма"],
        "customer": ["заказчик"],
        "income": ["приход"],
        "expense": ["расход"],
    }
    reader = CalamineReader(markers, aliases)

    # Create a file where the header is not on the first row
    data = [
        ["Some junk", "", "", ""],
        ["More junk", "", "", ""],
        ["сумма", "заказчик", "приход", "расход"],  # Header here (score 4)
        [100, "Client A", 100, 0],
        [200, "Client B", 200, 0],
    ]
    file_path = tmp_path / "test_two_pass.xlsx"
    create_temp_xlsx(file_path, data, sheet_name="01.01.2026")

    res = reader.read(file_path)
    assert len(res) == 2
    assert res[0]["amount"] == Decimal("100.00")
    assert res[0]["customer"] == "Client A"


def test_calamine_reader_trash_filtering(tmp_path, create_temp_xlsx):
    markers = {
        "amount": "сумма",
        "customer": "заказчик",
        "income": "приход",
        "expense": "расход",
    }
    aliases = {
        "amount": ["сумма"],
        "customer": ["заказчик"],
        "income": ["приход"],
        "expense": ["расход"],
    }
    reader = CalamineReader(markers, aliases)

    data = [
        ["сумма", "заказчик", "приход", "расход"],
        [100, "Client A", 100, 0],
        [0, "c16 junk", 0, 0],  # Should be filtered by trash_keywords
        [200, "Client B", 200, 0],
        [0, "d16 junk", 0, 0],  # Should be filtered by trash_keywords
    ]
    file_path = tmp_path / "test_trash.xlsx"
    create_temp_xlsx(file_path, data, sheet_name="01.01.2026")

    res = reader.read(file_path)
    assert len(res) == 2
    assert res[0]["customer"] == "Client A"
    assert res[1]["customer"] == "Client B"


def test_calamine_reader_network_copy_optimization(
    tmp_path, create_temp_xlsx, mock_network_drive
):
    markers = {"amount": "сумма", "customer": "заказчик"}
    aliases = {
        "amount": ["сумма"],
        "income": ["приход"],
        "expense": ["расход"],
        "customer": ["заказчик"],
    }
    reader = CalamineReader(markers, aliases)

    data = [["сумма", "заказчик", "приход", "расход"], [100, "Client A", 100, 0]]
    file_path = tmp_path / "temp_local.xlsx"
    create_temp_xlsx(file_path, data, sheet_name="01.01.2026")
    network_path = Path("Q:/test_network.xlsx")

    with patch(
        "core.infra.ingestion_reader.get_local_copy",
        return_value=(str(file_path), None),
    ):
        res = reader.read(network_path)
        assert len(res) == 1


def test_calamine_reader_strict_mode_raises_workbook_open_error(tmp_path):
    reader = CalamineReader({"amount": "сумма"}, {"amount": ["сумма"]})
    file_path = tmp_path / "broken.xlsx"
    file_path.touch()

    with patch(
        "core.infra.ingestion_reader.CalamineWorkbook.from_path",
        side_effect=ValueError("broken workbook"),
    ):
        with pytest.raises(ValueError, match="broken workbook"):
            reader.read(file_path, strict_io=True)


def test_calamine_reader_lenient_mode_keeps_empty_result_on_workbook_open_error(
    tmp_path,
):
    reader = CalamineReader({"amount": "сумма"}, {"amount": ["сумма"]})
    file_path = tmp_path / "broken.xlsx"
    file_path.touch()

    with patch(
        "core.infra.ingestion_reader.CalamineWorkbook.from_path",
        side_effect=ValueError("broken workbook"),
    ):
        assert reader.read(file_path, strict_io=False) == []


def test_ingestion_engine_get_available_dates(tmp_path, create_temp_xlsx):
    engine = IngestionEngine({"amount": "сумма"})
    file_path = tmp_path / "test_dates.xlsx"

    # Create file with multiple sheets using openpyxl directly since fixture only does one
    import openpyxl

    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "01.01.2026"
    ws2 = wb.create_sheet("02.01.2026")
    ws3 = wb.create_sheet("АНАЛИТИКА")  # Should be ignored
    ws4 = wb.create_sheet("_Hidden")  # Should be ignored
    wb.save(file_path)

    dates = engine.get_available_dates(file_path)
    assert dates == ["01.01.2026", "02.01.2026"]


def test_calamine_reader_read_xlsb(tmp_path, create_temp_xlsb):
    markers = {"amount": "сумма", "customer": "заказчик"}
    aliases = {
        "amount": ["сумма"],
        "income": ["приход"],
        "expense": ["расход"],
        "customer": ["заказчик"],
    }
    reader = CalamineReader(markers, aliases)

    data = [["сумма", "заказчик", "приход", "расход"], [100, "Client A", 100, 0]]
    file_path = tmp_path / "test.xlsb"
    # Call fixture to satisfy requirement
    create_temp_xlsb(file_path, data, sheet_name="01.01.2026")

    # Mock CalamineWorkbook.from_path because create_temp_xlsb might not create a valid XLSB
    with patch("python_calamine.CalamineWorkbook.from_path") as mock_from_path:
        mock_wb = MagicMock()
        mock_wb.sheet_names = ["01.01.2026"]
        mock_sheet = MagicMock()
        mock_sheet.to_python.return_value = data
        mock_sheet.iter_rows.side_effect = lambda: iter(data)
        mock_wb.get_sheet_by_name.return_value = mock_sheet

        mock_from_path.return_value = mock_wb

        res = reader.read(file_path)
        assert len(res) == 1
        assert res[0]["amount"] == Decimal("100.00")


def test_calamine_reader_multiple_headers_warning(tmp_path, create_temp_xlsx):
    markers = {
        "amount": "сумма",
        "customer": "заказчик",
        "income": "приход",
        "expense": "расход",
    }
    aliases = {
        "amount": ["сумма"],
        "customer": ["заказчик", "агент"],
        "income": ["приход"],
        "expense": ["расход"],
    }
    reader = CalamineReader(markers, aliases)

    data = [
        ["сумма", "заказчик", "приход", "расход"],  # Standard header (score 4)
        [100, "Client A", 100, 0],
        [
            "сумма",
            "агент",
            "приход",
            "расход",
        ],  # Different header (score 4, uses alias 'агент')
        [200, "Client B", 200, 0],
    ]
    file_path = tmp_path / "test_warning.xlsx"
    create_temp_xlsx(file_path, data, sheet_name="01.01.2026")

    res = reader.read(file_path)
    assert len(res) == 2
    assert res[0]["is_template_warning"] is False
    assert res[1]["is_template_warning"] is False
    assert "_template_warning_kind" not in res[1]


def test_calamine_reader_date_extraction(tmp_path, create_temp_xlsx):
    markers = {"amount": "сумма", "customer": "заказчик"}
    aliases = {
        "amount": ["сумма"],
        "income": ["приход"],
        "expense": ["расход"],
        "customer": ["заказчик"],
    }
    reader = CalamineReader(markers, aliases)

    data = [["сумма", "заказчик", "приход", "расход"], [100, "Client A", 100, 0]]
    file_path = tmp_path / "test_date_ext.xlsx"
    create_temp_xlsx(file_path, data, sheet_name="Отчет 15.03.2026")

    res = reader.read(file_path)
    assert len(res) == 1
    assert res[0]["date"] == "15.03.2026"


def test_calamine_reader_unicode_cleaning(tmp_path, create_temp_xlsx):
    # Requirement: Очистка Unicode-невидимок в названиях листов.
    # Using swan_1_unicode_invisible.xlsx behavior simulation
    markers = {"amount": "сумма", "customer": "заказчик"}
    aliases = {"amount": ["сумма"], "customer": ["заказчик"]}
    reader = CalamineReader(markers, aliases)

    data = [["сумма", "заказчик"], [100, "Client A"]]
    file_path = tmp_path / "unicode_sheet.xlsx"
    # \u200b is Zero Width Space
    create_temp_xlsx(file_path, data, sheet_name="\u200b01.01.2026\u200b")

    res = reader.read(file_path)
    assert len(res) == 1
    assert res[0]["date"] == "01.01.2026"


def test_calamine_reader_header_detection_huge_space():
    # Requirement: Детекция заголовков на 6000+ строках (использование фикстуры swan_2_huge_empty_space.xlsx).
    # swan_2_huge_empty_space.xlsx has header on row 5000 (1-indexed) which is within 6000 scan limit.
    markers = {"amount": "сумма платежа", "customer": "заказчик", "total": "итог"}
    aliases = {"amount": ["сумма платежа"], "customer": ["заказчик"], "total": ["итог"]}
    reader = CalamineReader(markers, aliases)
    fixture_path = (
        Path(__file__).resolve().parent
        / "fixtures"
        / "black_swan"
        / "swan_2_huge_empty_space.xlsx"
    )

    assert fixture_path.exists(), "Fixture swan_2_huge_empty_space.xlsx not found"

    res = reader.read(fixture_path)
    # swan_2 has 1 data row at line 5001
    assert len(res) == 1
    assert res[0]["customer"] == "Cust2"
    assert res[0]["amount"] == Decimal("2000.00")


def test_calamine_reader_garbage_keywords(tmp_path, create_temp_xlsx):
    # Requirement: Игнорирование мусорных строк (keywords: 'итого', 'всего').
    markers = {"amount": "сумма", "customer": "заказчик"}
    aliases = {"amount": ["сумма"], "customer": ["заказчик"]}
    reader = CalamineReader(markers, aliases)

    data = [
        ["сумма", "заказчик"],
        [100, "Client A"],
        [500, "ИТОГО:"],  # Row with garbage keyword
        [200, "Client B"],
        [1000, "ВСЕГО"],  # Row with garbage keyword
    ]
    file_path = tmp_path / "test_garbage.xlsx"
    create_temp_xlsx(file_path, data, sheet_name="01.01.2026")

    res = reader.read(file_path)

    trash_rows = [
        r
        for r in res
        if any(kw in str(r.get("customer")).lower() for kw in ["итого", "всего"])
    ]

    assert len(res) == 2
    assert len(trash_rows) == 0


def test_calamine_reader_cosmetic_header_variations_do_not_warn(
    tmp_path, create_temp_xlsx
):
    markers = {
        "amount": "сумма платежа",
        "customer": "заказчик",
        "contractor": "исполнитель",
        "commission": "комиссия",
        "total": "итог",
        "percent_broker": "% посредника",
        "broker1": "посредник 1(кэш)",
        "broker2": "посредник 2",
        "filters": "фильтры",
    }
    aliases = {
        "amount": ["сумма платежа"],
        "customer": ["заказчик"],
        "contractor": ["исполнитель"],
        "commission": ["комиссия"],
        "total": ["итог"],
        "percent_broker": ["% посредника"],
        "broker1": ["посредник 1(кэш)"],
        "broker2": ["посредник 2"],
        "filters": ["фильтры"],
    }
    reader = CalamineReader(markers, aliases)

    data = [
        [
            "  ЗАКАЗЧИК:  ",
            " ИСПОЛНИТЕЛЬ ",
            "СУММА   ПЛАТЕЖА",
            "КОМИССИЯ",
            "ИТОГ:",
            "%   ПОСРЕДНИКА",
            "ПОСРЕДНИК 1(КЭШ)",
            "ПОСРЕДНИК 2",
            "ФИЛЬТРЫ ",
        ],
        [
            "ООО Ромашка",
            "ИП Иванов",
            1000,
            0,
            1000,
            0,
            0,
            0,
            "",
        ],
    ]
    file_path = tmp_path / "cosmetic_headers.xlsx"
    create_temp_xlsx(file_path, data, sheet_name="01.01.2026")

    res = reader.read(file_path)

    assert len(res) == 1
    assert res[0]["customer"] == "ООО Ромашка"
    assert res[0]["is_template_warning"] is False
    assert res[0].get("_template_warning_kind") is None


def test_calamine_reader_currency_amount_does_not_shadow_payment_amount(
    tmp_path, create_temp_xlsx
):
    markers = {
        "amount": "сумма платежа",
        "customer": "заказчик",
        "contractor": "исполнитель",
        "commission": "комиссия",
        "total": "итог",
        "percent_broker": "% посредника",
        "broker1": "посредник 1(кэш)",
        "broker2": "посредник 2",
        "currency_amount": "сумма",
        "filters": "фильтры",
    }
    aliases = {
        "amount": ["сумма платежа", "приход", "расход"],
        "customer": ["заказчик"],
        "contractor": ["исполнитель"],
        "commission": ["комиссия"],
        "total": ["итог"],
        "percent_broker": ["% посредника"],
        "broker1": ["посредник 1(кэш)"],
        "broker2": ["посредник 2"],
        "currency_amount": ["сумма"],
        "filters": ["фильтры"],
    }
    reader = CalamineReader(markers, aliases)

    data = [
        [
            "Заказчик",
            "Исполнитель",
            "Сумма платежа",
            "Комиссия",
            "Итог",
            "% посредника",
            "посредник 1(кэш)",
            "посредник 2",
            "Фильтры",
        ],
        [
            "ООО Ромашка",
            "ИП Иванов",
            1000,
            0,
            1000,
            0,
            0,
            0,
            "",
        ],
    ]
    file_path = tmp_path / "currency_amount_shadow.xlsx"
    create_temp_xlsx(file_path, data, sheet_name="01.01.2026")

    res = reader.read(file_path)

    assert len(res) == 1
    assert res[0]["amount"] == Decimal("1000.00")
    assert "currency_amount" not in res[0]
    assert res[0]["is_template_warning"] is False
    assert res[0].get("_template_warning_kind") is None


def test_calamine_reader_boris_second_percent_is_soft_structure(
    tmp_path, create_temp_xlsx
):
    markers = {
        "amount": "сумма платежа",
        "customer": "заказчик",
        "contractor": "исполнитель",
        "commission": "комиссия",
        "total": "итог",
        "percent_broker": "% посредника",
        "broker1": "посредник 1(кэш)",
        "broker2": "посредник 2",
        "filters": "фильтры",
    }
    aliases = {
        "amount": ["сумма платежа"],
        "customer": ["заказчик"],
        "contractor": ["исполнитель"],
        "commission": ["комиссия"],
        "total": ["итог"],
        "percent_broker": ["% посредника", "%"],
        "broker1": ["посредник 1(кэш)", "комиссия посредника 1"],
        "broker2": ["посредник 2", "комиссия посредника 2"],
        "filters": ["фильтры"],
    }
    reader = CalamineReader(markers, aliases)

    data = [
        [
            "Заказчик",
            "Исполнитель",
            "Сумма платежа",
            "Комиссия",
            "Итог",
            "Оплата постащику, выплата зарплатного реестра",
            "",
            "%",
            "Комиссия посредника 1",
            "%",
            "Комиссия посредника 2",
        ],
        [
            "ООО Ромашка",
            "ИП Иванов",
            1000,
            0,
            1000,
            "",
            "",
            0.05,
            50,
            0.05,
            50,
        ],
    ]
    file_path = tmp_path / "boris_second_percent.xlsx"
    create_temp_xlsx(file_path, data, sheet_name="01.01.2026")

    res = reader.read(file_path)

    assert len(res) == 1
    assert res[0]["amount"] == Decimal("1000.00")
    assert res[0]["percent_broker2"] == Decimal("0.05")
    assert res[0]["is_template_warning"] is False
    assert res[0]["_template_warning_kind"] == "soft_structure"
    assert "unexpected columns" not in res[0]["_template_warning_reason"].lower()


def test_calamine_reader_boris_second_percent_keeps_negative_value(
    tmp_path, create_temp_xlsx
):
    markers = {
        "amount": "сумма платежа",
        "customer": "заказчик",
        "contractor": "исполнитель",
        "commission": "комиссия",
        "total": "итог",
        "percent_broker": "% посредника",
        "broker1": "посредник 1(кэш)",
        "broker2": "посредник 2",
        "filters": "фильтры",
    }
    aliases = {
        "amount": ["сумма платежа"],
        "customer": ["заказчик"],
        "contractor": ["исполнитель"],
        "commission": ["комиссия"],
        "total": ["итог"],
        "percent_broker": ["% посредника", "%"],
        "broker1": ["посредник 1(кэш)", "комиссия посредника 1"],
        "broker2": ["посредник 2", "комиссия посредника 2"],
        "filters": ["фильтры"],
    }
    reader = CalamineReader(markers, aliases)

    data = [
        [
            "Заказчик",
            "Исполнитель",
            "Сумма платежа",
            "Комиссия",
            "Итог",
            "Оплата постащику, выплата зарплатного реестра",
            "",
            "%",
            "Комиссия посредника 1",
            "%",
            "Комиссия посредника 2",
        ],
        ["СИБ Сбер", "СТИ, Альфа", 0, 24, -31237.17, "", "", -0.04, 2178.01, -0.02, 624.74],
    ]
    file_path = tmp_path / "boris_second_percent_negative.xlsx"
    create_temp_xlsx(file_path, data, sheet_name="10.04.2026")

    res = reader.read(file_path)

    assert len(res) == 1
    assert res[0]["percent_broker"] == Decimal("-0.04")
    assert res[0]["percent_broker2"] == Decimal("-0.02")
    assert res[0]["broker2"] == Decimal("624.74")


def test_calamine_reader_same_structure_alias_name_becomes_soft_warning(
    tmp_path, create_temp_xlsx
):
    markers = {
        "amount": "сумма платежа",
        "customer": "заказчик",
        "contractor": "исполнитель",
        "commission": "комиссия",
        "total": "итог",
        "percent_broker": "% посредника",
        "broker1": "посредник 1(кэш)",
        "broker2": "посредник 2",
        "filters": "фильтры",
    }
    aliases = {
        "amount": ["сумма платежа"],
        "customer": ["заказчик"],
        "contractor": ["исполнитель"],
        "commission": ["комиссия"],
        "total": ["итог"],
        "percent_broker": ["% посредника", "%"],
        "broker1": ["посредник 1(кэш)", "посредник 1"],
        "broker2": ["посредник 2"],
        "filters": ["фильтры", "фильтр"],
    }
    reader = CalamineReader(markers, aliases)

    data = [
        [
            "Заказчик",
            "Исполнитель",
            "Сумма платежа",
            "Комиссия",
            "Итог",
            "%",
            "посредник 1",
            "посредник 2",
            "Фильтр",
        ],
        [
            "ООО Ромашка",
            "ИП Иванов",
            1000,
            0,
            1000,
            0,
            0,
            0,
            "",
        ],
    ]
    file_path = tmp_path / "soft_warning_headers.xlsx"
    create_temp_xlsx(file_path, data, sheet_name="01.01.2026")

    res = reader.read(file_path)

    assert len(res) == 1
    assert res[0]["customer"] == "ООО Ромашка"
    assert res[0]["is_template_warning"] is False
    assert res[0]["_template_warning_kind"] == "soft_structure"
    assert "unsupported header name" in res[0]["_template_warning_reason"].lower()


def test_calamine_reader_extra_column_marks_hard_structure_warning(
    tmp_path, create_temp_xlsx
):
    markers = {
        "amount": "сумма платежа",
        "customer": "заказчик",
        "contractor": "исполнитель",
        "commission": "комиссия",
        "total": "итог",
        "percent_broker": "% посредника",
        "broker1": "посредник 1(кэш)",
        "broker2": "посредник 2",
        "filters": "фильтры",
    }
    aliases = {
        "amount": ["сумма платежа"],
        "customer": ["заказчик"],
        "contractor": ["исполнитель"],
        "commission": ["комиссия"],
        "total": ["итог"],
        "percent_broker": ["% посредника"],
        "broker1": ["посредник 1(кэш)"],
        "broker2": ["посредник 2"],
        "filters": ["фильтры"],
    }
    reader = CalamineReader(markers, aliases)

    data = [
        [
            "Заказчик",
            "Исполнитель",
            "Сумма платежа",
            "Комиссия",
            "Итог",
            "% посредника",
            "посредник 1(кэш)",
            "посредник 2",
            "курс",
            "Фильтры",
        ],
        [
            "ООО Ромашка",
            "ИП Иванов",
            1000,
            0,
            1000,
            0,
            0,
            0,
            90,
            "",
        ],
    ]
    file_path = tmp_path / "extra_column_headers.xlsx"
    create_temp_xlsx(file_path, data, sheet_name="01.01.2026")

    res = reader.read(file_path)

    assert len(res) == 1
    assert res[0]["customer"] == "ООО Ромашка"
    assert res[0]["is_template_warning"] is True
    assert res[0]["_template_warning_kind"] == "hard_structure"
    assert "unexpected columns" in res[0]["_template_warning_reason"].lower()


def test_calamine_reader_reordered_columns_mark_hard_structure_warning(
    tmp_path, create_temp_xlsx
):
    markers = {
        "amount": "сумма платежа",
        "customer": "заказчик",
        "contractor": "исполнитель",
        "commission": "комиссия",
        "total": "итог",
        "percent_broker": "% посредника",
        "broker1": "посредник 1(кэш)",
        "broker2": "посредник 2",
        "filters": "фильтры",
    }
    aliases = {
        "amount": ["сумма платежа"],
        "customer": ["заказчик"],
        "contractor": ["исполнитель"],
        "commission": ["комиссия"],
        "total": ["итог"],
        "percent_broker": ["% посредника"],
        "broker1": ["посредник 1(кэш)"],
        "broker2": ["посредник 2"],
        "filters": ["фильтры"],
    }
    reader = CalamineReader(markers, aliases)

    data = [
        [
            "Заказчик",
            "Исполнитель",
            "Сумма платежа",
            "Итог",
            "Комиссия",
            "% посредника",
            "посредник 1(кэш)",
            "посредник 2",
            "Фильтры",
        ],
        [
            "ООО Ромашка",
            "ИП Иванов",
            1000,
            1000,
            0,
            0,
            0,
            0,
            "",
        ],
    ]
    file_path = tmp_path / "reordered_headers.xlsx"
    create_temp_xlsx(file_path, data, sheet_name="01.01.2026")

    res = reader.read(file_path)

    assert len(res) == 1
    assert res[0]["customer"] == "ООО Ромашка"
    assert res[0]["is_template_warning"] is True
    assert res[0]["_template_warning_kind"] == "hard_structure"
    assert "column order mismatch" in res[0]["_template_warning_reason"].lower()


def test_calamine_reader_helper_day_total_column_becomes_soft_warning(
    tmp_path, create_temp_xlsx
):
    markers = {
        "amount": "сумма платежа",
        "customer": "заказчик",
        "contractor": "исполнитель",
        "commission": "комиссия",
        "total": "итог",
        "percent_broker": "% посредника",
        "broker1": "посредник 1(кэш)",
        "broker2": "посредник 2",
        "filters": "фильтры",
    }
    aliases = {
        "amount": ["сумма платежа"],
        "customer": ["заказчик"],
        "contractor": ["исполнитель"],
        "commission": ["комиссия"],
        "total": ["итог"],
        "percent_broker": ["% посредника"],
        "broker1": ["посредник 1(кэш)"],
        "broker2": ["посредник 2"],
        "filters": ["фильтры"],
    }
    reader = CalamineReader(markers, aliases)

    data = [
        [
            "Заказчик",
            "Исполнитель",
            "Сумма платежа",
            "Комиссия",
            "Итог",
            "ИТОГ ДНЯ",
            "% посредника",
            "посредник 1(кэш)",
            "посредник 2",
            "Фильтры",
        ],
        [
            "ООО Ромашка",
            "ИП Иванов",
            1000,
            0,
            1000,
            1000,
            0,
            0,
            0,
            "",
        ],
    ]
    file_path = tmp_path / "helper_day_total.xlsx"
    create_temp_xlsx(file_path, data, sheet_name="01.01.2026")

    res = reader.read(file_path)

    assert len(res) == 1
    assert res[0]["is_template_warning"] is False
    assert res[0]["_template_warning_kind"] == "soft_structure"
    assert "helper columns" in res[0]["_template_warning_reason"].lower()


def test_calamine_reader_missing_filters_column_becomes_soft_warning(
    tmp_path, create_temp_xlsx
):
    markers = {
        "amount": "сумма платежа",
        "customer": "заказчик",
        "contractor": "исполнитель",
        "commission": "комиссия",
        "total": "итог",
        "percent_broker": "% посредника",
        "broker1": "посредник 1(кэш)",
        "broker2": "посредник 2",
        "filters": "фильтры",
    }
    aliases = {
        "amount": ["сумма платежа"],
        "customer": ["заказчик"],
        "contractor": ["исполнитель"],
        "commission": ["комиссия"],
        "total": ["итог"],
        "percent_broker": ["% посредника"],
        "broker1": ["посредник 1(кэш)"],
        "broker2": ["посредник 2"],
        "filters": ["фильтры"],
    }
    reader = CalamineReader(markers, aliases)

    data = [
        [
            "Заказчик",
            "Исполнитель",
            "Сумма платежа",
            "Комиссия",
            "Итог",
            "% посредника",
            "посредник 1(кэш)",
            "посредник 2",
        ],
        [
            "ООО Ромашка",
            "ИП Иванов",
            1000,
            0,
            1000,
            0,
            0,
            0,
        ],
    ]
    file_path = tmp_path / "missing_filters.xlsx"
    create_temp_xlsx(file_path, data, sheet_name="01.01.2026")

    res = reader.read(file_path)

    assert len(res) == 1
    assert res[0]["is_template_warning"] is False
    assert res[0]["_template_warning_kind"] == "soft_structure"
    assert "missing optional columns" in res[0]["_template_warning_reason"].lower()


def test_calamine_reader_plain_posrednik_maps_to_broker1_softly(
    tmp_path, create_temp_xlsx
):
    markers = {
        "amount": "сумма платежа",
        "customer": "заказчик",
        "contractor": "исполнитель",
        "commission": "комиссия",
        "total": "итог",
        "percent_broker": "% посредника",
        "broker1": "посредник 1(кэш)",
        "broker2": "посредник 2",
        "filters": "фильтры",
    }
    aliases = {
        "amount": ["сумма платежа"],
        "customer": ["заказчик"],
        "contractor": ["исполнитель"],
        "commission": ["комиссия"],
        "total": ["итог"],
        "percent_broker": ["% посредника", "%"],
        "broker1": ["посредник 1(кэш)", "посредник 1", "комиссия посредника 1"],
        "broker2": ["посредник 2", "комиссия посредника 2"],
        "filters": ["фильтры", "фильтр"],
    }
    reader = CalamineReader(markers, aliases)

    data = [
        [
            "ЗАКАЗЧИК (название проекта, наименование ЮЛ)",
            "ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)",
            "сумма платежа",
            "комиссия",
            "ИТОГ",
            "% посредника",
            "посредник",
            "посредник 2",
            "фильтры",
        ],
        [
            "ООО Ромашка",
            "ИП Иванов",
            -1000,
            0.25,
            -1333.33,
            -0.07,
            70,
            0,
            "реестр",
        ],
    ]
    file_path = tmp_path / "plain_posrednik.xlsx"
    create_temp_xlsx(file_path, data, sheet_name="06.03.2026")

    res = reader.read(file_path)

    assert len(res) == 1
    assert res[0]["broker1"] == Decimal("70")
    assert res[0]["broker2"] == Decimal("0")
    assert res[0]["is_template_warning"] is False
    assert res[0]["_template_warning_kind"] == "soft_structure"
    assert "unsupported header name" in res[0]["_template_warning_reason"].lower()
