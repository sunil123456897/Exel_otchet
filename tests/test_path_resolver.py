from pathlib import Path
from unittest.mock import MagicMock

from core.infra.path_resolver import resolve_employee_path


def _config_controller(tmp_path, *, source_roots=None):
    controller = MagicMock()
    controller.config_path = str(tmp_path / "APP" / "config.yaml")
    controller.get_paths.return_value = {"source_roots": source_roots or []}
    return controller


def test_legacy_reports_alias_resolves_against_matching_source_root(tmp_path):
    root = tmp_path / "Отчет кураторов 1"
    employee_dir = root / "Оливия"
    employee_dir.mkdir(parents=True)
    report = employee_dir / "Ежедневый отчет Оливия Г.xlsx"
    report.touch()

    controller = _config_controller(tmp_path, source_roots=[root])

    resolved_path, meta, renamed = resolve_employee_path(
        "../REPORTS/Отчет кураторов 1/Оливия/Ежедневый отчет Оливия Г.xlsx",
        config_controller=controller,
    )

    assert Path(resolved_path) == report
    assert meta == {"path": str(report)}
    assert renamed is False
    controller.resolve_path.assert_not_called()


def test_missing_reports_alias_source_root_falls_back_to_config_relative_reports(tmp_path):
    local_report = tmp_path / "REPORTS" / "Отчет кураторов 2" / "Борис Ж" / "Отчёт Борис Ж.xlsx"
    local_report.parent.mkdir(parents=True)
    local_report.touch()

    missing_root = tmp_path / "missing" / "Отчет кураторов 2"
    controller = _config_controller(tmp_path, source_roots=[missing_root])
    controller.resolve_path.side_effect = lambda p: (tmp_path / "APP" / p).resolve()

    resolved_path, meta, renamed = resolve_employee_path(
        "../REPORTS/Отчет кураторов 2/Борис Ж/Отчёт Борис Ж.xlsx",
        config_controller=controller,
    )

    assert Path(resolved_path) == local_report
    assert meta == {"path": str(local_report)}
    assert renamed is False


def test_config_resolver_error_falls_back_to_config_relative_path(tmp_path):
    report = tmp_path / "APP" / "reports" / "fallback.xlsx"
    report.parent.mkdir(parents=True)
    report.touch()

    controller = _config_controller(tmp_path)
    controller.resolve_path.side_effect = OSError("offline")

    resolved_path, meta, renamed = resolve_employee_path(
        "reports/fallback.xlsx",
        file_id=7,
        file_hash="abc",
        config_controller=controller,
    )

    assert Path(resolved_path) == report
    assert meta == {"path": str(report), "id": 7, "fp": "abc"}
    assert renamed is False


def test_discovered_file_match_by_id_wins_over_missing_legacy_path(tmp_path):
    discovered = tmp_path / "new" / "renamed.xlsx"
    discovered.parent.mkdir()
    discovered.touch()

    resolved_path, meta, renamed = resolve_employee_path(
        "missing/old.xlsx",
        file_id=42,
        file_hash="old-hash",
        discovered_files=[
            {"path": str(discovered), "id": 42, "fp": "new-hash"},
        ],
    )

    assert resolved_path == str(discovered)
    assert meta == {"path": str(discovered), "id": 42, "fp": "new-hash"}
    assert renamed is True


def test_discovered_file_match_by_hash_handles_windows_style_paths(tmp_path):
    discovered = tmp_path / "reports" / "Alice" / "April.xlsx"
    discovered.parent.mkdir(parents=True)
    discovered.touch()
    stored_path = str(discovered).replace("/", "\\")

    resolved_path, meta, renamed = resolve_employee_path(
        r"old\Alice\April.xlsx",
        file_hash="same-hash",
        discovered_files=[
            {"path": stored_path, "id": 10, "fp": "same-hash"},
        ],
    )

    assert resolved_path == stored_path
    assert meta == {"path": stored_path, "id": 10, "fp": "same-hash"}
    assert renamed is True
