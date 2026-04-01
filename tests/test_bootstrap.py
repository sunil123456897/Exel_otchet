import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from core.bootstrap import Bootstrap

def test_bootstrap_setup_success(tmp_path):
    app_root = tmp_path
    config_path = tmp_path / "config.yaml"
    config_path.write_text("paths: {}\nsh1: {markers: {}}", encoding='utf-8')
    
    # Mock all classes instantiated in setup
    with patch('core.bootstrap.ConfigController') as mock_cfg_ctl, \
         patch('core.bootstrap.IngestionEngine'), \
         patch('core.bootstrap.SQLiteManager'), \
         patch('core.bootstrap.Validator'), \
         patch('core.bootstrap.LogicService'), \
         patch('core.bootstrap.MasterWriter'), \
         patch('core.bootstrap.AppController'):
        
        mock_cfg_ctl.return_value.config = {'paths': {}, 'sh1': {'markers': {}}}
        
        cfg_ctl, app_ctl, persistence = Bootstrap.setup(app_root, str(config_path))
        
        assert cfg_ctl is not None
        assert app_ctl is not None
        assert persistence is not None

def test_bootstrap_setup_invalid_config(tmp_path):
    app_root = tmp_path
    config_path = tmp_path / "config.yaml"
    config_path.write_text("invalid: config", encoding='utf-8')
    
    with patch('core.bootstrap.ConfigController') as mock_cfg_ctl, \
         patch('tkinter.messagebox.showerror'):
        
        mock_cfg_ctl.return_value.config = {'invalid': 'config'}
        
        with pytest.raises(ValueError, match="Файл config.yaml поврежден"):
            Bootstrap.setup(app_root, str(config_path))
