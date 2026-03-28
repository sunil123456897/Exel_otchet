import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
import openpyxl
from openpyxl.utils import get_column_letter
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

from .interfaces import IExporter

logger = logging.getLogger(__name__)

class MasterWriter(IExporter):
    def __init__(self, config: Dict[str, Any]):
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
        self.clr_warning_bg = "FFCC00" # Orange for template warnings
        
        self.fill_header = PatternFill(start_color=self.clr_header_bg, end_color=self.clr_header_bg, fill_type="solid")
        self.fill_odd = PatternFill(start_color=self.clr_row_odd, end_color=self.clr_row_odd, fill_type="solid")
        self.fill_even = PatternFill(start_color=self.clr_row_even, end_color=self.clr_row_even, fill_type="solid")
        self.fill_income = PatternFill(start_color=self.clr_income_bg, end_color=self.clr_income_bg, fill_type="solid")
        self.fill_expense = PatternFill(start_color=self.clr_expense_bg, end_color=self.clr_expense_bg, fill_type="solid")
        self.fill_total = PatternFill(start_color=self.clr_total_bg, end_color=self.clr_total_bg, fill_type="solid")
        self.fill_warning = PatternFill(start_color=self.clr_warning_bg, end_color=self.clr_warning_bg, fill_type="solid")
        
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

    def _make_named_styles(self):
        from openpyxl.styles import NamedStyle
        styles = {}
        style_header = NamedStyle(name="header_row")
        style_header.fill = self.fill_header
        style_header.font = self.font_header
        style_header.alignment = self.align_center
        style_header.border = self.border_thin
        styles['header_row'] = style_header
        return styles

    def _apply_header_style(self, ws, row_idx=1):
        for cell in ws[row_idx]:
            cell.fill, cell.font, cell.alignment, cell.border = self.fill_header, self.font_header, self.align_center, self.border_thin

    def _get_workbook(self):
        if os.path.exists(self.master_path):
            try:
                return openpyxl.load_workbook(self.master_path)
            except Exception as e:
                logger.warning(f"Workbook corrupted or unreadable: {e}, creating new.")
                return openpyxl.Workbook()
        wb = openpyxl.Workbook()
        if "Sheet" in wb.sheetnames:
            wb.remove(wb["Sheet"])
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
                        try:
                            if os.path.exists(temp_path):
                                os.remove(temp_path)
                        except Exception:
                            pass
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
        SPECIAL_ORDER = ["ВСЕ ОПЕРАЦИИ", "ДАШБОРД", "АНАЛИТИКА", "СВОД"]
        def sheet_key(name):
            if "." in name:
                try:
                    parts = name.split(".")
                    return (0, int(parts[1]), int(parts[0]), 0)
                except:
                    return (0, 99, 99, 0)
            priority = SPECIAL_ORDER.index(name) if name in SPECIAL_ORDER else 99
            return (1, 0, 0, priority)

        sheet_names = sorted(wb.sheetnames, key=sheet_key)
        for i, name in enumerate(sheet_names):
            current_idx = wb.sheetnames.index(name)
            offset = i - current_idx
            if offset != 0:
                wb.move_sheet(name, offset=offset)

    def _auto_adjust_columns(self, ws):
        max_row = ws.max_row
        max_col = ws.max_column
        if max_row == 0 or max_col == 0: return
        col_max_lengths = [0] * max_col
        numeric_keywords = ['приход', 'расход', 'комиссия', 'итог', 'посредник']
        numeric_cols = set()
        for col_idx, cell in enumerate(ws[1], start=1):
            if cell.value:
                val_lower = str(cell.value).lower()
                if any(kw in val_lower for kw in numeric_keywords):
                    numeric_cols.add(col_idx)
        for row in ws.iter_rows(min_row=1, max_row=min(100, max_row), values_only=True):
            for i, val in enumerate(row):
                if val is not None:
                    length = len(str(val))
                    if length > col_max_lengths[i]: col_max_lengths[i] = length
        for i in range(max_col):
            column_index = i + 1
            column_letter = get_column_letter(column_index)
            max_length = col_max_lengths[i]
            if column_index in numeric_cols:
                width = (max_length * 1.1) + 6
                ws.column_dimensions[column_letter].width = max(width, 15)
            else:
                width = max_length + 4
                ws.column_dimensions[column_letter].width = min(width, 35)

    def write_daily_data(self, date, employee_rows, wb=None):
        should_save = False
        if wb is None:
            wb = self._get_workbook()
            should_save = True
        sh_name = date.strftime("%d.%m")
        if sh_name in wb.sheetnames: del wb[sh_name]
        ws = wb.create_sheet(sh_name)
        if 'header_row' not in wb.named_styles:
            styles = self._make_named_styles()
            for s in styles.values():
                wb.add_named_style(s)
        headers = ["Дата", "Источник", "ЗАКАЗЧИК", "ИСПОЛНИТЕЛЬ", "Приход", "Расход", "Комиссия", "ИТОГ", "% посредника", "посредник 1(кэш)", "посредник 2", "Фильтры"]
        ws.append(headers)
        for cell in ws[1]: cell.style = 'header_row'
        ws.freeze_panes = 'A2'
        
        warning_rows = []
        for idx, r in enumerate(employee_rows):
            # Track row index for warnings (Excel is 1-indexed, headers are row 1)
            if r.get('is_template_warning'):
                warning_rows.append(ws.max_row + 1)
            
            row_vals = [
                date.strftime("%d.%m.%Y"), 
                r.get('Источник', ''),
                r.get('ЗАКАЗЧИК (название проекта, наименование ЮЛ)', ''),
                r.get('ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)', ''), 
                float(r.get('сумма платежа ПРИХОД', 0)),
                float(r.get('сумма платежа РАСХОД', 0)),
                float(r.get('комиссия', 0)),
                float(r.get('ИТОГ', 0)),
                float(r.get('% посредника', 0)),
                float(r.get('посредник 1(кэш)', 0)),
                float(r.get('посредник 2', 0)),
                r.get('фильтры', '')
            ]
            ws.append(row_vals)

        max_row = ws.max_row
        numeric_keywords = ['приход', 'расход', 'комиссия', 'итог', 'посредник']
        numeric_cols, income_col, expense_col, commission_col, total_col = set(), -1, -1, -1, -1
        for col_idx, cell in enumerate(ws[1], start=1):
            if cell.value:
                val_lower = str(cell.value).lower()
                if any(kw in val_lower for kw in numeric_keywords): numeric_cols.add(col_idx)
                if 'приход' in val_lower: income_col = col_idx
                elif 'расход' in val_lower: expense_col = col_idx
                elif 'итог' in val_lower: total_col = col_idx
                elif 'комисси' in val_lower and 'посред' not in val_lower: commission_col = col_idx

        fill_yellow = PatternFill(patternType='solid', fgColor="FFFF00")
        for r_idx, row_cells in enumerate(ws.iter_rows(min_row=2, max_row=max_row)):
            is_odd = (r_idx + 1) % 2 == 1
            fill_row = self.fill_odd if is_odd else self.fill_even
            
            # Check if this row is flagged for template warning
            is_warning = (r_idx + 2) in warning_rows
            num_fmt = '#,##0.00'
            commission_val = abs(float(row_cells[commission_col - 1].value or 0)) if commission_col > 0 else 0
            income_val     = float(row_cells[income_col - 1].value or 0) if income_col > 0 else 0
            expense_val    = abs(float(row_cells[expense_col - 1].value or 0)) if expense_col > 0 else 0
            total_val      = abs(float(row_cells[total_col - 1].value or 0)) if total_col > 0 else 0
            amount_val     = income_val if income_val != 0 else expense_val
            is_math_error = (commission_val == 0 and amount_val > 0.02 and (total_val < 0.02 or abs(amount_val - total_val) > 0.02))

            for c_idx, cell in enumerate(row_cells, start=1):
                cell.border = self.border_thin
                if c_idx in numeric_cols:
                    val = cell.value if cell.value else 0
                    if c_idx == income_col and val > 0.01:
                        cell.fill, cell.font = self.fill_income, self.font_income
                    elif c_idx == expense_col and abs(val) > 0.01:
                        cell.fill, cell.font = self.fill_expense, self.font_expense
                    else:
                        cell.fill = fill_yellow if is_math_error and c_idx not in (income_col, expense_col) else fill_row
                        cell.font = self.font_standard
                    # ORANGE HIGHLIGHT for Source cell if warning
                    if is_warning and c_idx == 2: # "Источник" column
                        cell.fill = self.fill_warning
                    cell.alignment, cell.number_format = self.align_right, num_fmt
                else:
                    cell.fill = fill_yellow if is_math_error and c_idx not in (income_col, expense_col) else fill_row
                    # ORANGE HIGHLIGHT for Source cell if warning
                    if is_warning and c_idx == 2:
                        cell.fill = self.fill_warning
                    cell.font, cell.alignment = self.font_standard, self.align_left

        total_row = max_row + 1
        total_label = ws.cell(total_row, 1, "ИТОГО:")
        total_label.font, total_label.fill, total_label.border = self.font_total, self.fill_total, self.border_medium
        for c in range(1, ws.max_column + 1):
            if c in numeric_cols:
                header_val = str(ws.cell(1, c).value).lower() if ws.cell(1, c).value else ""
                if any(kw in header_val for kw in ['приход', 'расход', 'комиссия', 'итог']):
                    let = get_column_letter(c)
                    cell = ws.cell(total_row, c)
                    cell.value = f"=SUM({let}2:{let}{total_row-1})"
                    cell.fill, cell.font, cell.border, cell.number_format = self.fill_total, self.font_total, self.border_medium, '#,##0.00'
        self._auto_adjust_columns(ws)
        if should_save: self._save_workbook(wb)

    def write_report(self, data: List[Dict[str, Any]], output_path: Path, template_errors: List[Dict[str, Any]] = None) -> bool:
        try:
            data_by_date = {}
            for row in data:
                date_str = row.get('Дата', '')
                if not date_str: continue
                if date_str not in data_by_date: data_by_date[date_str] = []
                data_by_date[date_str].append(row)
            self.master_path = str(output_path)
            wb = self._get_workbook()
            for d_str, rows in sorted(data_by_date.items()):
                try:
                    dt = datetime.strptime(d_str, "%d.%m.%Y")
                    self.write_daily_data(dt, rows, wb=wb)
                except Exception as e: logger.error(f"Failed to write date {d_str}: {e}")
            if "ОШИБКИ ШАБЛОНА" in wb.sheetnames: del wb["ОШИБКИ ШАБЛОНА"]
            self._save_workbook(wb)
            return True
        except Exception as e:
            logger.error(f"Failed to write report to {output_path}: {e}")
            return False

