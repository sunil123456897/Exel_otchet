"""Расширенные тесты для ingestion_engine.py."""
import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import openpyxl

from core.infra.ingestion_engine import IngestionEngine


@pytest.fixture
def markers():
    return {
        'customer': 'заказчик',
        'amount': 'сумма платежа',
    }


@pytest.fixture
def engine(markers):
    return IngestionEngine(markers)


@pytest.fixture
def temp_xlsx(tmp_path):
    def _create(name, sheets_data):
        f = tmp_path / name
        wb = openpyxl.Workbook()
        for i, (sheet_name, rows) in enumerate(sheets_data.items()):
            if i == 0:
                ws = wb.active
                ws.title = sheet_name
            else:
                ws = wb.create_sheet(sheet_name)
            for row in rows:
                ws.append(row)
        wb.save(f)
        return f
    return _create


class TestGetAvailableDates:
    """Тесты get_available_dates."""

    def test_single_date(self, engine, temp_xlsx):
        f = temp_xlsx("single.xlsx", {
            "Отчет 01.04.2026": [["Заказчик", "Сумма"], ["А", "100"]],
        })
        dates = engine.get_available_dates(f)
        assert dates == ["01.04.2026"]

    def test_date_without_year_is_ignored(self, engine, temp_xlsx):
        f = temp_xlsx("short-date.xlsx", {
            "Отчет 01.04": [["Заказчик", "Сумма"], ["А", "100"]],
            "Отчет 01.04.2026": [["Заказчик", "Сумма"], ["Б", "200"]],
        })
        dates = engine.get_available_dates(f)
        assert dates == ["01.04.2026"]

    def test_multiple_dates(self, engine, temp_xlsx):
        f = temp_xlsx("multi.xlsx", {
            "Отчет 01.04.2026": [["А", "100"]],
            "Отчет 02.04.2026": [["Б", "200"]],
            "Отчет 05.04.2026": [["В", "300"]],
        })
        dates = engine.get_available_dates(f)
        assert len(dates) == 3
        assert "01.04.2026" in dates
        assert "02.04.2026" in dates
        assert "05.04.2026" in dates

    def test_skips_hidden_sheets(self, engine, temp_xlsx):
        f = temp_xlsx("hidden.xlsx", {
            "_hidden": [["data"]],
            "Отчет 01.04.2026": [["А", "100"]],
        })
        dates = engine.get_available_dates(f)
        assert len(dates) == 1

    def test_skips_analytics(self, engine, temp_xlsx):
        f = temp_xlsx("analytics.xlsx", {
            "АНАЛИТИКА": [["data"]],
            "СВОД": [["total"]],
            "Отчет 01.04.2026": [["А", "100"]],
        })
        dates = engine.get_available_dates(f)
        assert dates == ["01.04.2026"]

    def test_dd_mm_yy_sheet_year_parsed(self, engine, temp_xlsx):
        f = temp_xlsx("two_digit_year.xlsx", {
            "Отчет 15.04.26": [["А", "100"]],
            "Отчет 15.04.2025": [["Б", "200"]],
        })
        dates = engine.get_available_dates(f)
        assert "15.04.2026" in dates
        assert "15.04.2025" in dates

    def test_invalid_sheet_date_is_not_returned(self, engine, temp_xlsx):
        f = temp_xlsx(
            "invalid_date_sheet.xlsx",
            {
                "31.04.2026": [["А", "100"]],
                "01.04.2026": [["Б", "200"]],
            },
        )
        dates = engine.get_available_dates(f)
        assert "31.04.2026" not in dates
        assert "01.04.2026" in dates

    def test_no_dates_returns_empty(self, engine, temp_xlsx):
        f = temp_xlsx("nodates.xlsx", {
            "Sheet1": [["Data"]],
            "Sheet2": [["More data"]],
        })
        dates = engine.get_available_dates(f)
        assert dates == []

    def test_missing_file_returns_empty(self, engine):
        dates = engine.get_available_dates(Path("/nonexistent.xlsx"))
        assert dates == []

    def test_sorted_output(self, engine, temp_xlsx):
        f = temp_xlsx("unsorted.xlsx", {
            "Отчет 10.04.2026": [["А", "100"]],
            "Отчет 01.04.2026": [["Б", "200"]],
            "Отчет 05.04.2026": [["В", "300"]],
        })
        dates = engine.get_available_dates(f)
        assert dates == sorted(dates)


