# -*- coding: utf-8 -*-
import os
import sys
import time
import pandas as pd
import numpy as np
from datetime import datetime
import shutil
from decimal import Decimal
import logging
import yaml

# Add APP and APP/src to sys.path
# Use absolute path directly to avoid issues
BASE_DIR = r'E:\Для Даши\Версия 5\APP'
sys.path.append(BASE_DIR)
sys.path.append(os.path.join(BASE_DIR, 'src'))

from consolidator import Consolidator

# Disable logging for benchmark
logging.getLogger('consolidator').setLevel(logging.ERROR)

def setup_benchmark_env(num_employees=25, files_per_employee=2):
    test_dir = os.path.join(BASE_DIR, 'tests', 'perf_test_data')
    if os.path.exists(test_dir):
        shutil.rmtree(test_dir)
    os.makedirs(test_dir)
    
    source_root = os.path.join(test_dir, 'source')
    os.makedirs(source_root)
    
    headers = ["Дата", "ЗАКАЗЧИК", "Исполнитель", "сумма платежа", "комиссия", "ИТОГ", "фильтры"]
    
    for i in range(num_employees):
        emp_dir = os.path.join(source_root, f"Employee_{i}")
        os.makedirs(emp_dir)
        for j in range(files_per_employee):
            file_path = os.path.join(emp_dir, f"Report_{j}.xlsx")
            # 100 rows of data
            data = []
            for k in range(100):
                data.append(["23.03", f"Customer_{k}", "Executor", 100.50, 0.05, 100.55, "Some filter"])
            
            # Add some junk rows
            data.append(["Итого", "", "", 10050, 5, 10055, ""])
            data.append(["ЗАКАЗЧИК", "Исполнитель", "Приход", "Расход", "", "", ""])
            
            df = pd.DataFrame(data, columns=headers)
            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='23.03', index=False)
                
    config_data = {
        'paths': {
            'source_root': source_root,
            'master_file': os.path.join(test_dir, 'Master.xlsx')
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
    
    config_path = os.path.join(test_dir, 'perf_config.yaml')
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config_data, f)
        
    return config_path, test_dir

def run_benchmark():
    num_employees = 25
    files_per_employee = 2
    print(f"Setting up benchmark with {num_employees} employees and {files_per_employee} files each...")
    config_path, test_dir = setup_benchmark_env(num_employees, files_per_employee)
    
    consolidator = Consolidator(config_path)
    
    print("\n--- Benchmarking discover_employees ---")
    start = time.time()
    for _ in range(5):
        consolidator.discover_employees()
    avg_discover = (time.time() - start) / 5
    print(f"Average discover_employees time: {avg_discover:.4f}s")
    
    print("\n--- Benchmarking get_employees ---")
    start = time.time()
    for _ in range(5):
        consolidator.get_employees()
    avg_get = (time.time() - start) / 5
    print(f"Average get_employees time: {avg_get:.4f}s")
    
    print("\n--- Benchmarking consolidate_multiple ---")
    target_date = datetime(2026, 3, 23)
    start = time.time()
    results = consolidator.consolidate_multiple([target_date])
    total_consolidate = time.time() - start
    num_rows = sum(len(rows) for rows in results.values())
    print(f"Total consolidate_multiple time: {total_consolidate:.4f}s for {num_rows} rows")

    print("\n--- Benchmarking to_decimal ---")
    vals = ["100.50", "1,234.56", "123,45", "-500", "abc123def", "1.234.567,89", ""] * 1000
    start = time.time()
    for v in vals:
        consolidator.to_decimal(v)
    total_to_decimal = time.time() - start
    print(f"Total to_decimal time for {len(vals)} calls: {total_to_decimal:.4f}s")

    print("\n--- Benchmarking is_junk_row ---")
    # Create a dummy row
    row = pd.Series({
        'ЗАКАЗЧИК': 'Some Customer',
        'Исполнитель': 'Some Executor',
        'сумма платежа': 100.50,
        'ИТОГ': 100.50
    })
    col_map = {'customer': 'ЗАКАЗЧИК', 'contractor': 'Исполнитель', 'amount': 'сумма платежа', 'total': 'ИТОГ'}
    start = time.time()
    for _ in range(10000):
        consolidator.is_junk_row(row, col_map)
    total_is_junk = time.time() - start
    print(f"Total is_junk_row time for 10000 calls: {total_is_junk:.4f}s")

if __name__ == "__main__":
    run_benchmark()
