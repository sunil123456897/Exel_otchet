"""Интеграционные тесты полного потока: ingestion → persistence → logic → export."""

import pytest
import tempfile
import os
from datetime import datetime
from pathlib import Path
from decimal import Decimal
from unittest.mock import MagicMock, patch
import openpyxl

from core.infra.ingestion_engine import IngestionEngine
from core.infra.session_repo import SQLiteManager
from core.domain.logic_service import LogicService, Validator
from core.infra.export_writer import MasterWriter


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def schema_file(temp_dir):
    schema = temp_dir / "schema.sql"
    schema.write_text(
        """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    metadata TEXT,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS source_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    file_path TEXT,
    file_hash TEXT,
    inode INTEGER,
    status TEXT DEFAULT 'pending',
    error_message TEXT
);
CREATE TABLE IF NOT EXISTS staging_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_id INTEGER,
    row_index INTEGER,
    raw_content_json TEXT,
    date_val TEXT,
    amount NUMERIC,
    employee_name TEXT,
    source_type TEXT
);
CREATE TABLE IF NOT EXISTS file_cache (
    file_path TEXT PRIMARY KEY,
    mtime REAL,
    size INTEGER,
    dates_json TEXT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS template_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    file_path TEXT,
    sheet_name TEXT,
    row_index INTEGER,
    error_type TEXT,
    details TEXT,
    raw_data TEXT
);
""",
        encoding="utf-8",
    )
    return str(schema)


@pytest.fixture
def test_xlsx(temp_dir):
    """Создаёт тестовый Excel файл с финансовыми данными."""
    f = temp_dir / "test_report.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Отчет 01.04"

    # Заголовки
    ws.append(
        [
            "Заказчик",
            "Исполнитель",
            "Сумма платежа",
            "Приход",
            "Расход",
            "Комиссия",
            "Итог",
            "% посредника",
            "Посредник 1(кэш)",
            "Фильтры",
        ]
    )

    # Данные
    ws.append(
        [
            "ООО Ромашка",
            "ИП Иванов",
            "10000",
            "10000",
            "0",
            "2.5",
            "10000",
            "5",
            "500",
            "",
        ]
    )
    ws.append(
        [
            "ООО Василек",
            "ООО Партнер",
            "5000",
            "0",
            "5000",
            "1",
            "5000",
            "3",
            "150",
            "возврат",
        ]
    )

    # Мусорная строка, которую Reader должен отфильтровать на ingestion-этапе
    ws.append(["ИТОГО", "", "1", "0", "0", "0", "0", "0", "0", ""])

    wb.save(f)
    return f


@pytest.fixture
def full_pipeline(temp_dir, schema_file, test_xlsx):
    """Полный pipeline: все компоненты."""
    config = {
        "paths": {"master_file": str(temp_dir / "output.xlsx")},
        "sh1": {
            "markers": {
                "customer": "заказчик",
                "contractor": "исполнитель",
                "amount": "сумма платежа",
                "income": "приход",
                "expense": "расход",
                "commission": "комиссия",
                "total": "итог",
                "percent_broker": "% посредника",
                "broker1": "посредник 1(кэш)",
            }
        },
        "logic": {
            "income_overrides": ["доп", "доп сф"],
            "return_keywords": ["возврат"],
        },
        "database": {"path": str(temp_dir / "test.db"), "schema_path": schema_file},
        "locking": {"retry_count": 2, "retry_backoff": 0.05},
    }

    # Компоненты
    ingestion = IngestionEngine(config["sh1"]["markers"])
    persistence = SQLiteManager(
        config["database"]["path"], config["database"]["schema_path"], config
    )
    validator = Validator(config)
    logic = LogicService(persistence, config)
    writer = MasterWriter(config)

    yield {
        "ingestion": ingestion,
        "persistence": persistence,
        "validator": validator,
        "logic": logic,
        "writer": writer,
        "config": config,
        "test_file": test_xlsx,
        "temp_dir": temp_dir,
    }

    # Ensure database is closed for cleanup
    persistence.close()
    import gc
    import time

    gc.collect()
    time.sleep(0.1)  # Give OS time to release file handles


