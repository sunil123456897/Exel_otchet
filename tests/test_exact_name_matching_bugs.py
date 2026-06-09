import pytest
from decimal import Decimal
from core.domain.logic_service import Validator, LogicService

@pytest.fixture
def validator():
    return Validator({})

@pytest.fixture
def logic_service():
    return LogicService(persistence=None, config={})

def test_bug_whitespace(validator):
    """
    Test A (Whitespace): Exact name matching should strip whitespace before comparing to 'итого'
    """
    assert not validator.validate_row({"customer": "Итого\n", "amount": "100"})

def test_bug_markers(validator):
    """
    Test B (Markers): Exact name matching should not reject valid companies that contain 'приход' or 'расход'
    """
    assert validator.validate_row({"customer": "ООО Приходько", "contractor": "ИП Расходов", "amount": "100"})

def test_bug_zero_formats(validator):
    """
    Test C (Zero Formats): A row containing only empty strings and '0.00' is effectively empty.
    """
    assert not validator.validate_row({"customer": "", "contractor": "", "filters": "", "amount": "0.00"})

def test_bug_filters(logic_service):
    """
    Test D (Filters): If a rule matches 'недопустимый' (contains 'доп' but not an exclude keyword),
    it should NOT trigger the 'доп' income override rule.
    """
    res = logic_service.apply_financial_rules([{"filters": "недопустимый", "amount": "-100", "total": "0"}])
    assert len(res) > 0
    assert res[0]["сумма платежа ПРИХОД"] == Decimal("0.00")
    assert res[0]["сумма платежа РАСХОД"] == Decimal("100.00")

def test_bug_headers(validator):
    """
    Test E (Headers): A cell containing 'комиссия' in parentheses should not trigger header rejection.
    """
    assert validator.validate_row({"customer": "A", "contractor": "B", "amount": "100", "commission": "100.00 (комиссия)"})
