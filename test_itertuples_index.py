import pandas as pd
df = pd.DataFrame([["CustA", "ExecA", "1000"]], columns=["ЗАКАЗЧИК", "Исполнитель", "сумма платежа"])

# If we pass name=None to itertuples, it yields regular tuples which we can zip with df.columns
for row in df.itertuples(index=False, name=None):
    row_dict = dict(zip(df.columns, row))
    print(row_dict)
