from python_calamine import CalamineWorkbook
import os

try:
    path = r"E:\Dlia Dashi\Version5\tests\fixtures\toxic_data\toxic_1_sheet_typo_31_04.xlsx"
    wb = CalamineWorkbook.from_path(path)
    sheet_name = wb.sheet_names[0]
    sheet = wb.get_sheet_by_name(sheet_name)
    rows_iter = sheet.iter_rows()
    print(f"Type of rows_iter: {type(rows_iter)}")
    first_row = next(rows_iter)
    print(f"First row: {first_row}")
except Exception as e:
    print(f"Error: {e}")
