import os
import logging
import pandas as pd
from datetime import datetime
import openpyxl
from openpyxl.utils import get_column_letter
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

logger = logging.getLogger(__name__)

class MasterWriter:
    def __init__(self, config):
        self.config = config
        if isinstance(config, dict):
            paths = config.get('paths', {})
            self.master_path = paths.get('master_file', 'Master_Report.xlsx')
        else:
            self.master_path = getattr(config, 'paths', {}).get('master_file', 'Master_Report.xlsx')
        
        if not os.path.isabs(self.master_path):
            if not os.path.exists(self.master_path) and os.path.exists("Master_Report.xlsx"):
                self.master_path = "Master_Report.xlsx"
            
        self.clr_header_bg = "1F4E79"
        self.clr_header_text = "FFFFFF"
        self.clr_row_odd = "F2F2F2"
        self.clr_row_even = "FFFFFF"
        self.clr_income_bg = "C6EFCE"
        self.clr_income_text = "006100"
        self.clr_expense_bg = "FFC7CE"
        self.clr_expense_text = "9C0006"
        self.clr_total_bg = "D9E1F2"
        
        self.fill_header = PatternFill(start_color=self.clr_header_bg, end_color=self.clr_header_bg, fill_type="solid")
        self.fill_odd = PatternFill(start_color=self.clr_row_odd, end_color=self.clr_row_odd, fill_type="solid")
        self.fill_even = PatternFill(start_color=self.clr_row_even, end_color=self.clr_row_even, fill_type="solid")
        self.fill_income = PatternFill(start_color=self.clr_income_bg, end_color=self.clr_income_bg, fill_type="solid")
        self.fill_expense = PatternFill(start_color=self.clr_expense_bg, end_color=self.clr_expense_bg, fill_type="solid")
        self.fill_total = PatternFill(start_color=self.clr_total_bg, end_color=self.clr_total_bg, fill_type="solid")
        
        self.font_header = Font(color=self.clr_header_text, bold=True, size=11)
        self.font_standard = Font(size=10)
        self.font_bold = Font(bold=True, size=10)
        self.font_income = Font(color=self.clr_income_text, bold=True)
        self.font_expense = Font(color=self.clr_expense_text, bold=True)
        self.font_total = Font(bold=True, size=11)
        
        thin_side = Side(style='thin', color="000000")
        self.border_thin = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
        self.border_medium = Border(left=Side(style='medium'), right=Side(style='medium'), top=Side(style='medium'), bottom=Side(style='medium'))
        self.align_center = Alignment(horizontal='center', vertical='center', wrap_text=True)
        self.align_left = Alignment(horizontal='left', vertical='center', wrap_text=True)
        self.align_right = Alignment(horizontal='right', vertical='center')

    def _apply_header_style(self, ws, row_idx=1):
        for cell in ws[row_idx]:
            cell.fill, cell.font, cell.alignment, cell.border = self.fill_header, self.font_header, self.align_center, self.border_thin

    def _get_workbook(self):
        if os.path.exists(self.master_path):
            try: return openpyxl.load_workbook(self.master_path)
            except: return openpyxl.Workbook()
        wb = openpyxl.Workbook()
        if "Sheet" in wb.sheetnames: wb.remove(wb["Sheet"])
        return wb

    def _save_workbook(self, wb):
        self._sort_sheets(wb)
        temp_path = self.master_path + ".tmp"
        try:
            wb.save(temp_path)
            if os.path.exists(temp_path):
                if os.path.exists(self.master_path):
                    try:
                        os.replace(temp_path, self.master_path)
                    except PermissionError:
                        import tkinter.messagebox as mb
                        mb.showerror("Файл занят", f"Не удалось сохранить отчет!\n\nФайл '{self.master_path}' открыт в Excel.\nПожалуйста, закройте его и попробуйте снова.")
                        return
                else:
                    os.rename(temp_path, self.master_path)
                logger.info(f"Report saved: {self.master_path}")
        except Exception as e:
            logger.error(f"Save failed: {e}")
            try: wb.save(self.master_path)
            except: pass

    def _sort_sheets(self, wb):
        def sheet_key(name):
            if "." in name:
                try:
                    parts = name.split(".")
                    # Sort by month, then by day
                    return int(parts[1]), int(parts[0])
                except: return 99, 99
            return 100, 100
        sheet_names = sorted(wb.sheetnames, key=sheet_key)
        for i, name in enumerate(sheet_names):
            sheet = wb[name]
            wb._sheets.remove(sheet)
            wb._sheets.insert(i, sheet)

    def _auto_adjust_columns(self, ws):
        for col in ws.columns:
            max_length = 0
            first_cell = col[0]
            column_letter = first_cell.column_letter
            column_index = first_cell.column # 1-based index
            
            for cell in col:
                if cell.value is not None:
                    # For numeric columns, we might have formulas or large numbers
                    # str(cell.value) for a formula is the formula itself, e.g., '=SUM(E2:E10)'
                    length = len(str(cell.value))
                    if length > max_length:
                        max_length = length
            
            if 5 <= column_index <= 11:
                # Numeric columns (Приход, Расход, Комиссия, ИТОГ, etc.)
                # Use multiplier for thousand separators and larger margin for bold/formulas
                width = (max_length * 1.1) + 6
                ws.column_dimensions[column_letter].width = max(width, 15)
            else:
                # Standard columns: increased margin from +2 to +4
                ws.column_dimensions[column_letter].width = max_length + 4

    def write_daily_data(self, date, employee_rows, wb=None):
        """
        Writes data for a single day to a specific sheet in the workbook.
        If wb is provided, uses it and DOES NOT save. 
        If wb is None, opens, writes and saves immediately (legacy/helper mode).
        """
        should_save = False
        if wb is None:
            wb = self._get_workbook()
            should_save = True
            
        sh_name = date.strftime("%d.%m")
        if sh_name in wb.sheetnames: del wb[sh_name]
        ws = wb.create_sheet(sh_name)
        
        headers = ["Дата", "Сотрудник", "ЗАКАЗЧИК", "ИСПОЛНИТЕЛЬ", "Приход", "Расход", "Комиссия", "ИТОГ", "% посредника", "посредник 1(кэш)", "посредник 2", "Фильтры"]
        ws.append(headers); self._apply_header_style(ws)
        ws.freeze_panes = 'A2'
        
        for idx, r in enumerate(employee_rows):
            # Use Decimal objects directly where possible, openpyxl supports them
            row_vals = [
                date.strftime("%d.%m.%Y"), 
                r.get('Сотрудник', ''), 
                r.get('ЗАКАЗЧИК (название проекта, наименование ЮЛ)', ''),
                r.get('ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)', ''), 
                r.get('сумма платежа ПРИХОД', 0), 
                r.get('сумма платежа РАСХОД', 0), 
                r.get('комиссия', 0), 
                r.get('ИТОГ', 0),
                r.get('% посредника', 0), 
                r.get('посредник 1(кэш)', 0), 
                r.get('посредник 2', 0), 
                r.get('фильтры', '')
            ]
            ws.append(row_vals)
            curr_row = ws.max_row
            fill = self.fill_odd if (idx+1)%2==1 else self.fill_even
            for c_idx, cell in enumerate(ws[curr_row], 1):
                cell.fill, cell.border, cell.font, cell.alignment = fill, self.border_thin, self.font_standard, self.align_left
                # Columns with numbers
                if 5 <= c_idx <= 11:
                    cell.number_format = '#,##0.00'; cell.alignment = self.align_right
                    val = cell.value if cell.value else 0
                    if c_idx == 5 and val > 0.01: cell.fill, cell.font = self.fill_income, self.font_income
                    if c_idx == 6 and abs(val) > 0.01: cell.fill, cell.font = self.fill_expense, self.font_expense

        total_row = ws.max_row + 1
        ws.cell(total_row, 1, "ИТОГО:").font = self.font_total
        for c in range(5, 9):
            let = get_column_letter(c); cell = ws.cell(total_row, c)
            cell.value = f"=SUM({let}2:{let}{total_row-1})"; cell.number_format = '#,##0.00'
            cell.fill, cell.font, cell.border = self.fill_total, self.font_total, self.border_medium
        self._auto_adjust_columns(ws)
        
        if should_save:
            self._save_workbook(wb)

    def write_all_days(self, data_by_date):
        """
        HIGH PERFORMANCE: Opens workbook once, writes all dates, saves once.
        """
        wb = self._get_workbook()
        for d_str, rows in sorted(data_by_date.items()):
            dt = datetime.strptime(d_str, "%d.%m.%Y")
            self.write_daily_data(dt, rows, wb=wb)
        
        self._save_workbook(wb)
