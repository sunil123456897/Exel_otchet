import sys
import os
import time
from datetime import datetime
import openpyxl

BASE_DIR = os.path.abspath('APP')
sys.path.append(BASE_DIR)
sys.path.append(os.path.join(BASE_DIR, 'src'))

def main():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Test"

    # Fill with 100000 rows, 12 columns
    for r in range(1, 100001):
        row_data = [
            "23.03.2023",
            f"Employee {r}",
            f"Customer ABC {r}",
            "Executor XYZ",
            100.50,
            50.25,
            1.5,
            48.75,
            0.1,
            5,
            0,
            "Filter string"
        ]
        ws.append(row_data)

    print("Starting _auto_adjust_columns benchmark (baseline)...")
    start_time = time.time()
    for col in ws.columns:
        max_length = 0
        first_cell = col[0]
        column_letter = first_cell.column_letter
        column_index = first_cell.column # 1-based index

        for cell in col:
            if cell.value is not None:
                length = len(str(cell.value))
                if length > max_length:
                    max_length = length
    end_time = time.time()
    print(f"Time taken (baseline): {end_time - start_time:.4f} seconds")

    print("Starting _auto_adjust_columns benchmark (limited sample)...")
    start_time = time.time()
    for col in ws.columns:
        first_cell = col[0]
        column_letter = first_cell.column_letter
        column_index = first_cell.column

        # Sample first 100 and last 100
        if len(col) > 200:
            sampled_cells = col[:100] + col[-100:]
        else:
            sampled_cells = col
        max_length = max((len(str(cell.value)) for cell in sampled_cells if cell.value is not None), default=0)
    end_time = time.time()
    print(f"Time taken (limited sample): {end_time - start_time:.4f} seconds")

if __name__ == '__main__':
    main()
