from pathlib import Path

from ruamel.yaml import YAML


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = REPO_ROOT / "APP"


def _entry_path(entry: object) -> str:
    if isinstance(entry, str):
        return entry.replace("\\", "/")
    if isinstance(entry, dict):
        raw_path = entry.get("path")
        assert isinstance(raw_path, str)
        assert raw_path.strip()
        return raw_path.replace("\\", "/")
    raise AssertionError(f"Unsupported employee entry: {entry!r}")


def _assert_has_path(data: dict[str, object], employee: str, suffix: str) -> None:
    entries = data[employee]
    assert isinstance(entries, list)
    normalized = [_entry_path(entry) for entry in entries]
    assert any(path.endswith(suffix.replace("\\", "/")) for path in normalized)


def _resolve_employee_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return (APP_ROOT / path).resolve()


def test_employees_yaml_matches_current_master_employee_set() -> None:
    employees_path = APP_ROOT / "employees.yaml"
    yaml = YAML(typ="safe")
    data = yaml.load(employees_path.read_text(encoding="utf-8")) or {}
    assert isinstance(data, dict)

    assert "Адам" not in data
    assert "Лев Е" not in data
    assert "Роман В" not in data
    assert "Лола Б" in data

    for employee, entries in data.items():
        assert isinstance(employee, str)
        assert isinstance(entries, list)
        assert entries
        for entry in entries:
            raw_path = _entry_path(entry)
            assert "E:/Dlia Dashi/Version5" not in raw_path
            assert _resolve_employee_path(raw_path).exists()

    _assert_has_path(
        data,
        "Амалия",
        "REPORTS/Отчет кураторов 1/Амалия/Отчет ОПТ Амалия.xlsx",
    )
    _assert_has_path(
        data,
        "Марго",
        "REPORTS/Отчет кураторов 1/Марго/Отчет Марго.xlsx",
    )
    _assert_has_path(
        data,
        "Алиса Ю",
        "REPORTS/Отчет кураторов 3/Алиса Ю/Отчёт Алиса Ю.xlsx",
    )


def test_runtime_config_uses_portable_app_local_paths() -> None:
    config_path = APP_ROOT / "config.yaml"
    yaml = YAML(typ="safe")
    config = yaml.load(config_path.read_text(encoding="utf-8")) or {}

    assert config["database"]["path"] == "cache.db"
    assert config["database"]["schema_path"] == "db_schema.sql"
    assert config["paths"]["master_file"] == "../Master_Report.xlsx"
    assert config["rsch"]["last_output_dir"] == "../РСЧ"
    assert all(
        str(path).startswith("../рсч всех/")
        for path in config["rsch"]["recent_sources"]
    )
