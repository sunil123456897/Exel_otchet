# -*- coding: utf-8 -*-
import time
import pandas as pd
import openpyxl
import os

file_path = r"E:\Для Даши\Версия 5\APP\tests\perf_test_data\source\Employee_0\Report_0.xlsx"

def method_a():
    start = time.time()
    xl = pd.ExcelFile(file_path, engine='openpyxl')
    sheets = [s.title for s in xl.book.worksheets if s.sheet_state == 'visible']
    for sh in sheets:
        # Current logic: read 150 rows via Pandas
        df_preview = pd.read_excel(xl, sheet_name=sh, header=None, nrows=150)
        # Then read the whole sheet again
        df = pd.read_excel(xl, sheet_name=sh, header=0)
    xl.close()
    return time.time() - start

def method_b():
    start = time.time()
    # Optimized logic: use openpyxl read_only for header discovery
    wb = openpyxl.load_workbook(file_path, read_only=True)
    sheets = [s.title for s in wb.worksheets if s.sheet_state == 'visible']
    to_process = []
    for sh in sheets:
        ws = wb[sh]
        rows = []
        for row in ws.iter_rows(max_row=150, values_only=True):
            rows.append(row)
        to_process.append((sh, 0))
    wb.close()
    
    # Then read the whole sheet ONLY ONCE via Pandas
    xl = pd.ExcelFile(file_path, engine='openpyxl')
    for sh, h_idx in to_process:
        df = pd.read_excel(xl, sheet_name=sh, header=h_idx, dtype=str)
    xl.close()
    return time.time() - start

print(f"Method A (Current): {method_a():.4f}s")
print(f"Method B (Optimized): {method_b():.4f}s")
