import pytest
import threading
import os
from unittest.mock import MagicMock, patch
from core.app_controller import AppController
from datetime import datetime
from pathlib import Path


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
    with patch("core.app_controller.DiscoveryService"):
        controller = AppController(**mock_deps)
        return controller


@pytest.fixture(autouse=True)
def mock_executor(mocker):
    mock_exec = MagicMock()
    mock_exec.__enter__.return_value = mock_exec

    def sync_submit(fn, *args, **kwargs):
        res = fn(*args, **kwargs)
        f = MagicMock()
        f.result.return_value = res
        f.done.return_value = True
        return f

    mock_exec.submit.side_effect = sync_submit
    mocker.patch("concurrent.futures.ThreadPoolExecutor", return_value=mock_exec)
    mocker.patch("concurrent.futures.as_completed", side_effect=lambda fs: list(fs))
    return mock_exec


def test_refresh_status(app_controller, mock_deps, mocker):
    # Mock DiscoveryService instance
    mock_discovery = app_controller.discovery
    mock_discovery.get_employees_map.return_value = {
        "Alice": [{"path": "alice.xlsx"}],
        "Bob": [],
    }
    mock_discovery.rename_detected = False

    mocker.patch("core.app_controller.check_master_lock", return_value=True)

    # Mock os.path.exists and stat
    mocker.patch("os.path.exists", side_effect=lambda p: p == "alice.xlsx")
    mocker.patch("os.path.basename", side_effect=lambda p: p)
    mocker.patch("os.stat", return_value=MagicMock(st_mtime=100, st_size=1000))

    # Mock ingestion.get_available_dates
    mock_deps["ingestion"].get_available_dates.return_value = ["01.01.2023"]

    on_progress = MagicMock()
    on_complete = MagicMock()
    selected_date = datetime(2023, 1, 1)

    # Run task synchronously by mocking Thread
    with patch("threading.Thread") as mock_thread:
        app_controller.refresh_status(selected_date, on_progress, on_complete)
        # Get the task function passed to Thread
        task = mock_thread.call_args[1]["target"]
        task()

    on_complete.assert_called_once()
    args = on_complete.call_args[0]
    # Alice should be ready, Bob missing
    assert args[0][0] == ("Alice", "🟢 ГОТОВО", "alice.xlsx", "ready")
    assert args[0][1] == ("Bob", "🔴 НЕТ ФАЙЛА", "---", "missing")


def test_refresh_status_error(app_controller, mock_deps, mocker, caplog):
    mock_discovery = app_controller.discovery
    mock_discovery.get_employees_map.side_effect = Exception("Discovery error")

    on_progress = MagicMock()
    on_complete = MagicMock()

    with patch("threading.Thread") as mock_thread:
        app_controller.refresh_status(datetime.now(), on_progress, on_complete)
        task = mock_thread.call_args[1]["target"]
        task()

    assert "Refresh error: Discovery error" in caplog.text


def test_refresh_status_calls_on_error_when_master_locked(app_controller, mocker):
    mocker.patch("core.app_controller.check_master_lock", return_value=False)
    on_progress = MagicMock()
    on_complete = MagicMock()
    on_error = MagicMock()

    app_controller.refresh_status(
        datetime.now(), on_progress, on_complete, on_error=on_error
    )

    on_complete.assert_called_once_with([], {}, False)
    on_error.assert_called_once()


def test_run_consolidation(app_controller, mock_deps, mocker):
    app_controller._cached_employees = {"Alice": [{"path": "alice.xlsx"}]}
    mocker.patch("os.path.exists", return_value=True)

    mock_deps["persistence"].save_file_metadata.return_value = [1]
    mock_deps["ingestion"].read_file.return_value = [
        {"date": "01.01.2023", "amount": 100}
    ]
    mock_deps["validator"].validate_row.return_value = True
    mock_deps["logic_service"].consolidate.return_value = [{"consolidated": True}]
    mock_deps["writer"].write_report.return_value = True

    on_progress = MagicMock()
    on_complete = MagicMock()
    selected_date = datetime(2023, 1, 1)

    with patch("threading.Thread") as mock_thread:
        app_controller.run_consolidation(selected_date, on_progress, on_complete)
        task = mock_thread.call_args[1]["target"]
        task()

    on_complete.assert_called_with(True, "Успешно!", mocker.ANY)
    mock_deps["persistence"].save_staging_data.assert_called_once()


