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


def test_percent_broker_small_fraction_normalized_to_positive(logic_service):
    raw_rows = [{"amount": "100", "percent_broker": Decimal("-0.002")}]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]["% посредника"] == Decimal("0.002")


def test_percent_broker_negative_is_normalized_to_positive(logic_service):
    raw_rows = [{"amount": "100", "percent_broker": "-1.5"}]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]["% посредника"] == Decimal("1.5")


def test_commission_negative_percent_is_normalized_to_positive(logic_service):
    raw_rows = [{"amount": "1000", "total": "1000", "commission": "-0.05"}]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]["комиссия"] == Decimal("5")


def test_commission_negative_fixed_value_is_normalized_to_positive(logic_service):
    raw_rows = [{"amount": "1000", "total": "1000", "commission": "-50"}]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]["комиссия"] == Decimal("50")


def test_commission_small_fraction_is_scaled_by_100(logic_service):
    raw_rows = [{"amount": "1000", "total": "1000", "commission": "0.24"}]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]["комиссия"] == Decimal("24")


def test_percent_broker_small_fraction_is_not_scaled(logic_service):
    raw_rows = [{"amount": "1000", "total": "1000", "percent_broker": "0.24"}]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]["% посредника"] == Decimal("0.24")


def test_broker_cash_negative_is_normalized_to_positive(logic_service):
    raw_rows = [{"amount": "100", "total": "100", "broker1": "-10609.09"}]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]["посредник 1(кэш)"] == Decimal("10609.09")


def test_template_warning_logging(logic_service):
    raw_rows = [
        {"amount": "100", "is_template_warning": True, "_source_info": "Warning source"}
    ]
    with patch("core.domain.logic_service.logger") as mock_logger:
        res = logic_service.apply_financial_rules(raw_rows)
        assert res[0]["is_template_warning"] is True
        mock_logger.warning.assert_called_once()


def test_template_warning_logging_is_aggregated(logic_service):
    raw_rows = [
        {"amount": "100", "is_template_warning": True, "_source_info": "Warning source 1"},
        {"amount": "200", "is_template_warning": True, "_source_info": "Warning source 2"},
    ]
    with patch("core.domain.logic_service.logger") as mock_logger:
        res = logic_service.apply_financial_rules(raw_rows)
        assert [row["is_template_warning"] for row in res] == [True, True]
        mock_logger.warning.assert_called_once()
        assert mock_logger.warning.call_args.args[1] == 2


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
    assert res[0]["посредник 1(кэш)"] == Decimal("10609.09")
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


def test_boris_does_not_autofill_intermediary2_rate(logic_service):
    raw_rows = [
        {
            "customer": "СИБ Сбер",
            "contractor": "СТИ, Альфа",
            "amount": "0",
            "total": "-31237.17",
            "commission": "24",
            "percent_broker": "-4",
            "broker1": "2178.01",
            "broker2": "0",
            "filters": "ЗП",
        }
    ]

    res = logic_service.apply_financial_rules(
        raw_rows,
        curator="boris",
        curator_config={"intermediary2_rate": 0.05},
    )

    assert res[0]["% посредник 2"] == Decimal("0.00")
    assert res[0]["Посредник 2 (сумма)"] == Decimal("0.00")
    assert res[0]["посредник 2"] == Decimal("0.00")


def test_boris_keeps_explicit_intermediary2_value(logic_service):
    raw_rows = [
        {
            "customer": "СИБ Сбер",
            "contractor": "СТИ, Альфа",
            "amount": "0",
            "total": "-31237.17",
            "commission": "24",
            "percent_broker": "-4",
            "broker1": "2178.01",
            "percent_broker2": "0.02",
            "broker2": "624.74",
            "filters": "ЗП",
        }
    ]

    res = logic_service.apply_financial_rules(
        raw_rows,
        curator="boris",
        curator_config={"intermediary2_rate": 0.05},
    )

    assert res[0]["% посредник 2"] == Decimal("0.02")
    assert res[0]["Посредник 2 (сумма)"] == Decimal("624.74")
    assert res[0]["посредник 2"] == Decimal("624.74")


def test_boris_intermediary2_rate_keeps_source_precision(logic_service):
    raw_rows = [
        {
            "customer": "СИБ Сбер",
            "contractor": "СТИ, Альфа",
            "amount": "0",
            "total": "-31237.17",
            "commission": "24",
            "percent_broker": Decimal("-0.04"),
            "broker1": "2178.01",
            "percent_broker2": Decimal("-0.015"),
            "broker2": "624.74",
            "filters": "ЗП",
        }
    ]

    res = logic_service.apply_financial_rules(
        raw_rows,
        curator="boris",
        curator_config={"intermediary2_rate": 0.05},
    )

    assert res[0]["% посредник 2"] == Decimal("0.015")
    assert res[0]["Посредник 2 (сумма)"] == Decimal("624.74")


def test_transit_only_row_is_not_dropped_for_ivan_layout(logic_service):
    raw_rows = [
        {
            "customer": "Бекхем",
            "contractor": "Доха Катар",
            "amount": "0",
            "total": "0",
            "transit_obligation": "335936.0",
            "exchange_rate": "23.2",
            "currency_amount": "14480",
            "currency": "риал",
            "filters": "транзит",
            "_source_info": "ivan.xlsx | 13.04.2026 | Row 3",
            "is_template_warning": True,
        }
    ]

    res = logic_service.apply_financial_rules(raw_rows, curator="ivan", curator_config={})

    assert len(res) == 1
    assert res[0]["ЗАКАЗЧИК (название проекта, наименование ЮЛ)"] == "Бекхем"
    assert res[0]["сумма платежа ПРИХОД"] == Decimal("0.00")
    assert res[0]["сумма платежа РАСХОД"] == Decimal("0.00")
    assert res[0]["ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ"] == Decimal("335936.0")
    assert res[0]["курс"] == Decimal("23.2")
    assert res[0]["сумма"] == Decimal("14480")
    assert res[0]["валюта"] == "риал"


def test_invalid_transit_amount_becomes_critical_row(logic_service):
    raw_rows = [
        {
            "customer": "Бекхем",
            "contractor": "Доха Катар",
            "amount": "0",
            "total": "0",
            "transit_obligation": "not-a-number",
            "exchange_rate": "23.2",
            "currency_amount": "14480",
            "currency": "риал",
            "_source_info": "ivan.xlsx | 13.04.2026 | Row 4",
        }
    ]

    res = logic_service.apply_financial_rules(raw_rows, curator="ivan", curator_config={})

    assert len(res) == 1
    assert res[0]["is_critical"] is True
    assert res[0]["Источник"] == "ivan.xlsx | 13.04.2026 | Row 4"


def test_invalid_fx_amount_does_not_abort_following_rows(logic_service):
    raw_rows = [
        {
            "customer": "Бекхем",
            "contractor": "Доха Катар",
            "amount": "100",
            "total": "100",
            "currency_amount": "#REF!",
            "_source_info": "ivan.xlsx | 13.04.2026 | Row 5",
        },
        {
            "customer": "Нормальный заказчик",
            "contractor": "Нормальный исполнитель",
            "amount": "200",
            "total": "200",
            "_source_info": "ivan.xlsx | 13.04.2026 | Row 6",
        },
    ]

    res = logic_service.apply_financial_rules(raw_rows, curator="ivan", curator_config={})

    assert len(res) == 2
    assert res[0]["is_critical"] is True
    assert res[0]["Источник"] == "ivan.xlsx | 13.04.2026 | Row 5"
    assert res[1]["is_critical"] is False
    assert res[1]["сумма платежа ПРИХОД"] == Decimal("200.00")
