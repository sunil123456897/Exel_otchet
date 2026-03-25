import pandas as pd
import numpy as np
import os
import yaml
import sys
import tempfile
from decimal import Decimal

# Add APP and APP/src to sys.path to import consolidator and audit_logic
sys.path.append(os.path.join(os.getcwd(), 'APP'))
sys.path.append(os.path.join(os.getcwd(), 'APP', 'src'))
from consolidator import Consolidator

def test_nan_fix():
    # Create a dummy config
    config_data = {
        'paths': {},
        'sh1': {'markers': {}},
        'sh2': {},
        'logic': {
            'income_overrides': ['доп'],
            'return_keywords': ['возврат']
        },
        'employees': []
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, 'test_config.yaml')
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f)

        consolidator = Consolidator(config_path)
        
        # Mock row with NaN values
        # Using np.nan and None to test both
        row = pd.Series({
            'cust_col': np.nan,
            'cont_col': None,
            'filt_col': np.nan,
            'amt_col': 100.0,
            'total_col': 100.0,
            'comm_col': np.nan,
            'perc_col': np.nan,
            'br1_col': np.nan,
            'br2_col': np.nan
        })
        
        col_map = {
            'customer': 'cust_col',
            'contractor': 'cont_col',
            'filters': 'filt_col',
            'amount': 'amt_col',
            'total': 'total_col',
            'commission': 'comm_col',
            'percent_broker': 'perc_col',
            'broker1': 'br1_col',
            'broker2': 'br2_col'
        }
        
        res = consolidator.transform_row(row, col_map, "TestEmp", "23.03", 10, log_audit=False)
        
        print(f"Result: {res}")
        
        # Assertions for text fields
        assert res['ЗАКАЗЧИК (название проекта, наименование ЮЛ)'] == "", f"Expected empty string, got {res['ЗАКАЗЧИК (название проекта, наименование ЮЛ)']}"
        assert res['ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)'] == "", f"Expected empty string, got {res['ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)']}"
        assert res['фильтры'] == "", f"Expected empty string, got {res['фильтры']}"
        
        # Assertions for numeric fields (should be Decimal('0.00') or Decimal('0'))
        assert res['сумма платежа ПРИХОД'] == Decimal('100.00')
        assert res['комиссия'] == Decimal('0')
        assert res['% посредника'] == Decimal('0')
        assert res['посредник 1(кэш)'] == Decimal('0.00')
        assert res['посредник 2'] == Decimal('0.00')
        
        print("Test passed!")

if __name__ == "__main__":
    try:
        test_nan_fix()
    except AssertionError as e:
        print(f"Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
