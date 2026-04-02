import pytest
import os
import hashlib
from unittest.mock import MagicMock, patch
from pathlib import Path
from core.infra.discovery_service import DiscoveryService

def test_discovery_service_init():
    config_controller = MagicMock()
    ingestion = MagicMock()
    service = DiscoveryService(config_controller, ingestion)
    assert service.config_controller == config_controller
    assert service.ingestion == ingestion
    assert service.rename_detected is False

def test_get_employees_map_empty():
    config_controller = MagicMock()
    config_controller.config = {}
    ingestion = MagicMock()
    ingestion.scan_directory.return_value = []
    service = DiscoveryService(config_controller, ingestion)
    
    result = service.get_employees_map()
    assert result == {}

def test_get_employees_map_with_source_root(tmp_path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    file1 = source_root / "Alice.xlsx"
    file1.write_text("content")
    
    config_controller = MagicMock()
    config_controller.config = {
        'employees': ['Alice'],
        'paths': {'source_root': str(source_root)}
    }
    
    ingestion = MagicMock()
    ingestion.scan_directory.return_value = [
        {'path': str(file1), 'id': 1, 'fp': 'hash1'}
    ]
    
    service = DiscoveryService(config_controller, ingestion)
    result = service.get_employees_map()
    
    assert 'Alice' in result
    assert len(result['Alice']) == 1
    assert result['Alice'][0]['path'] == str(file1)

def test_get_employees_map_rename_detection(tmp_path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    new_file = source_root / "Alice_new.xlsx"
    new_file.write_text("content")
    
    config_controller = MagicMock()
    config_controller.config_path = str(tmp_path / "config.yaml")
    config_controller.config = {
        'employees': ['Alice'],
        'employee_paths': {
            'Alice': [{'path': str(source_root / "Alice_old.xlsx"), 'id': 1, 'fp': 'hash1'}]
        },
        'paths': {'source_root': str(source_root)}
    }
    
    ingestion = MagicMock()
    # The old file doesn't exist, but a file with the same ID/hash is found in scan_directory
    ingestion.scan_directory.return_value = [
        {'path': str(new_file), 'id': 1, 'fp': 'hash1'}
    ]
    
    service = DiscoveryService(config_controller, ingestion)
    result = service.get_employees_map()
    
    assert service.rename_detected is True
    assert result['Alice'][0]['path'] == str(new_file)
    assert config_controller.config['employee_paths']['Alice'][0]['path'] == str(new_file)

def test_get_employees_map_no_config_list(tmp_path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    file1 = source_root / "Alice.xlsx"
    file1.write_text("content")
    
    config_controller = MagicMock()
    config_controller.config = {
        'paths': {'source_root': str(source_root)}
    }
    
    ingestion = MagicMock()
    ingestion.scan_directory.return_value = [
        {'path': str(file1), 'id': 1, 'fp': 'hash1'}
    ]
    
    service = DiscoveryService(config_controller, ingestion)
    result = service.get_employees_map()
    
    assert 'Alice' in result # Stem of Alice.xlsx is Alice

def test_get_employees_map_existing_custom_path(tmp_path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    file1 = source_root / "Alice.xlsx"
    file1.write_text("content")
    
    config_controller = MagicMock()
    config_controller.config = {
        'employees': ['Alice'],
        'employee_paths': {
            'Alice': [{'path': str(file1)}]
        }
    }
    
    ingestion = MagicMock()
    ingestion.scan_directory.return_value = []
    
    service = DiscoveryService(config_controller, ingestion)
    result = service.get_employees_map()
    
    assert 'Alice' in result
    assert result['Alice'][0]['path'] == str(file1)
    assert 'id' in result['Alice'][0]
    assert 'fp' in result['Alice'][0]

def test_get_employees_map_relative_path(tmp_path):
    config_path = tmp_path / "config.yaml"
    source_root = tmp_path / "source"
    source_root.mkdir()
    file1 = source_root / "Alice.xlsx"
    file1.write_text("content")
    
    config_controller = MagicMock()
    config_controller.config_path = str(config_path)
    config_controller.config = {
        'employees': ['Alice'],
        'employee_paths': {
            'Alice': [{'path': "source/Alice.xlsx"}]
        }
    }
    
    ingestion = MagicMock()
    ingestion.scan_directory.return_value = []
    
    service = DiscoveryService(config_controller, ingestion)
    result = service.get_employees_map()
    
    assert 'Alice' in result
    assert Path(result['Alice'][0]['path']).is_absolute()
    assert result['Alice'][0]['path'] == str(file1.absolute())

def test_get_employees_map_stat_error(tmp_path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    file1 = source_root / "Alice.xlsx"
    file1.write_text("content")
    
    config_controller = MagicMock()
    config_controller.config = {
        'employees': ['Alice'],
        'employee_paths': {
            'Alice': [{'path': str(file1)}]
        }
    }
    
    ingestion = MagicMock()
    ingestion.scan_directory.return_value = []
    
    service = DiscoveryService(config_controller, ingestion)
    
    # Mocking open to trigger the fallback in get_employees_map
    orig_open = open
    def mock_open(file, *args, **kwargs):
        if str(file1) in str(file):
            raise Exception("Open error")
        return orig_open(file, *args, **kwargs)
    
    with patch("builtins.open", side_effect=mock_open):
        result = service.get_employees_map()
    
    assert 'Alice' in result
    assert result['Alice'][0]['path'] == str(file1)
    assert 'fp' in result['Alice'][0]
    assert result['Alice'][0]['fp'] is None

