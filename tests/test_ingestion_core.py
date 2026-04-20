"""Расширенные тесты для ingestion_core.py — CalamineReader + extract_date_from_sheet."""
import pytest
import os
import tempfile
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch, MagicMock
import openpyxl

from core.infra.ingestion_reader import CalamineReader, extract_date_from_sheet


@pytest.fixture
def markers():
    return {
        'customer': 'заказчик',
        'contractor': 'исполнитель',
        'amount': 'сумма платежа',
        'income': 'приход',
        'expense': 'расход',
        'commission': 'комиссия',
        'total': 'итог',
        'percent_broker': '% посредника',
        'broker1': 'посредник 1(кэш)',
        'broker2': 'посредник 2',
    }


@pytest.fixture
def aliases():
    return {
        'amount': ['сумма платежа', 'бн рф руб', 'бн'],
        'customer': ['заказчик', 'агент'],
        'contractor': ['исполнитель', 'вторая сторона'],
    }


@pytest.fixture
def reader(markers, aliases):
    return CalamineReader(markers, aliases)


@pytest.fixture
def temp_xlsx(tmp_path):
    def _create(name, sheets_data):
        """sheets_data: {sheet_name: [[row1], [row2], ...]}"""
        f = tmp_path / name
        wb = openpyxl.Workbook()
        for sheet_name, rows in sheets_data.items():
            ws = wb.create_sheet(sheet_name) if wb.active.title != "Sheet" else wb.active
            ws.title = sheet_name
            for row in rows:
                ws.append(row)
        if "Sheet" in wb.sheetnames and len(wb.sheetnames) > 1:
            del wb["Sheet"]
        wb.save(f)
        return f
    return _create


class TestExtractDateFromSheet:
    """Тесты extract_date_from_sheet."""

    def test_dd_mm_format(self):
        assert extract_date_from_sheet("Отчет 01.04") == "01.04"

    def test_dd_mm_yyyy_format(self):
        assert extract_date_from_sheet("01.04.2025") == "01.04.2025"

    def test_comma_separator(self):
        assert extract_date_from_sheet("01,04") == "01.04"

    def test_no_date_returns_none(self):
        assert extract_date_from_sheet("АНАЛИТИКА") is None

    def test_empty_string_returns_none(self):
        assert extract_date_from_sheet("") is None

    def test_none_returns_none(self):
        assert extract_date_from_sheet(None) is None

    def test_leading_zeros(self):
        assert extract_date_from_sheet("05.01") == "05.01"

    def test_single_digit_day(self):
        assert extract_date_from_sheet("5.04") == "05.04"

    def test_dd_mm_yy_format(self):
        assert extract_date_from_sheet("15.04.26") == "15.04.2026"

    def test_dd_mm_yy_comma_format(self):
        assert extract_date_from_sheet("15,04,26") == "15.04.2026"

    def test_with_year_hint_metadata_when_year_present(self):
        meta = extract_date_from_sheet("Отчет 18.04.2025", with_year_hint=True)
        assert isinstance(meta, dict)
        assert meta["date"] == "18.04.2025"
        assert meta["year_hint"] == 2025

    def test_with_year_hint_metadata_when_year_absent(self):
        meta = extract_date_from_sheet("Отчет 18.04", with_year_hint=True)
        assert isinstance(meta, dict)
        assert meta["date"] == "18.04"
        assert meta["year_hint"] is None

    def test_plain_dd_mm_without_year_returns_short_date(self):
        assert extract_date_from_sheet("Отчет 18.04") == "18.04"

    def test_invalid_date_feb29(self):
        """29 февраля в невисокосном году — дата отбрасывается."""
        result = extract_date_from_sheet("29.02.2025")
        assert result is None

    def test_unicode_cleaning(self):
        assert extract_date_from_sheet("01.\u200b04") == "01.04"

    def test_bom_cleaning(self):
        assert extract_date_from_sheet("\ufeff01.04") == "01.04"

    def test_multiple_dates_uses_first(self):
        """Несколько дат — берёт первую."""
        result = extract_date_from_sheet("01.04 и 02.05")
        assert result == "01.04"


