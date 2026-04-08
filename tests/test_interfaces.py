"""Тесты для interfaces.py — проверка абстрактных контрактов."""
import pytest
from abc import ABC
from pathlib import Path
from typing import List, Dict, Any
from decimal import Decimal

from core.domain.interfaces import (
    IDataSource, IPersistence, IValidator, ILogicService, IExporter
)


class TestInterfacesExist:
    """Тесты что интерфейсы существуют и являются абстрактными."""

    def test_idata_source_is_abstract(self):
        assert issubclass(IDataSource, ABC)

    def test_ipersistence_is_abstract(self):
        assert issubclass(IPersistence, ABC)

    def test_ivalidator_is_abstract(self):
        assert issubclass(IValidator, ABC)

    def test_ilogic_service_is_abstract(self):
        assert issubclass(ILogicService, ABC)

    def test_iexporter_is_abstract(self):
        assert issubclass(IExporter, ABC)

    def test_cannot_instantiate_idata_source(self):
        with pytest.raises(TypeError):
            IDataSource()

    def test_cannot_instantiate_ipersistence(self):
        with pytest.raises(TypeError):
            IPersistence()

    def test_cannot_instantiate_ivalidator(self):
        with pytest.raises(TypeError):
            IValidator()

    def test_cannot_instantiate_ilogic_service(self):
        with pytest.raises(TypeError):
            ILogicService()

    def test_cannot_instantiate_iexporter(self):
        with pytest.raises(TypeError):
            IExporter()


class TestInterfaceMethods:
    """Тесты что методы интерфейсов определены как abstract."""

    def test_idata_source_has_methods(self):
        assert hasattr(IDataSource, 'scan_directory')
        assert hasattr(IDataSource, 'read_file')

    def test_ipersistence_has_methods(self):
        methods = [
            'init_db', 'save_session', 'save_file_metadata',
            'save_staging_data', 'save_template_error', 'get_template_errors',
            'get_session_status', 'get_consolidated_data', 'close'
        ]
        for method in methods:
            assert hasattr(IPersistence, method)

    def test_ivalidator_has_methods(self):
        assert hasattr(IValidator, 'validate_row')
        assert hasattr(IValidator, 'get_errors')

    def test_ilogic_service_has_methods(self):
        assert hasattr(ILogicService, 'apply_financial_rules')
        assert hasattr(ILogicService, 'consolidate')

    def test_iexporter_has_methods(self):
        assert hasattr(IExporter, 'write_report')


class TestConcreteImplementations:
    """Тесты что конкретные реализации удовлетворяют интерфейсам."""

    def test_ingestion_engine_implements_idata_source(self):
        from core.infra.ingestion_engine import IngestionEngine
        assert hasattr(IngestionEngine, 'scan_directory')
        assert hasattr(IngestionEngine, 'read_file')

    def test_sqlite_manager_implements_ipersistence(self):
        from core.infra.session_repo import SQLiteManager
        methods = [
            'init_db', 'save_session', 'save_file_metadata',
            'save_staging_data', 'get_template_errors',
            'get_session_status', 'get_consolidated_data', 'close'
        ]
        for method in methods:
            assert hasattr(SQLiteManager, method)

    def test_validator_implements_ivalidator(self):
        from core.domain.logic_service import Validator
        assert hasattr(Validator, 'validate_row')
        assert hasattr(Validator, 'get_errors')

    def test_logic_service_implements_ilogic_service(self):
        from core.domain.logic_service import LogicService
        assert hasattr(LogicService, 'apply_financial_rules')
        assert hasattr(LogicService, 'consolidate')

    def test_master_writer_implements_iexporter(self):
        from core.infra.export_writer import MasterWriter
        assert hasattr(MasterWriter, 'write_report')
