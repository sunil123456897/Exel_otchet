import os
import shutil
import pytest
import tempfile
import logging
import time
from decimal import Decimal
from unittest.mock import patch, MagicMock
from pathlib import Path
from core.infra.ingestion_reader import CalamineReader
from core.infra.ingestion_engine import IngestionEngine
from python_calamine import CalamineWorkbook

MARKERS = {
    "amount": ["сумма"],
    "customer": ["клиент", "контрагент"],
    "contractor": ["контрагент"],
    "date": ["дата"],
}
ALIASES = {}


@pytest.fixture
def reader():
    return CalamineReader(markers=MARKERS, aliases=ALIASES)


def test_local_copy_success(tmp_path, reader, create_temp_xlsx):
    real_source_file = tmp_path / "network_file.xlsx"
    data = [["Дата", "Контрагент", "Сумма"], ["01.01.2023", "Network Client", 1234.56]]
    sheet_name = "Data 01.01.2023"
    create_temp_xlsx(real_source_file, data, sheet_name=sheet_name)

    unc_path = r"\\server\share\file.xlsx"
    temp_copy_path = str(tmp_path / "local_temp_copy.xlsx")

    with patch(
        "core.infra.ingestion_reader.get_local_copy",
        return_value=(str(real_source_file), None),
    ):
        results = reader.read(Path(unc_path))
        assert len(results) > 0
        assert results[0]["amount"] == Decimal("1234.56")
        assert results[0]["contractor"] == "Network Client"


def test_network_failure_mid_copy(reader):
    unc_path = r"\\server\share\unreachable.xlsx"

    with (
        patch(
            "core.infra.ingestion_reader.get_local_copy", return_value=(unc_path, None)
        ),
        patch("core.infra.ingestion_reader.logger.error") as mock_log_error,
        patch(
            "python_calamine.CalamineWorkbook.from_path",
            side_effect=IOError("Connection reset by peer"),
        ),
    ):
        results = reader.read(Path(unc_path))

        assert results == []
        mock_log_error.assert_called()


def test_file_deleted_mid_read(tmp_path, reader, create_temp_xlsx):
    src_file = tmp_path / "src.xlsx"
    create_temp_xlsx(
        src_file,
        [["Date", "Client", "Sum"], ["01.01.2023", "A", 100]],
        sheet_name="01.01.2023",
    )

    unc_path = r"\\server\share\volatile.xlsx"

    with (
        patch(
            "core.infra.ingestion_reader.get_local_copy",
            return_value=(str(src_file), None),
        ),
        patch(
            "python_calamine.CalamineWorkbook.from_path",
            side_effect=FileNotFoundError("File disappeared during read!"),
        ),
        patch("core.infra.ingestion_reader.logger.error"),
    ):
        results = reader.read(Path(unc_path))
        assert results == []


def test_unsupported_network_path(reader):
    http_path = "http://raw.githubusercontent.com/test/data.xlsx"

    with (
        patch(
            "core.infra.ingestion_reader.get_local_copy", return_value=(http_path, None)
        ),
        patch("core.infra.ingestion_reader.logger"),
        patch(
            "python_calamine.CalamineWorkbook.from_path",
            side_effect=Exception("Skip read"),
        ),
    ):
        results = reader.read(Path(http_path))
        # get_local_copy returns path as-is for non-network paths (http:// doesn't start with \\ and isn't a drive letter)
        assert results == []


def test_ingestion_engine_retries_reader_os_error(tmp_path):
    engine = IngestionEngine({})
    source = tmp_path / "retry.xlsx"
    source.touch()

    attempts = {"count": 0}

    def flaky_read(_, strict_io=False):
        attempts["count"] += 1
        raise OSError("network lost")

    engine.reader.read = flaky_read

    with patch("time.sleep"):
        rows = engine.read_file(source)

    assert rows == []
    assert attempts["count"] == 3
