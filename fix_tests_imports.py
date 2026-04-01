import os
from pathlib import Path

mapping = {
    # UI
    'gui_master': 'core.ui.gui_master',
    'theme': 'core.ui.theme',
    'ui_dialogs': 'core.ui.ui_dialogs',
    'ui_employee_table': 'core.ui.ui_employee_table',
    'ui_log_panel': 'core.ui.ui_log_panel',
    'ui_sidebar': 'core.ui.ui_sidebar',
    'ui_stats_panel': 'core.ui.ui_stats_panel',
    # Domain
    'data_schemas': 'core.domain.data_schemas',
    'interfaces': 'core.domain.interfaces',
    'logic_service': 'core.domain.logic_service',
    'utils_helpers': 'core.domain.utils_helpers',
    # Infra
    'config_controller': 'core.infra.config_controller',
    'discovery_service': 'core.infra.discovery_service',
    'export_styles': 'core.infra.export_styles',
    'export_writer': 'core.infra.export_writer',
    'ingestion_engine': 'core.infra.ingestion_engine',
    'ingestion_readers': 'core.infra.ingestion_readers',
    'ingestion_utils': 'core.infra.ingestion_utils',
    'persistence_manager': 'core.infra.persistence_manager',
    'utils_logging': 'core.infra.utils_logging',
}

def fix_content(content):
    # 1. First, handle 'APP.core' occurrences - we want them to become 'core' or 'core.infra' etc.
    # But wait, if we have 'APP.core.bootstrap', it should become 'core.bootstrap'.
    # If we have 'APP.core.ingestion_engine', it should become 'core.infra.ingestion_engine'.
    
    # Let's handle 'APP.core.' explicitly
    content = content.replace('APP.core.bootstrap', 'core.bootstrap')
    content = content.replace('APP.core.app_controller', 'core.app_controller')
    
    for old, new in mapping.items():
        # Replace 'from core.old' with 'from new'
        content = content.replace(f'from core.{old}', f'from {new}')
        content = content.replace(f'import core.{old}', f'import {new}')
        # Replace 'from APP.core.old' with 'from new'
        content = content.replace(f'from APP.core.{old}', f'from {new}')
        content = content.replace(f'import APP.core.{old}', f'import {new}')
        # Replace 'patch("core.old' with 'patch("new'
        content = content.replace(f'patch("core.{old}', f'patch("{new}')
        content = content.replace(f"patch('core.{old}", f"patch('{new}")
        # Replace 'patch("APP.core.old' with 'patch("new'
        content = content.replace(f'patch("APP.core.{old}', f'patch("{new}')
        content = content.replace(f"patch('APP.core.{old}", f"patch('{new}")
        
    return content

tests_dir = Path("tests")
for f in tests_dir.glob("*.py"):
    if f.name == "conftest.py": continue
    print(f"Processing {f}")
    content = f.read_text(encoding="utf-8")
    new_content = fix_content(content)
    if new_content != content:
        f.write_text(new_content, encoding="utf-8")
        print(f"  Updated {f}")