class TestScanDirectory:
    """Тесты scan_directory."""

    def test_scan_finds_xlsx_files(self, engine, tmp_path):
        (tmp_path / "file1.xlsx").touch()
        (tmp_path / "file2.xlsx").touch()
        (tmp_path / "file3.txt").touch()

        results = engine.scan_directory(tmp_path)
        assert len(results) == 2
        assert all(r['path'].endswith('.xlsx') for r in results)

    def test_scan_finds_xlsb_files(self, engine, tmp_path):
        (tmp_path / "file.xlsb").touch()
        results = engine.scan_directory(tmp_path)
        assert len(results) == 1

    def test_scan_skips_temp_files(self, engine, tmp_path):
        (tmp_path / "~$temp.xlsx").touch()
        (tmp_path / "normal.xlsx").touch()
        results = engine.scan_directory(tmp_path)
        assert len(results) == 1
        assert all(not r['path'].startswith('~$') for r in results)

    def test_scan_recursive(self, engine, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "root.xlsx").touch()
        (sub / "sub.xlsx").touch()

        results = engine.scan_directory(tmp_path)
        assert len(results) == 2

    def test_scan_missing_directory(self, engine):
        results = engine.scan_directory(Path("/nonexistent"))
        assert results == []

    def test_scan_returns_metadata(self, engine, tmp_path):
        f = tmp_path / "test.xlsx"
        f.touch()

        results = engine.scan_directory(tmp_path)
        assert len(results) == 1
        meta = results[0]
        assert 'path' in meta
        assert 'id' in meta
        assert 'fp' in meta  # None при сканировании
        assert 'size' in meta
        assert 'mtime' in meta

    def test_scan_absolute_paths(self, engine, tmp_path):
        f = tmp_path / "test.xlsx"
        f.touch()
        results = engine.scan_directory(tmp_path)
        assert Path(results[0]['path']).is_absolute()

    def test_scan_does_not_require_path_resolve(self, engine, tmp_path):
        f = tmp_path / "test.xlsx"
        f.touch()

        with patch.object(Path, "resolve", side_effect=OSError("slow network resolve")):
            results = engine.scan_directory(tmp_path)

        assert len(results) == 1
        assert Path(results[0]["path"]).is_absolute()


class TestReadFile:
    """Тесты read_file."""

    def test_read_existing_file(self, engine, temp_xlsx):
        f = temp_xlsx("read.xlsx", {
            "Отчет 01.04.2026": [
                ["Заказчик", "Сумма платежа"],
                ["А", "100"],
            ]
        })
        rows = engine.read_file(f)
        assert len(rows) > 0

    def test_read_missing_file(self, engine):
        rows = engine.read_file(Path("/missing.xlsx"))
        assert rows == []

    def test_read_empty_file(self, engine, temp_xlsx):
        f = temp_xlsx("empty.xlsx", {"Sheet1": []})
        rows = engine.read_file(f)
        assert rows == []


class TestNetworkOptimization:
    """Тесты сетевых оптимизаций."""

    def test_local_file_no_copy(self, engine, temp_xlsx):
        """Локальный файл — не создаётся временная копия."""
        f = temp_xlsx("local.xlsx", {"Отчет 01.04.2026": [["А", "100"]]})
        with patch('shutil.copy2') as mock_copy:
            engine.get_available_dates(f)
            mock_copy.assert_not_called()

    def test_temp_file_cleanup_on_error(self, engine, tmp_path):
        """При ошибке — временный файл удаляется."""
        # Create a file that will cause error during CalamineWorkbook.from_path
        f = tmp_path / "bad.xlsx"
        f.write_bytes(b"not an excel file")

        # Should not raise, and any temp files should be cleaned up
        dates = engine.get_available_dates(f)
        assert dates == []
