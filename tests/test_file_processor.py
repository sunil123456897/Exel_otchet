from pathlib import Path
from unittest.mock import MagicMock, patch

from core.app.file_processor import check_master_lock


def test_check_master_lock_returns_false_when_parent_unavailable():
    config_controller = MagicMock()
    config_controller.config = {
        "paths": {"master_file": "E:/broken/Master_Report.xlsx"}
    }
    config_controller.resolve_path.return_value = Path("E:/broken/Master_Report.xlsx")

    with patch.object(Path, "mkdir", side_effect=OSError("no drive")):
        assert check_master_lock(config_controller) is False


def test_check_master_lock_falls_back_to_local_path_when_original_unavailable():
    config_controller = MagicMock()
    config_controller.config = {
        "paths": {"master_file": "E:/broken/Master_Report.xlsx"}
    }
    config_controller.config_path = "C:/app/config.yaml"
    config_controller.resolve_path.return_value = Path("E:/broken/Master_Report.xlsx")
    config_controller.save_config = MagicMock()

    mkdir_calls = {"count": 0}

    def mkdir_side_effect(*args, **kwargs):
        mkdir_calls["count"] += 1
        if mkdir_calls["count"] == 1:
            raise OSError("no drive")
        return None

    with (
        patch.object(Path, "mkdir", side_effect=mkdir_side_effect),
        patch(
            "core.app.file_processor.is_file_writable", return_value=True
        ) as writable,
    ):
        assert check_master_lock(config_controller) is True

    writable.assert_called_once()
    called_path = Path(writable.call_args[0][0])
    assert called_path == Path("C:/app/Master_Report.xlsx")
    assert Path(config_controller.config["paths"]["master_file"]) == Path(
        "C:/app/Master_Report.xlsx"
    )
    config_controller.save_config.assert_called_once()


def test_check_master_lock_prefers_config_dir_default_over_custom_path():
    config_controller = MagicMock()
    config_controller.config = {
        "paths": {"master_file": "E:/custom/Out.xlsx"}
    }
    config_controller.config_path = "C:/app/config.yaml"
    config_controller.resolve_path.return_value = Path("E:/custom/Out.xlsx")
    config_controller.save_config = MagicMock()

    with (
        patch.object(Path, "mkdir", return_value=None),
        patch("core.app.file_processor.is_file_writable", return_value=True) as writable,
    ):
        assert check_master_lock(config_controller) is True

    writable.assert_called_once_with(str(Path("E:/custom/Out.xlsx")))
    config_controller.save_config.assert_not_called()
