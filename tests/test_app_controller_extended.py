"""
Расширенные тесты для AppController.
Покрывает: parallel processing, cache behavior, validation filtering,
consolidation error handling, progress reporting.
"""

import pytest
import os
from datetime import datetime
from pathlib import Path
import queue
from unittest.mock import MagicMock, patch, call
from core.app_controller import AppController


@pytest.fixture
def mock_deps():
    return {
        "config_controller": MagicMock(),
        "ingestion": MagicMock(),
        "persistence": MagicMock(),
        "validator": MagicMock(),
        "logic_service": MagicMock(),
        "writer": MagicMock(),
    }


@pytest.fixture
def app_controller(mock_deps):
    with patch("core.app_controller.DiscoveryService") as mock_discovery:
        controller = AppController(**mock_deps)
        controller.discovery = mock_discovery.return_value
        return controller


def run_thread_task(mock_thread):
    """Хелпер для запуска задачи из Thread синхронно."""
    if mock_thread.call_args is None:
        # print(f"DEBUG: mock_thread.call_args is None! Method called: {mock_thread.method_calls}")
        return
    with patch("concurrent.futures.ThreadPoolExecutor") as mock_executor:
        mock_executor.return_value.__enter__.return_value = mock_executor.return_value

        def sync_submit(fn, *args, **kwargs):
            res = fn(*args, **kwargs)
            f = MagicMock()
            f.result.return_value = res
            return f

        mock_executor.return_value.submit.side_effect = sync_submit
        with patch("concurrent.futures.as_completed", side_effect=lambda fs: list(fs)):
            task = mock_thread.call_args[1]["target"]
            task()


class TestRefreshStatus:
    """refresh_status — статус сотрудников."""

    def test_cached_dates_used(self, app_controller, mock_deps):
        """Даты из кеша должны использоваться без повторного парсинга."""
        app_controller.discovery.get_employees_map.return_value = {
            "Alice": [{"path": "/path/alice.xlsx"}],
        }

        mock_deps["persistence"].get_file_cache.return_value = {
            "mtime": 1000.0,
            "size": 5000,
            "dates": ["01.04.2026"],
        }

        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("os.path.exists", return_value=True),
            patch("os.stat", return_value=MagicMock(st_mtime=1000.0, st_size=5000)),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.refresh_status(
                datetime(2026, 4, 1), on_progress, on_complete
            )
            run_thread_task(mock_thread)

        # get_available_dates НЕ должен вызываться — данные в кеше
        mock_deps["ingestion"].get_available_dates.assert_not_called()

    def test_cache_miss_triggers_parse(self, app_controller, mock_deps):
        """Отсутствие кеша — вызов get_available_dates."""
        app_controller.discovery.get_employees_map.return_value = {
            "Alice": [{"path": "/path/alice.xlsx"}],
        }
        mock_deps["persistence"].get_file_cache.return_value = None
        mock_deps["ingestion"].get_available_dates.return_value = ["01.04.2026"]

        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("os.path.exists", return_value=True),
            patch("os.stat", return_value=MagicMock(st_mtime=1000.0, st_size=5000)),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.refresh_status(
                datetime(2026, 4, 1), on_progress, on_complete
            )
            run_thread_task(mock_thread)

        mock_deps["ingestion"].get_available_dates.assert_called()
        mock_deps["persistence"].save_file_cache.assert_called()

    def test_progress_reported(self, app_controller, mock_deps):
        """on_progress должен вызываться для каждого сотрудника."""
        app_controller.discovery.get_employees_map.return_value = {
            "Alice": [{"path": "/a.xlsx"}],
            "Bob": [{"path": "/b.xlsx"}],
            "Charlie": [{"path": "/c.xlsx"}],
        }

        mock_deps["persistence"].get_file_cache.return_value = None
        mock_deps["ingestion"].get_available_dates.return_value = ["01.04.2026"]

        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("os.path.exists", return_value=True),
            patch("os.stat", return_value=MagicMock(st_mtime=1000, st_size=1000)),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.refresh_status(
                datetime(2026, 4, 1), on_progress, on_complete
            )
            run_thread_task(mock_thread)

        on_progress.assert_called()
        # Последний вызов должен быть 100%
        last_call = on_progress.call_args_list[-1]
        assert last_call[0][0] == 100.0

    def test_partial_status(self, app_controller, mock_deps):
        """Файл без нужной даты — статус 'НЕТ ДАТЫ'."""
        app_controller.discovery.get_employees_map.return_value = {
            "Alice": [{"path": "/a.xlsx"}],
        }
        mock_deps["persistence"].get_file_cache.return_value = None
        mock_deps["ingestion"].get_available_dates.return_value = [
            "02.04.2026"
        ]  # Не целевая дата

        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("os.path.exists", return_value=True),
            patch("os.stat", return_value=MagicMock(st_mtime=1000, st_size=1000)),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.refresh_status(
                datetime(2026, 4, 1), on_progress, on_complete
            )
            run_thread_task(mock_thread)

        args = on_complete.call_args[0]
        # Alice — нет нужной даты
        assert "🟠 НЕТ ДАТЫ" in args[0][0][1]

    def test_multiple_files_per_employee(self, app_controller, mock_deps):
        """Несколько файлов — проверка каждого до первого совпадения."""
        app_controller.discovery.get_employees_map.return_value = {
            "Alice": [
                {"path": "/a1.xlsx"},
                {"path": "/a2.xlsx"},
            ],
        }
        mock_deps["persistence"].get_file_cache.return_value = None
        # Первый файл без даты, второй — с нужной
        mock_deps["ingestion"].get_available_dates.side_effect = [
            ["02.04.2026"],  # a1 — нет
            ["01.04.2026"],  # a2 — есть
        ]

        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("os.path.exists", return_value=True),
            patch("os.stat", return_value=MagicMock(st_mtime=1000, st_size=1000)),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.refresh_status(
                datetime(2026, 4, 1), on_progress, on_complete
            )
            run_thread_task(mock_thread)

        args = on_complete.call_args[0]
        assert "🟢 ГОТОВО" in args[0][0][1]

    def test_os_stat_error(self, app_controller, mock_deps):
        """Ошибка os.stat — статус 'ОШИБКА'."""
        app_controller.discovery.get_employees_map.return_value = {
            "Alice": [{"path": "/a.xlsx"}],
        }

        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("os.path.exists", return_value=True),
            patch("os.stat", side_effect=OSError("Access denied")),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.refresh_status(
                datetime(2026, 4, 1), on_progress, on_complete
            )
            run_thread_task(mock_thread)

        args = on_complete.call_args[0]
        assert "[ERR] ОШИБКА" in args[0][0][1]


