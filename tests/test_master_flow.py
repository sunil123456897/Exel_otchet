import os
import pytest
import openpyxl
import uuid
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from core.bootstrap import Bootstrap
from core.infra.config_controller import ConfigController
from core.infra.persistence_manager import SQLiteManager
from core.domain.logic_service import LogicService, Validator
from core.infra.export_writer import MasterWriter
from core.infra.ingestion_engine import IngestionEngine

def test_toxic_data_master_flow(tmp_path):
    # 1. Setup paths
    toxic_data_dir = Path(r"E:\Для Даши\Версия 5\tests\fixtures\toxic_data")
    app_root = Path(r"E:\Для Даши\Версия 5\APP")
    
    test_dir = tmp_path / "test_run"
    test_dir.mkdir()
    
    db_path = test_dir / "test_cache.db"
    schema_path = app_root / "db_schema.sql"
    master_report_path = test_dir / "Master_Report_Toxic.xlsx"
    config_path = test_dir / "config_test.yaml"
    
    # 2. Create config.yaml
    config_content = f"""
database:
  path: {str(db_path).replace('\\', '/')}
  schema_path: {str(schema_path).replace('\\', '/')}
paths:
  master_file: {str(master_report_path).replace('\\', '/')}
  source_root: {str(toxic_data_dir).replace('\\', '/')}
sh1:
  markers:
    amount: сумма платежа
    broker1: посредник 1(кэш)
    broker2: посредник 2
    commission: комиссия
    contractor: Исполнитель
    customer: Заказчик
    expense: расход
    filters: фильтры
    income: приход
    percent_broker: '% посредника'
    total: итог
logic:
  income_overrides: [доп, доп сф, '% посред']
  return_keywords: [возврат]
employees: []
employee_paths: {{}}
"""
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(config_content)
        
    # 3. Initialize components
    cfg_ctl = ConfigController(str(config_path))
    cfg = cfg_ctl.config
    
    ingestion = IngestionEngine(cfg.get('sh1', {}).get('markers', {}))
    persistence = SQLiteManager(str(db_path), str(schema_path), cfg)
    validator = Validator(cfg)
    logic = LogicService(persistence, cfg)
    writer = MasterWriter(cfg)
    
    # 4. Run consolidation flow
    session_id = str(uuid.uuid4())
    persistence.save_session(session_id, {"type": "all_dates"})
    
    # Scan and read files
    files = ingestion.scan_directory(toxic_data_dir)
    for f_meta in files:
        file_path = Path(f_meta['path'])
        file_id = persistence.save_file_metadata(session_id, [f_meta])[0]
        rows = ingestion.read_file(file_path)
        valid_rows = []
        for row in rows:
            if validator.validate_row(row):
                row['employee_name'] = "ToxicTester"
                valid_rows.append(row)
        if valid_rows:
            persistence.save_staging_data(file_id, valid_rows)
            
    # Consolidate
    consolidated_data = logic.consolidate(session_id)
    assert len(consolidated_data) > 0, "Should have consolidated data"
    
    # Write report
    success = writer.write_report(consolidated_data, master_report_path)
    assert success is True
    assert master_report_path.exists()
    
    # 5. Verify results (Golden File approach)
    wb = openpyxl.load_workbook(master_report_path)
    
    # Check if we have the expected sheet (01.04.2026)
    assert "01.04.2026" in wb.sheetnames
    ws = wb["01.04.2026"]
    
    # Verify data and styles
    # Headers: Дата, Источник, ЗАКАЗЧИК, ИСПОЛНИТЕЛЬ, Приход, Расход, Комиссия, ИТОГ, % посредника, посредник 1(кэш), посредник 2, Фильтры
    
    # Find rows by 'ЗАКАЗЧИК'
    rows_by_customer = {}
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        cust = row[2].value
        if cust:
            rows_by_customer[cust] = row

    # Check toxic_3_trash_rows.xlsx (Cust3)
    assert "Cust3" in rows_by_customer
    # Ensure no trash rows for Cust3 (they should have been skipped by ingestion)
    # We can't easily check "absence" of rows in the middle, but we can check total count or specific values.
    
    # Check toxic_4_math_error.xlsx (Cust4)
    # Math error: amount=1000, total=500. Should be YELLOW.
    row4 = rows_by_customer["Cust4"]
    assert row4[7].value == 500.0 # ИТОГ
    assert row4[4].value == 1000.0 # Приход
    # Check fill color (YELLOW: FFFF00)
    # openpyxl PatternFill.fgColor.rgb might be '00FFFF00' or 'FFFF00'
    assert row4[0].fill.fgColor.rgb in ('00FFFF00', 'FFFF00')
    
    # Check toxic_6_percent_broker_high.xlsx (Cust6)
    # % посредника = 150. Should be RED (FFFF0000).
    row6 = rows_by_customer["Cust6"]
    assert row6[8].value == 150.0
    assert row6[8].fill.fgColor.rgb in ('FFFF0000', '00FF0000')
    
    # Check toxic_7_percent_broker_non_numeric.xlsx (Cust7)
    # % посредника = 'high'. Should be RED.
    row7 = rows_by_customer["Cust7"]
    assert row7[8].value == 'high'
    assert row7[8].fill.fgColor.rgb in ('FFFF0000', '00FF0000')
    
    # Check toxic_9_template_warning.xlsx (Cust9)
    # Template warning (uses 'агент' instead of 'Заказчик'). 'Источник' cell should be RED.
    row9 = rows_by_customer["Cust9"]
    assert "toxic_9_template_warning.xlsx" in str(row9[1].value)
    assert row9[1].fill.fgColor.rgb in ('FFFF0000', '00FF0000')
    
    # Check toxic_11_return_keyword.xlsx (Cust11)
    # 'возврат' keyword. Should be in 'Расход' as negative.
    row11 = rows_by_customer["Cust11"]
    assert row11[5].value == -1100.0 # Расход
    assert row11[4].value == 0.0 # Приход
    
    print("✅ E2E Toxic Data Test Passed!")

if __name__ == "__main__":
    # For manual run
    import sys
    from pathlib import Path
    # Add APP to sys.path
    sys.path.insert(0, str(Path(__file__).parent.parent / "APP"))
    # This won't work directly because of pytest fixtures, but good for reference.
