from decimal import Decimal

import pytest
from core.domain.logic_service import BorisCuratorStrategy, LogicService


@pytest.fixture
def logic_service():
    config = {"logic": {"commission_is_percent": True}}
    return LogicService(persistence=None, config=config)

def process_single_row(logic_service, row_data, curator=None, curator_config=None):
    if "amount" not in row_data:
        row_data["amount"] = 0
    rows = logic_service.apply_financial_rules([row_data], curator=curator, curator_config=curator_config)
    assert len(rows) == 1, "Row was unexpectedly filtered out"
    return rows[0]

def test_bug2_boris_curator_invalid_text():
    """
    2. Uncaught `decimal.InvalidOperation` or `ValueError` in `BorisCuratorStrategy.apply` 
    when `percent_broker2` is invalid text (e.g., "invalid"). It should handle gracefully but crashes.
    """
    strategy = BorisCuratorStrategy()
    strategy.apply({}, Decimal("0.05"), Decimal("100"), Decimal("100"), Decimal("50"), "invalid")
