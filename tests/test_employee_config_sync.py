from pathlib import Path

from ruamel.yaml import YAML


def test_employees_yaml_matches_current_master_employee_set() -> None:
    employees_path = Path(__file__).resolve().parents[1] / "APP" / "employees.yaml"
    yaml = YAML(typ="safe")
    data = yaml.load(employees_path.read_text(encoding="utf-8")) or {}

    assert "Адам" not in data
    assert "Лев Е" not in data
    assert "Роман В" not in data
    assert "Лола Б" in data

    assert data["Амалия"] == [
        "../REPORTS/Отчет кураторов 1/Амалия/Отчет  ОПТ  Амали.xlsx"
    ]
    assert data["Марго"] == [
        "../REPORTS/Отчет кураторов 1/Марго/Отчет Марго.xlsx"
    ]
    assert data["Алиса Ю"] == [
        "../REPORTS/Отчет кураторов 3/Алиса Ю/Отчет Алиса Ю Корень с 06.03.26.xlsx",
        "../REPORTS/Отчет кураторов 3/Алиса Ю/Отчет Гетворк Алиса Ю Актуальный.xlsx",
        "../REPORTS/Отчет кураторов 3/Алиса Ю/Отчет Корень Фонд Алиса Ю.xlsx",
    ]
