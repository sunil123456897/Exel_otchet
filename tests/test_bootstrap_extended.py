"""
Расширенные тесты для Bootstrap.
Покрывает: path resolution edge cases, config validation, dependency injection wiring.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from core.bootstrap import Bootstrap


@pytest.fixture
def app_root(tmp_path):
    """Временная app_root директория."""
    return tmp_path


@pytest.fixture
def valid_config_content():
    """Минимальный валидный конфиг."""
    return """
paths:
  master_file: Master_Report.xlsx
  source_root: REPORTS
  source_roots:
    - REPORTS/group1
    - REPORTS/group2
sh1:
  markers:
    amount: сумма платежа
    income: приход
database:
  path: cache.db
  schema_path: db_schema.sql
  use_wal: true
  timeout: 30.0
locking:
  retry_count: 3
  retry_backoff: 1.0
logic:
  income_overrides: ['доп']
  return_keywords: ['возврат']
"""


class TestPathResolution:
    """Разрешение относительных путей."""

    def test_relative_master_file_resolved(self, app_root, valid_config_content):
        config_file = app_root / "config.yaml"
        config_file.write_text(valid_config_content, encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap.IngestionEngine"),
            patch("core.bootstrap.SQLiteManager"),
            patch("core.bootstrap.Validator"),
            patch("core.bootstrap.LogicService"),
            patch("core.bootstrap.MasterWriter"),
            patch("core.bootstrap.AppController"),
        ):
            mock_cfg.return_value.config = {
                "paths": {
                    "source_root": "REPORTS",
                    "source_roots": ["REPORTS/g1"],
                },
                "sh1": {"markers": {}},
                "database": {"path": "cache.db", "schema_path": "schema.sql"},
                "locking": {},
            }

            Bootstrap.setup(app_root, str(config_file))

            cfg = mock_cfg.return_value.config
            assert Path(cfg["paths"]["master_file"]).is_absolute()
            assert cfg["paths"]["master_file"].endswith("Master_Report.xlsx")

    def test_master_file_forced_to_project_root_when_running_from_app(
        self, app_root, valid_config_content
    ):
        config_file = app_root / "config.yaml"
        config_file.write_text(valid_config_content, encoding="utf-8")

        (app_root / "main.py").write_text("# test main", encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap.IngestionEngine"),
            patch("core.bootstrap.SQLiteManager"),
            patch("core.bootstrap.Validator"),
            patch("core.bootstrap.LogicService"),
            patch("core.bootstrap.MasterWriter"),
            patch("core.bootstrap.AppController"),
        ):
            mock_cfg.return_value.config = {
                "paths": {
                    "master_file": "Q:/custom/Other.xlsx",
                    "source_root": "REPORTS",
                    "source_roots": ["REPORTS/g1"],
                },
                "sh1": {"markers": {}},
                "database": {"path": "cache.db", "schema_path": "schema.sql"},
                "locking": {},
            }

            Bootstrap.setup(app_root, str(config_file))

            cfg = mock_cfg.return_value.config
            assert cfg["paths"]["master_file"] == str(
                app_root.parent / "Master_Report.xlsx"
            )

    def test_master_file_keeps_tmp_root_default_without_main_py(
        self, app_root, valid_config_content
    ):
        config_file = app_root / "config.yaml"
        config_file.write_text(valid_config_content, encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap.IngestionEngine"),
            patch("core.bootstrap.SQLiteManager"),
            patch("core.bootstrap.Validator"),
            patch("core.bootstrap.LogicService"),
            patch("core.bootstrap.MasterWriter"),
            patch("core.bootstrap.AppController"),
        ):
            mock_cfg.return_value.config = {
                "paths": {
                    "master_file": "Q:/custom/Other.xlsx",
                    "source_root": "REPORTS",
                    "source_roots": ["REPORTS/g1"],
                },
                "sh1": {"markers": {}},
                "database": {"path": "cache.db", "schema_path": "schema.sql"},
                "locking": {},
            }

            Bootstrap.setup(app_root, str(config_file))

            cfg = mock_cfg.return_value.config
            assert cfg["paths"]["master_file"] == str(app_root / "Master_Report.xlsx")

    def test_absolute_paths_preserved_for_non_master_paths(
        self, app_root, valid_config_content
    ):
        """source_root должен сохранять абсолютный путь, master_file — принудительно дефолт."""
        config_file = app_root / "config.yaml"
        config_file.write_text(valid_config_content, encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap.IngestionEngine"),
            patch("core.bootstrap.SQLiteManager"),
            patch("core.bootstrap.Validator"),
            patch("core.bootstrap.LogicService"),
            patch("core.bootstrap.MasterWriter"),
            patch("core.bootstrap.AppController"),
        ):
            mock_cfg.return_value.config = {
                "paths": {
                    "source_root": "REPORTS",
                },
                "sh1": {"markers": {}},
                "database": {"path": "cache.db", "schema_path": "schema.sql"},
                "locking": {},
            }

            Bootstrap.setup(app_root, str(config_file))

            cfg = mock_cfg.return_value.config
            assert cfg["paths"]["master_file"] == str(app_root / "Master_Report.xlsx")

    def test_empty_path_gets_default(self, app_root, valid_config_content):
        """Пустые пути должны получать дефолтные значения."""
        config_file = app_root / "config.yaml"
        config_file.write_text(valid_config_content, encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap.IngestionEngine"),
            patch("core.bootstrap.SQLiteManager"),
            patch("core.bootstrap.Validator"),
            patch("core.bootstrap.LogicService"),
            patch("core.bootstrap.MasterWriter"),
            patch("core.bootstrap.AppController"),
        ):
            mock_cfg.return_value.config = {
                "paths": {},
                "sh1": {"markers": {}},
                "database": {},
                "locking": {},
            }

            Bootstrap.setup(app_root, str(config_file))

            cfg = mock_cfg.return_value.config
            assert cfg["database"]["path"] == str(app_root / "cache.db")
            assert cfg["paths"]["master_file"] == str(app_root / "Master_Report.xlsx")

    def test_none_path_gets_default(self, app_root, valid_config_content):
        """None пути должны получать дефолтные значения."""
        config_file = app_root / "config.yaml"
        config_file.write_text(valid_config_content, encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap.IngestionEngine"),
            patch("core.bootstrap.SQLiteManager"),
            patch("core.bootstrap.Validator"),
            patch("core.bootstrap.LogicService"),
            patch("core.bootstrap.MasterWriter"),
            patch("core.bootstrap.AppController"),
        ):
            mock_cfg.return_value.config = {
                "paths": {"master_file": None, "source_root": None},
                "sh1": {"markers": {}},
                "database": {"path": None, "schema_path": None},
                "locking": {},
            }

            # None должно обрабатываться как отсутствие — дефолт
            Bootstrap.setup(app_root, str(config_file))

            cfg = mock_cfg.return_value.config
            assert cfg["database"]["path"] == str(app_root / "cache.db")

    def test_unwritable_db_path_falls_back_to_local_when_explicitly_allowed(
        self, app_root, valid_config_content
    ):
        config_file = app_root / "config.yaml"
        config_file.write_text(valid_config_content, encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap._can_open_sqlite_path", return_value=(False, "boom")),
            patch("core.bootstrap.IngestionEngine"),
            patch("core.bootstrap.SQLiteManager"),
            patch("core.bootstrap.Validator"),
            patch("core.bootstrap.LogicService"),
            patch("core.bootstrap.MasterWriter"),
            patch("core.bootstrap.AppController"),
        ):
            mock_cfg.return_value.config = {
                "paths": {"master_file": "M.xlsx", "source_root": "REPORTS"},
                "sh1": {"markers": {}},
                "database": {
                    "path": "Q:/broken/cache.db",
                    "schema_path": "db_schema.sql",
                    "timeout": 30.0,
                    "allow_local_fallback": True,
                },
                "locking": {},
            }

            Bootstrap.setup(app_root, str(config_file))

            cfg = mock_cfg.return_value.config
            assert cfg["database"]["path"] == str(app_root / "cache.db")
            mock_cfg.return_value.save_config.assert_called_once()

    def test_unwritable_db_path_fails_closed_by_default(
        self, app_root, valid_config_content
    ):
        config_file = app_root / "config.yaml"
        config_file.write_text(valid_config_content, encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap._can_open_sqlite_path", return_value=(False, "boom")),
            patch("core.bootstrap.IngestionEngine"),
            patch("core.bootstrap.SQLiteManager"),
            patch("core.bootstrap.Validator"),
            patch("core.bootstrap.LogicService"),
            patch("core.bootstrap.MasterWriter"),
            patch("core.bootstrap.AppController"),
        ):
            mock_cfg.return_value.config = {
                "paths": {"master_file": "M.xlsx", "source_root": "REPORTS"},
                "sh1": {"markers": {}},
                "database": {
                    "path": "Q:/broken/cache.db",
                    "schema_path": "db_schema.sql",
                    "timeout": 30.0,
                },
                "locking": {},
            }

            with pytest.raises(RuntimeError, match="Refusing local fallback"):
                Bootstrap.setup(app_root, str(config_file))

    def test_stale_app_local_database_paths_recover_without_dev_fallback(
        self, app_root, valid_config_content
    ):
        app_root = app_root / "APP"
        app_root.mkdir()
        config_file = app_root / "config.yaml"
        config_file.write_text(valid_config_content, encoding="utf-8")
        (app_root / "db_schema.sql").write_text("-- schema", encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap._can_open_sqlite_path", return_value=(True, None)) as can_open,
            patch("core.bootstrap.IngestionEngine"),
            patch("core.bootstrap.SQLiteManager"),
            patch("core.bootstrap.Validator"),
            patch("core.bootstrap.LogicService"),
            patch("core.bootstrap.MasterWriter"),
            patch("core.bootstrap.AppController"),
        ):
            mock_cfg.return_value.config = {
                "paths": {"master_file": "M.xlsx", "source_root": "REPORTS"},
                "sh1": {"markers": {}},
                "database": {
                    "path": "E:/old/install/APP/cache.db",
                    "schema_path": "E:/old/install/APP/db_schema.sql",
                    "timeout": 30.0,
                    "allow_local_fallback": False,
                },
                "locking": {},
            }

            Bootstrap.setup(app_root, str(config_file))

            cfg = mock_cfg.return_value.config
            assert cfg["database"]["path"] == str(app_root / "cache.db")
            assert cfg["database"]["schema_path"] == str(app_root / "db_schema.sql")
            can_open.assert_called_once_with(app_root / "cache.db", 30.0)
            mock_cfg.return_value.save_config.assert_called_once()

    def test_missing_schema_path_falls_back_and_persists(self, app_root):
        config_file = app_root / "config.yaml"
        config_file.write_text("paths: {}\nsh1: {}\n", encoding="utf-8")
        (app_root / "db_schema.sql").write_text("-- schema", encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap._can_open_sqlite_path", return_value=(True, None)),
            patch("core.bootstrap.IngestionEngine"),
            patch("core.bootstrap.SQLiteManager"),
            patch("core.bootstrap.Validator"),
            patch("core.bootstrap.LogicService"),
            patch("core.bootstrap.MasterWriter"),
            patch("core.bootstrap.AppController"),
        ):
            mock_cfg.return_value.config = {
                "paths": {
                    "master_file": "Master_Report.xlsx",
                    "source_root": "REPORTS",
                },
                "database": {
                    "path": "cache.db",
                    "schema_path": "Q:/missing/db_schema.sql",
                    "timeout": 30.0,
                },
                "sh1": {"markers": {}},
                "locking": {},
            }

            Bootstrap.setup(app_root, str(config_file))

            cfg = mock_cfg.return_value.config
            assert cfg["database"]["schema_path"] == str(app_root / "db_schema.sql")
            mock_cfg.return_value.save_config.assert_called_once()

    def test_no_db_schema_fallback_does_not_persist(self, app_root):
        config_file = app_root / "config.yaml"
        config_file.write_text("paths: {}\nsh1: {}\n", encoding="utf-8")
        (app_root / "db_schema.sql").write_text("-- schema", encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap._can_open_sqlite_path", return_value=(True, None)),
            patch("core.bootstrap.IngestionEngine"),
            patch("core.bootstrap.SQLiteManager"),
            patch("core.bootstrap.Validator"),
            patch("core.bootstrap.LogicService"),
            patch("core.bootstrap.MasterWriter"),
            patch("core.bootstrap.AppController"),
        ):
            mock_cfg.return_value.config = {
                "paths": {
                    "master_file": "Master_Report.xlsx",
                    "source_root": "REPORTS",
                },
                "database": {
                    "path": "cache.db",
                    "schema_path": "db_schema.sql",
                    "timeout": 30.0,
                },
                "sh1": {"markers": {}},
                "locking": {},
            }

            Bootstrap.setup(app_root, str(config_file))

            mock_cfg.return_value.save_config.assert_not_called()

    def test_windows_like_source_root_not_prefixed(
        self, app_root, valid_config_content
    ):
        config_file = app_root / "config.yaml"
        config_file.write_text(valid_config_content, encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap.IngestionEngine"),
            patch("core.bootstrap.SQLiteManager"),
            patch("core.bootstrap.Validator"),
            patch("core.bootstrap.LogicService"),
            patch("core.bootstrap.MasterWriter"),
            patch("core.bootstrap.AppController"),
        ):
            mock_cfg.return_value.config = {
                "paths": {
                    "master_file": "M.xlsx",
                    "source_root": "Q:/reports",
                    "source_roots": ["Q:/reports", r"\\server\share\reports"],
                },
                "sh1": {"markers": {}},
                "database": {"path": "cache.db", "schema_path": "schema.sql"},
                "locking": {},
            }

            Bootstrap.setup(app_root, str(config_file))

            cfg = mock_cfg.return_value.config["paths"]
            assert str(Path(cfg["source_root"])) == str(Path("Q:/reports"))
            assert str(Path(cfg["source_roots"][0])) == str(Path("Q:/reports"))
            assert cfg["source_roots"][1] == r"\\server\share\reports"

    def test_relative_parent_escape_is_rejected(self, app_root, valid_config_content):
        config_file = app_root / "config.yaml"
        config_file.write_text(valid_config_content, encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap.IngestionEngine"),
            patch("core.bootstrap.SQLiteManager"),
            patch("core.bootstrap.Validator"),
            patch("core.bootstrap.LogicService"),
            patch("core.bootstrap.MasterWriter"),
            patch("core.bootstrap.AppController"),
        ):
            mock_cfg.return_value.config = {
                "paths": {
                    "master_file": "../outside/Master.xlsx",
                    "source_root": "REPORTS",
                },
                "sh1": {"markers": {}},
                "database": {"path": "cache.db", "schema_path": "schema.sql"},
                "locking": {},
            }

            Bootstrap.setup(app_root, str(config_file))

            cfg = mock_cfg.return_value.config
            assert cfg["paths"]["master_file"] == str(app_root / "Master_Report.xlsx")

    def test_reports_fallback_to_q_roots_when_local_reports_missing(self, app_root):
        config_file = app_root / "config.yaml"
        config_file.write_text("paths: {}\nsh1: {}\n", encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap.IngestionEngine"),
            patch("core.bootstrap.SQLiteManager"),
            patch("core.bootstrap.Validator"),
            patch("core.bootstrap.LogicService"),
            patch("core.bootstrap.MasterWriter"),
            patch("core.bootstrap.AppController"),
            patch("core.bootstrap.Path.exists", return_value=False),
        ):
            mock_cfg.return_value.config = {
                "paths": {
                    "source_root": "REPORTS",
                    "master_file": "Master_Report.xlsx",
                },
                "database": {"path": "cache.db", "schema_path": "db_schema.sql"},
                "sh1": {"markers": {}},
                "locking": {},
            }

            Bootstrap.setup(app_root, str(config_file))

            paths = mock_cfg.return_value.config["paths"]
            assert paths["source_root"] == "Q:/Отчет кураторов 1"
            assert paths["source_roots"] == [
                "Q:/Отчет кураторов 1",
                "Q:/Отчет кураторов 2",
                "Q:/Отчет кураторов 3",
            ]


class TestConfigValidation:
    """Валидация конфигурации."""

    def test_missing_paths_key(self, app_root):
        """Отсутствие 'paths' — safe default вместо ValueError."""
        config_file = app_root / "config.yaml"
        config_file.write_text("sh1: {markers: {}}", encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap.IngestionEngine"),
            patch("core.bootstrap.SQLiteManager"),
            patch("core.bootstrap.Validator"),
            patch("core.bootstrap.LogicService"),
            patch("core.bootstrap.MasterWriter"),
            patch("core.bootstrap.AppController"),
        ):
            mock_cfg.return_value.config = {"sh1": {"markers": {}}}

            cfg_ctl, app_ctl, persistence = Bootstrap.setup(app_root, str(config_file))
            assert cfg_ctl is not None
            assert "paths" in mock_cfg.return_value.config

    def test_missing_sh1_key(self, app_root):
        """Отсутствие 'sh1' — safe default вместо ValueError."""
        config_file = app_root / "config.yaml"
        config_file.write_text("paths: {}", encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap.IngestionEngine"),
            patch("core.bootstrap.SQLiteManager"),
            patch("core.bootstrap.Validator"),
            patch("core.bootstrap.LogicService"),
            patch("core.bootstrap.MasterWriter"),
            patch("core.bootstrap.AppController"),
        ):
            mock_cfg.return_value.config = {"paths": {}}

            cfg_ctl, app_ctl, persistence = Bootstrap.setup(app_root, str(config_file))
            assert cfg_ctl is not None
            assert "sh1" in mock_cfg.return_value.config

    def test_empty_config(self, app_root):
        """Пустой конфиг — safe default вместо ValueError."""
        config_file = app_root / "config.yaml"
        config_file.write_text("", encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap.IngestionEngine"),
            patch("core.bootstrap.SQLiteManager"),
            patch("core.bootstrap.Validator"),
            patch("core.bootstrap.LogicService"),
            patch("core.bootstrap.MasterWriter"),
            patch("core.bootstrap.AppController"),
        ):
            mock_cfg.return_value.config = None

            cfg_ctl, app_ctl, persistence = Bootstrap.setup(app_root, str(config_file))
            assert cfg_ctl is not None
            assert isinstance(mock_cfg.return_value.config, dict)

    def test_invalid_database_timeout_preserves_valid_paths(self, app_root):
        config_file = app_root / "config.yaml"
        config_file.write_text("paths: {}", encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap.IngestionEngine"),
            patch("core.bootstrap.SQLiteManager"),
            patch("core.bootstrap.Validator"),
            patch("core.bootstrap.LogicService"),
            patch("core.bootstrap.MasterWriter"),
            patch("core.bootstrap.AppController"),
        ):
            mock_cfg.return_value.config = {
                "paths": {
                    "master_file": "output/Master.xlsx",
                    "source_root": "REPORTS/custom",
                },
                "database": {
                    "path": "cache.db",
                    "schema_path": "schema.sql",
                    "timeout": "slow",
                },
                "sh1": {"markers": {}},
                "locking": {},
            }

            Bootstrap.setup(app_root, str(config_file))

            cfg = mock_cfg.return_value.config
            assert cfg["paths"]["master_file"] == str(app_root / "Master_Report.xlsx")
            assert cfg["paths"]["source_root"].endswith(str(Path("REPORTS") / "custom"))


class TestDependencyInjection:
    """Проверка DI wiring — все зависимости корректно созданы."""

    def test_all_components_instantiated(self, app_root, valid_config_content):
        config_file = app_root / "config.yaml"
        config_file.write_text(valid_config_content, encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap.IngestionEngine") as mock_ing,
            patch("core.bootstrap.SQLiteManager") as mock_db,
            patch("core.bootstrap.Validator") as mock_val,
            patch("core.bootstrap.LogicService") as mock_logic,
            patch("core.bootstrap.MasterWriter") as mock_writer,
            patch("core.bootstrap.AppController") as mock_app,
        ):
            mock_cfg.return_value.config = {
                "paths": {"master_file": "M.xlsx", "source_root": "R"},
                "sh1": {"markers": {"amount": "сумма"}},
                "database": {"path": "cache.db", "schema_path": "schema.sql"},
                "locking": {},
                "logic": {},
            }

            Bootstrap.setup(app_root, str(config_file))

            # Все компоненты должны быть созданы
            mock_cfg.assert_called_once()
            mock_ing.assert_called_once()
            mock_db.assert_called_once()
            mock_val.assert_called_once()
            mock_logic.assert_called_once()
            mock_writer.assert_called_once()
            mock_app.assert_called_once()

    def test_ingestion_gets_markers(self, app_root, valid_config_content):
        """IngestionEngine должен получить markers из конфига."""
        config_file = app_root / "config.yaml"
        config_file.write_text(valid_config_content, encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap.IngestionEngine") as mock_ing,
            patch("core.bootstrap.SQLiteManager"),
            patch("core.bootstrap.Validator"),
            patch("core.bootstrap.LogicService"),
            patch("core.bootstrap.MasterWriter"),
            patch("core.bootstrap.AppController"),
        ):
            markers = {"amount": "сумма", "income": "приход"}
            mock_cfg.return_value.config = {
                "paths": {"master_file": "M.xlsx", "source_root": "R"},
                "sh1": {"markers": markers},
                "database": {"path": "cache.db", "schema_path": "schema.sql"},
                "locking": {},
            }

            Bootstrap.setup(app_root, str(config_file))

            # IngestionEngine вызывается с markers
            mock_ing.assert_called_once_with(markers, ("Q", "Z"))

    def test_sqlite_manager_gets_db_config(self, app_root, valid_config_content):
        """SQLiteManager должен получить путь к БД и схеме."""
        config_file = app_root / "config.yaml"
        config_file.write_text(valid_config_content, encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap.IngestionEngine"),
            patch("core.bootstrap.SQLiteManager") as mock_db,
            patch("core.bootstrap.Validator"),
            patch("core.bootstrap.LogicService"),
            patch("core.bootstrap.MasterWriter"),
            patch("core.bootstrap.AppController"),
        ):
            mock_cfg.return_value.config = {
                "paths": {"master_file": "M.xlsx", "source_root": "R"},
                "sh1": {"markers": {}},
                "database": {
                    "path": str(app_root / "test_cache.db"),
                    "schema_path": str(app_root / "test_schema.sql"),
                },
                "locking": {"retry_count": 5},
            }

            Bootstrap.setup(app_root, str(config_file))

            args = mock_db.call_args
            assert mock_db.called
            # SQLiteManager receives (db_path, schema_path, config)
            assert len(args[0]) >= 2
            assert "test_cache.db" in str(args[0][0])

    def test_app_controller_gets_all_dependencies(self, app_root, valid_config_content):
        """AppController должен получить все 6 зависимостей."""
        config_file = app_root / "config.yaml"
        config_file.write_text(valid_config_content, encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap.IngestionEngine") as mock_ing,
            patch("core.bootstrap.SQLiteManager") as mock_db,
            patch("core.bootstrap.Validator") as mock_val,
            patch("core.bootstrap.LogicService") as mock_logic,
            patch("core.bootstrap.MasterWriter") as mock_writer,
            patch("core.bootstrap.AppController") as mock_app,
        ):
            mock_cfg.return_value.config = {
                "paths": {"master_file": "M.xlsx", "source_root": "R"},
                "sh1": {"markers": {}},
                "database": {"path": "cache.db", "schema_path": "schema.sql"},
                "locking": {},
            }

            Bootstrap.setup(app_root, str(config_file))

            # AppController получает: cfg_ctl, ingestion, persistence, validator, logic, writer
            mock_app.assert_called_once_with(
                mock_cfg.return_value,
                mock_ing.return_value,
                mock_db.return_value,
                mock_val.return_value,
                mock_logic.return_value,
                mock_writer.return_value,
            )

    def test_logic_service_gets_persistence_and_config(
        self, app_root, valid_config_content
    ):
        """LogicService получает persistence и config."""
        config_file = app_root / "config.yaml"
        config_file.write_text(valid_config_content, encoding="utf-8")

        with (
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap.IngestionEngine"),
            patch("core.bootstrap.SQLiteManager") as mock_db,
            patch("core.bootstrap.Validator"),
            patch("core.bootstrap.LogicService") as mock_logic,
            patch("core.bootstrap.MasterWriter"),
            patch("core.bootstrap.AppController"),
        ):
            mock_cfg.return_value.config = {
                "paths": {"master_file": "M.xlsx", "source_root": "R"},
                "sh1": {"markers": {}},
                "database": {"path": "cache.db", "schema_path": "schema.sql"},
                "locking": {},
            }

            Bootstrap.setup(app_root, str(config_file))

            mock_logic.assert_called_once_with(
                mock_db.return_value,
                mock_cfg.return_value.config,
            )


class TestEdgeCases:
    """Крайние случаи."""

    def test_calamine_missing_returns_none(self, app_root):
        """Отсутствие python-calamine — возврат None."""
        config_file = app_root / "config.yaml"
        config_file.write_text("paths: {}\nsh1: {}", encoding="utf-8")

        with (
            patch("importlib.util.find_spec", return_value=None),
            patch("logging.critical") as mock_critical,
        ):
            result = Bootstrap.setup(app_root, str(config_file))

            assert result == (None, None, None)
            mock_critical.assert_called_once()

    def test_calamine_present_continues(self, app_root, valid_config_content):
        """Наличие python-calamine — продолжение инициализации."""
        config_file = app_root / "config.yaml"
        config_file.write_text(valid_config_content, encoding="utf-8")

        with (
            patch("importlib.util.find_spec", return_value="python_calamine"),
            patch("core.bootstrap.ConfigController") as mock_cfg,
            patch("core.bootstrap.IngestionEngine"),
            patch("core.bootstrap.SQLiteManager"),
            patch("core.bootstrap.Validator"),
            patch("core.bootstrap.LogicService"),
            patch("core.bootstrap.MasterWriter"),
            patch("core.bootstrap.AppController"),
        ):
            mock_cfg.return_value.config = {
                "paths": {"master_file": "M.xlsx", "source_root": "R"},
                "sh1": {"markers": {}},
                "database": {"path": "cache.db", "schema_path": "schema.sql"},
                "locking": {},
            }

            cfg_ctl, app_ctl, persistence = Bootstrap.setup(app_root, str(config_file))

            assert cfg_ctl is not None
            assert app_ctl is not None
            assert persistence is not None
