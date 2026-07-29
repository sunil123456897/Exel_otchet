"""Atomicity of config.yaml / employees.yaml writes.

``ConfigController.save_config`` and ``_save_employees`` previously did
``open(path, "w")`` directly on the live file. On Windows that truncates the
file *before* the new content is written, so a crash / power loss / disk-full
between truncate and the completed ``yaml.dump`` left the operator's
configuration empty or half-written — destroying the employee→file mapping and
forcing a manual re-map of every network Excel file.

These tests pin the atomic (temp + ``os.replace``) behaviour: a failed write
must leave the previously-good file completely intact.
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from ruamel.yaml import YAML

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "APP"
sys.path.insert(0, str(APP_DIR))

from core.infra.config_controller import ConfigController  # noqa: E402
from core.infra.utils import atomic_save_yaml  # noqa: E402


def _write_initial_config(path: Path, data: dict) -> None:
    """Write a complete, valid YAML file the way the app normally would."""
    yaml = YAML()
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f)


def test_atomic_save_yaml_preserves_original_on_failure(tmp_path: Path) -> None:
    """If yaml.dump raises partway through, the target file is untouched."""
    target = tmp_path / "config.yaml"
    original = {"paths": {"master_file": "C:/keep/me.xlsx"}, "version": 7}
    _write_initial_config(target, original)
    original_bytes = target.read_bytes()
    original_size = len(original_bytes)

    yaml = YAML()
    new_data = {"paths": {"master_file": "C:/new.xlsx"}, "version": 8}

    # Sabotage dump so it fails after opening the temp file but before
    # completing — the realistic mid-write crash / disk-full scenario.
    with patch.object(YAML, "dump", side_effect=RuntimeError("disk full mid-write")):
        with pytest.raises(RuntimeError, match="disk full mid-write"):
            atomic_save_yaml(target, new_data, yaml)

    # The previously-good file must be byte-identical to what was there before.
    assert target.read_bytes() == original_bytes
    assert target.stat().st_size == original_size
    assert target.stat().st_size > 0, "config.yaml must NOT be truncated to empty"

    # And the partial temp file must be cleaned up so a retry does not collide.
    assert not Path(str(target) + ".tmp").exists()


def test_atomic_save_yaml_succeeds_and_replaces(tmp_path: Path) -> None:
    """Happy path: the new content fully replaces the old, atomically."""
    target = tmp_path / "config.yaml"
    _write_initial_config(target, {"old": True})

    yaml = YAML()
    atomic_save_yaml(target, {"new": 42}, yaml)

    yaml_in = YAML()
    with open(target, "r", encoding="utf-8") as f:
        loaded = yaml_in.load(f)
    assert loaded == {"new": 42}


def test_save_config_is_atomic(tmp_path: Path) -> None:
    """ConfigController.save_config must not corrupt the live config on failure."""
    config_path = tmp_path / "config.yaml"
    employees_path = tmp_path / "employees.yaml"
    original = {"paths": {"master_file": "../Master_Report.xlsx"}, "sh1": {"markers": {}}}
    _write_initial_config(config_path, original)

    ctl = ConfigController(str(config_path))
    ctl.config = {"paths": {"master_file": "Q:/new.xlsx"}}

    # employees.yaml is created by ConfigController.__init__; keep it out of
    # the assertion focus but ensure save_config only touches config.yaml.
    employees_path.unlink(missing_ok=True)

    original_bytes = config_path.read_bytes()

    with patch("core.infra.config_controller.atomic_save_yaml",
               side_effect=OSError("simulated write failure")):
        # save_config swallows exceptions (logs + returns) — it must not raise,
        # and it must not have truncated the live config.
        ctl.save_config()

    assert config_path.read_bytes() == original_bytes, (
        "save_config must leave the previous good config intact on failure"
    )
    assert config_path.stat().st_size > 0


def test_save_employees_is_atomic(tmp_path: Path) -> None:
    """_save_employees must not corrupt the live employees file on failure."""
    config_path = tmp_path / "config.yaml"
    employees_path = tmp_path / "employees.yaml"
    _write_initial_config(config_path, {"paths": {}})
    _write_initial_config(employees_path, {"Иванов И.И.": {"file": "old.xlsx"}})
    original_bytes = employees_path.read_bytes()

    ctl = ConfigController(str(config_path))
    ctl.employees = {"Петров П.П.": {"file": "new.xlsx"}}

    with patch("core.infra.config_controller.atomic_save_yaml",
               side_effect=OSError("simulated write failure")):
        ctl._save_employees()

    assert employees_path.read_bytes() == original_bytes, (
        "_save_employees must leave the previous good mapping intact on failure"
    )
    assert employees_path.stat().st_size > 0
