import os
import time
import psutil
import openpyxl
from pathlib import Path
from core.infra.ingestion_engine import IngestionEngine


def generate_large_excel(file_path, num_rows=100000):
    print(f"Generating {num_rows} rows in {file_path}...")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "01.01.2026"
    
    headers = ["Дата", "Заказчик", "Исполнитель", "Сумма платежа", "Итог", "Комиссия", "Фильтры"]
    ws.append(headers)
    
    for i in range(num_rows):
        ws.append(["01.01.2026", f"Client {i}", f"Bank {i}", 100.0, 100.0, 0.0, "stress test"])
        if i % 10000 == 0:
            print(f"  Written {i} rows...")
            
    wb.save(file_path)
    print("Generation complete.")

def monitor_memory(func):
    def wrapper(*args, **kwargs):
        process = psutil.Process(os.getpid())
        mem_before = process.memory_info().rss / (1024 * 1024)
        start_time = time.time()
        
        result = func(*args, **kwargs)
        
        end_time = time.time()
        mem_after = process.memory_info().rss / (1024 * 1024)
        
        print(f"Execution time: {end_time - start_time:.2f} seconds")
        print(f"Memory before: {mem_before:.2f} MB")
        print(f"Memory after: {mem_after:.2f} MB")
        print(f"Memory diff: {mem_after - mem_before:.2f} MB")
        return result
    return wrapper

@monitor_memory
def run_ingestion(file_path):
    markers = {
        'amount': 'Сумма платежа',
        'total': 'Итог',
        'customer': 'Заказчик',
        'contractor': 'Исполнитель',
        'commission': 'Комиссия',
        'filters': 'Фильтры'
    }
    engine = IngestionEngine(markers)
    rows = engine.read_file(Path(file_path))
    print(f"Read {len(rows)} rows.")
    return rows

if __name__ == "__main__":
    test_file = "stress_test_data.xlsx"
    try:
        if not os.path.exists(test_file):
            generate_large_excel(test_file, 100000)
        
        print("\nRunning ingestion stress test...")
        run_ingestion(test_file)
        
    finally:
        if os.path.exists(test_file):
            # os.remove(test_file)
            print(f"\nTest file kept at {test_file} for manual inspection if needed.")
            pass
