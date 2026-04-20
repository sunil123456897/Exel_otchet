import pytest
from decimal import Decimal
from hypothesis import given, strategies as st
from core.domain.logic_service import LogicService

# Strategy for financial amounts
# We use decimals with 2 decimal places
financial_amount = st.decimals(min_value=-10**9, max_value=10**9, places=2)

@given(
    amount=financial_amount,
    total=financial_amount,
    filters=st.text(),
    commission=st.decimals(min_value=-1000, max_value=1000, places=2)
)
def test_apply_financial_rules_properties(amount, total, filters, commission):
    config = {
        'logic': {
            'income_overrides': ['доп', 'доп сф', '% посред'],
            'return_keywords': ['возврат']
        }
    }
    logic_service = LogicService(None, config)
    
    raw_rows = [{
        'date': '01.01.2026',
        'amount': str(amount),
        'total': str(total),
        'customer': 'Test Client',
        'contractor': 'Test Bank',
        'filters': filters,
        'commission': str(commission),
        'percent_broker': '0',
        'broker1': '0',
        'broker2': '0'
    }]
    
    res = logic_service.apply_financial_rules(raw_rows)
    
    # If amount and total are 0 and no 'доп' in filters, it might be skipped
    is_add = any(kw in filters.lower() for kw in logic_service.inc_over)
    if amount == 0 and total == 0 and not is_add:
        assert len(res) == 0
        return

    assert len(res) == 1
    row = res[0]
    
    inc = row['сумма платежа ПРИХОД']
    exp = row['сумма платежа РАСХОД']
    
    # Invariants
    # 1. Either inc or exp should be non-zero (unless amount is 0 and it's an 'add' case)
    # Actually, if amount is 0 and is_add is true, both can be 0.
    
    # 2. Return logic: if 'возврат' in filters, exp should be -abs(amount)
    is_ret = any(kw in filters.lower() for kw in logic_service.ret_kw)
    if is_ret:
        assert inc == 0
        assert exp == -abs(amount)
    elif is_add:
        assert inc == amount
        assert exp == 0
    elif amount < 0:
        assert inc == 0
        assert exp == abs(amount)
    else:
        assert inc == amount
        assert exp == 0

    # 3. Commission logic
    # comm = (c_raw * 100 if c_raw != 0 and abs(c_raw) <= 1 else c_raw).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    # We can't easily re-calculate exactly without duplicating logic, but we can check it's a Decimal
    assert isinstance(row['комиссия'], Decimal)
    assert row['комиссия'] >= 0
    c_abs = abs(commission)
    expected_comm = c_abs * Decimal('100') if c_abs != 0 and c_abs <= 1 else c_abs
    assert row['комиссия'] == expected_comm.quantize(Decimal('0.01'))
    if isinstance(row['% посредника'], Decimal):
        assert row['% посредника'] >= 0
