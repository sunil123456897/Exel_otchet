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

    print("Starting _auto_adjust_columns benchmark (ws.iter_rows pure sample vs full loop)...")
    start_time = time.time()

    max_row = ws.max_row
    max_col = ws.max_column

    # It's better to just sample up to 100 rows.
    col_max_lengths = [0] * max_col

    # we iterate to 100, which handles small size sheets automatically
    for row in ws.iter_rows(min_row=1, max_row=min(100, max_row), values_only=True):
        for i, val in enumerate(row):
            if val is not None:
                length = len(str(val))
                if length > col_max_lengths[i]:
                    col_max_lengths[i] = length

    if max_row > 100:
        for row in ws.iter_rows(min_row=max(101, max_row-99), max_row=max_row, values_only=True):
            for i, val in enumerate(row):
                if val is not None:
                    length = len(str(val))
                    if length > col_max_lengths[i]:
                        col_max_lengths[i] = length

    # Then map the columns lengths...
    for i in range(max_col):
        max_length = col_max_lengths[i]
        column_index = i + 1
        column_letter = get_column_letter(column_index)

    end_time = time.time()
    print(f"Time taken (ws.iter_rows sampling): {end_time - start_time:.4f} seconds")

if __name__ == '__main__':
    main()
