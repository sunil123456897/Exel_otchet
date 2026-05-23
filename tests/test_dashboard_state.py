import os
from pathlib import Path
from unittest.mock import Mock

from core.ui.dashboard_state import (
    format_file_size,
    format_mtime,
    find_latest_file,
    run_light_diagnostics,
    safe_open_existing_path,
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
