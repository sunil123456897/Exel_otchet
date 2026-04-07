from python_calamine import CalamineWorkbook
import os

# Create a dummy xlsx if needed, but we just want to see the API
try:
    # Just list methods of a sheet object
    # We need a real file to get a sheet object easily
    # I'll use one of the existing fixtures
    path = r"E:\Dlia Dashi\Version5\tests\fixtures\toxic_data\toxic_1_sheet_typo_31_04.xlsx"
    wb = CalamineWorkbook.from_path(path)
    sheet_name = wb.sheet_names[0]
    sheet = wb.get_sheet_by_name(sheet_name)
    print(f"Sheet methods: {dir(sheet)}")
    # Check if .rows() exists
    if hasattr(sheet, 'rows'):
        print("sheet.rows() exists")
    else:
        print("sheet.rows() does NOT exist")
    
    # Check if it's iterable
    try:
        it = iter(sheet)
        print("Sheet is iterable")
    except TypeError:
        print("Sheet is NOT iterable")

except Exception as e:
    print(f"Error: {e}")
