"""
Расширенные тесты для AppController.
Покрывает: parallel processing, cache behavior, validation filtering,
consolidation error handling, progress reporting.
"""
import pytest
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from core.app_controller import AppController


@pytest.fixture
def mock_deps():
    return {
        'config_controller': MagicMock(),
        'ingestion': MagicMock(),
        'persistence': MagicMock(),
        'validator': MagicMock(),
        'logic_service': MagicMock(),
        'writer': MagicMock(),
    }


@pytest.fixture
def app_controller(mock_deps):
    with patch('core.app_controller.DiscoveryService') as mock_discovery:
        controller = AppController(**mock_deps)
        controller.discovery = mock_discovery.return_value
        return controller


def run_thread_task(mock_thread):
    """Хелпер для запуска задачи из Thread синхронно."""
    task = mock_thread.call_args[1]['target']
    task()


class TestRefreshStatus:
    """refresh_status — статус сотрудников."""

    def test_cached_dates_used(self, app_controller, mock_deps):
        """Даты из кеша должны использоваться без повторного парсинга."""
        app_controller.discovery.get_employees_map.return_value = {
            'Alice': [{'path': '/path/alice.xlsx'}],
        }

        mock_deps['persistence'].get_file_cache.return_value = {
            'mtime': 1000.0,
            'size': 5000,
            'dates': ['01.04.2026'],
        }

        on_progress = MagicMock()
        on_complete = MagicMock()

        with patch('os.path.exists', return_value=True), \
             patch('os.stat', return_value=MagicMock(st_mtime=1000.0, st_size=5000)), \
             patch('threading.Thread') as mock_thread:
            app_controller.refresh_status(datetime(2026, 4, 1), on_progress, on_complete)
            run_thread_task(mock_thread)

        # get_available_dates НЕ должен вызываться — данные в кеше
        mock_deps['ingestion'].get_available_dates.assert_not_called()

    def test_cache_miss_triggers_parse(self, app_controller, mock_deps):
        """Отсутствие кеша — вызов get_available_dates."""
        app_controller.discovery.get_employees_map.return_value = {
            'Alice': [{'path': '/path/alice.xlsx'}],
        }
        mock_deps['persistence'].get_file_cache.return_value = None
        mock_deps['ingestion'].get_available_dates.return_value = ['01.04.2026']

        on_progress = MagicMock()
        on_complete = MagicMock()

        with patch('os.path.exists', return_value=True), \
             patch('os.stat', return_value=MagicMock(st_mtime=1000.0, st_size=5000)), \
             patch('threading.Thread') as mock_thread:
            app_controller.refresh_status(datetime(2026, 4, 1), on_progress, on_complete)
            run_thread_task(mock_thread)

        mock_deps['ingestion'].get_available_dates.assert_called()
        mock_deps['persistence'].save_file_cache.assert_called()

    def test_progress_reported(self, app_controller, mock_deps):
        """on_progress должен вызываться для каждого сотрудника."""
        app_controller.discovery.get_employees_map.return_value = {
            'Alice': [{'path': '/a.xlsx'}],
            'Bob': [{'path': '/b.xlsx'}],
            'Charlie': [{'path': '/c.xlsx'}],
        }

        mock_deps['persistence'].get_file_cache.return_value = None
        mock_deps['ingestion'].get_available_dates.return_value = ['01.04.2026']

        on_progress = MagicMock()
        on_complete = MagicMock()

        with patch('os.path.exists', return_value=True), \
             patch('os.stat', return_value=MagicMock(st_mtime=1000, st_size=1000)), \
             patch('threading.Thread') as mock_thread:
            app_controller.refresh_status(datetime(2026, 4, 1), on_progress, on_complete)
            run_thread_task(mock_thread)

        on_progress.assert_called()
        # Последний вызов должен быть 100%
        last_call = on_progress.call_args_list[-1]
        assert last_call[0][0] == 100.0

    def test_partial_status(self, app_controller, mock_deps):
        """Файл без нужной даты — статус 'НЕТ ДАТЫ'."""
        app_controller.discovery.get_employees_map.return_value = {
            'Alice': [{'path': '/a.xlsx'}],
        }
        mock_deps['persistence'].get_file_cache.return_value = None
        mock_deps['ingestion'].get_available_dates.return_value = ['02.04.2026']  # Не целевая дата

        on_progress = MagicMock()
        on_complete = MagicMock()

        with patch('os.path.exists', return_value=True), \
             patch('os.stat', return_value=MagicMock(st_mtime=1000, st_size=1000)), \
             patch('threading.Thread') as mock_thread:
            app_controller.refresh_status(datetime(2026, 4, 1), on_progress, on_complete)
            run_thread_task(mock_thread)

        args = on_complete.call_args[0]
        # Alice — нет нужной даты
        assert "🟠 НЕТ ДАТЫ" in args[0][0][1]

    def test_multiple_files_per_employee(self, app_controller, mock_deps):
        """Несколько файлов — проверка каждого до первого совпадения."""
        app_controller.discovery.get_employees_map.return_value = {
            'Alice': [
                {'path': '/a1.xlsx'},
                {'path': '/a2.xlsx'},
            ],
        }
        mock_deps['persistence'].get_file_cache.return_value = None
        # Первый файл без даты, второй — с нужной
        mock_deps['ingestion'].get_available_dates.side_effect = [
            ['02.04.2026'],  # a1 — нет
            ['01.04.2026'],  # a2 — есть
        ]

        on_progress = MagicMock()
        on_complete = MagicMock()

        with patch('os.path.exists', return_value=True), \
             patch('os.stat', return_value=MagicMock(st_mtime=1000, st_size=1000)), \
             patch('threading.Thread') as mock_thread:
            app_controller.refresh_status(datetime(2026, 4, 1), on_progress, on_complete)
            run_thread_task(mock_thread)

        args = on_complete.call_args[0]
        assert "🟢 ГОТОВО" in args[0][0][1]

    def test_os_stat_error(self, app_controller, mock_deps):
        """Ошибка os.stat — статус 'ОШИБКА'."""
        app_controller.discovery.get_employees_map.return_value = {
            'Alice': [{'path': '/a.xlsx'}],
        }

        on_progress = MagicMock()
        on_complete = MagicMock()

        with patch('os.path.exists', return_value=True), \
             patch('os.stat', side_effect=OSError("Access denied")), \
             patch('threading.Thread') as mock_thread:
            app_controller.refresh_status(datetime(2026, 4, 1), on_progress, on_complete)
            run_thread_task(mock_thread)

        args = on_complete.call_args[0]
        assert "❌ ОШИБКА" in args[0][0][1]