def test_run_curator_consolidation_filters_employees_and_uses_curator_output(
    app_controller, mock_deps, mocker
):
    app_controller._cached_employees = {
        "Борис Ж": [{"path": "boris.xlsx"}],
        "Иван": [{"path": "ivan.xlsx"}],
    }
    mock_deps["config_controller"].config = {
        "curators": {
            "boris": {
                "enabled": True,
                "employees_key": "борис",
                "output_path": "output/boris_report.xlsx",
                "headers": ["Дата", "Источник"],
                "intermediary2_rate": 0.05,
            }
        }
    }
    mock_deps["config_controller"].resolve_path.side_effect = lambda p: Path(p)
    mocker.patch("os.path.exists", return_value=True)

    mock_deps["persistence"].save_file_metadata.return_value = [1]
    mock_deps["ingestion"].read_file.return_value = [
        {"date": "01.01.2023", "amount": 100}
    ]
    mock_deps["validator"].validate_row.return_value = True
    mock_deps["logic_service"].consolidate.return_value = [{"consolidated": True}]
    mock_deps["persistence"].get_template_errors.return_value = []
    mock_deps["writer"].write_report.return_value = True

    on_progress = MagicMock()
    on_complete = MagicMock()

    with patch("threading.Thread") as mock_thread:
        app_controller.run_consolidation(
            datetime(2023, 1, 1), on_progress, on_complete, curator="boris"
        )
        task = mock_thread.call_args[1]["target"]
        task()

    mock_deps["ingestion"].read_file.assert_called_once()
    assert mock_deps["ingestion"].read_file.call_args.args[0] == Path("boris.xlsx")
    mock_deps["logic_service"].consolidate.assert_called_once()
    assert mock_deps["logic_service"].consolidate.call_args.kwargs["curator"] == "boris"
    assert mock_deps["logic_service"].consolidate.call_args.kwargs["curator_config"]["intermediary2_rate"] == 0.05
    mock_deps["writer"].write_report.assert_called_once()
    write_args = mock_deps["writer"].write_report.call_args
    assert write_args.args[1] == Path("output/boris_report.xlsx")
    assert write_args.kwargs["curator"] == "boris"


def test_run_auto_reconciliation_day_rebuilds_reports_rsch_and_combined_output(
    app_controller,
    mocker,
):
    report_paths = {
        None: Path("Master_Report.xlsx"),
        "boris": Path("output/boris_report.xlsx"),
        "ivan": Path("output/ivan_report.xlsx"),
    }
    run_blocking = mocker.patch.object(
        app_controller,
        "_run_consolidation_blocking",
        side_effect=lambda **kwargs: report_paths[kwargs["curator"]],
    )
    build_rsch = mocker.patch("core.app_controller.build_rsch_report", return_value=42)
    build_combined = mocker.patch(
        "core.app_controller.build_combined_reconciliation_report",
        return_value={"Общий": 10, "Борис": 20, "Иван": 30},
    )
    on_complete = MagicMock()

    with patch("threading.Thread") as mock_thread:
        app_controller.run_auto_reconciliation_day(
            [Path("rsch_source.xlsx")],
            Path("out/Отчет_расхождений_21.04.2026.xlsx"),
            datetime(2026, 4, 21),
            on_complete,
        )
        task = mock_thread.call_args.kwargs["target"]
        task()

    assert [call.kwargs["curator"] for call in run_blocking.call_args_list] == [
        None,
        "boris",
        "ivan",
    ]
    build_rsch.assert_called_once()
    assert build_rsch.call_args.args[0] == [Path("rsch_source.xlsx")]
    assert build_rsch.call_args.args[1] == Path("out/РСЧ_отчет_21.04.2026.xlsx")
    assert build_rsch.call_args.kwargs["drive_letters"] == ("Q", "Z")
    build_combined.assert_called_once_with(
        {
            "Общий": Path("Master_Report.xlsx"),
            "Борис": Path("output/boris_report.xlsx"),
            "Иван": Path("output/ivan_report.xlsx"),
        },
        Path("out/РСЧ_отчет_21.04.2026.xlsx"),
        Path("out/Отчет_расхождений_21.04.2026.xlsx"),
        target_date=datetime(2026, 4, 21).date(),
        drive_letters=("Q", "Z"),
    )
    on_complete.assert_called_once()
    assert on_complete.call_args.args[0] is True
    assert on_complete.call_args.args[2] == Path("out/Отчет_расхождений_21.04.2026.xlsx")


