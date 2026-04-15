import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch
from core.domain.logic_service import LogicService, Validator
from core.domain.utils_helpers import NumericParsingError


@pytest.fixture
def logic_service():
    config = {
        "logic": {
            "income_overrides": ["доп", "доп сф", "% посред"],
            "return_keywords": ["возврат"],
        }
    }
    # No persistence needed for direct apply_financial_rules testing
    return LogicService(None, config)


def test_financial_routing_is_add(logic_service):
    """Cover is_add (keywords like 'доп'): goes to INCOME"""
    raw_rows = [{"amount": "150.00", "filters": "оплата доп сф"}]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]["сумма платежа ПРИХОД"] == Decimal("150.00")
    assert res[0]["сумма платежа РАСХОД"] == Decimal("0.00")


def test_financial_routing_is_ret(logic_service):
    """Cover is_ret (keywords like 'возврат'): goes to EXPENSE as NEGATIVE"""
    # Case: positive amount with 'возврат'
    raw_rows = [{"amount": "100.00", "filters": "возврат средств"}]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]["сумма платежа ПРИХОД"] == Decimal("0.00")
    assert res[0]["сумма платежа РАСХОД"] == Decimal("-100.00")

    # Case: negative amount with 'возврат'
    raw_rows = [{"amount": "-50.00", "filters": "возврат"}]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]["сумма платежа ПРИХОД"] == Decimal("0.00")
    assert res[0]["сумма платежа РАСХОД"] == Decimal("-50.00")


def test_financial_routing_negative_amt_no_keywords(logic_service):
    """Cover amt < 0 (standard expense): goes to EXPENSE as POSITIVE"""
    raw_rows = [{"amount": "-200.00", "filters": "some payment"}]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]["сумма платежа ПРИХОД"] == Decimal("0.00")
    assert res[0]["сумма платежа РАСХОД"] == Decimal("200.00")


def test_malformed_number_handling(logic_service):
    """Cover error handling for malformed numbers (NumericParsingError)"""
    # to_decimal raises NumericParsingError for things like 'nan' or empty-after-clean
    raw_rows = [{"amount": "nan", "_source_info": "TestFile.xlsx | Sheet1 | Row 5"}]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]["сумма платежа ПРИХОД"] == Decimal("0.00")
    assert res[0]["is_critical"] is True

    # Case: Amount is trash that cleans to empty
    raw_rows = [{"amount": "???", "_source_info": "TestFile.xlsx | Sheet1 | Row 6"}]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]["is_critical"] is True


def test_total_parsing_error(logic_service):
    """Cover error handling for malformed total"""
    raw_rows = [
        {
            "amount": "100.00",
            "total": "invalid",
            "_source_info": "TestFile.xlsx | Sheet1 | Row 7",
        }
    ]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]["ИТОГ"] == Decimal("0.00")
    assert res[0]["is_critical"] is True


def test_validator_comprehensive():
    """Increase coverage for Validator logic"""
    v = Validator({})

    # Empty-ish row
    assert v.validate_row({"amount": "0", "customer": "  "}) == False

    # Row with junk markers in values
    assert v.validate_row({"col1": "заказчик", "col2": "исполнитель"}) == False

    # Row with header words in financial columns
    assert v.validate_row({"amount": "Сумма платежа"}) == False
    assert v.validate_row({"commission": "Комиссия"}) == False

    # Valid row
    assert v.validate_row({"customer": "Client", "amount": "123.45"}) == True


def test_validator_rejects_day_total_variants():
    v = Validator({})
    assert v.validate_row({"customer": "Итоги дня", "amount": "1000"}) is False
    assert v.validate_row({"customer": "Итог дня", "amount": "1000"}) is False


def test_validator_rejects_numeric_subtotal_without_parties():
    v = Validator({})
    assert (
        v.validate_row(
            {
                "customer": "",
                "contractor": "",
                "filters": "",
                "amount": "1000",
                "total": "1000",
            }
        )
        is False
    )