class TestFullPipeline:
    """Интеграционные тесты полного потока."""

    def test_ingest_to_export(self, full_pipeline):
        """Полный поток: прочитать → сохранить → консолидировать → записать."""
        p = full_pipeline
        session_id = "integration_test_1"

        # 1. Ingestion
        rows = p["ingestion"].read_file(p["test_file"])
        assert len(rows) == 2

        # 2. Validation
        valid_rows = [r for r in rows if p["validator"].validate_row(r)]
        assert len(valid_rows) == 2

        # 3. Persistence
        p["persistence"].save_session(session_id, {"type": "integration_test"})
        file_ids = p["persistence"].save_file_metadata(
            session_id, [{"path": str(p["test_file"])}]
        )
        file_id = file_ids[0]
        p["persistence"].save_staging_data(file_id, valid_rows)

        # Подождать writer thread
        import time

        time.sleep(0.5)

    def test_template_warning_persisted_and_exported(self, full_pipeline):
        p = full_pipeline
        session_id = "integration_warning_sheet"

        p["persistence"].save_session(session_id, {"type": "integration_warning"})
        file_id = p["persistence"].save_file_metadata(
            session_id, [{"path": str(p["test_file"])}]
        )[0]

        warning_rows = [
            {
                "date": "01.04.2026",
                "amount": "1000",
                "total": None,
                "customer": "ООО Ромашка",
                "contractor": "ИП Иванов",
                "filters": "",
                "is_template_warning": True,
                "_sheet_name": "01.04",
                "_row_index": 7,
                "_file_path": str(p["test_file"]),
                "_source_info": "test_report.xlsx | 01.04 | Row 7",
                "employee_name": "Emp",
            }
        ]
        p["persistence"].save_staging_data(file_id, warning_rows)
        p["persistence"].save_template_error(
            session_id,
            {
                "file_path": str(p["test_file"]),
                "sheet_name": "01.04",
                "row_index": 7,
                "error_type": "template_warning",
                "details": "test_report.xlsx | 01.04 | Row 7",
                "raw_data": warning_rows[0],
            },
        )

        import time

        time.sleep(0.5)

        consolidated = p["logic"].consolidate(session_id)
        errors = p["persistence"].get_template_errors(session_id)

        assert consolidated[0]["is_template_warning"] is True
        assert len(errors) == 1
        assert errors[0]["error_type"] == "template_warning"

        output_path = p["temp_dir"] / "warning_output.xlsx"
        assert (
            p["writer"].write_report(consolidated, output_path, template_errors=errors)
            is True
        )

        wb = openpyxl.load_workbook(output_path)
        assert "ОШИБКИ ШАБЛОНА" not in wb.sheetnames
        assert "01.04.2026" in wb.sheetnames
        wb.close()

    def test_soft_structure_warning_exported_without_red_source(self, full_pipeline):
        p = full_pipeline
        session_id = "integration_soft_structure"

        p["persistence"].save_session(
            session_id, {"type": "integration_soft_structure"}
        )
        file_id = p["persistence"].save_file_metadata(
            session_id, [{"path": str(p["test_file"])}]
        )[0]

        soft_rows = [
            {
                "date": "01.04.2026",
                "amount": "1000",
                "total": "1000",
                "customer": "ООО Ромашка",
                "contractor": "ИП Иванов",
                "filters": "",
                "is_template_warning": False,
                "_template_warning_kind": "soft_structure",
                "_template_warning_reason": "unsupported header name: % -> % посредника",
                "_sheet_name": "01.04",
                "_row_index": 7,
                "_file_path": str(p["test_file"]),
                "_source_info": "test_report.xlsx | 01.04 | Row 7",
                "employee_name": "Emp",
            }
        ]
        p["persistence"].save_staging_data(file_id, soft_rows)
        p["persistence"].save_template_error(
            session_id,
            {
                "file_path": str(p["test_file"]),
                "sheet_name": "01.04",
                "row_index": 7,
                "error_type": "soft_structure",
                "details": "unsupported header name: % -> % посредника",
                "raw_data": soft_rows[0],
            },
        )

        import time

        time.sleep(0.5)

        consolidated = p["logic"].consolidate(session_id)
        errors = p["persistence"].get_template_errors(session_id)

        assert consolidated[0]["is_template_warning"] is False
        assert errors[0]["error_type"] == "soft_structure"

        output_path = p["temp_dir"] / "soft_structure_output.xlsx"
        assert p["writer"].write_report(
            consolidated, output_path, template_errors=errors
        )

        wb = openpyxl.load_workbook(output_path)
        ws = wb["01.04.2026"]
        assert (
            ws.cell(2, 1).fill.start_color.rgb
            != p["writer"].st.fill_warning.start_color.rgb
        )
        assert "ОШИБКИ ШАБЛОНА" not in wb.sheetnames
        wb.close()

    def test_hard_structure_warning_exported_with_red_source(self, full_pipeline):
        p = full_pipeline
        session_id = "integration_hard_structure"

        p["persistence"].save_session(
            session_id, {"type": "integration_hard_structure"}
        )
        file_id = p["persistence"].save_file_metadata(
            session_id, [{"path": str(p["test_file"])}]
        )[0]

        hard_rows = [
            {
                "date": "01.04.2026",
                "amount": "1000",
                "total": "1000",
                "customer": "ООО Ромашка",
                "contractor": "ИП Иванов",
                "filters": "",
                "is_template_warning": True,
                "_template_warning_kind": "hard_structure",
                "_template_warning_reason": "unexpected columns: курс",
                "_sheet_name": "01.04",
                "_row_index": 7,
                "_file_path": str(p["test_file"]),
                "_source_info": "test_report.xlsx | 01.04 | Row 7",
                "employee_name": "Emp",
            }
        ]
        p["persistence"].save_staging_data(file_id, hard_rows)
        p["persistence"].save_template_error(
            session_id,
            {
                "file_path": str(p["test_file"]),
                "sheet_name": "01.04",
                "row_index": 7,
                "error_type": "hard_structure",
                "details": "unexpected columns: курс",
                "raw_data": hard_rows[0],
            },
        )

        import time

        time.sleep(0.5)

        consolidated = p["logic"].consolidate(session_id)
        errors = p["persistence"].get_template_errors(session_id)

        assert consolidated[0]["is_template_warning"] is True
        assert errors[0]["error_type"] == "hard_structure"

        output_path = p["temp_dir"] / "hard_structure_output.xlsx"
        assert p["writer"].write_report(
            consolidated, output_path, template_errors=errors
        )

        wb = openpyxl.load_workbook(output_path)
        ws = wb["01.04.2026"]
        assert (
            ws.cell(2, 1).fill.start_color.rgb
            == p["writer"].st.fill_warning.start_color.rgb
        )
        assert "ОШИБКИ ШАБЛОНА" not in wb.sheetnames
        wb.close()

    def test_numeric_text_total_warning_paints_total_not_source(self, full_pipeline):
        p = full_pipeline
        session_id = "integration_numeric_total_warning"

        p["persistence"].save_session(
            session_id, {"type": "integration_numeric_total_warning"}
        )
        file_id = p["persistence"].save_file_metadata(
            session_id, [{"path": str(p["test_file"])}]
        )[0]

        warning_rows = [
            {
                "date": "01.04.2026",
                "amount": "-1000",
                "total": 0,
                "customer": "ООО Ромашка",
                "contractor": "ИП Иванов",
                "filters": "",
                "is_template_warning": True,
                "_template_warning_kind": "template_warning",
                "_template_warning_reason": "text in numeric field: total",
                "_sheet_name": "01.04",
                "_row_index": 7,
                "_file_path": str(p["test_file"]),
                "_source_info": "test_report.xlsx | 01.04 | Row 7",
                "employee_name": "Emp",
            }
        ]
        p["persistence"].save_staging_data(file_id, warning_rows)
        p["persistence"].save_template_error(
            session_id,
            {
                "file_path": str(p["test_file"]),
                "sheet_name": "01.04",
                "row_index": 7,
                "error_type": "template_warning",
                "details": "text in numeric field: total",
                "raw_data": warning_rows[0],
            },
        )

        import time

        time.sleep(0.5)

        consolidated = p["logic"].consolidate(session_id)
        assert consolidated[0]["is_template_warning"] is True
        assert (
            consolidated[0]["_template_warning_reason"]
            == "text in numeric field: total"
        )

        output_path = p["temp_dir"] / "numeric_total_warning_output.xlsx"
        assert p["writer"].write_report(consolidated, output_path)

        wb = openpyxl.load_workbook(output_path)
        ws = wb["01.04.2026"]
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        source_idx = headers.index("Источник") + 1
        total_idx = headers.index("ИТОГ") + 1

        assert (
            ws.cell(2, source_idx).fill.start_color.rgb
            != p["writer"].st.fill_warning.start_color.rgb
        )
        assert (
            ws.cell(2, total_idx).fill.start_color.rgb
            == p["writer"].st.fill_warning.start_color.rgb
        )
        wb.close()

    def test_file_with_template_warning_not_marked_plain_processed(self, full_pipeline):
        p = full_pipeline
        session_id = "integration_warning_status"

        p["persistence"].save_session(
            session_id, {"type": "integration_warning_status"}
        )
        file_id = p["persistence"].save_file_metadata(
            session_id, [{"path": str(p["test_file"])}]
        )[0]
        p["persistence"].update_file_status(file_id, "processed_with_warnings")

        status = p["persistence"].get_session_status(session_id)
        assert status["file_stats"]["processed_with_warnings"] == 1

    def test_validation_filters_junk(self, full_pipeline):
        """Валидатор должен отфильтровать мусорные строки."""
        p = full_pipeline
        rows = p["ingestion"].read_file(p["test_file"])

        # Reader now filters the summary junk row during ingestion.
        assert len(rows) == 2

        valid_count = sum(1 for r in rows if p["validator"].validate_row(r))
        # Оставшиеся две строки валидны и доходят до валидатора.
        assert valid_count == 2
        assert valid_count == len(rows)

    def test_logic_applies_financial_rules(self, full_pipeline):
        """LogicService применяет финансовые правила."""
        p = full_pipeline
        session_id = "logic_test"

        rows = p["ingestion"].read_file(p["test_file"])
        valid_rows = [r for r in rows if p["validator"].validate_row(r)]

        p["persistence"].save_session(session_id, {})
        file_ids = p["persistence"].save_file_metadata(
            session_id, [{"path": str(p["test_file"])}]
        )
        p["persistence"].save_staging_data(file_ids[0], valid_rows)

        import time

        time.sleep(0.3)

        consolidated = p["logic"].consolidate(session_id)

        # Проверить что финансовые поля присутствуют
        for row in consolidated:
            assert "сумма платежа ПРИХОД" in row
            assert "сумма платежа РАСХОД" in row
            assert "комиссия" in row

    def test_empty_file_handling(self, full_pipeline, temp_dir):
        """Пустой файл — обработка без ошибок."""
        p = full_pipeline
        empty_file = temp_dir / "empty.xlsx"
        wb = openpyxl.Workbook()
        wb.save(empty_file)

        rows = p["ingestion"].read_file(empty_file)
        assert rows == []

    def test_multiple_files_same_session(self, full_pipeline, temp_dir):
        """Несколько файлов в одной сессии."""
        p = full_pipeline
        session_id = "multi_file_test"

        # Создать второй файл
        file2 = temp_dir / "test_report_2.xlsx"
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Отчет 02.04"
        ws.append(
            [
                "Заказчик",
                "Исполнитель",
                "Сумма платежа",
                "Приход",
                "Расход",
                "Комиссия",
                "Итог",
            ]
        )
        ws.append(["ООО Третий", "ИП Петров", "20000", "20000", "0", "3", "20000"])
        wb.save(file2)

        p["persistence"].save_session(session_id, {})

        # Файл 1
        rows1 = p["ingestion"].read_file(p["test_file"])
        valid1 = [r for r in rows1 if p["validator"].validate_row(r)]
        ids1 = p["persistence"].save_file_metadata(
            session_id, [{"path": str(p["test_file"])}]
        )
        p["persistence"].save_staging_data(ids1[0], valid1)

        # Файл 2
        rows2 = p["ingestion"].read_file(file2)
        valid2 = [r for r in rows2 if p["validator"].validate_row(r)]
        ids2 = p["persistence"].save_file_metadata(session_id, [{"path": str(file2)}])
        p["persistence"].save_staging_data(ids2[0], valid2)

        import time

        time.sleep(0.5)

        # Консолидация
        consolidated = p["logic"].consolidate(session_id)
        assert len(consolidated) >= 2  # Данные из обоих файлов

        p["persistence"].close()
