import pytest
import os
from pathlib import Path
from core.infra.config_controller import ConfigController

@pytest.fixture
def config_file(tmp_path):
    config_path = tmp_path / "config.yaml"
    content = """
employees:
  - Alice
  - Bob
paths:
  input: ./input
  output: ./output
employee_paths:
  Alice:
    - path: "E:/data/alice_report.xlsx"
      id: 12345
      fp: "abcde"
"""
    config_path.write_text(content, encoding='utf-8')
    return config_path

def test_load_config(config_file):
    controller = ConfigController(str(config_file))
    assert controller.get_employees() == ["Alice", "Bob"]
    assert controller.get_paths()["input"] == "./input"

def test_load_config_not_found(tmp_path, caplog):
    config_path = tmp_path / "non_existent.yaml"
    controller = ConfigController(str(config_path))
    assert controller.config == {}
    assert f"Config file not found: {config_path}" in caplog.text

def test_load_config_error(tmp_path, caplog):
    config_path = tmp_path / "invalid.yaml"
    config_path.write_text("invalid: [yaml", encoding='utf-8')
    controller = ConfigController(str(config_path))
    assert controller.config == {}
    assert "Error loading config" in caplog.text

def test_add_employee(config_file):
    controller = ConfigController(str(config_file))
    controller.add_employee("Charlie")
    assert "Charlie" in controller.get_employees()
    assert controller.get_employees() == ["Alice", "Bob", "Charlie"]
    
    # Test adding existing
    controller.add_employee("Alice")
    assert controller.get_employees().count("Alice") == 1
    
    # Test adding empty
    controller.add_employee("  ")
    assert "" not in controller.get_employees()

def test_delete_employee(config_file):
    controller = ConfigController(str(config_file))
    controller.delete_employee("Alice")
    assert "Alice" not in controller.get_employees()
    assert "Alice" not in controller.config.get("employee_paths", {})

def test_attach_files(config_file, tmp_path):
    controller = ConfigController(str(config_file))
    test_file = tmp_path / "test.xlsx"
    test_file.write_text("dummy content")
    
    controller.attach_files("Bob", [str(test_file)])
    bob_paths = controller.config["employee_paths"]["Bob"]
    assert len(bob_paths) == 1
    assert bob_paths[0]["path"] == str(test_file.absolute())
    assert "id" in bob_paths[0]
    assert "fp" in bob_paths[0]

def test_attach_files_non_existent(config_file):
    controller = ConfigController(str(config_file))
    controller.attach_files("Bob", ["non_existent.xlsx"])
    # Implementation sets an empty list for the employee if no files were added
    assert controller.config.get("employee_paths", {}).get("Bob") == []

def test_attach_files_error(config_file, tmp_path):
    controller = ConfigController(str(config_file))
    test_file = tmp_path / "error_test.xlsx"
    test_file.write_text("content")
    
    # Mocking open to trigger the fallback in attach_files
    import unittest.mock as mock
    
    # We need to be careful not to break other open calls
    orig_open = open
    def mock_open(file, *args, **kwargs):
        if str(test_file) in str(file):
            raise Exception("Open error")
        return orig_open(file, *args, **kwargs)
    
    with mock.patch("builtins.open", side_effect=mock_open):
        controller.attach_files("Bob", [str(test_file)])
        
    bob_paths = controller.config["employee_paths"]["Bob"]
    assert bob_paths[0]["path"] == str(test_file.absolute())
    assert "fp" not in bob_paths[0]

def test_attach_files_append_false(config_file, tmp_path):
    controller = ConfigController(str(config_file))
    test_file = tmp_path / "test2.xlsx"
    test_file.write_text("content")
    
    controller.attach_files("Alice", [str(test_file)], append=False)
    alice_paths = controller.config["employee_paths"]["Alice"]
    assert len(alice_paths) == 1
    assert alice_paths[0]["path"] == str(test_file.absolute())

def test_save_config_error(config_file, mocker, caplog):
    controller = ConfigController(str(config_file))
    mocker.patch("builtins.open", side_effect=Exception("Save error"))
    controller.save_config()
    assert "Error saving config: Save error" in caplog.text
