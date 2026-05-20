import queue
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.app.file_processor import process_file_task, date_matches_target, run_engine


def test_run_engine_propagates_wait_for_writes_failure():
    persistence = MagicMock()
    persistence.wait_for_writes.side_effect = RuntimeError("staging write failed")

    ingestion = MagicMock()
    validator = MagicMock()

    employees_map = {
        "Alice": [{"path": "C:/good.xlsx"}],
    }

    with patch("core.app.file_processor.process_file_task", return_value=1) as mock_task:
        with pytest.raises(RuntimeError, match="staging write failed"):
            run_engine(
                persistence,
                ingestion,
                validator,
                employees_map,
                "session-1",
                "01.04.2026",
                lambda _p: None,
            )
    persistence.wait_for_writes.assert_called_once()


def test_process_file_task_reads_with_strict_io_enabled():
    persistence = MagicMock()
    persistence.save_file_metadata.return_value = [5]

    ingestion = MagicMock()
    ingestion.read_file.return_value = [{"date": "01.04.2026", "amount": 100}]

    validator = MagicMock()
    validator.validate_row.return_value = True

    meta = {"path": "C:/reports/strict.xlsx"}

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
    ingestion.read_file.assert_called_once_with(
        Path("C:/reports/strict.xlsx"),
        strict_io=True,
        target_date_str="01.04.2026",
        start_date_str=None,
        end_date_str=None,
    )


def test_process_file_task_passes_date_scope_to_reader():
    persistence = MagicMock()
    persistence.save_file_metadata.return_value = [6]

    ingestion = MagicMock()
    ingestion.read_file.return_value = [{"date": "01.04.2026", "amount": 100}]

    validator = MagicMock()
    validator.validate_row.return_value = True

    meta = {"path": "C:/reports/scoped.xlsx"}

    with patch("os.path.exists", return_value=True):
        processed = process_file_task(
            persistence,
            ingestion,
            validator,
            "Alice",
            meta,
            "session-1",
            "01.04.2026",
            start_date_str=None,
            end_date_str=None,
        )

    assert processed == 1
    ingestion.read_file.assert_called_once_with(
        Path("C:/reports/scoped.xlsx"),
        strict_io=True,
        target_date_str="01.04.2026",
        start_date_str=None,
        end_date_str=None,
    )


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


def test_date_matches_target_accepts_short_dd_mm():
    target = __import__("datetime").datetime(2026, 4, 1)
    assert date_matches_target("01.04", target) is False


def test_process_file_task_all_dates_uses_file_year_for_short_dates():
    persistence = MagicMock()
    persistence.save_file_metadata.return_value = [41]

    ingestion = MagicMock()
    ingestion.read_file.return_value = [
        {"date": "18.04.2025", "amount": 150, "_sheet_year_hint": 2025},
    ]

    validator = MagicMock()
    validator.validate_row.return_value = True

    meta = {"path": "C:/reports/employee.xlsx"}

    with (
        patch("os.path.exists", return_value=True),
        patch("core.app.file_processor.datetime") as mock_datetime,
    ):
        real_datetime = __import__("datetime").datetime
        mock_datetime.now.return_value = real_datetime(2026, 4, 17)
        mock_datetime.strptime = __import__("datetime").datetime.strptime
        mock_datetime.min = real_datetime.min
        mock_datetime.combine.side_effect = real_datetime.combine

        processed = process_file_task(
            persistence,
            ingestion,
            validator,
            "Alice",
            meta,
            "session-1",
            None,
        )

    assert processed == 1
    saved_rows = persistence.save_staging_data.call_args.args[1]
    assert saved_rows[0]["date"] == "18.04.2025"


def test_date_matches_target_accepts_explicit_two_digit_year():
    target = __import__("datetime").datetime(2026, 4, 1)
    assert date_matches_target("01.04.26", target) is True


def test_process_file_task_all_dates_defaults_short_dates_to_current_year_without_hint():
    persistence = MagicMock()
    persistence.save_file_metadata.return_value = [42]

    ingestion = MagicMock()
    ingestion.read_file.return_value = [
        {"date": "10.04", "amount": 150},
    ]

    validator = MagicMock()
    validator.validate_row.return_value = True

    meta = {"path": "C:/reports/employee.xlsx"}

    with (
        patch("os.path.exists", return_value=True),
        patch("core.app.file_processor.datetime") as mock_datetime,
    ):
        real_datetime = __import__("datetime").datetime
        mock_datetime.now.return_value = real_datetime(2026, 4, 17)
        mock_datetime.strptime = __import__("datetime").datetime.strptime
        mock_datetime.min = real_datetime.min
        mock_datetime.combine.side_effect = real_datetime.combine

        processed = process_file_task(
            persistence,
            ingestion,
            validator,
            "Alice",
            meta,
            "session-1",
            None,
        )

    assert processed == 0
    persistence.save_staging_data.assert_not_called()
    persistence.save_template_error.assert_called_once()
    saved_error = persistence.save_template_error.call_args.args[1]
    assert saved_error["error_type"] == "missing_year"


def test_process_file_task_skips_future_and_invalid_dates_with_template_errors():
    persistence = MagicMock()
    persistence.save_file_metadata.return_value = [33]

    ingestion = MagicMock()
    ingestion.read_file.return_value = [
        {"date": "bad", "amount": 100, "_sheet_name": "S1", "_row_index": 2},
        {
            "date": "24.04.2999",
            "amount": 100,
            "_sheet_name": "S2",
            "_row_index": 3,
        },
        {"date": "01.04.2026", "amount": 200},
    ]

    validator = MagicMock()
    validator.validate_row.return_value = True

    meta = {"path": "C:/reports/mixed.xlsx"}

    with (
        patch("os.path.exists", return_value=True),
        patch("core.app.file_processor.datetime") as mock_datetime,
    ):
        real_datetime = __import__("datetime").datetime
        mock_datetime.now.return_value = real_datetime(2026, 4, 17)
        mock_datetime.strptime = __import__("datetime").datetime.strptime
        mock_datetime.min = real_datetime.min
        mock_datetime.combine.side_effect = real_datetime.combine

        processed = process_file_task(
            persistence,
            ingestion,
            validator,
            "Alice",
            meta,
            "session-1",
            None,
        )

    assert processed == 1
    assert persistence.save_template_error.call_count == 2
    saved_rows = persistence.save_staging_data.call_args.args[1]
    assert len(saved_rows) == 1
    assert saved_rows[0]["amount"] == 200


def test_run_engine_reports_failed_files_via_callback():
    persistence = MagicMock()
    ingestion = MagicMock()
    validator = MagicMock()
    errors = []

    def on_file_error(items):
        errors.extend(items)

    employees_map = {
        "Alice": [{"path": "C:/good.xlsx"}],
        "Bob": [{"path": "C:/bad.xlsx"}],
    }

    with patch("core.app.file_processor.process_file_task") as mock_task:
        mock_task.side_effect = [1, RuntimeError("broken")]
        ok = run_engine(
            persistence,
            ingestion,
            validator,
            employees_map,
            "session-1",
            "01.04.2026",
            lambda _p: None,
            on_file_error=on_file_error,
        )

    assert ok is True
    assert len(errors) == 1
    assert errors[0]["path"] == "C:/bad.xlsx"
