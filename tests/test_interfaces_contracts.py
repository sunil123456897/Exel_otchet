import inspect
from pathlib import Path

from core.domain.interfaces import (
    IDataSource,
    IExporter,
    ILogicService,
    IPersistence,
    IValidator,
)


def test_idata_source_read_file_signature_has_strict_io_default_false():
    sig = inspect.signature(IDataSource.read_file)
    assert "strict_io" in sig.parameters
    strict_io = sig.parameters["strict_io"]
    assert strict_io.default is False


def test_idata_source_read_file_type_hints_are_stable():
    hints = inspect.get_annotations(IDataSource.read_file)
    assert "file_path" in hints
    assert hints["file_path"] is Path
    assert "strict_io" in hints
    assert hints["strict_io"] is bool


def test_idata_source_get_available_dates_signature_supports_remote_metadata_hints():
    sig = inspect.signature(IDataSource.get_available_dates)
    assert "file_path" in sig.parameters
    assert "remote_mtime" in sig.parameters
    assert sig.parameters["remote_mtime"].default is None
    assert "remote_size" in sig.parameters
    assert sig.parameters["remote_size"].default is None


def test_ipersistence_has_expected_core_methods():
    methods = {
        "init_db",
        "save_session",
        "save_file_metadata",
        "save_staging_data",
        "save_template_error",
        "get_template_errors",
        "get_session_status",
        "get_consolidated_data",
        "close",
    }
    assert methods.issubset(set(dir(IPersistence)))


def test_ivalidator_contract_methods_exist():
    assert hasattr(IValidator, "validate_row")
    assert hasattr(IValidator, "get_errors")


def test_ilogic_service_contract_methods_exist():
    assert hasattr(ILogicService, "apply_financial_rules")
    assert hasattr(ILogicService, "consolidate")


def test_iexporter_contract_method_exists():
    assert hasattr(IExporter, "write_report")
