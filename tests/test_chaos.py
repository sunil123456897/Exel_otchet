import os
import pytest
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch
from core.infra.ingestion_engine import IngestionEngine
from core.infra.ingestion_core import CalamineReader


def test_network_interruption_get_available_dates(monkeypatch, caplog):
    engine = IngestionEngine({})
    network_path = Path(r"\\SERVER\share\test.xlsx")

    def mock_copy2(*args, **kwargs):
        raise OSError("Network connection lost")

    class MockStat:
        st_mtime = 1
        st_size = 1

    monkeypatch.setattr(shutil, "copy2", mock_copy2)
    monkeypatch.setattr(os, "stat", lambda p, **kw: MockStat())

    dates = engine.get_available_dates(network_path)

    assert dates == []
    assert "Error getting dates from" in caplog.text


def test_network_interruption_read_file(monkeypatch, caplog):
    markers = {"amount": "Сумма"}
    aliases = {"amount": ["сумма"]}
    reader = CalamineReader(markers, aliases)
    network_path = Path(r"Q:\Reports\test.xlsx")

    def mock_copy2(*args, **kwargs):
        raise OSError("Network timeout")

    class MockStat:
        st_mtime = 1
        st_size = 1

    monkeypatch.setattr(shutil, "copy2", mock_copy2)
    monkeypatch.setattr(os, "stat", lambda p, **kw: MockStat())

    rows = reader.read(network_path)

    assert rows == []
    assert "Calamine error" in caplog.text


def test_ingestion_engine_read_file_handles_missing_file():
    engine = IngestionEngine({})
    missing_path = Path("non_existent_file.xlsx")

    # Act
    rows = engine.read_file(missing_path)

    # Assert
    assert rows == []


def test_ingestion_engine_get_available_dates_handles_exception_during_read(
    tmp_path, caplog
):
    # Setup: Create a real file but mock CalamineWorkbook to fail
    engine = IngestionEngine({})
    p = tmp_path / "test.xlsx"
    p.touch()

    with patch(
        "python_calamine.CalamineWorkbook.from_path",
        side_effect=Exception("Corrupt file"),
    ):
        # Act
        dates = engine.get_available_dates(p)

        # Assert
        assert dates == []
        assert "Error getting dates from" in caplog.text
        assert "Corrupt file" in caplog.text
