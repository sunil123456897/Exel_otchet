import pandas as pd
import numpy as np

# Simulate reading a DataFrame from Excel with 'openpyxl' and 'dtype=str'
df = pd.DataFrame([
    ["23.03", "CustA", "ExecA", "1000", np.nan, "1000", ""],
    [np.nan, np.nan, np.nan, np.nan, np.nan, np.nan, np.nan]
], columns=["Дата", "ЗАКАЗЧИК", "Исполнитель", "сумма платежа", "комиссия", "ИТОГ", "фильтры"])

# Print to_dict
print("--- to_dict('index') ---")
for idx, row in df.to_dict('index').items():
    print(f"{idx}: {row}")

print("\n--- itertuples(index=False) ---")
for idx, row in enumerate(df.itertuples(index=False)):
    row_dict = row._asdict()
    print(f"{idx}: {row_dict}")

    # Inline check
    v_c = row_dict.get('ЗАКАЗЧИК')
    v_a = row_dict.get('сумма платежа')
    v_i = row_dict.get('приход')
    v_e = row_dict.get('расход')

    if (v_c != v_c or v_c is None) and \
       (v_a != v_a or v_a is None) and \
       (v_i != v_i or v_i is None) and \
       (v_e != v_e or v_e is None):
        print(f"  --> SKIPPING ROW {idx} (inline check failed)")
    else:
        print(f"  --> KEEPING ROW {idx}")