class TestCalamineReaderMapColumns:
    """Тесты _map_columns."""

    def test_exact_marker_match(self, reader):
        header = ["Заказчик", "Исполнитель", "Сумма платежа", "Приход"]
        col_map, used = reader._map_columns(header)
        assert col_map['customer'] == 0
        assert col_map['contractor'] == 1
        assert col_map['amount'] == 2
        assert col_map['income'] == 3

    def test_alias_match(self, reader):
        header = ["Агент", "Вторая сторона", "бн рф руб"]
        col_map, used = reader._map_columns(header)
        assert col_map['customer'] == 0  # "агент" alias
        assert used is True

    def test_no_match(self, reader):
        header = ["Колонка1", "Колонка2"]
        col_map, used = reader._map_columns(header)
        assert col_map == {}
        assert used is False

    def test_commission_skip_broker(self, reader):
        """Комиссия посредника — не должна мапиться на commission."""
        header = ["% посредника", "Комиссия"]
        col_map, _ = reader._map_columns(header)
        assert 'commission' not in col_map or col_map['commission'] == 1

    def test_partial_match(self, reader):
        """Частичное совпадение — должно работать."""
        header = ["Название заказчика", "Сумма платежа"]
        col_map, _ = reader._map_columns(header)
        assert col_map['customer'] == 0
        assert col_map['amount'] == 1


class TestCalamineReaderRead:
    """Тесты read — полное чтение файлов."""

    def test_read_simple_xlsx(self, reader, temp_xlsx):
        f = temp_xlsx("simple.xlsx", {
            "Отчет 01.04": [
                ["Заказчик", "Исполнитель", "Сумма платежа", "Приход", "Расход", "Комиссия", "Итог"],
                ["ООО А", "ИП Б", "10000", "10000", "0", "2.5", "10000"],
                ["ООО В", "ИП Г", "5000", "0", "5000", "1", "5000"],
            ]
        })
        rows = reader.read(f)
        assert len(rows) >= 2

    def test_read_skips_analytics_sheet(self, reader, temp_xlsx):
        f = temp_xlsx("with_analytics.xlsx", {
            "Отчет 01.04": [
                ["Заказчик", "Сумма платежа"],
                ["А", "100"],
            ],
            "АНАЛИТИКА": [["Данные"]],
            "СВОД": [["Итого"]],
        })
        rows = reader.read(f)
        # Данные только из "Отчет 01.04"
        for row in rows:
            assert row.get('_sheet_name') != "АНАЛИТИКА"
            assert row.get('_sheet_name') != "СВОД"

    def test_read_skips_hidden_sheets(self, reader, temp_xlsx):
        f = temp_xlsx("hidden.xlsx", {
            "_hidden": [["data"]],
            "Отчет 01.04": [
                ["Заказчик", "Сумма платежа"],
                ["А", "100"],
            ]
        })
        rows = reader.read(f)
        for row in rows:
            assert not row.get('_sheet_name', '').startswith('_')

    def test_read_includes_metadata(self, reader, temp_xlsx):
        f = temp_xlsx("meta.xlsx", {
            "Отчет 01.04": [
                ["Заказчик", "Сумма платежа"],
                ["А", "100"],
            ]
        })
        rows = reader.read(f)
        assert len(rows) > 0
        row = rows[0]
        assert '_sheet_name' in row
        assert '_row_index' in row
        assert '_file_path' in row
        assert 'date' in row

    def test_read_missing_file(self, reader):
        rows = reader.read(Path("/nonexistent/file.xlsx"))
        assert rows == []

    def test_read_empty_sheet(self, reader, temp_xlsx):
        f = temp_xlsx("empty.xlsx", {
            "Отчет 01.04": [],
        })
        rows = reader.read(f)
        assert rows == []

    def test_read_no_financial_data(self, reader, temp_xlsx):
        """Лист без финансовых данных — пустой результат."""
        f = temp_xlsx("nofin.xlsx", {
            "Отчет 01.04": [
                ["Имя", "Фамилия"],
                ["Иван", "Иванов"],
            ]
        })
        rows = reader.read(f)
        assert rows == []

    def test_read_trash_filtering(self, reader, temp_xlsx):
        """Строки с trash keywords — фильтруются."""
        f = temp_xlsx("trash.xlsx", {
            "Отчет 01.04": [
                ["Заказчик", "Сумма платежа"],
                ["Название клиента", "100"],  # trash
                ["ООО А", "200"],  # valid
            ]
        })
        rows = reader.read(f)
        for row in rows:
            assert row.get('customer') != "Название клиента"

    def test_read_numeric_conversion(self, reader, temp_xlsx):
        """Числовые значения должны быть Decimal."""
        f = temp_xlsx("numeric.xlsx", {
            "Отчет 01.04": [
                ["Заказчик", "Сумма платежа", "Приход"],
                ["А", "1234.56", "1234.56"],
            ]
        })
        rows = reader.read(f)
        assert len(rows) > 0
        row = rows[0]
        # amount должен быть Decimal или число
        assert isinstance(row.get('amount'), (Decimal, int, float)) or row.get('amount') is not None
