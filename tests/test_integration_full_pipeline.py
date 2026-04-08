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
    schema.write_text("""
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
    status TEXT DEFAULT 'pending'
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
""", encoding='utf-8')
    return str(schema)


@pytest.fixture
def test_xlsx(temp_dir):
    """Создаёт тестовый Excel файл с финансовыми данными."""
    f = temp_dir / "test_report.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Отчет 01.04"

    # Заголовки
    ws.append(["Заказчик", "Исполнитель", "Сумма платежа", "Приход", "Расход", "Комиссия", "Итог", "% посредника", "Посредник 1(кэш)", "Фильтры"])

    # Данные
    ws.append(["ООО Ромашка", "ИП Иванов", "10000", "10000", "0", "2.5", "10000", "5", "500", ""])
    ws.append(["ООО Василек", "ООО Партнер", "5000", "0", "5000", "1", "5000", "3", "150", "возврат"])
    
    # Мусорная строка, которую Reader НЕ отфильтрует (так как есть '1' в сумме), но Validator ДОЛЖЕН
    ws.append(["ИТОГО", "", "1", "0", "0", "0", "0", "0", "0", ""]) 

    wb.save(f)
    return f


@pytest.fixture
def full_pipeline(temp_dir, schema_file, test_xlsx):
    """Полный pipeline: все компоненты."""
    config = {
        'paths': {'master_file': str(temp_dir / 'output.xlsx')},
        'sh1': {
            'markers': {
                'customer': 'заказчик',
                'contractor': 'исполнитель',
                'amount': 'сумма платежа',
                'income': 'приход',
                'expense': 'расход',
                'commission': 'комиссия',
                'total': 'итог',
                'percent_broker': '% посредника',
                'broker1': 'посредник 1(кэш)',
            }
        },
        'logic': {
            'income_overrides': ['доп', 'доп сф'],
            'return_keywords': ['возврат'],
        },
        'database': {'path': str(temp_dir / 'test.db'), 'schema_path': schema_file},
        'locking': {'retry_count': 2, 'retry_backoff': 0.05},
    }

    # Компоненты
    ingestion = IngestionEngine(config['sh1']['markers'])
    persistence = SQLiteManager(config['database']['path'], config['database']['schema_path'], config)
    validator = Validator(config)
    logic = LogicService(persistence, config)
    writer = MasterWriter(config)

    yield {
        'ingestion': ingestion,
        'persistence': persistence,
        'validator': validator,
        'logic': logic,
        'writer': writer,
        'config': config,
        'test_file': test_xlsx,
        'temp_dir': temp_dir,
    }
    
    # Ensure database is closed for cleanup
    persistence.close()
    import gc
    import time
    gc.collect()
    time.sleep(0.1) # Give OS time to release file handles


class TestFullPipeline:
    """Интеграционные тесты полного потока."""

    def test_ingest_to_export(self, full_pipeline):
        """Полный поток: прочитать → сохранить → консолидировать → записать."""
        p = full_pipeline
        session_id = "integration_test_1"

        # 1. Ingestion
        rows = p['ingestion'].read_file(p['test_file'])
        assert len(rows) == 3

        # 2. Validation
        valid_rows = [r for r in rows if p['validator'].validate_row(r)]
        assert len(valid_rows) == 2

        # 3. Persistence
        p['persistence'].save_session(session_id, {'type': 'integration_test'})
        file_ids = p['persistence'].save_file_metadata(session_id, [{'path': str(p['test_file'])}])
        file_id = file_ids[0]
        p['persistence'].save_staging_data(file_id, valid_rows)

        # Подождать writer thread
        import time
        time.sleep(0.5)

        # 4. Logic
        consolidated = p['logic'].consolidate(session_id)
        assert len(consolidated) == 2
        # Check for presence of main columns (using partial match for long keys)
        row_keys = consolidated[0].keys()
        assert any('ЗАКАЗЧИК' in k for k in row_keys)
        assert any('ИСПОЛНИТЕЛЬ' in k for k in row_keys)

        # 5. Export
        output_path = p['temp_dir'] / 'master_output.xlsx'
        success = p['writer'].write_report(consolidated, output_path)
        assert success is True
        assert output_path.exists()

        # 6. Verify output
        wb = openpyxl.load_workbook(output_path)
        assert len(wb.sheetnames) > 0
        wb.close()

    def test_validation_filters_junk(self, full_pipeline):
        """Валидатор должен отфильтровать мусорные строки."""
        p = full_pipeline
        rows = p['ingestion'].read_file(p['test_file'])
        
        # In updated test_xlsx fixture, we have 3 rows that reader picks up
        assert len(rows) == 3

        valid_count = sum(1 for r in rows if p['validator'].validate_row(r))
        # "ИТОГО" junk row should be filtered out by Validator, leaving 2 valid rows
        assert valid_count == 2
        assert valid_count < len(rows)

    def test_logic_applies_financial_rules(self, full_pipeline):
        """LogicService применяет финансовые правила."""
        p = full_pipeline
        session_id = "logic_test"

        rows = p['ingestion'].read_file(p['test_file'])
        valid_rows = [r for r in rows if p['validator'].validate_row(r)]

        p['persistence'].save_session(session_id, {})
        file_ids = p['persistence'].save_file_metadata(session_id, [{'path': str(p['test_file'])}])
        p['persistence'].save_staging_data(file_ids[0], valid_rows)

        import time
        time.sleep(0.3)

        consolidated = p['logic'].consolidate(session_id)

        # Проверить что финансовые поля присутствуют
        for row in consolidated:
            assert 'сумма платежа ПРИХОД' in row
            assert 'сумма платежа РАСХОД' in row
            assert 'комиссия' in row

    def test_empty_file_handling(self, full_pipeline, temp_dir):
        """Пустой файл — обработка без ошибок."""
        p = full_pipeline
        empty_file = temp_dir / "empty.xlsx"
        wb = openpyxl.Workbook()
        wb.save(empty_file)

        rows = p['ingestion'].read_file(empty_file)
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
        ws.append(["Заказчик", "Исполнитель", "Сумма платежа", "Приход", "Расход", "Комиссия", "Итог"])
        ws.append(["ООО Третий", "ИП Петров", "20000", "20000", "0", "3", "20000"])
        wb.save(file2)

        p['persistence'].save_session(session_id, {})

        # Файл 1
        rows1 = p['ingestion'].read_file(p['test_file'])
        valid1 = [r for r in rows1 if p['validator'].validate_row(r)]
        ids1 = p['persistence'].save_file_metadata(session_id, [{'path': str(p['test_file'])}])
        p['persistence'].save_staging_data(ids1[0], valid1)

        # Файл 2
        rows2 = p['ingestion'].read_file(file2)
        valid2 = [r for r in rows2 if p['validator'].validate_row(r)]
        ids2 = p['persistence'].save_file_metadata(session_id, [{'path': str(file2)}])
        p['persistence'].save_staging_data(ids2[0], valid2)

        import time
        time.sleep(0.5)

        # Консолидация
        consolidated = p['logic'].consolidate(session_id)
        assert len(consolidated) >= 2  # Данные из обоих файлов

        p['persistence'].close()
