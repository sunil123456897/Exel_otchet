import pytest
from decimal import Decimal
from core.logic_service import LogicService, Validator

@pytest.fixture
def logic_service():
    config = {
        'logic': {
            'income_overrides': ['доп', 'доп сф', '% посред'],
            'return_keywords': ['возврат']
        }
    }
    return LogicService(None, config)

def test_apply_financial_rules_standard_income(logic_service):
    raw_rows = [{
        'date': '01.01.2026',
        'amount': '100.00',
        'total': '100.00',
        'customer': 'Client A',
        'contractor': 'Bank X',
        'filters': 'some filter'
    }]
    res = logic_service.apply_financial_rules(raw_rows)
    assert len(res) == 1
    assert res[0]['сумма платежа ПРИХОД'] == Decimal('100.00')
    assert res[0]['сумма платежа РАСХОД'] == Decimal('0.00')

def test_apply_financial_rules_standard_expense(logic_service):
    raw_rows = [{
        'date': '01.01.2026',
        'amount': '-50.00',
        'total': '-50.00',
        'customer': 'Client A',
        'contractor': 'Bank X',
        'filters': 'some filter'
    }]
    res = logic_service.apply_financial_rules(raw_rows)
    assert len(res) == 1
    assert res[0]['сумма платежа ПРИХОД'] == Decimal('0.00')
    assert res[0]['сумма платежа РАСХОД'] == Decimal('50.00') # abs(amt) for amt < 0

def test_apply_financial_rules_return_logic(logic_service):
    # 'возврат' logic: goes to EXPENSE as NEGATIVE
    raw_rows = [{
        'date': '01.01.2026',
        'amount': '30.00',
        'total': '30.00',
        'customer': 'Client A',
        'contractor': 'Bank X',
        'filters': 'возврат средств'
    }]
    res = logic_service.apply_financial_rules(raw_rows)
    assert len(res) == 1
    assert res[0]['сумма платежа ПРИХОД'] == Decimal('0.00')
    assert res[0]['сумма платежа РАСХОД'] == Decimal('-30.00')

def test_apply_financial_rules_income_override(logic_service):
    # 'доп' logic: goes to INCOME
    raw_rows = [{
        'date': '01.01.2026',
        'amount': '20.00',
        'total': '20.00',
        'customer': 'Client A',
        'contractor': 'Bank X',
        'filters': 'доп оплата'
    }]
    res = logic_service.apply_financial_rules(raw_rows)
    assert len(res) == 1
    assert res[0]['сумма платежа ПРИХОД'] == Decimal('20.00')
    assert res[0]['сумма платежа РАСХОД'] == Decimal('0.00')

def test_apply_financial_rules_commission_calculation(logic_service):
    raw_rows = [{
        'date': '01.01.2026',
        'amount': '1000.00',
        'commission': '0.05', # 5%
        'total': '950.00',
        'filters': ''
    }]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]['комиссия'] == Decimal('5.00') # 0.05 * 100 = 5.00

    raw_rows = [{
        'date': '01.01.2026',
        'amount': '1000.00',
        'commission': '50.00', # Fixed amount
        'total': '950.00',
        'filters': ''
    }]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]['комиссия'] == Decimal('50.00')

def test_validator_junk_rows():
    v = Validator({})
    # Junk total row
    assert v.validate_row({'customer': 'ИТОГО', 'amount': '1000'}) == False
    # Junk markers
    assert v.validate_row({'customer': 'заказчик', 'contractor': 'исполнитель'}) == False
    # Empty row
    assert v.validate_row({'customer': '', 'contractor': '', 'amount': '0'}) == False
    # Valid row
    assert v.validate_row({'customer': 'Real Client', 'amount': '1000'}) == True
