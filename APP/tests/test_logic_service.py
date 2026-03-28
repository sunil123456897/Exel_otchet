import pytest
from decimal import Decimal
from unittest.mock import MagicMock
from APP.src.logic_service import Validator, LogicService
from APP.src.interfaces import IPersistence

@pytest.fixture
def config():
    return {
        'logic': {
            'income_overrides': ['доп', 'доп сф', '% посред'],
            'return_keywords': ['возврат']
        },
        'sh1': {
            'markers': {
                'amount': 'сумма платежа',
                'customer': 'Заказчик',
                'contractor': 'Исполнитель'
            }
        }
    }

@pytest.fixture
def validator(config):
    return Validator(config)

@pytest.fixture
def mock_persistence():
    return MagicMock(spec=IPersistence)

@pytest.fixture
def logic_service(mock_persistence, config):
    return LogicService(mock_persistence, config)

class TestValidator:
    def test_validate_empty_row(self, validator):
        row = {'customer': '', 'contractor': '  ', 'filters': '', 'amount': 0}
        assert validator.validate_row(row) is False

    def test_validate_header_row(self, validator):
        # Marker count >= 2
        row = {'col1': 'Заказчик', 'col2': 'Исполнитель', 'col3': 'something'}
        assert validator.validate_row(row) is False

    def test_validate_total_row(self, validator):
        row = {'customer': 'Итого:', 'amount': 1000}
        assert validator.validate_row(row) is False
        
        row2 = {'some_col': 'всего'}
        assert validator.validate_row(row2) is False

    def test_validate_valid_row(self, validator):
        row = {
            'customer': 'Client A',
            'contractor': 'Bank B',
            'filters': 'some filters',
            'amount': 1000.50
        }
        assert validator.validate_row(row) is True

    def test_validate_numeric_header_leak(self, validator):
        # If a numeric column contains a header word
        row = {'amount': 'сумма платежа', 'customer': 'Client A'}
        assert validator.validate_row(row) is False

class TestLogicService:
    def test_to_decimal_conversions(self, logic_service):
        assert logic_service._to_decimal(100.5) == Decimal('100.50')
        assert logic_service._to_decimal("1,234.56") == Decimal('1234.56')
        assert logic_service._to_decimal("1.234,56") == Decimal('1234.56')
        assert logic_service._to_decimal("(100.00)") == Decimal('-100.00')
        assert logic_service._to_decimal("  -50.2  ") == Decimal('-50.20')
        assert logic_service._to_decimal(None) == Decimal('0.00')
        assert logic_service._to_decimal("invalid") == Decimal('0.00')

    def test_to_decimal_percent(self, logic_service):
        assert logic_service._to_decimal_percent("0.1") == Decimal('0.1')
        assert logic_service._to_decimal_percent("10%") == Decimal('0.1')
        assert logic_service._to_decimal_percent(0.05) == Decimal('0.05')

    def test_apply_financial_rules_income_expense(self, logic_service):
        raw_rows = [
            {'amount': 1000, 'customer': 'A', 'employee_name': 'Emp1'}, # Normal income
            {'amount': -200, 'customer': 'B', 'employee_name': 'Emp1'}, # Normal expense
            {'amount': 300, 'filters': 'возврат', 'customer': 'C'},      # Return (expense)
            {'amount': -300, 'filters': 'возврат', 'customer': 'C2'},     # Return with negative amount (expense)
            {'amount': 150, 'filters': 'доп доход', 'customer': 'D'},   # Additional income
            {'amount': -50, 'filters': 'доп доход', 'customer': 'E'},    # Additional income with negative amount
        ]
        
        results = logic_service.apply_financial_rules(raw_rows)
        
        assert len(results) == 6
        # Row 0: Income
        assert results[0]['сумма платежа ПРИХОД'] == Decimal('1000.00')
        assert results[0]['сумма платежа РАСХОД'] == Decimal('0.00')
        
        # Row 1: Expense (negative amount)
        assert results[1]['сумма платежа ПРИХОД'] == Decimal('0.00')
        assert results[1]['сумма платежа РАСХОД'] == Decimal('200.00')
        
        # Row 2: Return (expense)
        assert results[2]['сумма платежа ПРИХОД'] == Decimal('0.00')
        assert results[2]['сумма платежа РАСХОД'] == Decimal('300.00')

        # Row 3: Return with negative amount (expense)
        assert results[3]['сумма платежа ПРИХОД'] == Decimal('0.00')
        assert results[3]['сумма платежа РАСХОД'] == Decimal('300.00')
        
        # Row 4: Additional income
        assert results[4]['сумма платежа ПРИХОД'] == Decimal('150.00')
        assert results[4]['сумма платежа РАСХОД'] == Decimal('0.00')

        # Row 5: Additional income with negative amount (stays negative income per current logic)
        assert results[5]['сумма платежа ПРИХОД'] == Decimal('-50.00')
        assert results[5]['сумма платежа РАСХОД'] == Decimal('0.00')

    def test_apply_financial_rules_commissions(self, logic_service):
        raw_rows = [
            {'amount': 1000, 'commission': '0.1', 'percent_broker': 0.02},
            {'amount': 500, 'commission': '15%', 'broker1': '50'},
        ]
        
        results = logic_service.apply_financial_rules(raw_rows)
        
        # 0.1 -> 10.00%
        assert results[0]['комиссия'] == Decimal('10.00')
        assert results[0]['% посредника'] == Decimal('0.02')
        
        # 15% -> 15.00%
        assert results[1]['комиссия'] == Decimal('15.00')
        assert results[1]['посредник 1(кэш)'] == Decimal('50.00')

    def test_consolidate_calls_persistence(self, logic_service, mock_persistence):
        session_id = "test_session"
        mock_data = [
            {'amount': 100, 'customer': 'Client X', 'employee_name': 'John'}
        ]
        mock_persistence.get_consolidated_data.return_value = mock_data
        
        result = logic_service.consolidate(session_id)
        
        mock_persistence.get_consolidated_data.assert_called_once_with(session_id)
        assert len(result) == 1
        assert result[0]['сумма платежа ПРИХОД'] == Decimal('100.00')

    def test_sanitize_formula_injection(self, logic_service):
        raw_rows = [
            {'amount': 100, 'customer': '=SUM(A1:A10)', 'filters': '+special'}
        ]
        results = logic_service.apply_financial_rules(raw_rows)
        
        assert results[0]['ЗАКАЗЧИК (название проекта, наименование ЮЛ)'].startswith("'")
        assert results[0]['фильтры'].startswith("'")
