"""Тесты для ViewModels."""

import pytest
from datetime import datetime
from unittest.mock import MagicMock
from core.view_models.employee_list_viewmodel import (
    EmployeeListViewModel,
    EmployeeStatus,
)
from core.view_models.consolidation_viewmodel import ConsolidationViewModel


class TestEmployeeListViewModel:
    """Тесты EmployeeListViewModel."""

    def test_initial_state(self):
        vm = EmployeeListViewModel()
        assert vm.get_filtered_employees() == []
        assert vm.get_ready_count() == 0
        assert vm.get_total_count() == 0
        assert vm.get_missing_names() == []
        assert vm.rename_detected is False

    def test_set_data_via_callback(self):
        vm = EmployeeListViewModel()
        updated = []

        def on_update():
            updated.append(True)

        vm.set_update_callback(on_update)

        # Симуляция завершения refresh
        vm._all_employees = [
            EmployeeStatus("Alice", "🟢 ГОТОВО", "file.xlsx", "ready"),
            EmployeeStatus("Bob", "🔴 НЕТ ФАЙЛА", "---", "missing"),
        ]

        assert vm.get_ready_count() == 1
        assert vm.get_total_count() == 2
        assert vm.get_missing_names() == ["Bob"]

    def test_filter_by_search(self):
        vm = EmployeeListViewModel()
        vm._all_employees = [
            EmployeeStatus("Alice", "🟢 ГОТОВО", "file.xlsx", "ready"),
            EmployeeStatus("Bob", "🔴 НЕТ ФАЙЛА", "---", "missing"),
            EmployeeStatus("Charlie", "🟠 НЕТ ДАТЫ", "report.xlsx", "partial"),
        ]

        vm.search_query = "ali"
        filtered = vm.get_filtered_employees()
        assert len(filtered) == 1
        assert filtered[0].name == "Alice"

    def test_filter_by_status(self):
        vm = EmployeeListViewModel()
        vm._all_employees = [
            EmployeeStatus("Alice", "🟢 ГОТОВО", "file.xlsx", "ready"),
            EmployeeStatus("Bob", "🔴 НЕТ ФАЙЛА", "---", "missing"),
        ]

        vm.search_query = "готово"
        filtered = vm.get_filtered_employees()
        assert len(filtered) == 1
        assert filtered[0].name == "Alice"

    def test_get_selected_employee_path(self):
        vm = EmployeeListViewModel()
        vm._employees_map = {
            "Alice": [{"path": "/path/alice.xlsx"}],
            "Bob": [{"path": "/path/bob.xlsx"}],
        }

        assert vm.get_selected_employee_path("Alice") == "/path/alice.xlsx"
        assert vm.get_selected_employee_path("Missing") is None
        assert vm.get_selected_employee_path(None) is None

    def test_progress_percent(self):
        vm = EmployeeListViewModel()
        vm._all_employees = [
            EmployeeStatus("A", "🟢 ГОТОВО", "f.xlsx", "ready"),
            EmployeeStatus("B", "🟢 ГОТОВО", "f.xlsx", "ready"),
            EmployeeStatus("C", "🔴 НЕТ ФАЙЛА", "---", "missing"),
        ]
        assert vm.get_progress_percent() == pytest.approx(66.67, abs=0.1)

    def test_empty_progress(self):
        vm = EmployeeListViewModel()
        assert vm.get_progress_percent() == 0.0

    def test_employee_status_to_tuple(self):
        status = EmployeeStatus("Alice", "🟢 ГОТОВО", "a.xlsx", "ready")
        assert status.to_tuple() == ("Alice", "🟢 ГОТОВО", "a.xlsx", "ready")

    def test_refresh_updates_state_and_triggers_side_effects(self):
        vm = EmployeeListViewModel()
        updates = []

        vm.set_update_callback(lambda: updates.append(True))

        mock_controller = MagicMock()
        mock_controller.config_controller = MagicMock()

        def fake_refresh(selected_date, on_progress, on_complete, curator=None):
            on_complete(
                [("Alice", "🟢 ГОТОВО", "a.xlsx", "ready")],
                {"Alice": [{"path": "C:/a.xlsx"}]},
                True,
            )

        mock_controller.refresh_status.side_effect = fake_refresh

        vm.refresh(mock_controller, datetime(2026, 4, 1), lambda _p: None)

        assert vm.get_total_count() == 1
        assert vm.get_ready_count() == 1
        assert vm.rename_detected is True
        assert vm.get_selected_employee_path("Alice") == "C:/a.xlsx"
        mock_controller.config_controller.save_config.assert_called_once()
        assert updates == [True]

    def test_attach_files_delegates_to_config_controller(self):
        vm = EmployeeListViewModel()
        cfg = MagicMock()

        vm.attach_files(cfg, "Alice", ["a.xlsx", "b.xlsx"])

        cfg.attach_files.assert_called_once_with("Alice", ["a.xlsx", "b.xlsx"])

    def test_search_query_getter_returns_lowercase(self):
        vm = EmployeeListViewModel()

        vm.search_query = "AliCE"

        assert vm.search_query == "alice"

    def test_employees_map_property_returns_copy(self):
        vm = EmployeeListViewModel()
        vm._employees_map = {"Alice": [{"path": "C:/a.xlsx"}]}

        snapshot = vm.employees_map
        snapshot["Bob"] = [{"path": "C:/b.xlsx"}]

        assert "Bob" not in vm._employees_map


