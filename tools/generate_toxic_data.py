import openpyxl
from pathlib import Path
import os

def create_toxic_files(base_dir: Path):
    headers = ["Дата", "Заказчик", "Исполнитель", "сумма платежа", "комиссия", "итог", "% посредника", "посредник 1(кэш)", "посредник 2", "фильтры"]
    
    # 1. Typos in sheet names
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "31.04.2026"
    ws.append(headers)
    ws.append(["01.04.2026", "Cust1", "Cont1", 1000, 0, 1000, 0.1, 0, 0, ""])
    wb.save(base_dir / "toxic_1_sheet_typo_31_04.xlsx")

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "32.05.2026"
    ws.append(headers)
    ws.append(["01.05.2026", "Cust2", "Cont2", 2000, 0, 2000, 0.2, 0, 0, ""])
    wb.save(base_dir / "toxic_2_sheet_typo_32_05.xlsx")

    # 2. Trash rows
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "01.04.2026"
    ws.append(headers)
    ws.append(["01.04.2026", "Cust3", "Cont3", 3000, 0, 3000, 0.3, 0, 0, ""])
    ws.append(["c16", "trash", "trash", "trash", "trash", "trash", "trash", "trash", "trash", "trash"])
    ws.append(["d16", "trash", "trash", "trash", "trash", "trash", "trash", "trash", "trash", "trash"])
    wb.save(base_dir / "toxic_3_trash_rows.xlsx")

    # 3. Math errors
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "01.04.2026"
    ws.append(headers)
    ws.append(["01.04.2026", "Cust4", "Cont4", 1000, 0, 500, 0.1, 0, 0, ""]) # Math error: 1000 != 500
    wb.save(base_dir / "toxic_4_math_error.xlsx")

    # 4. Missing columns
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "01.04.2026"
    # Missing 'Заказчик'
    ws.append(["Дата", "Исполнитель", "сумма платежа", "комиссия", "итог", "% посредника", "посредник 1(кэш)", "посредник 2", "фильтры"])
    ws.append(["01.04.2026", "Cont5", 5000, 0, 5000, 0.5, 0, 0, ""])
    wb.save(base_dir / "toxic_5_missing_cols.xlsx")

    # 5. Formatted broker percentages (> 100%)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "01.04.2026"
    ws.append(headers)
    ws.append(["01.04.2026", "Cust6", "Cont6", 6000, 0, 6000, 150, 0, 0, ""]) # 15000% if treated as decimal, or 150% if treated as raw. 
    # Actually, the logic says: if > 100, it's an error.
    wb.save(base_dir / "toxic_6_percent_broker_high.xlsx")

    # 6. Formatted broker percentages (non-numeric/extreme)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "01.04.2026"
    ws.append(headers)
    ws.append(["01.04.2026", "Cust7", "Cont7", 7000, 0, 7000, 999, 0, 0, ""]) # Extreme value
    wb.save(base_dir / "toxic_7_percent_broker_non_numeric.xlsx")

    # 7. Mixed issues
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "01.04.2026"
    ws.append(headers)
    ws.append(["01.04.2026", "Cust8", "Cont8", 8000, 0, 4000, 0.8, 0, 0, ""]) # Math error
    ws.append(["c16", "trash", "trash", "trash", "trash", "trash", "trash", "trash", "trash", "trash"]) # Trash row
    wb.save(base_dir / "toxic_8_mixed_issues.xlsx")

    # 8. Template warning (uses aliases)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "01.04.2026"
    # 'агент' instead of 'Заказчик'
    ws.append(["Дата", "агент", "Исполнитель", "сумма платежа", "комиссия", "итог", "% посредника", "посредник 1(кэш)", "посредник 2", "фильтры"])
    ws.append(["01.04.2026", "Cust9", "Cont9", 9000, 0, 9000, 0.9, 0, 0, ""])
    wb.save(base_dir / "toxic_9_template_warning.xlsx")

    # 9. Empty financials
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "01.04.2026"
    ws.append(headers)
    ws.append(["01.04.2026", "Cust10", "Cont10", 0, 0, 0, 0, 0, 0, ""]) # Should be skipped by LogicService
    ws.append(["01.04.2026", "Cust10", "Cont10", 100, 0, 100, 0, 0, 0, ""])
    wb.save(base_dir / "toxic_10_empty_financials.xlsx")

    # 10. Return keyword
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "01.04.2026"
    ws.append(headers)
    ws.append(["01.04.2026", "Cust11", "Cont11", 1100, 0, 1100, 0.11, 0, 0, "возврат"]) # Should go to EXPENSE as negative
    wb.save(base_dir / "toxic_11_return_keyword.xlsx")

if __name__ == "__main__":
    create_toxic_files(Path(r"E:\Для Даши\Версия 5\tests\fixtures\toxic_data"))
