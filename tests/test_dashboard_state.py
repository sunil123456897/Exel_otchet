import os
from pathlib import Path
from unittest.mock import Mock

from core.ui.dashboard_state import (
    RuntimeResult,
    build_diagnostic_summary,
    format_file_size,
    format_mtime,
    find_latest_file,
    load_runtime_results,
    run_light_diagnostics,
    safe_open_existing_path,
    save_runtime_results,
)


class DummyConfigController:
    def __init__(self, config_path: Path, employees_path: Path, config: dict) -> None:
        self.config_path = str(config_path)
        self.employees_path = str(employees_path)
        self.config = config

    def resolve_path(self, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return Path(self.config_path).parent / path


def test_find_latest_file_uses_mtime_and_patterns(tmp_path: Path) -> None:
    old_file = tmp_path / "РСЧ_отчет_01.05.2026.xlsx"
    new_file = tmp_path / "РСЧ_отчет_02.05.2026.xlsx"
    ignored = tmp_path / "notes.txt"
    old_file.write_text("old", encoding="utf-8")
    new_file.write_text("new", encoding="utf-8")
    ignored.write_text("ignore", encoding="utf-8")
    old_time = 1_700_000_000
    new_time = 1_800_000_000
    os.utime(old_file, (old_time, old_time))
    os.utime(new_file, (new_time, new_time))

    assert find_latest_file(tmp_path, ("РСЧ_отчет_*.xlsx",)) == new_file


def test_format_file_size_and_mtime_are_user_readable(tmp_path: Path) -> None:
    file_path = tmp_path / "report.xlsx"
    file_path.write_bytes(b"x" * 1536)
    os.utime(file_path, (1_800_000_000, 1_800_000_000))

    assert format_file_size(file_path) == "1.5 KB"
    assert format_mtime(file_path) != "-"


def test_safe_open_existing_path_reports_missing_path(tmp_path: Path) -> None:
    opener = Mock()
    missing = Mock()

    ok = safe_open_existing_path(tmp_path / "missing.xlsx", opener, missing)

    assert ok is False
    opener.assert_not_called()
    missing.assert_called_once()


def test_run_light_diagnostics_marks_missing_config_path(tmp_path: Path) -> None:
    employees_path = tmp_path / "employees.yaml"
    employees_path.write_text("{}", encoding="utf-8")
    controller = DummyConfigController(
        tmp_path / "config.yaml",
        employees_path,
        {
            "paths": {"master_file": "Master_Report.xlsx", "source_roots": ["Q:/missing"]},
            "database": {"path": "cache.db"},
        },
    )

    diagnostics = run_light_diagnostics(controller, tmp_path)

    by_label = {item.label: item for item in diagnostics}
    assert by_label["config.yaml"].status == "error"
    assert by_label["employees.yaml"].status == "ok"
    assert by_label["cache.db"].status in {"ok", "warning"}
    assert by_label["Q:/missing"].status == "warning"


def test_run_light_diagnostics_can_skip_network_paths(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    employees_path = tmp_path / "employees.yaml"
    config_path.write_text("{}", encoding="utf-8")
    employees_path.write_text("{}", encoding="utf-8")
    controller = DummyConfigController(
        config_path,
        employees_path,
        {
            "paths": {"source_roots": ["Q:/missing"]},
            "network": {"drive_letters": ["Q"]},
        },
    )

    diagnostics = run_light_diagnostics(controller, tmp_path, include_network=False)

    labels = {item.label for item in diagnostics}
    assert "Q:/missing" not in labels
    assert "Q:\\" not in labels


def test_runtime_state_round_trip_keeps_latest_ten(tmp_path: Path) -> None:
    state_path = tmp_path / "runtime_state.json"
    results = [
        RuntimeResult("Master", True, f"ok {idx}", tmp_path / f"{idx}.xlsx")
        for idx in range(12)
    ]

    save_runtime_results(state_path, results)
    loaded = load_runtime_results(state_path)

    assert len(loaded) == 10
    assert loaded[0].message == "ok 0"
    assert loaded[-1].message == "ok 9"
    assert loaded[0].path == tmp_path / "0.xlsx"


def test_runtime_state_ignores_broken_json(tmp_path: Path) -> None:
    state_path = tmp_path / "runtime_state.json"
    state_path.write_text("{broken", encoding="utf-8")

    assert load_runtime_results(state_path) == []


def test_build_diagnostic_summary_contains_key_sections(tmp_path: Path) -> None:
    diagnostics = [
        RuntimeResult("Master", True, "готово", tmp_path / "Master_Report.xlsx")
    ]
    log_path = tmp_path / "startup_log.txt"
    log_path.write_text("2026 ERROR bad file", encoding="utf-8")

    summary = build_diagnostic_summary(
        [
            ("Python", "✅ OK", "3.12", Path("python.exe")),
            (".venv", "⚠️ Внимание", "degraded", Path("C:/Python")),
            ("Q:\\", "⚠️ Внимание", "не найден или недоступен", Path("Q:/")),
        ],
        diagnostics,
        ["2026 ERROR bad file"],
    )

    assert "Python" in summary
    assert ".venv" in summary
    assert "Q:\\" in summary
    assert "Master" in summary
    assert "2026 ERROR bad file" in summary


def test_missing_backup_and_benchmark_are_non_critical(tmp_path: Path) -> None:
    config_path = tmp_path / "APP" / "config.yaml"
    employees_path = tmp_path / "APP" / "employees.yaml"
    config_path.parent.mkdir()
    config_path.write_text("{}", encoding="utf-8")
    employees_path.write_text("{}", encoding="utf-8")
    (tmp_path / "Master_Report.xlsx").write_text("x", encoding="utf-8")
    controller = DummyConfigController(
        config_path,
        employees_path,
        {
            "paths": {"master_file": "../Master_Report.xlsx", "archive_dir": "../backups"},
            "database": {"path": "cache.db"},
        },
    )

    diagnostics = run_light_diagnostics(controller, config_path.parent)
    by_label = {item.label: item for item in diagnostics}

    assert by_label["Backup folder"].status == "warning"
    assert by_label["Benchmarks"].status == "warning"
