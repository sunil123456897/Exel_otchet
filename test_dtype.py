import pandas as pd
import numpy as np
import io

# Create a small CSV-like string to simulate Excel data
data = "A,B\n1,2\n,4\n5,"
df = pd.read_csv(io.StringIO(data), dtype=str)
print(f"Value at (1,0): {df.iloc[1,0]} (type: {type(df.iloc[1,0])})")
print(f"Is NaN: {pd.isna(df.iloc[1,0])}")