class TestConsolidationViewModel:
    """Тесты ConsolidationViewModel."""

    def test_initial_state(self):
        vm = ConsolidationViewModel()
        assert vm.is_running is False
        assert vm.progress == 0.0
        assert vm.get_button_state() == "normal"

    def test_can_run_single_date(self):
        vm = ConsolidationViewModel()
        assert vm.can_run_single_date(0) is True
        assert vm.can_run_single_date(3) is False

    def test_run_consolidation_updates_state(self):
        vm = ConsolidationViewModel()
        progress_values = []
        complete_results = []

        vm.set_callbacks(
            on_progress=lambda p: progress_values.append(p),
            on_complete=lambda ok, msg, path: complete_results.append((ok, msg, path)),
        )

        mock_controller = MagicMock()
        mock_controller.run_consolidation = lambda date, on_prog, on_comp, **kwargs: (
            on_prog(50.0),
            on_comp(True, "Успешно!", "/path/master.xlsx"),
        )

        vm.run_consolidation(mock_controller, datetime(2026, 4, 1))

        assert vm.is_running is False
        assert 50.0 in progress_values
        assert complete_results[0] == (True, "Успешно!", "/path/master.xlsx")

    def test_double_run_prevented(self):
        """Нельзя запустить дважды одновременно."""
        vm = ConsolidationViewModel()
        vm._is_running = True

        mock_controller = MagicMock()
        vm.run_consolidation(mock_controller, datetime(2026, 4, 1))

        mock_controller.run_consolidation.assert_not_called()

    def test_run_all_dates(self):
        vm = ConsolidationViewModel()
        progress_values = []
        complete_results = []

        vm.set_callbacks(
            on_progress=lambda p: progress_values.append(p),
            on_complete=lambda ok, msg, path: complete_results.append((ok, msg, path)),
        )

        mock_controller = MagicMock()
        mock_controller.run_consolidation_all_dates = (
            lambda on_prog, on_comp, **kwargs: (
                on_prog(75.0),
                on_comp(True, "Готово!", "/path/master.xlsx"),
            )
        )

        vm.run_consolidation_all_dates(mock_controller)

        assert vm.is_running is False
        assert 75.0 in progress_values

    def test_error_handling(self):
        vm = ConsolidationViewModel()
        complete_results = []

        vm.set_callbacks(
            on_progress=lambda p: None,
            on_complete=lambda ok, msg, path: complete_results.append((ok, msg, path)),
        )

        mock_controller = MagicMock()
        mock_controller.run_consolidation = lambda date, on_prog, on_comp, **kwargs: (
            on_comp(False, "DB error", None)
        )

        vm.run_consolidation(mock_controller, datetime(2026, 4, 1))

        assert complete_results[0] == (False, "DB error", None)
        assert vm.is_running is False
