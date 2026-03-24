
import zipfile
from xml.etree import ElementTree
import os
import re
from datetime import datetime

def get_sheetnames_fast(file_path):
    sheetnames = []
    try:
        with zipfile.ZipFile(file_path, 'r') as zf:
            if 'xl/workbook.xml' in zf.namelist():
                with zf.open('xl/workbook.xml') as f:
                    content = f.read().decode('utf-8')
                    print(f"Workbook XML Content (sample): {content[:500]}")
                    f.seek(0)
                    tree = ElementTree.parse(f)
                    root = tree.getroot()
                    for sheet in root.findall('.//{*}sheet'):
                        name = sheet.attrib.get('name')
                        state = sheet.attrib.get('state', 'visible')
                        print(f"Found sheet: {name} (state: {state})")
                        if state == 'visible':
                            sheetnames.append(name)
    except Exception as e:
        print(f"Error: {e}")
    return sheetnames

def check_date_exists(sheetnames, target_date):
    date_pattern = re.compile(rf"{target_date.day:02}\.{target_date.month:02}")
    date_pattern_loose = re.compile(rf"{target_date.day}\.{target_date.month}")
    for sh in sheetnames:
        if date_pattern.search(sh) or date_pattern_loose.search(sh):
            return True
    return False

# Find any xlsx file in the repo to test
for root, dirs, files in os.walk('.'):
    for f in files:
        if f.endswith('.xlsx') and 'perf_test_data' not in root:
            path = os.path.join(root, f)
            print(f"\nTesting file: {path}")
            sheets = get_sheetnames_fast(path)
            print(f"Visible sheets: {sheets}")
            
            test_date = datetime(2026, 3, 23)
            exists = check_date_exists(sheets, test_date)
            print(f"Does 23.03 exist? {exists}")
