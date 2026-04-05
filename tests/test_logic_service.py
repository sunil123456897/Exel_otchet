import pytest
from decimal import Decimal
from core.domain.logic_service import LogicService, Validator

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

def test_apply_financial_rules_percent_broker_preservation(logic_service):
    # Requirement: percent_broker > 1.0 (проверка презервации исходного значения)
    raw_rows = [{
        'date': '01.01.2026',
        'amount': '1000.00',
        'percent_broker': '1.5', # > 1.0
        'customer': 'Client A',
        'filters': ''
    }]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]['% посредника'] == Decimal('1.50')
    
    raw_rows = [{
        'date': '01.01.2026',
        'amount': '1000.00',
        'percent_broker': '0.05', # <= 1.0
        'customer': 'Client A',
        'filters': ''
    }]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]['% посредника'] == Decimal('0.05')

def test_apply_financial_rules_rounding_half_up(logic_service):
    # Requirement: ROUND_HALF_UP (банковское округление? In prompt it says ROUND_HALF_UP but calls it banking rounding)
    # Standard ROUND_HALF_UP: 0.005 -> 0.01
    raw_rows = [{
        'date': '01.01.2026',
        'amount': '1000.00',
        'commission': '0.005', # 0.005 * 100 = 0.5 (abs <= 1), wait 
        # Logic: (c_raw * 100 if c_raw != 0 and abs(c_raw) <= 1 else c_raw).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        'customer': 'Client A',
        'filters': ''
    }]
    # Case 1: Commission is 0.00005 (percent)
    raw_rows[0]['commission'] = '0.00005' # 0.00005 * 100 = 0.005 -> 0.01
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]['комиссия'] == Decimal('0.01')

    # Case 2: Commission is 0.00004 (percent)
    raw_rows[0]['commission'] = '0.00004' # 0.00004 * 100 = 0.004 -> 0.00
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]['комиссия'] == Decimal('0.00')

    # Case 3: Commission is 1.005 (fixed amount)
    raw_rows[0]['commission'] = '1.005' # 1.005 -> 1.01
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]['комиссия'] == Decimal('1.01')

    # Case 4: Commission is 1.004 (fixed amount)
    raw_rows[0]['commission'] = '1.004' # 1.004 -> 1.00
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]['комиссия'] == Decimal('1.00')

def test_apply_financial_rules_routing_advanced(logic_service):
    # Requirement: Маршрутизация ПРИХОД/РАСХОД (по ключевым словам: "доп", "возврат")
    # 'доп' -> ПРИХОД
    raw_rows = [{
        'amount': '100.00',
        'filters': 'доп сф'
    }]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]['сумма платежа ПРИХОД'] == Decimal('100.00')
    assert res[0]['сумма платежа РАСХОД'] == Decimal('0.00')
    
    # 'возврат' -> РАСХОД (negative)
    raw_rows = [{
        'amount': '50.00',
        'filters': 'частичный возврат'
    }]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]['сумма платежа ПРИХОД'] == Decimal('0.00')
    assert res[0]['сумма платежа РАСХОД'] == Decimal('-50.00')

    # 'возврат' with negative amount -> РАСХОД (negative -abs)
    raw_rows = [{
        'amount': '-50.00',
        'filters': 'возврат'
    }]
    res = logic_service.apply_financial_rules(raw_rows)
    assert res[0]['сумма платежа ПРИХОД'] == Decimal('0.00')
    assert res[0]['сумма платежа РАСХОД'] == Decimal('-50.00')

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
