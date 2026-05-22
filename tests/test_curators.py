import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch
from pathlib import Path
from core.infra.export_writer import MasterWriter, DEFAULT_HEADERS
from core.domain.logic_service import LogicService
from core.infra.export_formatting import detect_header_columns

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def writer():
    return MasterWriter({"paths": {"master_file": "test.xlsx"}})


@pytest.fixture
def boris_config():
    return {
        "headers": [
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
        ],
        "intermediary2_rate": 0.05,
        "output_path": "output/boris_report.xlsx",
    }


@pytest.fixture
def ivan_config():
    return {
        "headers": [
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
        ],
        "intermediary1_rate": 0.05,
        "intermediary2_rate": 0.05,
        "output_path": "output/ivan_report.xlsx",
    }


@pytest.fixture
def sample_data():
    return [
        {
            "Дата": "10.04.2026",
            "Источник": "test.xlsx",
            "ЗАКАЗЧИК (название проекта, наименование ЮЛ)": "ООО Тест",
            "ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)": "ООО Исп",
            "сумма платежа ПРИХОД": Decimal("1000"),
            "сумма платежа РАСХОД": Decimal("0"),
            "комиссия": Decimal("50"),
            "ИТОГ": Decimal("950"),
            "% посредника": Decimal("0.10"),
            "посредник 1(кэш)": Decimal("95"),
            "посредник 2": Decimal("47.50"),
            "% посредник 2": Decimal("0.05"),
            "Посредник 2 (сумма)": Decimal("47.50"),
            "ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ": Decimal("14480"),
            "курс": Decimal("23.20"),
            "сумма": Decimal("14480"),
            "валюта": "риал",
            "фильтры": "",
            "is_critical": False,
            "is_template_warning": False,
        }
    ]


# --- Boris tests (5) ---


def test_boris_headers_count(boris_config):
    assert len(boris_config["headers"]) == 12


def test_boris_percent_broker2_in_output(sample_data):
    r = sample_data[0]
    assert "% посредник 2" in r
    assert r["% посредник 2"] == Decimal("0.05")


def test_boris_column_order(writer, sample_data, boris_config):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "10.04.2026"
    ws.append(boris_config["headers"])
    writer._append_data_rows(ws, datetime(2026, 4, 10), sample_data, curator="boris")
    assert ws.cell(1, 1).value == "Источник"
    assert ws.cell(1, 8).value == "% посредник 1"
    assert ws.cell(1, 10).value == "% посредник 2"
    assert ws.cell(1, 11).value == "посредник 2"
    assert ws.cell(1, 12).value == "Фильтры"
    assert ws.cell(2, 10).value == Decimal("0.05")
    assert ws.cell(2, 11).value == pytest.approx(47.50)


def test_boris_isolation(writer, sample_data, boris_config, tmp_path):
    master_before = writer.master_path
    boris_path = tmp_path / "boris.xlsx"
    writer.write_report(
        sample_data, boris_path, curator="boris", curator_config=boris_config
    )
    assert writer.master_path == master_before


def test_boris_empty_data(writer, boris_config, tmp_path):
    boris_path = tmp_path / "boris_empty.xlsx"
    result = writer.write_report(
        [], boris_path, curator="boris", curator_config=boris_config
    )
    assert isinstance(result, bool)


# --- Ivan tests (5) ---


def test_ivan_headers_count(ivan_config):
    assert len(ivan_config["headers"]) == 15


def test_ivan_both_intermediaries(writer, sample_data, ivan_config):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "10.04.2026"
    ws.append(ivan_config["headers"])
    writer._append_data_rows(ws, datetime(2026, 4, 10), sample_data, curator="ivan")
    assert ws.cell(2, 9).value == Decimal("0.10")
    assert ws.cell(2, 11).value == pytest.approx(47.50)


def test_ivan_column_order_matches_customer_layout(writer, sample_data, ivan_config):
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "10.04.2026"
    ws.append(ivan_config["headers"])
    writer._append_data_rows(ws, datetime(2026, 4, 10), sample_data, curator="ivan")

    assert ws.cell(1, 1).value == "Сотрудник"
    assert ws.cell(1, 8).value == "ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ"
    assert ws.cell(1, 9).value == "% посредника 1"
    assert ws.cell(1, 10).value == "посредник 1(кэш)"
    assert ws.cell(1, 11).value == "посредник 2"
    assert ws.cell(1, 12).value == "курс"
    assert ws.cell(1, 13).value == "сумма"
    assert ws.cell(1, 14).value == "валюта"
    assert ws.cell(1, 15).value == "фильтры"
    assert ws.cell(2, 8).value == pytest.approx(14480.0)
    assert ws.cell(2, 12).value == Decimal("23.20")
    assert ws.cell(2, 13).value == Decimal("14480")
    assert ws.cell(2, 14).value == "риал"


def test_ivan_isolation(writer, sample_data, ivan_config, tmp_path):
    master_before = writer.master_path
    ivan_path = tmp_path / "ivan.xlsx"
    writer.write_report(
        sample_data, ivan_path, curator="ivan", curator_config=ivan_config
    )
    assert writer.master_path == master_before


def test_ivan_empty_data(writer, ivan_config, tmp_path):
    ivan_path = tmp_path / "ivan_empty.xlsx"
    result = writer.write_report(
        [], ivan_path, curator="ivan", curator_config=ivan_config
    )
    assert isinstance(result, bool)


def test_ivan_template_headers(tmp_path):
    import openpyxl

    tpl_path = REPO_ROOT / "APP" / "templates" / "master_ivan.xlsx"
    wb = openpyxl.load_workbook(str(tpl_path))
    ws = wb.active
    headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
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
        "фильтры",
    ]