class TestRunConsolidation:
    """run_consolidation — процесс консолидации."""

    def test_file_not_exists_skipped(self, app_controller, mock_deps):
        """Несуществующие файлы должны пропускаться."""
        missing_path = "/missing.xlsx"
        app_controller._cached_employees = {
            "Alice": [{"path": missing_path}],
        }

        on_progress = MagicMock()
        on_complete = MagicMock()

        # Mock os.path.exists to return False for the missing path
        with (
            patch("os.path.exists", side_effect=lambda p: p != missing_path),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.run_consolidation(
                datetime(2026, 4, 1), on_progress, on_complete
            )
            run_thread_task(mock_thread)

        # Файл не читался
        mock_deps["ingestion"].read_file.assert_not_called()

    def test_invalid_rows_filtered(self, app_controller, mock_deps):
        """Невалидные строки должны отфильтровываться."""
        app_controller._cached_employees = {
            "Alice": [{"path": "/a.xlsx"}],
        }

        mock_deps["persistence"].save_file_metadata.return_value = [1]
        mock_deps["ingestion"].read_file.return_value = [
            {"date": "01.04.2026", "amount": 100},  # valid
            {"date": "01.04.2026", "amount": 0},  # invalid
            {"date": "02.04.2026", "amount": 200},  # wrong date
        ]
        # Только первая строка валидна и совпадает по дате
        mock_deps["validator"].validate_row.side_effect = [True, False, True]

        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.run_consolidation(
                datetime(2026, 4, 1), on_progress, on_complete
            )
            run_thread_task(mock_thread)

        # save_staging_data вызывается только с валидными строки
        call_args = mock_deps["persistence"].save_staging_data.call_args
        saved_rows = call_args[0][1]
        assert len(saved_rows) == 1
        assert saved_rows[0]["amount"] == 100

    def test_consolidation_error_propagates(self, app_controller, mock_deps):
        """Ошибка в logic_service.consolidate должна propagate."""
        app_controller._cached_employees = {
            "Alice": [{"path": "/a.xlsx"}],
        }
        mock_deps["persistence"].save_file_metadata.return_value = [1]
        mock_deps["ingestion"].read_file.return_value = [
            {"date": "01.04.2026", "amount": 100}
        ]
        mock_deps["validator"].validate_row.return_value = True
        mock_deps["logic_service"].consolidate.side_effect = Exception("DB error")

        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.run_consolidation(
                datetime(2026, 4, 1), on_progress, on_complete
            )
            run_thread_task(mock_thread)

        on_complete.assert_called()
        args = on_complete.call_args[0]
        assert args[0] is False
        assert "DB error" in args[1]

    def test_writer_failure(self, app_controller, mock_deps):
        """Ошибка записи writer — onFailure с сообщением."""
        app_controller._cached_employees = {
            "Alice": [{"path": "/a.xlsx"}],
        }
        mock_deps["persistence"].save_file_metadata.return_value = [1]
        mock_deps["persistence"].close = MagicMock()
        mock_deps["ingestion"].read_file.return_value = [
            {"date": "01.04.2026", "amount": 100}
        ]
        mock_deps["validator"].validate_row.return_value = True
        mock_deps["logic_service"].consolidate.return_value = [{"consolidated": True}]
        mock_deps["writer"].write_report.return_value = False

        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.run_consolidation(
                datetime(2026, 4, 1), on_progress, on_complete
            )
            run_thread_task(mock_thread)

        on_complete.assert_called_with(False, "Ошибка записи основного отчёта", None)

    def test_staging_write_failure_marks_file_and_session_failed(
        self, app_controller, mock_deps
    ):
        app_controller._cached_employees = {
            "Alice": [{"path": "/a.xlsx"}],
        }
        mock_deps["persistence"].save_file_metadata.return_value = [1]
        mock_deps["ingestion"].read_file.return_value = [
            {"date": "01.04.2026", "amount": 100}
        ]
        mock_deps["validator"].validate_row.return_value = True
        mock_deps["persistence"].wait_for_writes.side_effect = RuntimeError(
            "staging write failed"
        )

        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.run_consolidation(
                datetime(2026, 4, 1), on_progress, on_complete
            )
            run_thread_task(mock_thread)

        mock_deps["persistence"].update_file_status.assert_any_call(
            1, "error", "staging write failed"
        )
        mock_deps["persistence"].update_session_status.assert_called_with(
            mock_deps["persistence"].save_session.call_args[0][0], "failed"
        )
        on_complete.assert_called_with(False, "staging write failed", None)

    def test_session_status_marked_completed(self, app_controller, mock_deps):
        app_controller._cached_employees = {
            "Alice": [{"path": "/a.xlsx"}],
        }
        mock_deps["persistence"].save_file_metadata.return_value = [1]
        mock_deps["ingestion"].read_file.return_value = [
            {"date": "01.04.2026", "amount": 100}
        ]
        mock_deps["validator"].validate_row.return_value = True
        mock_deps["logic_service"].consolidate.return_value = [{"consolidated": True}]
        mock_deps["writer"].write_report.return_value = True
        mock_deps["persistence"].get_template_errors.return_value = []

        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.run_consolidation(
                datetime(2026, 4, 1), on_progress, on_complete
            )
            run_thread_task(mock_thread)

        mock_deps["persistence"].update_session_status.assert_called_with(
            mock_deps["persistence"].save_session.call_args[0][0], "completed"
        )

    def test_session_status_marked_failed_on_writer_error(
        self, app_controller, mock_deps
    ):
        app_controller._cached_employees = {
            "Alice": [{"path": "/a.xlsx"}],
        }
        mock_deps["persistence"].save_file_metadata.return_value = [1]
        mock_deps["ingestion"].read_file.return_value = [
            {"date": "01.04.2026", "amount": 100}
        ]
        mock_deps["validator"].validate_row.return_value = True
        mock_deps["logic_service"].consolidate.return_value = [{"consolidated": True}]
        mock_deps["writer"].write_report.return_value = False
        mock_deps["persistence"].get_template_errors.return_value = []

        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.run_consolidation(
                datetime(2026, 4, 1), on_progress, on_complete
            )
            run_thread_task(mock_thread)

        mock_deps["persistence"].update_session_status.assert_called_with(
            mock_deps["persistence"].save_session.call_args[0][0], "failed"
        )

    def test_relative_master_path_resolved(self, app_controller, mock_deps):
        """Относительный путь к мастер-файлу должен быть разрешён."""
        app_controller._cached_employees = {
            "Alice": [{"path": "/a.xlsx"}],
        }
        mock_deps["persistence"].save_file_metadata.return_value = [1]
        mock_deps["persistence"].close = MagicMock()
        mock_deps["ingestion"].read_file.return_value = [
            {"date": "01.04.2026", "amount": 100}
        ]
        mock_deps["validator"].validate_row.return_value = True
        mock_deps["logic_service"].consolidate.return_value = [{"consolidated": True}]
        mock_deps["writer"].write_report.return_value = True

        mock_deps[
            "config_controller"
        ].config.get.return_value.get.return_value = "Master.xlsx"

        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("os.path.exists", return_value=True),
            patch.object(Path, "is_absolute", return_value=False),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.run_consolidation(
                datetime(2026, 4, 1), on_progress, on_complete
            )
            run_thread_task(mock_thread)

        # writer.write_report вызван с Path объектом
        call_args = mock_deps["writer"].write_report.call_args
        assert call_args is not None


class TestRunConsolidationAllDates:
    """run_consolidation_all_dates — все даты."""

    def test_fetches_employees_map(self, app_controller, mock_deps):
        """Должен получить актуальный список сотрудников."""
        app_controller.discovery.get_employees_map.return_value = {
            "Alice": [{"path": "/a.xlsx"}],
        }
        mock_deps["persistence"].save_file_metadata.return_value = [1]
        mock_deps["persistence"].close = MagicMock()
        mock_deps["ingestion"].read_file.return_value = [
            {"date": "01.04.2026", "amount": 100}
        ]
        mock_deps["validator"].validate_row.return_value = True
        mock_deps["logic_service"].consolidate.return_value = [{"consolidated": True}]
        mock_deps["writer"].write_report.return_value = True
        mock_deps["persistence"].get_template_errors.return_value = []

        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.run_consolidation_all_dates(on_progress, on_complete)
            run_thread_task(mock_thread)

        app_controller.discovery.get_employees_map.assert_called_once()
        # _cached_employees должен обновиться
        assert "Alice" in app_controller._cached_employees

    def test_template_errors_passed_to_writer(self, app_controller, mock_deps):
        """Template errors должны передаваться в writer."""
        app_controller.discovery.get_employees_map.return_value = {
            "Alice": [{"path": "/a.xlsx"}],
        }
        mock_deps["persistence"].save_file_metadata.return_value = [1]
        mock_deps["persistence"].close = MagicMock()
        mock_deps["ingestion"].read_file.return_value = [
            {"date": "01.04.2026", "amount": 100}
        ]
        mock_deps["validator"].validate_row.return_value = True
        mock_deps["logic_service"].consolidate.return_value = [{"consolidated": True}]
        mock_deps["writer"].write_report.return_value = True

        template_errors = [{"file_path": "/bad.xlsx", "error_type": "missing_column"}]
        mock_deps["persistence"].get_template_errors.return_value = template_errors

        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch.object(
                app_controller.config_controller,
                "resolve_path",
                return_value=Path("/tmp/Master_Report.xlsx"),
            ),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.run_consolidation_all_dates(on_progress, on_complete)
            run_thread_task(mock_thread)

        call_args = mock_deps["writer"].write_report.call_args
        if call_args is None:
            pytest.fail("write_report was not called")
        assert (
            call_args[1].get("template_errors") == template_errors
            or len(call_args[0]) >= 3
            and call_args[0][2] == template_errors
        )

    def test_session_with_template_errors_not_marked_plain_completed(
        self, app_controller, mock_deps
    ):
        app_controller.discovery.get_employees_map.return_value = {
            "Alice": [{"path": "/a.xlsx"}],
        }
        mock_deps["persistence"].save_file_metadata.return_value = [1]
        mock_deps["persistence"].close = MagicMock()
        mock_deps["ingestion"].read_file.return_value = [
            {"date": "01.04.2026", "amount": 100}
        ]
        mock_deps["validator"].validate_row.return_value = True
        mock_deps["logic_service"].consolidate.return_value = [{"consolidated": True}]
        mock_deps["writer"].write_report.return_value = True
        mock_deps["persistence"].get_template_errors.return_value = [
            {"file_path": "/a.xlsx", "error_type": "template_warning"}
        ]

        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.run_consolidation_all_dates(on_progress, on_complete)
            run_thread_task(mock_thread)

        statuses = [
            c.args[1]
            for c in mock_deps["persistence"].update_session_status.call_args_list
        ]
        assert "completed" not in statuses

    def test_session_with_only_soft_structure_errors_stays_completed(
        self, app_controller, mock_deps
    ):
        app_controller.discovery.get_employees_map.return_value = {
            "Alice": [{"path": "/a.xlsx"}],
        }
        mock_deps["persistence"].save_file_metadata.return_value = [1]
        mock_deps["persistence"].close = MagicMock()
        mock_deps["ingestion"].read_file.return_value = [
            {"date": "01.04.2026", "amount": 100}
        ]
        mock_deps["validator"].validate_row.return_value = True
        mock_deps["logic_service"].consolidate.return_value = [{"consolidated": True}]
        mock_deps["writer"].write_report.return_value = True
        mock_deps["persistence"].get_template_errors.return_value = [
            {"file_path": "/a.xlsx", "error_type": "soft_structure"}
        ]

        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.run_consolidation_all_dates(on_progress, on_complete)
            run_thread_task(mock_thread)

        statuses = [
            c.args[1]
            for c in mock_deps["persistence"].update_session_status.call_args_list
        ]
        assert "completed" in statuses
        assert "completed_with_warnings" not in statuses


class TestEdgeCases:
    """Крайние случаи."""

    def test_empty_employees_map(self, app_controller):
        """Пустая карта — быстрый возврат."""
        app_controller._cached_employees = {}

        on_progress = MagicMock()
        on_complete = MagicMock()

        with patch("threading.Thread") as mock_thread:
            app_controller.run_consolidation(
                datetime(2026, 4, 1), on_progress, on_complete
            )
            run_thread_task(mock_thread)

        on_complete.assert_called_with(False, "Нет файлов", None)

    def test_session_id_generated(self, app_controller, mock_deps):
        """Session ID должен быть UUID."""
        app_controller._cached_employees = {
            "Alice": [{"path": "/a.xlsx"}],
        }
        mock_deps["persistence"].save_file_metadata.return_value = [1]
        mock_deps["persistence"].close = MagicMock()
        mock_deps["ingestion"].read_file.return_value = [
            {"date": "01.04.2026", "amount": 100}
        ]
        mock_deps["validator"].validate_row.return_value = True
        mock_deps["logic_service"].consolidate.return_value = [{"consolidated": True}]
        mock_deps["writer"].write_report.return_value = True

        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.run_consolidation(
                datetime(2026, 4, 1), on_progress, on_complete
            )
            run_thread_task(mock_thread)

        # save_session вызан с UUID
        call_args = mock_deps["persistence"].save_session.call_args
        session_id = call_args[0][0]
        assert len(session_id) > 10  # UUID format

    def test_persistence_close_on_complete(self, app_controller, mock_deps):
        """wait_for_writes() должен вызываться после завершения."""
        app_controller._cached_employees = {
            "Alice": [{"path": "/a.xlsx"}],
        }
        mock_deps["persistence"].save_file_metadata.return_value = [1]
        mock_deps["persistence"].wait_for_writes = MagicMock()
        mock_deps["ingestion"].read_file.return_value = [
            {"date": "01.04.2026", "amount": 100}
        ]
        mock_deps["validator"].validate_row.return_value = True
        mock_deps["logic_service"].consolidate.return_value = [{"consolidated": True}]
        mock_deps["writer"].write_report.return_value = True

        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.run_consolidation(
                datetime(2026, 4, 1), on_progress, on_complete
            )
            run_thread_task(mock_thread)

        mock_deps["persistence"].wait_for_writes.assert_called()


class TestRunConsolidationMonth:
    """run_consolidation_month — консолидация за период."""

    def test_date_range_filter(self, app_controller, mock_deps):
        """Данные должны фильтроваться по диапазону дат."""
        app_controller._cached_employees = {
            "Alice": [{"path": "/a.xlsx"}],
        }
        mock_deps["persistence"].save_file_metadata.return_value = [1]
        mock_deps["persistence"].close = MagicMock()
        mock_deps["ingestion"].read_file.return_value = [
            {"date": "01.03.2026", "amount": 100},  # в диапазоне
            {"date": "15.03.2026", "amount": 200},  # в диапазоне
            {"date": "01.04.2026", "amount": 300},  # вне диапазона
        ]
        mock_deps["validator"].validate_row.return_value = True

        on_progress = MagicMock()
        on_complete = MagicMock()

        start = datetime(2026, 3, 1)
        end = datetime(2026, 3, 31)

        with (
            patch("os.path.exists", return_value=True),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.run_consolidation_month(start, end, on_progress, on_complete)
            run_thread_task(mock_thread)

        # Только 2 строки должны пройти фильтр
        call_args = mock_deps["persistence"].save_staging_data.call_args
        saved_rows = call_args[0][1]
        assert len(saved_rows) == 2
        assert all(r["amount"] in [100, 200] for r in saved_rows)

    def test_success_message_includes_dates(self, app_controller, mock_deps):
        """Сообщение об успехе должно содержать даты периода."""
        app_controller._cached_employees = {
            "Alice": [{"path": "/a.xlsx"}],
        }
        mock_deps["persistence"].save_file_metadata.return_value = [1]
        mock_deps["persistence"].close = MagicMock()
        mock_deps["ingestion"].read_file.return_value = [
            {"date": "15.03.2026", "amount": 100}
        ]
        mock_deps["validator"].validate_row.return_value = True
        mock_deps["logic_service"].consolidate.return_value = [{"consolidated": True}]
        mock_deps["writer"].write_report.return_value = True

        on_progress = MagicMock()
        on_complete = MagicMock()

        start = datetime(2026, 3, 1)
        end = datetime(2026, 3, 31)

        with (
            patch("os.path.exists", return_value=True),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.run_consolidation_month(start, end, on_progress, on_complete)
            run_thread_task(mock_thread)

        on_complete.assert_called()
        args = on_complete.call_args[0]
        assert args[0] is True
        assert "01.03.2026" in args[1]
        assert "31.03.2026" in args[1]

    def test_no_data_in_range(self, app_controller, mock_deps):
        """Нет данных за период — сообщение об ошибке."""
        app_controller._cached_employees = {
            "Alice": [{"path": "/a.xlsx"}],
        }
        mock_deps["persistence"].save_file_metadata.return_value = [1]
        mock_deps["persistence"].close = MagicMock()
        mock_deps["ingestion"].read_file.return_value = [
            {"date": "01.01.2026", "amount": 100}
        ]
        mock_deps["validator"].validate_row.return_value = True
        mock_deps["logic_service"].consolidate.return_value = []  # Нет данных

        on_progress = MagicMock()
        on_complete = MagicMock()

        start = datetime(2026, 3, 1)
        end = datetime(2026, 3, 31)

        with (
            patch("os.path.exists", return_value=True),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.run_consolidation_month(start, end, on_progress, on_complete)
            run_thread_task(mock_thread)

        on_complete.assert_called()
        args = on_complete.call_args[0]
        assert args[0] is False
        assert "Нет данных за период" in args[1]

    def test_no_files(self, app_controller, mock_deps):
        """Нет файлов — быстрый возврат."""
        app_controller._cached_employees = {}

        on_progress = MagicMock()
        on_complete = MagicMock()

        with patch("threading.Thread") as mock_thread:
            app_controller.run_consolidation_month(
                datetime(2026, 3, 1), datetime(2026, 3, 31), on_progress, on_complete
            )
            run_thread_task(mock_thread)

        on_complete.assert_called_with(False, "Нет файлов", None)

    def test_session_type_is_monthly(self, app_controller, mock_deps):
        """Session должен иметь type='monthly'."""
        app_controller._cached_employees = {
            "Alice": [{"path": "/a.xlsx"}],
        }
        mock_deps["persistence"].save_file_metadata.return_value = [1]
        mock_deps["persistence"].close = MagicMock()
        mock_deps["ingestion"].read_file.return_value = [
            {"date": "15.03.2026", "amount": 100}
        ]
        mock_deps["validator"].validate_row.return_value = True
        mock_deps["logic_service"].consolidate.return_value = [{"consolidated": True}]
        mock_deps["writer"].write_report.return_value = True

        on_progress = MagicMock()
        on_complete = MagicMock()

        start = datetime(2026, 3, 1)
        end = datetime(2026, 3, 31)

        with (
            patch("os.path.exists", return_value=True),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.run_consolidation_month(start, end, on_progress, on_complete)
            run_thread_task(mock_thread)

        call_args = mock_deps["persistence"].save_session.call_args
        metadata = call_args[0][1]
        assert metadata["type"] == "monthly"
        assert metadata["start_date"] == "01.03.2026"
        assert metadata["end_date"] == "31.03.2026"

    def test_fetches_map_if_not_cached(self, app_controller, mock_deps):
        """Если _cached_employees пуст — должен получить из discovery."""
        app_controller._cached_employees = {}
        app_controller.discovery.get_employees_map.return_value = {
            "Alice": [{"path": "/a.xlsx"}],
        }
        mock_deps["persistence"].save_file_metadata.return_value = [1]
        mock_deps["persistence"].close = MagicMock()
        mock_deps["ingestion"].read_file.return_value = [
            {"date": "15.03.2026", "amount": 100}
        ]
        mock_deps["validator"].validate_row.return_value = True
        mock_deps["logic_service"].consolidate.return_value = [{"consolidated": True}]
        mock_deps["writer"].write_report.return_value = True

        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.run_consolidation_month(
                datetime(2026, 3, 1), datetime(2026, 3, 31), on_progress, on_complete
            )
            run_thread_task(mock_thread)

        app_controller.discovery.get_employees_map.assert_called_once()

    def test_writer_failure(self, app_controller, mock_deps):
        """Ошибка записи — onFailure."""
        app_controller._cached_employees = {
            "Alice": [{"path": "/a.xlsx"}],
        }
        mock_deps["persistence"].save_file_metadata.return_value = [1]
        mock_deps["persistence"].close = MagicMock()
        mock_deps["ingestion"].read_file.return_value = [
            {"date": "15.03.2026", "amount": 100}
        ]
        mock_deps["validator"].validate_row.return_value = True
        mock_deps["logic_service"].consolidate.return_value = [{"consolidated": True}]
        mock_deps["writer"].write_report.return_value = False

        on_progress = MagicMock()
        on_complete = MagicMock()

        with (
            patch("os.path.exists", return_value=True),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.run_consolidation_month(
                datetime(2026, 3, 1), datetime(2026, 3, 31), on_progress, on_complete
            )
            run_thread_task(mock_thread)

        on_complete.assert_called_with(False, "Ошибка записи основного отчёта", None)

    def test_cross_month_range(self, app_controller, mock_deps):
        """Диапазон может пересекать месяцы (например, 15 марта — 15 апреля)."""
        app_controller._cached_employees = {
            "Alice": [{"path": "/a.xlsx"}],
        }
        mock_deps["persistence"].save_file_metadata.return_value = [1]
        mock_deps["persistence"].close = MagicMock()
        mock_deps["ingestion"].read_file.return_value = [
            {"date": "20.03.2026", "amount": 100},  # в диапазоне
            {"date": "10.04.2026", "amount": 200},  # в диапазоне
            {"date": "20.04.2026", "amount": 300},  # вне диапазона
        ]
        mock_deps["validator"].validate_row.return_value = True
        mock_deps["logic_service"].consolidate.return_value = [{"consolidated": True}]
        mock_deps["writer"].write_report.return_value = True

        on_progress = MagicMock()
        on_complete = MagicMock()

        start = datetime(2026, 3, 15)
        end = datetime(2026, 4, 15)

        with (
            patch("os.path.exists", return_value=True),
            patch("core.app_controller.check_master_lock", return_value=True),
            patch("threading.Thread") as mock_thread,
        ):
            app_controller.run_consolidation_month(start, end, on_progress, on_complete)
            run_thread_task(mock_thread)

        call_args = mock_deps["persistence"].save_staging_data.call_args
        saved_rows = call_args[0][1]
        assert len(saved_rows) == 2