def test_run_reconciliation_report_builds_in_background(app_controller, mocker):
    build_combined = mocker.patch(
        "core.app_controller.build_combined_reconciliation_report",
        return_value={"Общий": 10, "Борис": 20, "Иван": 30},
    )
    on_complete = MagicMock()

    with patch("threading.Thread") as mock_thread:
        app_controller.run_reconciliation_report(
            {
                "Общий": Path("master.xlsx"),
                "Борис": Path("boris.xlsx"),
                "Иван": Path("ivan.xlsx"),
            },
            Path("rsch.xlsx"),
            Path("out.xlsx"),
            datetime(2026, 4, 21),
            on_complete,
        )
        task = mock_thread.call_args.kwargs["target"]
        task()

    build_combined.assert_called_once_with(
        {
            "Общий": Path("master.xlsx"),
            "Борис": Path("boris.xlsx"),
            "Иван": Path("ivan.xlsx"),
        },
        Path("rsch.xlsx"),
        Path("out.xlsx"),
        target_date=datetime(2026, 4, 21).date(),
        drive_letters=("Q", "Z"),
    )
    on_complete.assert_called_once_with(
        True,
        "Отчет расхождений собран: Общий 10, Борис 20, Иван 30 строк.",
        Path("out.xlsx"),
    )


def test_network_drive_letters_read_from_config(app_controller):
    app_controller.config_controller.config = {"network": {"drive_letters": ["R", "S:"]}}

    assert app_controller._get_network_drive_letters() == ("R", "S:")


@pytest.mark.parametrize(
    ("curator", "employee_name", "source_path", "output_path"),
    [
        ("boris", "Борис Ж", "boris.xlsx", "output/boris_report.xlsx"),
        ("ivan", "Иван П", "ivan.xlsx", "output/ivan_report.xlsx"),
    ],
)
def test_daily_curator_consolidation_uses_selected_curator_config(
    app_controller,
    mock_deps,
    mocker,
    curator,
    employee_name,
    source_path,
    output_path,
):
    app_controller._cached_employees = {
        employee_name: [{"path": source_path}],
        "Амалия": [{"path": "amalia.xlsx"}],
    }
    mock_deps["config_controller"].config = {
        "curators": {
            "boris": {
                "enabled": True,
                "employees_key": "борис",
                "output_path": "output/boris_report.xlsx",
                "headers": ["Источник", "ЗАКАЗЧИК"],
            },
            "ivan": {
                "enabled": True,
                "employees_key": "иван",
                "output_path": "output/ivan_report.xlsx",
                "headers": ["Сотрудник", "ЗАКАЗЧИК"],
            },
        }
    }
    mock_deps["config_controller"].resolve_path.side_effect = lambda p: Path(p)
    mocker.patch("os.path.exists", return_value=True)

    mock_deps["persistence"].save_file_metadata.return_value = [1]
    mock_deps["ingestion"].read_file.return_value = [
        {"date": "01.01.2023", "amount": 100}
    ]
    mock_deps["validator"].validate_row.return_value = True
    mock_deps["logic_service"].consolidate.return_value = [{"consolidated": True}]
    mock_deps["persistence"].get_template_errors.return_value = []
    mock_deps["writer"].write_report.return_value = True

    on_progress = MagicMock()
    on_complete = MagicMock()

    with patch("threading.Thread") as mock_thread:
        app_controller.run_consolidation(
            datetime(2023, 1, 1), on_progress, on_complete, curator=curator
        )
        task = mock_thread.call_args[1]["target"]
        task()

    mock_deps["ingestion"].read_file.assert_called_once()
    assert mock_deps["ingestion"].read_file.call_args.args[0] == Path(source_path)
    assert mock_deps["logic_service"].consolidate.call_args.kwargs["curator"] == curator
    assert (
        mock_deps["writer"].write_report.call_args.args[1]
        == Path(output_path)
    )
    assert mock_deps["writer"].write_report.call_args.kwargs["curator"] == curator


