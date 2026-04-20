import os
import pytest
import openpyxl
import uuid
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch, MagicMock
from core.bootstrap import Bootstrap
from core.infra.config_controller import ConfigController
from core.infra.session_repo import SQLiteManager
from core.domain.logic_service import LogicService, Validator
from core.infra.export_writer import MasterWriter
from core.infra.ingestion_engine import IngestionEngine


def test_toxic_data_master_flow(tmp_path):
    # 1. Setup paths
    project_root = Path(__file__).parent.parent
    toxic_data_dir = project_root / "tests" / "fixtures" / "toxic_data"
    app_root = project_root / "APP"

    test_dir = tmp_path / "test_run"
    test_dir.mkdir()

    db_path = test_dir / "test_cache.db"
    schema_path = app_root / "db_schema.sql"
    master_report_path = test_dir / "Master_Report_Toxic.xlsx"
    config_path = test_dir / "config_test.yaml"

    # 2. Create config.yaml
    config_content = f"""
database:
  path: {str(db_path).replace("\\", "/")}
  schema_path: {str(schema_path).replace("\\", "/")}
paths:
  master_file: {str(master_report_path).replace("\\", "/")}
  source_root: {str(toxic_data_dir).replace("\\", "/")}
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
"""
    with open(config_path, "w", encoding="utf-8") as f:
        f.write(config_content)

    # 3. Initialize components
    cfg_ctl = ConfigController(str(config_path))
    cfg = cfg_ctl.config

    ingestion = IngestionEngine(cfg.get("sh1", {}).get("markers", {}), ("Q", "Z"))
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
        file_path = Path(f_meta["path"])
        file_id = persistence.save_file_metadata(session_id, [f_meta])[0]
        rows = ingestion.read_file(file_path)
        valid_rows = []
        for row in rows:
            if validator.validate_row(row):
                row["employee_name"] = "ToxicTester"
                valid_rows.append(row)
        if valid_rows:
            persistence.save_staging_data(file_id, valid_rows)

    # Consolidate
    persistence.wait_for_writes()
    consolidated_data = logic.consolidate(session_id)
    assert len(consolidated_data) > 0, "Should have consolidated data"

    # Write report
    success = writer.write_report(consolidated_data, master_report_path)
    assert success is True
    assert master_report_path.exists()

    # 5. Verify results
    wb = openpyxl.load_workbook(master_report_path)

    def _idx(headers, *needles):
        normalized = [str(h or "").strip().lower() for h in headers]
        for i, h in enumerate(normalized):
            if all(n.lower() in h for n in needles):
                return i
        raise AssertionError(
            f"Header not found for needles={needles}. headers={headers}"
        )

    # Find rows by customer across all sheets
    rows_by_customer = {}
    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        headers = [cell.value for cell in ws[1]]
        customer_idx = _idx(headers, "заказчик")
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
            cust = row[customer_idx].value
            if cust:
                rows_by_customer[str(cust)] = (row, headers)

    # Check toxic_3_trash_rows.xlsx (Cust3)
    assert "Cust3" in rows_by_customer

    # Check toxic_4_math_error.xlsx (Cust4)
    row4, headers4 = rows_by_customer["Cust4"]
    total_idx = _idx(headers4, "итог")
    income_idx = _idx(headers4, "приход")
    source_idx = _idx(headers4, "источник")
    assert row4[total_idx].value == 500.0  # ИТОГ
    assert row4[income_idx].value == 1000.0  # Приход
    source_fill = row4[source_idx].fill.fgColor.rgb
    total_fill = row4[total_idx].fill.fgColor.rgb
    assert source_fill in ("FFFF0000", "00FF0000") or total_fill in (
        "00FFFF00",
        "FFFF00",
    )

    # Check toxic_6_percent_broker_high.xlsx (Cust6)
    assert "Cust6" in rows_by_customer
    row6, headers6 = rows_by_customer["Cust6"]
    percent_idx6 = _idx(headers6, "% посредника")
    assert row6[percent_idx6].value == 150.0
    assert row6[percent_idx6].fill.fgColor.rgb in ("FFFF0000", "00FF0000")

    # Check toxic_7_percent_broker_non_numeric.xlsx (Cust7)
    assert "Cust7" in rows_by_customer
    row7, headers7 = rows_by_customer["Cust7"]
    percent_idx7 = _idx(headers7, "% посредника")
    assert row7[percent_idx7].value == "high"
    assert row7[percent_idx7].fill.fgColor.rgb in ("FFFF0000", "00FF0000")

    # Check toxic_9_template_warning.xlsx (Cust9)
    assert "Cust9" in rows_by_customer
    row9, headers9 = rows_by_customer["Cust9"]
    source_idx9 = _idx(headers9, "источник")
    assert row9[source_idx9].fill.fgColor.rgb in ("FFFF0000", "00FF0000")

    # Check toxic_11_return_keyword.xlsx (Cust11)
    assert "Cust11" in rows_by_customer
    row11, headers11 = rows_by_customer["Cust11"]
    expense_idx11 = _idx(headers11, "расход")
    income_idx11 = _idx(headers11, "приход")
    assert row11[expense_idx11].value == -1100.0  # Расход
    assert row11[income_idx11].value == 0.0  # Приход

    print("✅ E2E Toxic Data Test Passed!")
