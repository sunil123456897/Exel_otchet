import pytest
import logging
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch
from core.bootstrap import Bootstrap


def test_bootstrap_setup_success(tmp_path):
    app_root = tmp_path
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "paths: {master_file: 'M.xlsx', source_root: 'R'}\nsh1: {markers: {}}",
        encoding="utf-8",
    )

    # Mock all classes instantiated in setup
    with (
        patch("core.bootstrap.ConfigController") as mock_cfg_ctl,
        patch("core.bootstrap.IngestionEngine"),
        patch("core.bootstrap.SQLiteManager"),
        patch("core.bootstrap.Validator"),
        patch("core.bootstrap.LogicService"),
        patch("core.bootstrap.MasterWriter"),
        patch("core.bootstrap.AppController"),
    ):
        mock_cfg_ctl.return_value.config = {
            "paths": {
                "master_file": "M.xlsx",
                "source_root": "R",
                "source_roots": ["R1", "R2"],
            },
            "sh1": {"markers": {}},
            "database": {"path": "db.sqlite", "schema_path": "schema.sql"},
        }

        cfg_ctl, app_ctl, persistence = Bootstrap.setup(app_root, str(config_path))

        assert cfg_ctl is not None
        assert app_ctl is not None
        assert persistence is not None

        # Verify absolute paths initialization
        cfg = mock_cfg_ctl.return_value.config
        assert Path(cfg["paths"]["master_file"]).is_absolute()
        assert Path(cfg["paths"]["source_root"]).is_absolute()
        assert all(Path(r).is_absolute() for r in cfg["paths"]["source_roots"])
        assert Path(cfg["database"]["path"]).is_absolute()
        assert Path(cfg["database"]["schema_path"]).is_absolute()

        assert str(app_root) in cfg["paths"]["master_file"]
        assert str(app_root) in cfg["database"]["path"]


def test_bootstrap_setup_invalid_config(tmp_path):
    app_root = tmp_path
    config_path = tmp_path / "config.yaml"
    config_path.write_text("invalid: config", encoding="utf-8")

    with (
        patch("core.bootstrap.ConfigController") as mock_cfg_ctl,
        patch("core.bootstrap.IngestionEngine"),
        patch("core.bootstrap.SQLiteManager"),
        patch("core.bootstrap.Validator"),
        patch("core.bootstrap.LogicService"),
        patch("core.bootstrap.MasterWriter"),
        patch("core.bootstrap.AppController"),
    ):
        mock_cfg_ctl.return_value.config = {"invalid": "config"}

        cfg_ctl, app_ctl, persistence = Bootstrap.setup(app_root, str(config_path))
        assert cfg_ctl is not None
        assert "paths" in mock_cfg_ctl.return_value.config
        assert "sh1" in mock_cfg_ctl.return_value.config


def test_bootstrap_missing_dependency():
    app_root = Path("/tmp")
    config_path = "/tmp/config.yaml"

    with (
        patch("importlib.util.find_spec", return_value=None) as mock_find_spec,
        patch("logging.critical") as mock_log_critical,
    ):
        cfg_ctl, app_ctl, persistence = Bootstrap.setup(app_root, config_path)

        mock_find_spec.assert_called_once_with("python_calamine")
        mock_log_critical.assert_called_once_with(
            "Критическая ошибка: библиотека 'python-calamine' не найдена!"
        )
        assert cfg_ctl is None
        assert app_ctl is None
        assert persistence is None
