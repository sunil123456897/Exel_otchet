import os
import pytest
import openpyxl
import uuid
import shutil
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch

from core.infra.config_controller import ConfigController
from core.infra.persistence_manager import SQLiteManager
from core.domain.logic_service import LogicService, Validator
from core.infra.export_writer import MasterWriter
from core.infra.ingestion_engine import IngestionEngine


def test_black_swan_scenarios(tmp_path):
    # 1. Setup paths
    project_root = Path(__file__).parent.parent
    swan_data_dir = project_root / "tests" / "fixtures" / "black_swan"
    app_root = project_root / "APP"

    test_dir = tmp_path / "swan_run"
    test_dir.mkdir()

    db_path = test_dir / "swan_cache.db"
    schema_path = app_root / "db_schema.sql"
    master_report_path = test_dir / "Master_Report_Swan.xlsx"
    config_path = test_dir / "config_swan.yaml"

    # Create config.yaml
    config_content = f"""
database:
  path: {str(db_path).replace("\\", "/")}
  schema_path: {str(schema_path).replace("\\", "/")}
paths:
  master_file: {str(master_report_path).replace("\\", "/")}
  source_root: {str(swan_data_dir).replace("\\", "/")}
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
"""
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(config_content)

    # 2. Initialize components
    cfg_ctl = ConfigController(str(config_path))
    cfg = cfg_ctl.config
    ingestion = IngestionEngine(cfg.get("sh1", {}).get("markers", {}))
    persistence = SQLiteManager(str(db_path), str(schema_path), cfg)
    validator = Validator(cfg)
    logic = LogicService(persistence, cfg)
    writer = MasterWriter(cfg)

    session_id = str(uuid.uuid4())
    persistence.save_session(session_id, {"type": "all_dates"})

    # 3. Process files (including the fake and problematic ones)
    files = ingestion.scan_directory(swan_data_dir)
    assert (
        len(files) >= 4
    )  # swan_3_fake_xlsx might be skipped or fail during scan if it's too small/weird

    for f_meta in files:
        file_path = Path(f_meta["path"])
        file_id = persistence.save_file_metadata(session_id, [f_meta])[0]

        try:
            rows = ingestion.read_file(file_path)
            valid_rows = []
            for row in rows:
                if validator.validate_row(row):
                    row["employee_name"] = "SwanTester"
                    valid_rows.append(row)
            if valid_rows:
                persistence.save_staging_data(file_id, valid_rows)
        except Exception as e:
            # We expect swan_3_fake_xlsx to fail, but it should NOT crash the whole loop
            print(f"Expected failure for {file_path.name}: {e}")

    persistence.wait_for_writes()

    # 4. Consolidate and Export
    consolidated_data = logic.consolidate(session_id)
    assert len(consolidated_data) > 0, "Should have successfully parsed some swan data"

    success = writer.write_report(consolidated_data, master_report_path)
    assert success is True

    # 5. Verification of specific scenarios
    wb = openpyxl.load_workbook(master_report_path)

    # Scenario 1: Unicode Invisible
    assert "01.04.2026" in wb.sheetnames  # Should have cleaned the \u200B

    # Scenario 4: Precision (rounding 0.333333 to 0.33)
    ws = wb["01.04.2026"]
    prec_row = None
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[2] == "Cust4":  # Заказчик
            prec_row = row
            break
    assert prec_row is not None
    assert prec_row[4] == 0.33  # ПРИХОД (rounded by to_decimal)

    # Scenario 5: Time Loop (Far Future/Past)
    assert "01.01.2099" in wb.sheetnames
    assert "01.01.1800" in wb.sheetnames

    print("✅ Black Swan Scenarios Passed!")


def test_ghost_file_deletion_mid_read(tmp_path):
    """
    Scenario: File exists during scan but vanishes before read_file finishes its local copy.
    """
    app_root = Path(r"E:\Для Даши\Версия 5\APP")
    source_dir = tmp_path / "ghost_source"
    source_dir.mkdir()

    ghost_file = source_dir / "ghost.xlsx"
    # Create a real small excel file
    import pandas as pd

    pd.DataFrame({"A": [1]}).to_excel(ghost_file, index=False)

    ingestion = IngestionEngine({})

    # Mock shutil.copy2 to delete the file before it can copy it
    original_copy2 = shutil.copy2

    def evil_copy2(src, dst, **kwargs):
        if os.path.exists(src):
            os.remove(src)  # Delete it right now!
        return original_copy2(src, dst, **kwargs)

    with patch("shutil.copy2", side_effect=evil_copy2):
        # This should handle FileNotFoundError gracefully and return empty rows, not crash
        rows = ingestion.read_file(ghost_file)
        assert rows == []

    print("✅ Ghost File Scenario Passed!")
