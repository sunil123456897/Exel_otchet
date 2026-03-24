import sys
import os
import time
from datetime import datetime
import openpyxl
from openpyxl.utils import get_column_letter

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

    print("Starting _auto_adjust_columns benchmark (row generator with yield)...")
    start_time = time.time()

    max_row = ws.max_row

    for col in ws.columns:
        first_cell = col[0]
        column_letter = first_cell.column_letter
        column_index = first_cell.column

        max_length = 0

        # Only check the first 100 and last 100 rows to find max column width,
        # since typically the longest text is either headers/first rows or summary totals at the end.
        if len(col) > 200:
            cells_to_check = col[:100] + col[-100:]
        else:
            cells_to_check = col

        for cell in cells_to_check:
            if cell.value is not None:
                length = len(str(cell.value))
                if length > max_length:
                    max_length = length

    end_time = time.time()
    print(f"Time taken (generator yield): {end_time - start_time:.4f} seconds")

if __name__ == '__main__':
    main()