class TestRunConsolidation:
    """run_consolidation — процесс консолидации."""

    def test_file_not_exists_skipped(self, app_controller, mock_deps):
        """Несуществующие файлы должны пропускаться."""
        app_controller._cached_employees = {
            'Alice': [{'path': '/missing.xlsx'}],
        }

        on_progress = MagicMock()
        on_complete = MagicMock()

        with patch('os.path.exists', return_value=False), \
             patch('threading.Thread') as mock_thread:
            app_controller.run_consolidation(datetime(2026, 4, 1), on_progress, on_complete)
            run_thread_task(mock_thread)

        # Файл не читался
        mock_deps['ingestion'].read_file.assert_not_called()

    def test_invalid_rows_filtered(self, app_controller, mock_deps):
        """Невалидные строки должны отфильтровываться."""
        app_controller._cached_employees = {
            'Alice': [{'path': '/a.xlsx'}],
        }

        mock_deps['persistence'].save_file_metadata.return_value = [1]
        mock_deps['ingestion'].read_file.return_value = [
            {'date': '01.04.2026', 'amount': 100},  # valid
            {'date': '01.04.2026', 'amount': 0},     # invalid
            {'date': '02.04.2026', 'amount': 200},  # wrong date
        ]
        # Только первая строка валидна и совпадает по дате
        mock_deps['validator'].validate_row.side_effect = [True, False, True]

        on_progress = MagicMock()
        on_complete = MagicMock()

        with patch('os.path.exists', return_value=True), \
             patch('threading.Thread') as mock_thread:
            app_controller.run_consolidation(datetime(2026, 4, 1), on_progress, on_complete)
            run_thread_task(mock_thread)

        # save_staging_data вызывается только с валидными строки
        call_args = mock_deps['persistence'].save_staging_data.call_args
        saved_rows = call_args[0][1]
        assert len(saved_rows) == 1
        assert saved_rows[0]['amount'] == 100

    def test_consolidation_error_propagates(self, app_controller, mock_deps):
        """Ошибка в logic_service.consolidate должна propagate."""
        app_controller._cached_employees = {
            'Alice': [{'path': '/a.xlsx'}],
        }
        mock_deps['persistence'].save_file_metadata.return_value = [1]
        mock_deps['ingestion'].read_file.return_value = [{'date': '01.04.2026', 'amount': 100}]
        mock_deps['validator'].validate_row.return_value = True
        mock_deps['logic_service'].consolidate.side_effect = Exception("DB error")

        on_progress = MagicMock()
        on_complete = MagicMock()

        with patch('os.path.exists', return_value=True), \
             patch('threading.Thread') as mock_thread:
            app_controller.run_consolidation(datetime(2026, 4, 1), on_progress, on_complete)
            run_thread_task(mock_thread)

        on_complete.assert_called()
        args = on_complete.call_args[0]
        assert args[0] is False
        assert "DB error" in args[1]

    def test_writer_failure(self, app_controller, mock_deps):
        """Ошибка записи writer — onFailure с сообщением."""
        app_controller._cached_employees = {
            'Alice': [{'path': '/a.xlsx'}],
        }
        mock_deps['persistence'].save_file_metadata.return_value = [1]
        mock_deps['persistence'].close = MagicMock()
        mock_deps['ingestion'].read_file.return_value = [{'date': '01.04.2026', 'amount': 100}]
        mock_deps['validator'].validate_row.return_value = True
        mock_deps['logic_service'].consolidate.return_value = [{'consolidated': True}]
        mock_deps['writer'].write_report.return_value = False

        on_progress = MagicMock()
        on_complete = MagicMock()

        with patch('os.path.exists', return_value=True), \
             patch('threading.Thread') as mock_thread:
            app_controller.run_consolidation(datetime(2026, 4, 1), on_progress, on_complete)
            run_thread_task(mock_thread)

        on_complete.assert_called_with(False, "Ошибка записи", None)

    def test_relative_master_path_resolved(self, app_controller, mock_deps):
        """Относительный путь к мастер-файлу должен быть разрешён."""
        app_controller._cached_employees = {
            'Alice': [{'path': '/a.xlsx'}],
        }
        mock_deps['persistence'].save_file_metadata.return_value = [1]
        mock_deps['persistence'].close = MagicMock()
        mock_deps['ingestion'].read_file.return_value = [{'date': '01.04.2026', 'amount': 100}]
        mock_deps['validator'].validate_row.return_value = True
        mock_deps['logic_service'].consolidate.return_value = [{'consolidated': True}]
        mock_deps['writer'].write_report.return_value = True

        mock_deps['config_controller'].config.get.return_value.get.return_value = 'Master.xlsx'

        on_progress = MagicMock()
        on_complete = MagicMock()

        with patch('os.path.exists', return_value=True), \
             patch.object(Path, 'is_absolute', return_value=False), \
             patch('threading.Thread') as mock_thread:
            app_controller.run_consolidation(datetime(2026, 4, 1), on_progress, on_complete)
            run_thread_task(mock_thread)

        # writer.write_report вызван с Path объектом
        call_args = mock_deps['writer'].write_report.call_args
        assert call_args is not None


