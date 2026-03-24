import sys
import os
import time
from datetime import datetime
import openpyxl

BASE_DIR = os.path.abspath('APP')
sys.path.append(BASE_DIR)
sys.path.append(os.path.join(BASE_DIR, 'src'))

from writer import MasterWriter

class DummyConfig:
    paths = {'master_file': 'test_benchmark.xlsx'}

def main():
    writer = MasterWriter(DummyConfig())
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Test"

    # Fill with 10000 rows, 12 columns
    for r in range(1, 10001):
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

    print("Starting _auto_adjust_columns benchmark...")
    start_time = time.time()
    writer._auto_adjust_columns(ws)
    end_time = time.time()

    print(f"Time taken: {end_time - start_time:.4f} seconds")

if __name__ == '__main__':
    main()
