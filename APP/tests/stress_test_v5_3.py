import os
import sys
import yaml
import pandas as pd
import openpyxl
from datetime import datetime
import shutil
import logging
from decimal import Decimal

# Add APP and APP/src to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
sys.path.append(os.path.join(BASE_DIR, 'src'))

from consolidator import Consolidator
from audit_logic import audit

# Configure logging for tests
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_test_excel(file_path, sheet_name, data_rows, headers=None):
    if headers is None:
        headers = ["Дата", "ЗАКАЗЧИК", "Исполнитель", "сумма платежа", "комиссия", "ИТОГ", "фильтры"]
    df = pd.DataFrame(data_rows, columns=headers)
    
    with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=0)

def setup_test_env():
    test_dir = os.path.join(BASE_DIR, 'tests', 'stress_test_data')
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    
    # Redirect audit to a temporary file
    test_audit_file = os.path.join(test_dir, 'test_audit.txt')
    audit.audit_file = test_audit_file
    
    return test_dir

def create_config(test_dir, employees=None, employee_paths=None):
    config_data = {
        'employees': employees or ['TestUser'],
        'paths': {
            'source_root': test_dir,
            'master_file': os.path.join(test_dir, 'Master.xlsx')
        },
        'employee_paths': employee_paths or {},
        'sh1': {
            'markers': {
                'amount': 'сумма платежа',
                'commission': 'комиссия',
                'contractor': 'Исполнитель',
                'customer': 'ЗАКАЗЧИК',
                'date': 'дата',
                'filters': 'фильтры',
                'total': 'ИТОГ'
            }
        },
        'logic': {
            'income_overrides': ['доп'],
            'return_keywords': ['возврат']
        }
    }
    
    config_path = os.path.join(test_dir, 'test_config.yaml')
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config_data, f)
    return config_path

def test_scenario_1_missing_file():
    print("\n--- Scenario 1: Missing File ---")
    test_dir = setup_test_env()
    file_exists = os.path.join(test_dir, 'Exists.xlsx')
    file_missing = os.path.join(test_dir, 'Missing.xlsx')
    
    create_test_excel(file_exists, '23.03', [["23.03", "CustExists", "Exec", 100, 0, 100, ""]])
    # Do NOT create file_missing
    
    config_path = create_config(test_dir, employee_paths={'TestUser': [file_exists, file_missing]})
    
    consolidator = Consolidator(config_path)
    target_date = datetime(2026, 3, 23)
    results = consolidator.consolidate_multiple([target_date])
    
    date_key = target_date.strftime("%d.%m.%Y")
    rows = results.get(date_key, [])
    
    print(f"Found {len(rows)} rows")
    assert len(rows) == 1, f"Expected 1 row from existing file, got {len(rows)}"
    assert "CustExists" in rows[0]['ЗАКАЗЧИК (название проекта, наименование ЮЛ)']
    print("Scenario 1 passed!")

def test_scenario_2_fuzzy_date_matching():
    print("\n--- Scenario 2: Fuzzy Date Matching ---")
    test_dir = setup_test_env()
    file_path = os.path.join(test_dir, 'FuzzyDates.xlsx')
    
    # Create Excel with two sheets: '23.03' and '23.3'
    with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
        headers = ["Дата", "ЗАКАЗЧИК", "Исполнитель", "сумма платежа", "комиссия", "ИТОГ", "фильтры"]
        pd.DataFrame([["23.03", "Cust1", "Exec", 100, 0, 100, ""]], columns=headers).to_excel(writer, sheet_name='23.03', index=False)
        pd.DataFrame([["23.3", "Cust2", "Exec", 200, 0, 200, ""]], columns=headers).to_excel(writer, sheet_name='23.3', index=False)
    
    config_path = create_config(test_dir, employee_paths={'TestUser': [file_path]})
    
    consolidator = Consolidator(config_path)
    target_date = datetime(2026, 3, 23)
    results = consolidator.consolidate_multiple([target_date])
    
    date_key = target_date.strftime("%d.%m.%Y")
    rows = results.get(date_key, [])
    
    print(f"Found {len(rows)} rows")
    assert len(rows) == 2, f"Expected 2 rows (one from each sheet), got {len(rows)}"
    customers = [r['ЗАКАЗЧИК (название проекта, наименование ЮЛ)'] for r in rows]
    assert "Cust1" in customers
    assert "Cust2" in customers
    print("Scenario 2 passed!")

def test_scenario_3_duplicate_path_prevention():
    print("\n--- Scenario 3: Duplicate Path Prevention ---")
    test_dir = setup_test_env()
    file_path = os.path.join(test_dir, 'Duplicate.xlsx')
    create_test_excel(file_path, '23.03', [["23.03", "Cust", "Exec", 100, 0, 100, ""]])
    
    # Add same path twice
    config_path = create_config(test_dir, employee_paths={'TestUser': [file_path, file_path]})
    
    consolidator = Consolidator(config_path)
    
    # Check get_employees directly
    employees = consolidator.get_employees()
    paths = employees.get('TestUser', [])
    print(f"Paths for TestUser: {paths}")
    assert len(paths) == 1, f"Expected 1 unique path, got {len(paths)}"
    
    # Check consolidation result
    target_date = datetime(2026, 3, 23)
    results = consolidator.consolidate_multiple([target_date])
    date_key = target_date.strftime("%d.%m.%Y")
    rows = results.get(date_key, [])
    
    print(f"Found {len(rows)} rows")
    assert len(rows) == 1, f"Expected 1 row, got {len(rows)}"
    print("Scenario 3 passed!")

