import os
import sys
import time
import pandas as pd
from pathlib import Path

# Add APP to sys.path
APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'APP'))
sys.path.append(APP_ROOT)

from core.infra.ingestion_reader import CalamineReader

MARKERS = {
    'date': 'дата',
    'customer': 'клиент',
    'contractor': 'контрагент',
    'amount': 'сумма',
    'income': 'приход',
    'expense': 'расход',
    'commission': 'комиссия'
}
ALIASES = {
    'amount': ['выплата', 'всего'],
    'customer': ['фио', 'сотрудник']
}

def generate_150k_data(file_path):
    if os.path.exists(file_path):
        return
    data = {
        'дата': ['01.01.2024'] * 150000,
        'клиент': [f'Client_{i % 100}' for i in range(150000)],
        'сумма': [100.50 + i for i in range(150000)],
        'приход': [50.0] * 150000,
        'расход': [20.0] * 150000,
        'комиссия': [5.0] * 150000
    }
    df = pd.DataFrame(data)
    with pd.ExcelWriter(file_path, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='01.01.2024', index=False)

if __name__ == "__main__":
    file_path = Path("benchmark_150k.xlsx")
    generate_150k_data(file_path)
    
    reader = CalamineReader(MARKERS, ALIASES)
    
    start = time.time()
    rows = reader.read(file_path)
    duration = time.time() - start
    print(f"Parsing duration: {duration:.4f}s (Rows: {len(rows)})")
