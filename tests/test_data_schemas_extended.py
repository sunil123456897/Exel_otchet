from decimal import Decimal

from core.domain.data_schemas import FinancialRowSchema


def test_financial_row_schema_invalid_date_is_kept_as_string():
    row = FinancialRowSchema(date="31.02.2026", amount="1")
    assert row.date == "31.02.2026"


def test_financial_row_schema_empty_numeric_defaults_to_zero():
    row = FinancialRowSchema(amount="", income=None, expense="")
    assert row.amount == Decimal("0.00")
    assert row.income == Decimal("0.00")
    assert row.expense == Decimal("0.00")


def test_financial_row_schema_decimal_passthrough():
    row = FinancialRowSchema(amount=Decimal("10.25"), commission=Decimal("1.50"))
    assert row.amount == Decimal("10.25")
    assert row.commission == Decimal("1.50")


def test_financial_row_schema_strips_spaces_and_commas_for_numbers():
    row = FinancialRowSchema(amount=" 1 234,56 ", total="2 000,00")
    assert row.amount == Decimal("1234.56")
    assert row.total == Decimal("2000.00")


def test_financial_row_schema_non_numeric_percent_is_preserved():
    row = FinancialRowSchema(percent_broker="high", percent_broker2="n/a")
    assert row.percent_broker == "high"
    assert row.percent_broker2 == "n/a"


def test_financial_row_schema_reduces_multiple_dots_and_minus_signs():
    row = FinancialRowSchema(amount="--1.2.3")
    assert row.amount == Decimal("-1.23")


def test_financial_row_schema_allows_extra_metadata_fields():
    row = FinancialRowSchema(amount="5", custom_note="ok", source_tag="import")
    dumped = row.model_dump()
    assert dumped["custom_note"] == "ok"
    assert dumped["source_tag"] == "import"


def test_financial_row_schema_empty_garbage_returns_zero():
    row = FinancialRowSchema(percent_broker="---")
    assert row.percent_broker == "---"
