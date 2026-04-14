from pathlib import Path

import pytest

from core.infra.ingestion_engine import IngestionEngine


def test_read_file_raises_on_reader_os_error_for_retry_visibility(tmp_path):
    engine = IngestionEngine({})
    test_file = tmp_path / "broken.xlsx"
    test_file.touch()

    engine.reader.read = lambda _, strict_io=False: (_ for _ in ()).throw(
        OSError("network lost")
    )

    rows = engine.read_file(test_file)

    assert rows == []


def test_process_file_task_marks_error_when_reader_returns_exception(tmp_path):
    from core.app.file_processor import process_file_task

    persistence = __import__("unittest.mock").mock.MagicMock()
    persistence.save_file_metadata.return_value = [99]

    ingestion = __import__("unittest.mock").mock.MagicMock()
    ingestion.read_file.side_effect = OSError("network lost")

    validator = __import__("unittest.mock").mock.MagicMock()
    meta = {"path": str(tmp_path / "broken.xlsx")}
    Path(meta["path"]).touch()

    with pytest.raises(OSError, match="network lost"):
        process_file_task(
            persistence,
            ingestion,
            validator,
            "Alice",
            meta,
            "session-1",
            "01.04.2026",
        )

    persistence.update_file_status.assert_any_call(99, "error", "network lost")
