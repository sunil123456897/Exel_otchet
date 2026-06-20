"""Tests for view models — ConsolidationViewModel and EmployeeListViewModel."""

from pathlib import Path
from unittest.mock import MagicMock

from core.view_models.consolidation_viewmodel import ConsolidationViewModel
from core.view_models.employee_list_viewmodel import EmployeeListViewModel, EmployeeStatus


class TestConsolidationViewModel:
    def test_initial_state(self):
        vm = ConsolidationViewModel()
        assert vm.is_running is False
        assert vm.progress == 0.0
        assert vm.get_button_state() == "normal"

    def test_can_run_single_date(self):
        vm = ConsolidationViewModel()
        assert vm.can_run_single_date(0) is True
        assert vm.can_run_single_date(1) is False
        assert vm.can_run_single_date(5) is False

    def test_callbacks_set(self):
        vm = ConsolidationViewModel()
        on_p = MagicMock()
        on_c = MagicMock()
        vm.set_callbacks(on_p, on_c)
        assert vm._on_progress is on_p
        assert vm._on_complete is on_c

    def test_execute_sets_running(self):
        vm = ConsolidationViewModel()
        calls = []

        def action(on_progress, on_complete):
            calls.append("called")
            assert vm.is_running is True
            on_complete(True, "done", None)

        vm._execute(action)
        assert len(calls) == 1
        assert vm.is_running is False

    def test_execute_prevents_concurrent(self):
        vm = ConsolidationViewModel()
        inner_calls = []

        def action(on_progress, on_complete):
            inner_calls.append("first")
            vm._execute(lambda p, c: inner_calls.append("second"))
            on_complete(True, "ok", None)

        vm._execute(action)
        assert "second" not in inner_calls

    def test_execute_progress_callback(self):
        vm = ConsolidationViewModel()
        progress_values = []

        def on_progress(p):
            progress_values.append(p)

        vm.set_callbacks(on_progress, lambda ok, msg, path: None)

        def action(on_progress, on_complete):
            on_progress(50.0)
            on_complete(True, "ok", None)

        vm._execute(action)
        assert 50.0 in progress_values

    def test_execute_exception_resets_running(self):
        vm = ConsolidationViewModel()

        def bad_action(on_progress, on_complete):
            raise RuntimeError("boom")

        try:
            vm._execute(bad_action)
        except RuntimeError:
            pass
        assert vm.is_running is False

    def test_button_state_disabled_while_running(self):
        vm = ConsolidationViewModel()

        def action(on_progress, on_complete):
            assert vm.get_button_state() == "disabled"
            on_complete(True, "ok", None)

        vm._execute(action)


class TestEmployeeStatus:
    def test_to_tuple(self):
        es = EmployeeStatus(
            name="Иванов", status_text="🟢 ГОТОВО",
            path_text="file.xlsx", tag="ready"
        )
        assert es.to_tuple() == ("Иванов", "🟢 ГОТОВО", "file.xlsx", "ready")