def test_logic_service_sanitize():
    ls = LogicService(None, {})
    assert ls._sanitize("=SUM(A1:A10)") == "'=SUM(A1:A10)"
    assert ls._sanitize("+7900") == "'+7900"
    assert ls._sanitize("-100") == "'-100"
    assert ls._sanitize("@handle") == "'@handle"
    assert ls._sanitize("Normal") == "Normal"


def test_logic_service_consolidate():
    mock_persistence = MagicMock()
    mock_persistence.get_consolidated_data.return_value = [
        {"amount": "100", "customer": "A"}
    ]
    ls = LogicService(mock_persistence, {})
    res = ls.consolidate("session_123")
    assert len(res) == 1
    assert res[0]["сумма платежа ПРИХОД"] == Decimal("100.00")
    mock_persistence.get_consolidated_data.assert_called_with("session_123")


def test_apply_financial_rules_skipping(logic_service):
    # amt == 0 and tot == 0 and not is_add and not is_critical: continue
    raw_rows = [
        {"amount": "0", "total": "0", "filters": "none"},  # skip
        {"amount": "1", "total": "0", "filters": "none"},  # keep
        {"amount": "0", "total": "1", "filters": "none"},  # keep
        {"amount": "0", "total": "0", "filters": "доп"},  # keep (is_add)
    ]
    res = logic_service.apply_financial_rules(raw_rows)
    assert len(res) == 3


def test_percent_broker_parsing_error(logic_service):
    # pb_val = to_decimal(pb_raw) except ValueError: pb_val = pb_raw
    raw_rows = [{"amount": "100", "percent_broker": "NotANumber"}]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]["% посредника"] == "NotANumber"


def test_template_warning_logging(logic_service):
    raw_rows = [
        {"amount": "100", "is_template_warning": True, "_source_info": "Warning source"}
    ]
    with patch("core.domain.logic_service.logger") as mock_logger:
        res = logic_service.apply_financial_rules(raw_rows)
        assert res[0]["is_template_warning"] is True
        mock_logger.warning.assert_called()


def test_invalid_commission_becomes_template_warning_not_silent_zero(logic_service):
    raw_rows = [
        {
            "amount": "100",
            "total": "100",
            "commission": "not-a-number",
            "_source_info": "Warning source",
        }
    ]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]["комиссия"] == Decimal("0.00")
    assert res[0]["is_template_warning"] is True


def test_template_warning_does_not_leak_to_following_rows(logic_service):
    raw_rows = [
        {
            "amount": "100",
            "total": "100",
            "commission": "not-a-number",
            "_source_info": "Warning source",
        },
        {
            "amount": "200",
            "total": "200",
            "commission": "0",
            "_source_info": "Clean source",
        },
    ]

    res = logic_service.apply_financial_rules(raw_rows)

    assert res[0]["is_template_warning"] is True
    assert res[1]["is_template_warning"] is False


def test_broker_only_row_is_not_dropped(logic_service):
    raw_rows = [
        {
            "customer": "Broker-only adjustment",
            "amount": "0",
            "total": "0",
            "broker1": "-10609.09",
            "filters": "посредник",
            "_source_info": "broker-only source",
        }
    ]

    res = logic_service.apply_financial_rules(raw_rows)

    assert len(res) == 1
    assert res[0]["сумма платежа ПРИХОД"] == Decimal("0.00")
    assert res[0]["сумма платежа РАСХОД"] == Decimal("0.00")
    assert res[0]["посредник 1(кэш)"] == Decimal("-10609.09")
    assert res[0]["ИТОГ"] == Decimal("0.00")


def test_broker_only_row_with_broker2_is_not_dropped(logic_service):
    raw_rows = [
        {
            "customer": "Broker2-only adjustment",
            "amount": "0",
            "total": "0",
            "broker2": "500.50",
            "filters": "посредник",
            "_source_info": "broker2-only source",
        }
    ]

    res = logic_service.apply_financial_rules(raw_rows)

    assert len(res) == 1
    assert res[0]["сумма платежа ПРИХОД"] == Decimal("0.00")
    assert res[0]["сумма платежа РАСХОД"] == Decimal("0.00")
    assert res[0]["посредник 2"] == Decimal("500.50")
    assert res[0]["ИТОГ"] == Decimal("0.00")
