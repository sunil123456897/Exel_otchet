import os
import logging
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

    def _make_named_styles(self):
        from openpyxl.styles import NamedStyle

        styles = {}

        style_header = NamedStyle(name="header_row")
        style_header.fill = self.fill_header
        style_header.font = self.font_header
        style_header.alignment = self.align_center
        style_header.border = self.border_thin
        styles['header_row'] = style_header

        style_odd = NamedStyle(name="odd_row")
        style_odd.fill = self.fill_odd
        style_odd.font = self.font_standard
        style_odd.alignment = self.align_left
        style_odd.border = self.border_thin
        styles['odd_row'] = style_odd

        style_even = NamedStyle(name="even_row")
        style_even.fill = self.fill_even
        style_even.font = self.font_standard
        style_even.alignment = self.align_left
        style_even.border = self.border_thin
        styles['even_row'] = style_even

        style_income = NamedStyle(name="income_cell")
        style_income.fill = self.fill_income
        style_income.font = self.font_income
        style_income.alignment = self.align_right
        style_income.border = self.border_thin
        style_income.number_format = '#,##0.00'
        styles['income_cell'] = style_income

        style_expense = NamedStyle(name="expense_cell")
        style_expense.fill = self.fill_expense
        style_expense.font = self.font_expense
        style_expense.alignment = self.align_right
        style_expense.border = self.border_thin
        style_expense.number_format = '#,##0.00'
        styles['expense_cell'] = style_expense

        style_standard_num_odd = NamedStyle(name="standard_num_odd")
        style_standard_num_odd.fill = self.fill_odd
        style_standard_num_odd.font = self.font_standard
        style_standard_num_odd.alignment = self.align_right
        style_standard_num_odd.border = self.border_thin
        style_standard_num_odd.number_format = '#,##0.00'
        styles['standard_num_odd'] = style_standard_num_odd

        style_standard_num_even = NamedStyle(name="standard_num_even")
        style_standard_num_even.fill = self.fill_even
        style_standard_num_even.font = self.font_standard
        style_standard_num_even.alignment = self.align_right
        style_standard_num_even.border = self.border_thin
        style_standard_num_even.number_format = '#,##0.00'
        styles['standard_num_even'] = style_standard_num_even

        style_total = NamedStyle(name="total_cell")
        style_total.fill = self.fill_total
        style_total.font = self.font_total
        style_total.border = self.border_medium
        style_total.number_format = '#,##0.00'
        styles['total_cell'] = style_total

        return styles

    def _apply_header_style(self, ws, row_idx=1):
        for cell in ws[row_idx]:
            cell.fill, cell.font, cell.alignment, cell.border = self.fill_header, self.font_header, self.align_center, self.border_thin

    def _get_workbook(self):
        if os.path.exists(self.master_path):
            try:
                return openpyxl.load_workbook(self.master_path)
            except Exception as e:
                # FIXED: bare except
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
            # FIXED: 2
            current_idx = wb.sheetnames.index(name)
            offset = i - current_idx
            if offset != 0:
                wb.move_sheet(name, offset=offset)

    def _auto_adjust_columns(self, ws):
        max_row = ws.max_row
        max_col = ws.max_column

        if max_row == 0 or max_col == 0:
            return
            
        col_max_lengths = [0] * max_col

        # FIXED: 12
        numeric_keywords = ['приход', 'расход', 'комиссия', 'итог', 'посредник']
        numeric_cols = set()

        # Determine numeric columns based on row 1 headers
        for col_idx, cell in enumerate(ws[1], start=1):
            if cell.value:
                val_lower = str(cell.value).lower()
                if any(kw in val_lower for kw in numeric_keywords):
                    numeric_cols.add(col_idx)

        # Sample rows to avoid checking every cell in large sheets.
        # Check first 100 rows (headers, initial data) and last 100 rows (totals).
        for row in ws.iter_rows(min_row=1, max_row=min(100, max_row), values_only=True):
            for i, val in enumerate(row):
                if val is not None:
                    length = len(str(val))
                    if length > col_max_lengths[i]:
                        col_max_lengths[i] = length

        if max_row > 100:
            for row in ws.iter_rows(min_row=max(101, max_row - 99), max_row=max_row, values_only=True):
                for i, val in enumerate(row):
                    if val is not None:
                        length = len(str(val))
                        if length > col_max_lengths[i]:
                            col_max_lengths[i] = length

        for i in range(max_col):
            column_index = i + 1
            column_letter = get_column_letter(column_index)
            max_length = col_max_lengths[i]

            if column_index in numeric_cols:
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
        
        if 'header_row' not in wb.named_styles:
            styles = self._make_named_styles()
            for s in styles.values():
                wb.add_named_style(s)

        headers = ["Дата", "Сотрудник", "ЗАКАЗЧИК", "ИСПОЛНИТЕЛЬ", "Приход", "Расход", "Комиссия", "ИТОГ", "% посредника", "посредник 1(кэш)", "посредник 2", "Фильтры"]
        ws.append(headers)
        for cell in ws[1]:
            cell.style = 'header_row'
        ws.freeze_panes = 'A2'
        
        for idx, r in enumerate(employee_rows):
            # Use Decimal objects directly where possible, openpyxl supports them
            row_vals = [
                date.strftime("%d.%m.%Y"), 
                r.get('Сотрудник', ''), 
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
        fill_row_styles = [self.fill_odd, self.fill_even]
        font_row_styles = [self.font_standard, self.font_standard]

        # FIXED: 12
        numeric_keywords = ['приход', 'расход', 'комиссия', 'итог', 'посредник']
        numeric_cols = set()
        income_col = -1
        expense_col = -1

        for col_idx, cell in enumerate(ws[1], start=1):
            if cell.value:
                val_lower = str(cell.value).lower()
                if any(kw in val_lower for kw in numeric_keywords):
                    numeric_cols.add(col_idx)
                if 'приход' in val_lower:
                    income_col = col_idx
                elif 'расход' in val_lower:
                    expense_col = col_idx

        for r_idx, row in enumerate(ws.iter_rows(min_row=2, max_row=max_row)):
            is_odd = (r_idx + 1) % 2 == 1
            fill_row = self.fill_odd if is_odd else self.fill_even
            num_fmt = '#,##0.00'

            for c_idx, cell in enumerate(row, start=1):
                if c_idx in numeric_cols:
                    val = cell.value if cell.value else 0
                    if c_idx == income_col and val > 0.01:
                        cell.fill = self.fill_income
                        cell.font = self.font_income
                        cell.alignment = self.align_right
                        cell.border = self.border_thin
                        cell.number_format = num_fmt
                    elif c_idx == expense_col and abs(val) > 0.01:
                        cell.fill = self.fill_expense
                        cell.font = self.font_expense
                        cell.alignment = self.align_right
                        cell.border = self.border_thin
                        cell.number_format = num_fmt
                    else:
                        cell.fill = fill_row
                        cell.font = self.font_standard
                        cell.alignment = self.align_right
                        cell.border = self.border_thin
                        cell.number_format = num_fmt
                else:
                    cell.fill = fill_row
                    cell.font = self.font_standard
                    cell.alignment = self.align_left
                    cell.border = self.border_thin

        total_row = max_row + 1
        total_label = ws.cell(total_row, 1, "ИТОГО:")
        total_label.font = self.font_total
        total_label.fill = self.fill_total
        total_label.border = self.border_medium

        # Apply formulas to numeric columns containing 'приход', 'расход', 'комиссия', 'итог'
        for c in range(1, ws.max_column + 1):
            if c in numeric_cols:
                header_val = str(ws.cell(1, c).value).lower() if ws.cell(1, c).value else ""
                if any(kw in header_val for kw in ['приход', 'расход', 'комиссия', 'итог']):
                    let = get_column_letter(c)
                    cell = ws.cell(total_row, c)
                    cell.value = f"=SUM({let}2:{let}{total_row-1})"
                    cell.fill = self.fill_total
                    cell.font = self.font_total
                    cell.border = self.border_medium
                    cell.number_format = '#,##0.00'

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
