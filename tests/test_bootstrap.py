import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from APP.core.bootstrap import Bootstrap

def test_bootstrap_setup_success(tmp_path):
    app_root = tmp_path
    config_path = tmp_path / "config.yaml"
    config_path.write_text("paths: {}\nsh1: {markers: {}}", encoding='utf-8')
    
    # Mock all classes instantiated in setup
    with patch('APP.core.bootstrap.ConfigController') as mock_cfg_ctl, \
         patch('APP.core.bootstrap.IngestionEngine'), \
         patch('APP.core.bootstrap.SQLiteManager'), \
         patch('APP.core.bootstrap.Validator'), \
         patch('APP.core.bootstrap.LogicService'), \
         patch('APP.core.bootstrap.MasterWriter'), \
         patch('APP.core.bootstrap.AppController'):
        
        mock_cfg_ctl.return_value.config = {'paths': {}, 'sh1': {'markers': {}}}
        
        cfg_ctl, app_ctl, persistence = Bootstrap.setup(app_root, str(config_path))
        
        assert cfg_ctl is not None
        assert app_ctl is not None
        assert persistence is not None

def test_bootstrap_setup_invalid_config(tmp_path):
    app_root = tmp_path
    config_path = tmp_path / "config.yaml"
    config_path.write_text("invalid: config", encoding='utf-8')
    
    with patch('APP.core.bootstrap.ConfigController') as mock_cfg_ctl, \
         patch('tkinter.messagebox.showerror'):
        
        mock_cfg_ctl.return_value.config = {'invalid': 'config'}
        
        with pytest.raises(ValueError, match="Файл config.yaml поврежден"):
            Bootstrap.setup(app_root, str(config_path))
