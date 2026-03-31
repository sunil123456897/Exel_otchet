import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
import openpyxl
from openpyxl.utils import get_column_letter
from openpyxl.styles import PatternFill
from .interfaces import IExporter
from .export_styles import ExcelStyles

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
        if os.path.exists(self.master_path):
            try: return openpyxl.load_workbook(self.master_path)
            except: return openpyxl.Workbook()
        wb = openpyxl.Workbook()
        if "Sheet" in wb.sheetnames: wb.remove(wb["Sheet"])
        return wb

    def _save_workbook(self, wb):
        SPECIAL_ORDER = ["ВСЕ ОПЕРАЦИИ", "ДАШБОРД", "АНАЛИТИКА", "СВОД"]
        def key(n):
            if "." in n:
                try: p = n.split("."); return (0, int(p[1]), int(p[0]), 0)
                except: return (0, 99, 99, 0)
            return (1, 0, 0, SPECIAL_ORDER.index(n) if n in SPECIAL_ORDER else 99)
        for i, n in enumerate(sorted(wb.sheetnames, key=key)):
            curr = wb.sheetnames.index(n); offset = i - curr
            if offset != 0: wb.move_sheet(n, offset=offset)
        
        tmp = self.master_path + ".tmp"
        try:
            wb.save(tmp)
            if os.path.exists(tmp):
                if os.path.exists(self.master_path):
                    try: os.replace(tmp, self.master_path)
                    except PermissionError:
                        if os.path.exists(tmp): os.remove(tmp)
                        import tkinter.messagebox as mb
                        mb.showerror("Файл занят", f"Закройте '{self.master_path}' в Excel!")
                else: os.rename(tmp, self.master_path)
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
        sh_name = date.strftime("%d.%m")
        if sh_name in wb.sheetnames: del wb[sh_name]
        ws = wb.create_sheet(sh_name)
        
        headers = ["Дата", "Источник", "ЗАКАЗЧИК", "ИСПОЛНИТЕЛЬ", "Приход", "Расход", "Комиссия", "ИТОГ", "% посредника", "посредник 1(кэш)", "посредник 2", "Фильтры"]
        ws.append(headers); self._apply_header_style(ws); ws.freeze_panes = 'A2'
        
        warning_rows = []
        for r in rows:
            if r.get('is_template_warning'): warning_rows.append(ws.max_row + 1)
            ws.append([date.strftime("%d.%m.%Y"), r.get('Источник', ''), r.get('ЗАКАЗЧИК (название проекта, наименование ЮЛ)', ''), r.get('ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)', ''), float(r.get('сумма платежа ПРИХОД', 0)), float(r.get('сумма платежа РАСХОД', 0)), float(r.get('комиссия', 0)), float(r.get('ИТОГ', 0)), float(r.get('% посредника', 0)), float(r.get('посредник 1(кэш)', 0)), float(r.get('посредник 2', 0)), r.get('фильтры', '')])

        num_kw = ['приход', 'расход', 'комиссия', 'итог', 'посредник']
        cols = {kw: -1 for kw in num_kw}; num_indices = set()
        for i, cell in enumerate(ws[1], 1):
            val = str(cell.value or "").lower()
            if any(kw in val for kw in num_kw): num_indices.add(i)
            for kw in num_kw:
                if kw in val:
                    if kw == 'комиссия' and 'посред' in val: continue
                    cols[kw] = i
        
        fill_yellow = PatternFill(patternType='solid', fgColor="FFFF00")
        for r_idx, row_cells in enumerate(ws.iter_rows(min_row=2, max_row=ws.max_row)):
            is_warning = (r_idx + 2) in warning_rows
            fill_row = self.st.fill_odd if (r_idx + 1) % 2 == 1 else self.st.fill_even
            
            c_val = abs(float(row_cells[cols['комиссия']-1].value or 0)) if cols['комиссия']>0 else 0
            i_val = float(row_cells[cols['приход']-1].value or 0) if cols['приход']>0 else 0
            e_val = abs(float(row_cells[cols['расход']-1].value or 0)) if cols['расход']>0 else 0
            t_val = abs(float(row_cells[cols['итог']-1].value or 0)) if cols['итог']>0 else 0
            amt = i_val if i_val != 0 else e_val
            is_math_err = (c_val == 0 and amt > 0.02 and (t_val < 0.02 or abs(amt - t_val) > 0.02))

            for c_idx, cell in enumerate(row_cells, 1):
                cell.border = self.st.border_thin
                if c_idx in num_indices:
                    val = cell.value or 0
                    if c_idx == cols['приход'] and val > 0.01: cell.fill, cell.font = self.st.fill_income, self.st.font_income
                    elif c_idx == cols['расход'] and abs(val) > 0.01: cell.fill, cell.font = self.st.fill_expense, self.st.font_expense
                    else: cell.fill, cell.font = (fill_yellow if is_math_err and c_idx not in (cols['приход'], cols['расход']) else fill_row), self.st.font_standard
                    if is_warning and c_idx == 2: cell.fill = self.st.fill_warning
                    fmt = '0.00"%"' if c_idx == cols.get('% посредника', -1) or '%' in str(ws.cell(1, c_idx).value) else '#,##0.00'
                    cell.alignment, cell.number_format = self.st.align_right, fmt
                else:
                    cell.fill = self.st.fill_warning if is_warning and c_idx == 2 else fill_row
                    cell.font, cell.alignment = self.st.font_standard, self.st.align_left

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
        try:
            dbd = {}
            for r in data:
                d = r.get('Дата', '')
                if d: dbd.setdefault(d, []).append(r)
            self.master_path = str(path); wb = self._get_workbook()
            for d_str, rows in sorted(dbd.items()):
                try: self.write_daily_data(datetime.strptime(d_str, "%d.%m.%Y"), rows, wb=wb)
                except Exception as e: logger.error(f"Date error {d_str}: {e}")
            if "ОШИБКИ ШАБЛОНА" in wb.sheetnames: del wb["ОШИБКИ ШАБЛОНА"]
            self._save_workbook(wb); return True
        except Exception as e: logger.error(f"Write error: {e}"); return False
