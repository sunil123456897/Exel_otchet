import queue
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.app.file_processor import process_file_task


def test_process_file_task_marks_file_error_when_wait_for_writes_fails():
    persistence = MagicMock()
    persistence.save_file_metadata.return_value = [17]
    persistence.wait_for_writes.side_effect = RuntimeError("staging write failed")

    ingestion = MagicMock()
    ingestion.read_file.return_value = [{"date": "01.04.2026", "amount": 100}]

    validator = MagicMock()
    validator.validate_row.return_value = True

    meta = {"path": "C:/reports/a.xlsx"}

    with patch("os.path.exists", return_value=True):
        with pytest.raises(RuntimeError, match="staging write failed"):
            process_file_task(
                persistence,
                ingestion,
                validator,
                "Alice",
                meta,
                "session-1",
                "01.04.2026",
            )

    persistence.update_file_status.assert_any_call(17, "error", "staging write failed")
    assert (17, "processed") not in [
        call.args for call in persistence.update_file_status.call_args_list
    ]
