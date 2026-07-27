from decimal import Decimal

import pytest
from core.domain.data_schemas import FinancialRowSchema
from core.infra.ingestion_reader import CalamineReader


def test_xlsx_signature_validation_invalid_file(tmp_path):
    # Create a non-ZIP file (text file)
    bad_file = tmp_path / "fake_excel.xlsx"
    bad_file.write_text("This is not a zip file or xlsx file.")

    reader = CalamineReader(markers={"amount": "сумма"}, aliases={})
    # This should return an empty list because the signature validation fails
    rows = reader.read(bad_file, strict_io=False)
    assert rows == []

    # Under strict_io=True, it should raise ValueError
    with pytest.raises(ValueError, match="Invalid file signature"):
        reader.read(bad_file, strict_io=True)


def test_pydantic_schema_validation():
    # Valid row dictionary
    valid_data = {
        "customer": "Test Customer",
        "amount": "123.45",
        "total": "123.45",
        "percent_broker": "0.05",
    }
    row = FinancialRowSchema(**valid_data)
    assert row.customer == "Test Customer"
    assert row.amount == Decimal("123.45")
    assert row.percent_broker == Decimal("0.05")

    # Empty string conversion check
    empty_data = {
        "amount": "",
        "total": None,
    }
    row_empty = FinancialRowSchema(**empty_data)
    assert row_empty.amount == Decimal("0.00")
    assert row_empty.total == Decimal("0.00")