def test_scenario_4_malformed_data():
    print("\n--- Scenario 4: Malformed Data ---")
    test_dir = setup_test_env()
    
    # File 1: Good data
    file_good = os.path.join(test_dir, 'Good.xlsx')
    create_test_excel(file_good, '23.03', [["23.03", "GoodCust", "Exec", 100, 0, 100, ""]])
    
    # File 2: Malformed data (wrong headers)
    file_bad = os.path.join(test_dir, 'Bad.xlsx')
    create_test_excel(file_bad, '23.03', [["Wrong", "Headers", "Here", "No", "Markers"]], headers=["A", "B", "C", "D", "E"])
    
    # File 3: Empty sheet
    file_empty = os.path.join(test_dir, 'Empty.xlsx')
    with pd.ExcelWriter(file_empty, engine='openpyxl') as writer:
        pd.DataFrame().to_excel(writer, sheet_name='23.03', index=False)
        
    config_path = create_config(test_dir, employee_paths={'TestUser': [file_good, file_bad, file_empty]})
    
    consolidator = Consolidator(config_path)
    target_date = datetime(2026, 3, 23)
    results = consolidator.consolidate_multiple([target_date])
    
    date_key = target_date.strftime("%d.%m.%Y")
    rows = results.get(date_key, [])
    
    print(f"Found {len(rows)} rows")
    assert len(rows) == 1, f"Expected only 1 row from Good.xlsx, got {len(rows)}"
    assert "GoodCust" in rows[0]['ЗАКАЗЧИК (название проекта, наименование ЮЛ)']
    print("Scenario 4 passed!")

def test_scenario_5_precision_check():
    print("\n--- Scenario 5: Precision Check ---")
    test_dir = setup_test_env()
    file_path = os.path.join(test_dir, 'Precision.xlsx')
    
    # Create rows with values that often cause float issues: 0.1, 0.2, 0.1
    # Sum should be exactly 0.40
    data_rows = [
        ["23.03", "Cust1", "Exec", 0.1, 0, 0.1, ""],
        ["23.03", "Cust2", "Exec", 0.2, 0, 0.2, ""],
        ["23.03", "Cust3", "Exec", 0.1, 0, 0.1, ""]
    ]
    create_test_excel(file_path, '23.03', data_rows)
    
    config_path = create_config(test_dir, employee_paths={'TestUser': [file_path]})
    
    consolidator = Consolidator(config_path)
    target_date = datetime(2026, 3, 23)
    results = consolidator.consolidate_multiple([target_date])
    
    date_key = target_date.strftime("%d.%m.%Y")
    rows = results.get(date_key, [])
    
    total_income = sum(r['сумма платежа ПРИХОД'] for r in rows)
    print(f"Total income: {total_income} (Type: {type(total_income)})")
    
    assert isinstance(total_income, Decimal), f"Expected Decimal, got {type(total_income)}"
    assert total_income == Decimal('0.40'), f"Expected 0.40, got {total_income}"
    
    # Test with more complex values
    test_dir_2 = setup_test_env()
    file_path_2 = os.path.join(test_dir_2, 'Precision2.xlsx')
    data_rows_2 = [
        ["23.03", "Cust1", "Exec", "100.05", 0, "100.05", ""],
        ["23.03", "Cust2", "Exec", "200.10", 0, "200.10", ""],
    ]
    create_test_excel(file_path_2, '23.03', data_rows_2)
    config_path_2 = create_config(test_dir_2, employee_paths={'TestUser': [file_path_2]})
    consolidator_2 = Consolidator(config_path_2)
    results_2 = consolidator_2.consolidate_multiple([target_date])
    rows_2 = results_2.get(date_key, [])
    total_income_2 = sum(r['сумма платежа ПРИХОД'] for r in rows_2)
    print(f"Total income 2: {total_income_2}")
    assert total_income_2 == Decimal('300.15')

    print("Scenario 5 passed!")

def run_all_tests():
    try:
        test_scenario_1_missing_file()
        test_scenario_2_fuzzy_date_matching()
        test_scenario_3_duplicate_path_prevention()
        test_scenario_4_malformed_data()
        test_scenario_5_precision_check()
        print("\nALL STRESS TESTS PASSED!")
    finally:
        # Final cleanup
        test_dir = os.path.join(BASE_DIR, 'tests', 'stress_test_data')
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
        if os.path.exists("consolidation.log"):
            try: os.remove("consolidation.log")
            except: pass

if __name__ == "__main__":
    run_all_tests()