class TestEmployeeListViewModel:
    def _make_vm(self, employees=None):
        vm = EmployeeListViewModel()
        if employees:
            vm._all_employees = employees
        return vm

    def test_initial_state(self):
        vm = EmployeeListViewModel()
        assert vm.get_total_count() == 0
        assert vm.get_ready_count() == 0
        assert vm.get_missing_names() == []
        assert vm.get_progress_percent() == 0.0
        assert vm.last_error is None

    def test_search_query(self):
        vm = EmployeeListViewModel()
        vm.search_query = "Test"
        assert vm.search_query == "test"

    def test_get_filtered_employees_no_query(self):
        emp = EmployeeStatus("A", "🟢 ГОТОВО", "a.xlsx", "ready")
        vm = self._make_vm([emp])
        assert vm.get_filtered_employees() == [emp]

    def test_get_filtered_employees_with_query(self):
        emp1 = EmployeeStatus("Иванов", "🟢 ГОТОВО", "file1.xlsx", "ready")
        emp2 = EmployeeStatus("Петров", "🔴 НЕТ", "file2.xlsx", "missing")
        vm = self._make_vm([emp1, emp2])
        vm.search_query = "Иванов"
        filtered = vm.get_filtered_employees()
        assert len(filtered) == 1
        assert filtered[0].name == "Иванов"

    def test_get_ready_count(self):
        emps = [
            EmployeeStatus("A", "🟢 ГОТОВО", "a.xlsx", "ready"),
            EmployeeStatus("B", "🔴 НЕТ", "b.xlsx", "missing"),
            EmployeeStatus("C", "🟢 ГОТОВО", "c.xlsx", "ready"),
        ]
        vm = self._make_vm(emps)
        assert vm.get_ready_count() == 2
        assert vm.get_total_count() == 3

    def test_get_missing_names(self):
        emps = [
            EmployeeStatus("A", "🟢 ГОТОВО", "a.xlsx", "ready"),
            EmployeeStatus("B", "🔴 НЕТ", "b.xlsx", "missing"),
        ]
        vm = self._make_vm(emps)
        names = vm.get_missing_names()
        assert names == ["B"]

    def test_get_all_names(self):
        emps = [
            EmployeeStatus("A", "status", "path", "tag"),
            EmployeeStatus("B", "status", "path", "tag"),
        ]
        vm = self._make_vm(emps)
        assert vm.get_all_names() == ["A", "B"]

    def test_get_progress_percent(self):
        emps = [
            EmployeeStatus("A", "🟢 ГОТОВО", "a.xlsx", "ready"),
            EmployeeStatus("B", "🔴 НЕТ", "b.xlsx", "missing"),
        ]
        vm = self._make_vm(emps)
        assert vm.get_progress_percent() == 50.0

    def test_get_selected_employee_path(self):
        vm = EmployeeListViewModel()
        vm._employees_map = {"A": [{"path": "/path/a.xlsx"}]}
        assert vm.get_selected_employee_path("A") == "/path/a.xlsx"

    def test_get_selected_employee_path_none(self):
        vm = EmployeeListViewModel()
        assert vm.get_selected_employee_path(None) is None
        assert vm.get_selected_employee_path("Unknown") is None

    def test_get_selected_employee_paths(self):
        vm = EmployeeListViewModel()
        vm._employees_map = {"A": [{"path": "/a.xlsx"}, {"path": "/b.xlsx"}]}
        paths = vm.get_selected_employee_paths("A")
        assert len(paths) == 2

    def test_get_selected_employee_paths_empty(self):
        vm = EmployeeListViewModel()
        assert vm.get_selected_employee_paths(None) == []
        assert vm.get_selected_employee_paths("X") == []

    def test_employees_map_copy(self):
        vm = EmployeeListViewModel()
        vm._employees_map = {"A": [{"path": "/a.xlsx"}]}
        copy = vm.employees_map
        copy["B"] = []
        assert "B" not in vm._employees_map

    def test_rename_detected(self):
        vm = EmployeeListViewModel()
        assert vm.rename_detected is False
        vm._rename_detected = True
        assert vm.rename_detected is True

    def test_set_update_callback(self):
        vm = EmployeeListViewModel()
        cb = MagicMock()
        vm.set_update_callback(cb)
        assert vm._on_update is cb

    def test_add_employee_delegates(self):
        vm = EmployeeListViewModel()
        cc = MagicMock()
        vm.add_employee(cc, "Иванов")
        cc.add_employee.assert_called_once_with("Иванов")

    def test_delete_employee_delegates(self):
        vm = EmployeeListViewModel()
        cc = MagicMock()
        vm.delete_employee(cc, "Иванов")
        cc.delete_employee.assert_called_once_with("Иванов")

    def test_attach_files_delegates(self):
        vm = EmployeeListViewModel()
        cc = MagicMock()
        vm.attach_files(cc, "Иванов", ["/a.xlsx"], append=True)
        cc.attach_files.assert_called_once_with("Иванов", ["/a.xlsx"], append=True)

    def test_get_master_path_delegates(self):
        vm = EmployeeListViewModel()
        cc = MagicMock()
        cc.get_paths.return_value = {"master_file": "Master.xlsx"}
        cc.resolve_path.return_value = Path("/resolved/Master.xlsx")
        result = vm.get_master_path(cc)
        assert result == Path("/resolved/Master.xlsx")
