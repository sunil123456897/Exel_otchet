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


def test_process_file_task_persists_soft_structure_warning_without_warning_status():
    persistence = MagicMock()
    persistence.save_file_metadata.return_value = [21]

    ingestion = MagicMock()
    ingestion.read_file.return_value = [
        {
            "date": "01.04.2026",
            "amount": 100,
            "customer": "ООО Ромашка",
            "_source_info": "a.xlsx | 01.04 | Row 5",
            "_template_warning_kind": "soft_structure",
            "_template_warning_reason": "unsupported header name: % -> % посредника",
            "is_template_warning": False,
        }
    ]

    validator = MagicMock()
    validator.validate_row.return_value = True

    meta = {"path": "C:/reports/a.xlsx"}

    with patch("os.path.exists", return_value=True):
        processed = process_file_task(
            persistence,
            ingestion,
            validator,
            "Alice",
            meta,
            "session-1",
            "01.04.2026",
        )

    assert processed == 1
    persistence.save_template_error.assert_called_once()
    saved_error = persistence.save_template_error.call_args.args[1]
    assert saved_error["error_type"] == "soft_structure"
    assert saved_error["details"] == "unsupported header name: % -> % посредника"
    persistence.update_file_status.assert_any_call(21, "processed")
    assert (21, "processed_with_warnings") not in [
        call.args for call in persistence.update_file_status.call_args_list
    ]
