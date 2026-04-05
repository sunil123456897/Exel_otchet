"""Тесты для ConfigController."""
import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from ruamel.yaml import YAML

from core.infra.config_controller import ConfigController


@pytest.fixture
def temp_config_file(tmp_path):
    """Создаёт временный config.yaml."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text("""
employees:
  - Иван П
  - Марго
paths:
  master_file: Master_Report.xlsx
  source_root: REPORTS
  archive_dir: ../backups
sh1:
  markers:
    amount: сумма платежа
employee_paths:
  Иван П:
    - path: reports/ivan/report.xlsx
      id: 12345
      fp: abc123
""", encoding='utf-8')
    return str(cfg)


@pytest.fixture
def config_controller(temp_config_file):
    """ConfigController с временным конфигом."""
    return ConfigController(temp_config_file)


class TestConfigControllerInit:
    """Тесты инициализации."""

    def test_load_config_success(self, config_controller):
        assert config_controller.config is not None
        assert 'Иван П' in config_controller.get_employees()
        assert 'Марго' in config_controller.get_employees()

    def test_load_config_missing_file(self, tmp_path):
        """Несуществующий файл — пустой конфиг."""
        cfg = ConfigController(str(tmp_path / "nonexistent.yaml"))
        assert cfg.config == {}

    def test_load_config_invalid_yaml(self, tmp_path):
        """Невалидный YAML — пустой конфиг."""
        cfg_file = tmp_path / "bad.yaml"
        cfg_file.write_text("{{invalid yaml:::", encoding='utf-8')
        cfg = ConfigController(str(cfg_file))
        # YAML может выбросить или вернуть None
        assert cfg.config is None or cfg.config == {}

    def test_yaml_settings_preserved(self, config_controller):
        """Настройки YAML должны сохранять комментарии."""
        assert config_controller.yaml.preserve_quotes is True
        assert config_controller.yaml.indent.mapping == 2


class TestAddEmployee:
    """Тесты добавления сотрудников."""

    def test_add_new_employee(self, config_controller, tmp_path):
        config_controller.add_employee("Алексей")
        assert "Алексей" in config_controller.get_employees()

    def test_add_duplicate_employee(self, config_controller):
        """Повторное добавление не должно дублировать."""
        config_controller.add_employee("Иван П")
        count = config_controller.get_employees().count("Иван П")
        assert count == 1

    def test_add_empty_name(self, config_controller):
        """Пустое имя — ничего не меняется."""
        before = config_controller.get_employees().copy()
        config_controller.add_employee("")
        assert config_controller.get_employees() == before

    def test_add_whitespace_name(self, config_controller):
        """Имя с пробелами — trim."""
        config_controller.add_employee("  Новый Сотрудник  ")
        assert "Новый Сотрудник" in config_controller.get_employees()

    def test_add_sorts_employees(self, config_controller):
        """Список сотрудников должен быть отсортирован."""
        config_controller.add_employee("Алексей")
        emps = config_controller.get_employees()
        assert emps == sorted(emps)

    def test_add_persists_to_file(self, config_controller, temp_config_file):
        """Добавление должно сохраняться в файл."""
        config_controller.add_employee("Борис")
        # Перезагрузить конфиг из файла
        cc2 = ConfigController(temp_config_file)
        assert "Борис" in cc2.get_employees()


class TestDeleteEmployee:
    """Тесты удаления сотрудников."""

    def test_delete_existing_employee(self, config_controller):
        config_controller.delete_employee("Иван П")
        assert "Иван П" not in config_controller.get_employees()

    def test_delete_removes_custom_paths(self, config_controller):
        """Удаление сотрудника должно удалить его пути."""
        config_controller.delete_employee("Иван П")
        emp_paths = config_controller.config.get('employee_paths', {})
        assert "Иван П" not in emp_paths

    def test_delete_nonexistent_employee(self, config_controller):
        """Удаление несуществующего — без ошибок."""
        before = config_controller.get_employees().copy()
        config_controller.delete_employee("Никто")
        assert config_controller.get_employees() == before

    def test_delete_persists(self, config_controller, temp_config_file):
        cc2 = ConfigController(temp_config_file)
        cc2.delete_employee("Марго")
        cc3 = ConfigController(temp_config_file)
        assert "Марго" not in cc3.get_employees()


class TestAttachFiles:
    """Тесты прикрепления файлов."""

    def test_attach_single_file(self, config_controller, tmp_path):
        f = tmp_path / "report.xlsx"
        f.write_bytes(b"test content")

        config_controller.attach_files("Марго", [str(f)])
        paths = config_controller.config.get('employee_paths', {}).get('Марго', [])
        assert len(paths) == 1
        assert paths[0]['path'] == str(f)
        assert 'id' in paths[0]
        assert 'fp' in paths[0]

    def test_attach_multiple_files(self, config_controller, tmp_path):
        f1 = tmp_path / "report1.xlsx"
        f2 = tmp_path / "report2.xlsx"
        f1.write_bytes(b"content1")
        f2.write_bytes(b"content2")

        config_controller.attach_files("Марго", [str(f1), str(f2)])
        paths = config_controller.config.get('employee_paths', {}).get('Марго', [])
        assert len(paths) == 2

    def test_attach_file_not_exists(self, config_controller):
        """Несуществующий файл — пропускается."""
        config_controller.attach_files("Марго", ["/nonexistent/file.xlsx"])
        paths = config_controller.config.get('employee_paths', {}).get('Марго', [])
        assert len(paths) == 0

    def test_attach_replace_mode(self, config_controller, tmp_path):
        """append=False — замена всех файлов."""
        f = tmp_path / "new.xlsx"
        f.write_bytes(b"new")

        config_controller.attach_files("Иван П", [str(f)], append=False)
        paths = config_controller.config.get('employee_paths', {}).get('Иван П', [])
        assert len(paths) == 1
        assert paths[0]['path'] == str(f)

    def test_attach_deduplicates(self, config_controller, tmp_path):
        """Одинаковые пути — дедупликация."""
        f = tmp_path / "report.xlsx"
        f.write_bytes(b"content")

        config_controller.attach_files("Марго", [str(f), str(f)])
        paths = config_controller.config.get('employee_paths', {}).get('Марго', [])
        assert len(paths) == 1

    def test_attach_generates_md5_hash(self, config_controller, tmp_path):
        """Прикрепление должно генерировать MD5 хэш."""
        f = tmp_path / "report.xlsx"
        f.write_bytes(b"hello world")

        config_controller.attach_files("Марго", [str(f)])
        paths = config_controller.config.get('employee_paths', {}).get('Марго', [])
        # MD5 от первых 8192 байт
        assert len(paths[0]['fp']) == 32  # hex length

    def test_attach_new_employee(self, config_controller, tmp_path):
        """Прикрепление к новому сотруднику — создаёт запись."""
        f = tmp_path / "report.xlsx"
        f.write_bytes(b"content")

        config_controller.attach_files("Новый", [str(f)])
        assert "Новый" not in config_controller.get_employees()  # Не добавляет в список
        assert "Новый" in config_controller.config.get('employee_paths', {})


class TestGetters:
    """Тесты getter методов."""

    def test_get_employees(self, config_controller):
        emps = config_controller.get_employees()
        assert isinstance(emps, list)
        assert "Иван П" in emps
        assert "Марго" in emps

    def test_get_employees_empty(self, tmp_path):
        cfg_file = tmp_path / "empty.yaml"
        cfg_file.write_text("", encoding='utf-8')
        cc = ConfigController(str(cfg_file))
        assert cc.get_employees() == []

    def test_get_paths(self, config_controller):
        paths = config_controller.get_paths()
        assert isinstance(paths, dict)
        assert 'master_file' in paths
        assert 'source_root' in paths
        assert 'archive_dir' in paths

    def test_get_paths_empty_config(self, tmp_path):
        cfg_file = tmp_path / "empty.yaml"
        cfg_file.write_text("", encoding='utf-8')
        cc = ConfigController(str(cfg_file))
        assert cc.get_paths() == {}


class TestSaveConfig:
    """Тесты сохранения конфига."""

    def test_save_and_reload(self, config_controller, temp_config_file):
        config_controller.add_employee("Тестовый")
        cc2 = ConfigController(temp_config_file)
        assert "Тестовый" in cc2.get_employees()

    def test_save_error_handled(self, config_controller):
        """Ошибка записи — логирование без падения."""
        with patch('builtins.open', side_effect=PermissionError("Access denied")):
            # Не должно выбрасывать
            config_controller.save_config()


class TestEdgeCases:
    """Крайние случаи."""

    def test_config_with_unicode_names(self, config_controller):
        config_controller.add_employee("Александр-Максим")
        assert "Александр-Максим" in config_controller.get_employees()

    def test_employee_paths_as_string(self, tmp_path):
        """employee_paths может быть строкой вместо списка."""
        cfg_file = tmp_path / "str_paths.yaml"
        cfg_file.write_text("employee_paths:\n  Emp: single_path.xlsx\n", encoding='utf-8')
        cc = ConfigController(str(cfg_file))
        # attach_files должен обработать строку как список
        f = tmp_path / "new.xlsx"
        f.write_bytes(b"content")
        cc.attach_files("Emp", [str(f)])

    def test_config_with_special_chars_in_path(self, config_controller, tmp_path):
        f = tmp_path / "Отчёт #1 (2026).xlsx"
        f.write_bytes(b"content")

        config_controller.attach_files("Марго", [str(f)])
        paths = config_controller.config.get('employee_paths', {}).get('Марго', [])
        assert len(paths) == 1
        assert "#1" in paths[0]['path']