def test_run_general_consolidation_excludes_enabled_curator_employees(
    app_controller, mock_deps, mocker
):
    app_controller._cached_employees = {
        "Борис Ж": [{"path": "boris.xlsx"}],
        "Иван П": [{"path": "ivan.xlsx"}],
        "Амалия": [{"path": "amalia.xlsx"}],
    }
    mock_deps["config_controller"].config = {
        "curators": {
            "boris": {"enabled": True, "employees_key": "борис"},
            "ivan": {"enabled": True, "employees_key": "иван"},
        }
    }
    mocker.patch("os.path.exists", return_value=True)

    mock_deps["persistence"].save_file_metadata.return_value = [1]
    mock_deps["ingestion"].read_file.return_value = [
        {"date": "01.01.2023", "amount": 100}
    ]
    mock_deps["validator"].validate_row.return_value = True
    mock_deps["logic_service"].consolidate.return_value = [{"consolidated": True}]
    mock_deps["persistence"].get_template_errors.return_value = []
    mock_deps["writer"].write_report.return_value = True

    on_progress = MagicMock()
    on_complete = MagicMock()

    with (
        patch("core.app_controller.check_master_lock", return_value=True),
        patch("threading.Thread") as mock_thread,
    ):
        app_controller.run_consolidation(
            datetime(2023, 1, 1), on_progress, on_complete
        )
        task = mock_thread.call_args[1]["target"]
        task()

    mock_deps["ingestion"].read_file.assert_called_once()
    assert mock_deps["ingestion"].read_file.call_args.args[0] == Path("amalia.xlsx")
    assert mock_deps["logic_service"].consolidate.call_args.kwargs["curator"] is None
    assert "curator" not in mock_deps["writer"].write_report.call_args.kwargs


def test_run_consolidation_no_files(app_controller, mock_deps, mocker):
    app_controller._cached_employees = {}

    on_progress = MagicMock()
    on_complete = MagicMock()
    selected_date = datetime(2023, 1, 1)

    with patch("threading.Thread") as mock_thread:
        app_controller.run_consolidation(selected_date, on_progress, on_complete)
        task = mock_thread.call_args[1]["target"]
        task()

    on_complete.assert_called_with(False, "Нет файлов", None)


def test_run_consolidation_no_data(app_controller, mock_deps, mocker):
    app_controller._cached_employees = {"Alice": [{"path": "alice.xlsx"}]}
    mocker.patch("os.path.exists", return_value=True)
    mock_deps["persistence"].save_file_metadata.return_value = [1]
    mock_deps["ingestion"].read_file.return_value = []
    mock_deps["logic_service"].consolidate.return_value = []

    on_progress = MagicMock()
    on_complete = MagicMock()

    with patch("threading.Thread") as mock_thread:
        app_controller.run_consolidation(datetime.now(), on_progress, on_complete)
        task = mock_thread.call_args[1]["target"]
        task()

    on_complete.assert_called_with(False, "Нет данных за дату", None)


def test_run_consolidation_all_dates(app_controller, mock_deps, mocker):
    mock_discovery = app_controller.discovery
    mock_discovery.get_employees_map.return_value = {"Alice": [{"path": "alice.xlsx"}]}
    mocker.patch("os.path.exists", return_value=True)

    mock_deps["persistence"].save_file_metadata.return_value = [1]
    mock_deps["ingestion"].read_file.return_value = [
        {"date": "01.01.2023", "amount": 100}
    ]
    mock_deps["validator"].validate_row.return_value = True
    mock_deps["logic_service"].consolidate.return_value = [{"consolidated": True}]
    mock_deps["persistence"].get_template_errors.return_value = []
    mock_deps["writer"].write_report.return_value = True

    on_progress = MagicMock()
    on_complete = MagicMock()

    with patch("threading.Thread") as mock_thread:
        app_controller.run_consolidation_all_dates(on_progress, on_complete)
        task = mock_thread.call_args[1]["target"]
        task()

    on_complete.assert_called_with(True, "Готово!", mocker.ANY)


def test_rename_detected_property(app_controller):
    app_controller.discovery.rename_detected = True
    assert app_controller.rename_detected is True
