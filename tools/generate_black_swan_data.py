import pandas as pd
import openpyxl
from pathlib import Path

def create_black_swan_fixtures():
    target_dir = Path("tests/fixtures/black_swan")
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Unicode Invisible Characters (\u200B)
    # Sheet name: "01.04.2026" with invisible spaces
    path1 = target_dir / "swan_1_unicode_invisible.xlsx"
    with pd.ExcelWriter(path1, engine='openpyxl') as writer:
        df = pd.DataFrame({
            'Заказчик': ['Cust1'], 
            'сумма платежа': [1000], 
            'итог': [1000]
        })
        # Adding \u200B around the date
        df.to_excel(writer, sheet_name="\u200B01.04.2026\u200B", index=False)

    # 2. Huge Empty Space
    # Data starts at row 5000, column 50
    path2 = target_dir / "swan_2_huge_empty_space.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "01.04.2026"
    ws.cell(row=5000, column=50, value="Заказчик")
    ws.cell(row=5000, column=51, value="сумма платежа")
    ws.cell(row=5000, column=52, value="итог")
    ws.cell(row=5001, column=50, value="Cust2")
    ws.cell(row=5001, column=51, value=2000)
    ws.cell(row=5001, column=52, value=2000)
    wb.save(path2)

    # 3. False XLSX (Fake content)
    path3 = target_dir / "swan_3_fake_xlsx.xlsx"
    with open(path3, "w") as f:
        f.write("This is not an Excel file, it's just text.")

    # 4. Infinite Decimals
    path4 = target_dir / "swan_4_precision_hell.xlsx"
    with pd.ExcelWriter(path4, engine='openpyxl') as writer:
        df = pd.DataFrame({
            'Заказчик': ['Cust4'], 
            'сумма платежа': [0.3333333333333333333333333], 
            'итог': [0.3333333333333333333333333]
        })
        df.to_excel(writer, sheet_name="01.04.2026", index=False)

    # 5. Time Loop (Far Future/Past)
    path5 = target_dir / "swan_5_time_loop.xlsx"
    with pd.ExcelWriter(path5, engine='openpyxl') as writer:
        df = pd.DataFrame({
            'Заказчик': ['Cust5_Future', 'Cust5_Past'], 
            'сумма платежа': [5000, 10], 
            'итог': [5000, 10]
        })
        # Sheet 1: 2099
        df.iloc[[0]].to_excel(writer, sheet_name="01.01.2099", index=False)
        # Sheet 2: 1800
        df.iloc[[1]].to_excel(writer, sheet_name="01.01.1800", index=False)

    print(f"✅ Black Swan fixtures created in {target_dir}")

if __name__ == "__main__":
    create_black_swan_fixtures()