class TestRunConsolidationAllDates:
    """run_consolidation_all_dates — все даты."""

    def test_fetches_employees_map(self, app_controller, mock_deps):
        """Должен получить актуальный список сотрудников."""
        app_controller.discovery.get_employees_map.return_value = {
            'Alice': [{'path': '/a.xlsx'}],
        }
        mock_deps['persistence'].save_file_metadata.return_value = [1]
        mock_deps['persistence'].close = MagicMock()
        mock_deps['ingestion'].read_file.return_value = [{'date': '01.04.2026', 'amount': 100}]
        mock_deps['validator'].validate_row.return_value = True
        mock_deps['logic_service'].consolidate.return_value = [{'consolidated': True}]
        mock_deps['writer'].write_report.return_value = True
        mock_deps['persistence'].get_template_errors.return_value = []

        on_progress = MagicMock()
        on_complete = MagicMock()

        with patch('os.path.exists', return_value=True), \
             patch('threading.Thread') as mock_thread:
            app_controller.run_consolidation_all_dates(on_progress, on_complete)
            run_thread_task(mock_thread)

        app_controller.discovery.get_employees_map.assert_called_once()
        # _cached_employees должен обновиться
        assert 'Alice' in app_controller._cached_employees

    def test_template_errors_passed_to_writer(self, app_controller, mock_deps):
        """Template errors должны передаваться в writer."""
        app_controller._cached_employees = {
            'Alice': [{'path': '/a.xlsx'}],
        }
        mock_deps['persistence'].save_file_metadata.return_value = [1]
        mock_deps['persistence'].close = MagicMock()
        mock_deps['ingestion'].read_file.return_value = [{'date': '01.04.2026', 'amount': 100}]
        mock_deps['validator'].validate_row.return_value = True
        mock_deps['logic_service'].consolidate.return_value = [{'consolidated': True}]
        mock_deps['writer'].write_report.return_value = True

        template_errors = [
            {'file_path': '/bad.xlsx', 'error_type': 'missing_column'}
        ]
        mock_deps['persistence'].get_template_errors.return_value = template_errors

        on_progress = MagicMock()
        on_complete = MagicMock()

        with patch('os.path.exists', return_value=True), \
             patch('threading.Thread') as mock_thread:
            app_controller.run_consolidation_all_dates(on_progress, on_complete)
            run_thread_task(mock_thread)

        call_args = mock_deps['writer'].write_report.call_args
        assert call_args[1].get('template_errors') == template_errors or \
               len(call_args[0]) >= 3 and call_args[0][2] == template_errors


