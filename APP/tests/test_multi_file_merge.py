import os
import sys
import yaml
import pandas as pd
import openpyxl
from datetime import datetime
import shutil
import logging

# Add APP and APP/src to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
sys.path.append(os.path.join(BASE_DIR, 'src'))

from consolidator import Consolidator

def create_test_excel(file_path, sheet_name, data_row):
    # Create a dataframe with headers
    headers = ["Дата", "ЗАКАЗЧИК", "Исполнитель", "сумма платежа", "комиссия", "ИТОГ", "фильтры"]
    df = pd.DataFrame([data_row], columns=headers)
    
    # Create Excel file
    with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=0)

def test_multi_file_merge():
    test_dir = os.path.join(BASE_DIR, 'tests', 'temp_test_data')
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    
    file_a = os.path.join(test_dir, 'FileA.xlsx')
    file_b = os.path.join(test_dir, 'FileB.xlsx')
    
    # Create FileA
    create_test_excel(file_a, '23.03', ["23.03", "CustA", "ExecA", 1000, 0, 1000, ""])
    # Create FileB
    create_test_excel(file_b, '23.03', ["23.03", "CustB", "ExecB", 2000, 0, 2000, ""])
    
    # Create temporary config.yaml
    config_data = {
        'employees': ['TestUser'],
        'paths': {
            'source_root': test_dir,
            'master_file': os.path.join(test_dir, 'Master.xlsx')
        },
        'employee_paths': {
            'TestUser': [file_a, file_b]
        },
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
        
    # Redirect audit to a temporary file
    from audit_logic import audit
    test_audit_file = os.path.join(test_dir, 'test_audit.txt')
    audit.audit_file = test_audit_file
        
    try:
        consolidator = Consolidator(config_path)
        # Use a fixed year for consistency
        target_date = datetime(2026, 3, 23)
        
        results = consolidator.consolidate_multiple([target_date])
        
        # The date key in results is formatted as "%d.%m.%Y"
        date_key = target_date.strftime("%d.%m.%Y")
        
        if date_key not in results:
            available = list(results.keys())
            raise AssertionError(
                f"Expected date '{date_key}' not found in results. "
                f"Available keys: {available}"
            )
        
        rows = results[date_key]
        
        print(f"Found {len(rows)} rows for {date_key}")
        for r in rows:
            print(f"Row: {r['Сотрудник']} | {r['ЗАКАЗЧИК (название проекта, наименование ЮЛ)']}")
            
        assert len(rows) == 2, f"Expected 2 rows, got {len(rows)}"
        
        # Check filenames in 'Сотрудник' field
        filenames_found = [r['Сотрудник'] for r in rows]
        assert any("FileA.xlsx" in f for f in filenames_found), "FileA.xlsx not found in results"
        assert any("FileB.xlsx" in f for f in filenames_found), "FileB.xlsx not found in results"
        
        # Verify specific row content
        row_a = next(r for r in rows if "FileA.xlsx" in r['Сотрудник'])
        row_b = next(r for r in rows if "FileB.xlsx" in r['Сотрудник'])
        
        assert row_a['ЗАКАЗЧИК (название проекта, наименование ЮЛ)'] == "CustA"
        assert row_b['ЗАКАЗЧИК (название проекта, наименование ЮЛ)'] == "CustB"
        
        print("Test passed!")
        
    finally:
        # Cleanup
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
        # Remove logs created during test
        if os.path.exists("consolidation.log"):
            try: os.remove("consolidation.log")
            except: pass

if __name__ == "__main__":
    # Setup logging to see what's happening
    logging.basicConfig(level=logging.INFO)
    test_multi_file_merge()
