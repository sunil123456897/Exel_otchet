import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

import pytest
import pandas as pd
from unittest.mock import MagicMock

@pytest.fixture
def mock_config_dict():
    """Returns a basic valid configuration dictionary."""
    return {
        'paths': {
            'source_root': './data/reports',
            'master_file': './data/Master_Report.xlsx'
        },
        'sh1': {
            'markers': {
                'customer': 'ЗАКАЗЧИК',
                'contractor': 'ИСПОЛНИТЕЛЬ',
                'amount': 'сумма платежа',
                'total': 'ИТОГ',
                'commission': 'комиссия',
                'percent_broker': '% посредника',
                'broker1': 'посредник 1',
                'broker2': 'посредник 2',
                'filters': 'фильтры'
            }
        },
        'sh2': {},
        'logic': {
            'income_overrides': ['доп', 'доп сф', '% посред'],
            'return_keywords': ['возврат']
        },
        'employees': ['EmpA', 'EmpB']
    }

@pytest.fixture
def mock_col_map():
    """Returns a standard column map mapping keys to actual column names."""
    return {
        'customer': 'ЗАКАЗЧИК (название проекта, наименование ЮЛ)',
        'contractor': 'ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)',
        'amount': 'сумма платежа',
        'income': 'приход',
        'expense': 'расход',
        'total': 'ИТОГ',
        'commission': 'комиссия',
        'percent_broker': '% посредника',
        'broker1': 'посредник 1(кэш)',
        'broker2': 'посредник 2',
        'filters': 'фильтры'
    }

@pytest.fixture
def mock_row_dict_basic():
    """Returns a basic dictionary representing a row of data."""
    return {
        'ЗАКАЗЧИК (название проекта, наименование ЮЛ)': 'Client A',
        'ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)': 'Contractor B',
        'сумма платежа': 1000,
        'ИТОГ': 1000,
        'комиссия': 0,
        '% посредника': 0,
        'посредник 1(кэш)': 0,
        'посредник 2': 0,
        'фильтры': ''
    }

@pytest.fixture
def mock_audit(monkeypatch):
    """Mocks the global audit object to prevent file writes during tests."""
    mock = MagicMock()
    # Mock 'audit_logic.audit' - Since 'consolidator' does 'from audit_logic import audit',
    # we might need to patch 'consolidator.audit' instead depending on how it's used.
    # Usually better to patch at the point of use.
    return mock