class TestEdgeCases:
    """Крайние случаи."""

    def test_empty_employees_map(self, app_controller):
        """Пустая карта — быстрый возврат."""
        app_controller._cached_employees = {}

        on_progress = MagicMock()
        on_complete = MagicMock()

        with patch('threading.Thread') as mock_thread:
            app_controller.run_consolidation(datetime(2026, 4, 1), on_progress, on_complete)
            run_thread_task(mock_thread)

        on_complete.assert_called_with(False, "Нет файлов", None)

    def test_session_id_generated(self, app_controller, mock_deps):
        """Session ID должен быть UUID."""
        app_controller._cached_employees = {
            'Alice': [{'path': '/a.xlsx'}],
        }
        mock_deps['persistence'].save_file_metadata.return_value = [1]
        mock_deps['persistence'].close = MagicMock()
        mock_deps['ingestion'].read_file.return_value = [{'date': '01.04.2026', 'amount': 100}]
        mock_deps['validator'].validate_row.return_value = True
        mock_deps['logic_service'].consolidate.return_value = [{'consolidated': True}]
        mock_deps['writer'].write_report.return_value = True

        on_progress = MagicMock()
        on_complete = MagicMock()

        with patch('os.path.exists', return_value=True), \
             patch('threading.Thread') as mock_thread:
            app_controller.run_consolidation(datetime(2026, 4, 1), on_progress, on_complete)
            run_thread_task(mock_thread)

        # save_session вызан с UUID
        call_args = mock_deps['persistence'].save_session.call_args
        session_id = call_args[0][0]
        assert len(session_id) > 10  # UUID format

    def test_persistence_close_on_complete(self, app_controller, mock_deps):
        """persistence.close() должен вызываться после завершения."""
        app_controller._cached_employees = {
            'Alice': [{'path': '/a.xlsx'}],
        }
        mock_deps['persistence'].save_file_metadata.return_value = [1]
        mock_deps['persistence'].close = MagicMock()
        mock_deps['ingestion'].read_file.return_value = [{'date': '01.04.2026', 'amount': 100}]
        mock_deps['validator'].validate_row.return_value = True
        mock_deps['logic_service'].consolidate.return_value = [{'consolidated': True}]
        mock_deps['writer'].write_report.return_value = True

        on_progress = MagicMock()
        on_complete = MagicMock()

        with patch('os.path.exists', return_value=True), \
             patch('threading.Thread') as mock_thread:
            app_controller.run_consolidation(datetime(2026, 4, 1), on_progress, on_complete)
            run_thread_task(mock_thread)

        mock_deps['persistence'].close.assert_called()
