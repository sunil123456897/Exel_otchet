"""Расширенные тесты для ingestion_engine.py — Покрытие пропущенных веток."""

import pytest
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
from core.infra.ingestion_engine import IngestionEngine
from core.domain.utils_helpers import get_local_copy


@pytest.fixture
def markers():
    return {
        "customer": "заказчик",
        "amount": "сумма платежа",
    }


@pytest.fixture
def engine(markers):
    return IngestionEngine(markers)


def test_get_available_dates_network_mock(engine, tmp_path):
    """Cover lines 42-45: Network file detection and get_local_copy."""
    network_path = Path("\\\\server\\share\\file.xlsx")

    with (
        patch(
            "core.domain.utils_helpers.get_local_copy",
            return_value=(str(network_path), None),
        ),
        patch("python_calamine.CalamineWorkbook.from_path") as mock_wb,
    ):
        mock_wb.return_value.sheet_names = ["Отчет 01.01"]

        dates = engine.get_available_dates(network_path)

        assert "01.01.2026" in dates


def test_get_available_dates_exception_logging(engine, tmp_path):
    """Cover lines 56-57: Exception logging in get_available_dates."""
    f = tmp_path / "error.xlsx"
    f.touch()

    with (
        patch(
            "python_calamine.CalamineWorkbook.from_path",
            side_effect=RuntimeError("Test error"),
        ),
        patch("core.infra.ingestion_engine.logger") as mock_logger,
    ):
        dates = engine.get_available_dates(f)
        assert dates == []
        mock_logger.error.assert_called()


def test_scan_directory_exception_logging(engine, tmp_path):
    """Cover lines 80-81: Exception logging in scan_directory."""
    f = tmp_path / "unreadable.xlsx"
    f.touch()

    # We want root_path.exists() to succeed, so we need to be careful with patching os.stat
    # since pathlib.Path.exists() calls os.stat.
    # We'll use a side_effect function that only raises error for the specific file.
    original_stat = os.stat

    def side_effect(path, *args, **kwargs):
        if str(path).endswith("unreadable.xlsx"):
            raise PermissionError("Access denied")
        return original_stat(path, *args, **kwargs)

    with (
        patch("os.stat", side_effect=side_effect),
        patch("core.infra.ingestion_engine.logger") as mock_logger,
    ):
        res = engine.scan_directory(tmp_path)
        # Should still find the directory but fail on the file
        mock_logger.error.assert_called()


def test_scan_directory_network_drive(engine, tmp_path):
    """Cover network drive detection (Q: or Z:)."""
    # Case Q:
    q_path = Path("Q:\\some\\file.xlsx")
    q_local = str(tmp_path / "q_local.xlsx")
    with (
        patch("core.domain.utils_helpers.get_local_copy", return_value=(q_local, None)),
        patch("python_calamine.CalamineWorkbook.from_path") as mock_wb,
    ):
        mock_wb.return_value.sheet_names = ["Отчет 02.02"]
        dates = engine.get_available_dates(q_path)
        assert "02.02.2026" in dates

    # Case Z:
    z_path = Path("Z:\\some\\file.xlsx")
    z_local = str(tmp_path / "z_local.xlsx")
    with (
        patch("core.domain.utils_helpers.get_local_copy", return_value=(z_local, None)),
        patch("python_calamine.CalamineWorkbook.from_path") as mock_wb,
    ):
        mock_wb.return_value.sheet_names = ["Отчет 03.03"]
        dates = engine.get_available_dates(z_path)
        assert "03.03.2026" in dates
