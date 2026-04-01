import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
import openpyxl
from openpyxl.utils import get_column_letter
from openpyxl.styles import PatternFill
from core.domain.interfaces import IExporter
from core.infra.export_styles import ExcelStyles

logger = logging.getLogger(__name__)

class MasterWriter(IExporter):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        p = config.get('paths', {}) if isinstance(config, dict) else getattr(config, 'paths', {})
        self.master_path = p.get('master_file', 'Master_Report.xlsx')
        if not os.path.isabs(self.master_path) and not os.path.exists(self.master_path) and os.path.exists("Master_Report.xlsx"):
            self.master_path = "Master_Report.xlsx"
        self.st = ExcelStyles()

    def _apply_header_style(self, ws, row_idx=1):
        for cell in ws[row_idx]:
            cell.fill, cell.font, cell.alignment, cell.border = self.st.fill_header, self.st.font_header, self.st.align_center, self.st.border_thin

    def _get_workbook(self):
        path_abs = os.path.abspath(self.master_path)
        if os.path.exists(path_abs):
            try: return openpyxl.load_workbook(path_abs)
            except: return openpyxl.Workbook()
        wb = openpyxl.Workbook()
        if "Sheet" in wb.sheetnames: wb.remove(wb["Sheet"])
        return wb

    def _save_workbook(self, wb):
        SPECIAL_ORDER = ["ВСЕ ОПЕРАЦИИ", "ДАШБОРД", "АНАЛИТИКА", "СВОД"]
        def key(n):
            if "." in n:
                try: 
                    p = n.split(".")
                    if len(p) == 3: # DD.MM.YYYY
                        return (0, int(p[2]), int(p[1]), int(p[0]))
                    return (0, 9999, int(p[1]), int(p[0]))
                except: return (0, 9999, 99, 99)
            return (1, 0, 0, SPECIAL_ORDER.index(n) if n in SPECIAL_ORDER else 99)
        for i, n in enumerate(sorted(wb.sheetnames, key=key)):
            curr = wb.sheetnames.index(n); offset = i - curr
            if offset != 0: wb.move_sheet(n, offset=offset)
        
        path_abs = os.path.abspath(self.master_path)
        tmp = path_abs + ".tmp"
        try:
            wb.save(tmp)
            if os.path.exists(tmp):
                if os.path.exists(path_abs):
                    try: os.replace(tmp, path_abs)
                    except PermissionError:
                        if os.path.exists(tmp): os.remove(tmp)
                        import tkinter.messagebox as mb
                        mb.showerror("Файл занят", f"Закройте '{self.master_path}' в Excel!")
                else: os.rename(tmp, path_abs)
        except Exception as e: logger.error(f"Save failed: {e}")

    def _auto_adjust(self, ws):
        numeric_keywords = ['приход', 'расход', 'комиссия', 'итог', 'посредник']
        for i in range(1, ws.max_column + 1):
            max_len = 0
            for row in ws.iter_rows(min_row=1, max_row=min(100, ws.max_row), values_only=True):
                if row[i-1]: max_len = max(max_len, len(str(row[i-1])))
            let = get_column_letter(i); header = str(ws.cell(1, i).value or "").lower()
            if any(kw in header for kw in numeric_keywords): ws.column_dimensions[let].width = max((max_len * 1.1) + 6, 15)
            else: ws.column_dimensions[let].width = min(max_len + 4, 35)

    def write_daily_data(self, date, rows, wb=None):
        should_save = False
        if wb is None: wb = self._get_workbook(); should_save = True
        sh_name = date.strftime("%d.%m.%Y")
        if sh_name in wb.sheetnames: del wb[sh_name]
        ws = wb.create_sheet(sh_name)
        
        headers = ["Дата", "Источник", "ЗАКАЗЧИК", "ИСПОЛНИТЕЛЬ", "Приход", "Расход", "Комиссия", "ИТОГ", "% посредника", "посредник 1(кэш)", "посредник 2", "Фильтры"]
        ws.append(headers); self._apply_header_style(ws); ws.freeze_panes = 'A2'
        
        warning_rows = []
        for r in rows:
            if r.get('is_template_warning'): warning_rows.append(ws.max_row + 1)
            ws.append([date.strftime("%d.%m.%Y"), r.get('Источник', ''), r.get('ЗАКАЗЧИК (название проекта, наименование ЮЛ)', ''), r.get('ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)', ''), float(r.get('сумма платежа ПРИХОД', 0)), float(r.get('сумма платежа РАСХОД', 0)), float(r.get('комиссия', 0)), float(r.get('ИТОГ', 0)), r.get('% посредника', 0), float(r.get('посредник 1(кэш)', 0)), float(r.get('посредник 2', 0)), r.get('фильтры', '')])

        num_kw = ['приход', 'расход', 'комиссия', 'итог', 'посредник']
        cols = {kw: -1 for kw in num_kw}; num_indices = set()
        for i, cell in enumerate(ws[1], 1):
            val = str(cell.value or "").lower()
            if any(kw in val for kw in num_kw): num_indices.add(i)
            for kw in num_kw:
                if kw in val:
                    if kw == 'комиссия' and 'посред' in val: continue
                    cols[kw] = i
                    
        percent_broker_col = -1
        for i, cell in enumerate(ws[1], 1):
            if str(cell.value or "").lower() == '% посредника':
                percent_broker_col = i
                break
        
        fill_yellow = PatternFill(patternType='solid', fgColor="FFFF00")
        for r_idx, row_cells in enumerate(ws.iter_rows(min_row=2, max_row=ws.max_row)):
            is_warning = (r_idx + 2) in warning_rows
            fill_row = self.st.fill_odd if (r_idx + 1) % 2 == 1 else self.st.fill_even
            
            i_val = float(row_cells[cols['приход']-1].value or 0) if cols['приход']>0 else 0
            e_val = float(row_cells[cols['расход']-1].value or 0) if cols['расход']>0 else 0
            t_val = float(row_cells[cols['итог']-1].value or 0) if cols['итог']>0 else 0
            
            c_val = abs(float(row_cells[cols['комиссия']-1].value or 0)) if cols['комиссия']>0 else 0
            
            # The balance impact: income adds to total, expense subtracts from total
            expected_total = i_val - e_val
            has_money = abs(i_val) > 0.02 or abs(e_val) > 0.02
            
            # Trusted logic: if commission exists, we skip math check.
            is_math_err = (c_val == 0 and has_money and (abs(t_val) < 0.02 or abs(expected_total - t_val) > 0.02))

            for c_idx, cell in enumerate(row_cells, 1):
                cell.border = self.st.border_thin
                
                # Base fill logic: math error (yellow) takes priority for the whole row, then alternate rows.
                # Warning (red) is applied ONLY to the specific 'Источник' cell later to avoid hiding yellow rows.
                if is_math_err:
                    cell.fill = fill_yellow
                else:
                    cell.fill = fill_row
                cell.font = self.st.font_standard

                is_percent_err = False
                if c_idx in num_indices:
                    val = cell.value or 0
                    if c_idx == cols['приход'] and isinstance(val, (int, float)) and val > 0.01:
                        cell.fill, cell.font = self.st.fill_income, self.st.font_income
                    elif c_idx == cols['расход'] and isinstance(val, (int, float)) and abs(val) > 0.01:
                        cell.fill, cell.font = self.st.fill_expense, self.st.font_expense
                    
                    if c_idx == percent_broker_col:
                        try:
                            v_float = float(val)
                            if abs(v_float) <= 1.0:
                                cell.value = v_float
                            elif abs(v_float) <= 100.0:
                                cell.value = v_float / 100.0
                            else:
                                is_percent_err = True
                                cell.value = v_float
                        except (ValueError, TypeError):
                            is_percent_err = True
                            cell.value = val
                        
                        if is_percent_err: 
                            cell.fill = self.st.fill_warning
                    
                    # Formatting rules: % for commission and percent_broker, standard for others
                    h = str(ws.cell(1, c_idx).value or "").lower()
                    if '%' in h and 'посред' in h:
                        if is_percent_err:
                            fmt = 'General' if isinstance(cell.value, str) else '#,##0.00'
                        else:
                            fmt = '0.00%'
                    elif 'комиссия' in h:
                        fmt = '0.00"%"'
                    else:
                        fmt = '#,##0.00'
                        
                    cell.alignment, cell.number_format = self.st.align_right, fmt
                    
                    # Apply template warning red color ONLY to 'Источник' (c_idx == 2)
                    if is_warning and c_idx == 2:
                        cell.fill = self.st.fill_warning
                else:
                    if is_warning and c_idx == 2:
                        cell.fill = self.st.fill_warning
                    cell.alignment = self.st.align_left

        total_row = ws.max_row + 1
        total_label = ws.cell(total_row, 1, "ИТОГО:")
        total_label.font, total_label.fill, total_label.border = self.st.font_total, self.st.fill_total, self.st.border_medium
        for c in range(1, ws.max_column + 1):
            if c in num_indices:
                h = str(ws.cell(1, c).value or "").lower()
                if any(kw in h for kw in ['приход', 'расход', 'итог', 'посредник']) and '%' not in h:
                    let = get_column_letter(c); cell = ws.cell(total_row, c)
                    cell.value = f"=SUM({let}2:{let}{total_row-1})"
                    cell.fill, cell.font, cell.border, cell.number_format = self.st.fill_total, self.st.font_total, self.st.border_medium, '#,##0.00'
        self._auto_adjust(ws)
        if should_save: self._save_workbook(wb)

    def write_report(self, data: List[Dict[str, Any]], path: Path, template_errors: List[Dict[str, Any]] = None) -> bool:
        # Fix 6: Early Lock Check
        p_str = os.path.abspath(str(path))
        if os.path.exists(p_str):
            try:
                with open(p_str, 'a') as f: pass
            except (IOError, PermissionError):
                import tkinter.messagebox as mb
                mb.showerror("Файл занят", f"Закройте '{p_str}' в Excel перед началом!")
                return False
        
        try:
            dbd = {}
            for r in data:
                d = r.get('Дата')
                if not d:
                    d = "01.01.1900"
                    logger.warning(f"TEMPORAL FALLBACK: Row from {r.get('Источник')} has no valid date. Using 01.01.1900.")
                dbd.setdefault(d, []).append(r)
            self.master_path = str(path); wb = self._get_workbook()
            for d_str, rows in sorted(dbd.items()):
                try: self.write_daily_data(datetime.strptime(d_str, "%d.%m.%Y"), rows, wb=wb)
                except Exception as e: logger.error(f"Date error {d_str}: {e}")
            if "ОШИБКИ ШАБЛОНА" in wb.sheetnames: del wb["ОШИБКИ ШАБЛОНА"]
            self._save_workbook(wb); return True
        except Exception as e: logger.error(f"Write error: {e}"); return False

