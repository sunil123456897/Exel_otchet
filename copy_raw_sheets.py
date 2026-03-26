import os
import sys
import re
import pandas as pd
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows

def extract_raw_sheets_from_dirs(target_dates=["25.03", "24.03", "23.03", "22.03", "21.03", "20.03"]):
    reports_dir = os.path.abspath('REPORTS')
    output_file = "Raw_Sheets_All_Employees.xlsx"
    
    # Pre-compile regexes for dates
    date_regexes = {}
    for d_str in target_dates:
        parts = d_str.split('.')
        d = parts[0]
        m = parts[1]
        date_regexes[d_str] = re.compile(rf"(^|[^0-9])0?{int(d)}\.0?{int(m)}([^0-9]|$)", re.IGNORECASE)
    
    print(f"Scanning '{reports_dir}' for employee folders...")
    print(f"Fallback date order: {target_dates}")
    
    wb = Workbook()
    if "Sheet" in wb.sheetnames:
        wb.remove(wb["Sheet"])
        
    copied = 0
    
    # Find all employee folders (they are inside "Отчет кураторов X")
    employee_folders = []
    for root, dirs, files in os.walk(reports_dir):
        # If we are inside an "Отчет кураторов" folder, its subdirectories are employee folders
        if "Отчет кураторов" in os.path.basename(root):
            for d in dirs:
                employee_folders.append((d, os.path.join(root, d)))

    for emp_name, emp_dir in employee_folders:
        found_sheet_for_emp = False
        
        # Get all excel files for this employee
        excel_files = []
        for file in os.listdir(emp_dir):
            if file.endswith('.xlsx') or file.endswith('.xlsb'):
                if not file.startswith('~$'): # Ignore temp files
                    excel_files.append(os.path.join(emp_dir, file))
                    
        if not excel_files:
            print(f"[{emp_name}] No Excel files found in directory.")
            continue
            
        # Check files for target dates
        for file_path in excel_files:
            try:
                engine = 'pyxlsb' if file_path.lower().endswith('.xlsb') else 'openpyxl'
                xl = pd.ExcelFile(file_path, engine=engine)
                
                target_sheet = None
                matched_date_str = None
                
                # Check dates in order of priority
                for d_str in target_dates:
                    regex = date_regexes[d_str]
                    for sh in xl.sheet_names:
                        if regex.search(str(sh).strip()):
                            target_sheet = sh
                            matched_date_str = d_str
                            break
                    if target_sheet:
                        break # Found highest priority date
                
                if target_sheet:
                    print(f"[{emp_name}] Found sheet '{target_sheet}' (matched {matched_date_str}) in {os.path.basename(file_path)}")
                    df = pd.read_excel(file_path, sheet_name=target_sheet, header=None, engine=engine)
                    
                    # Create safe sheet name
                    safe_emp = re.sub(r'[\\/*?:\[\]]', '', str(emp_name))[:25]
                    safe_emp = f"{safe_emp} ({matched_date_str})"
                    
                    original_safe = safe_emp
                    counter = 1
                    while safe_emp in wb.sheetnames:
                        safe_emp = f"{original_safe[:25]}_{counter}"
                        counter += 1
                        
                    ws = wb.create_sheet(title=safe_emp)
                    
                    for r in dataframe_to_rows(df, index=False, header=False):
                        ws.append(r)
                        
                    copied += 1
                    found_sheet_for_emp = True
                    break  # Move to next employee
            except Exception as e:
                print(f"[{emp_name}] Error processing {os.path.basename(file_path)}: {e}")
                
        if not found_sheet_for_emp:
            print(f"[{emp_name}] WARNING: Could not find ANY matching sheets in {target_dates}")
                
    if copied == 0:
        ws = wb.create_sheet(title="Empty")
        ws.append(["No sheets found"])
        print("\nNo sheets found.")
    else:
        print(f"\nSuccessfully copied {copied} sheets.")
        
    wb.save(output_file)
    print(f"Saved to {output_file}")

if __name__ == '__main__':
    extract_raw_sheets_from_dirs(["25.03", "24.03", "23.03", "22.03", "21.03", "20.03", "19.03", "18.03"])