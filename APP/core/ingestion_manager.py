import os
import hashlib
import logging
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import openpyxl
from pyxlsb import open_workbook as open_xlsb


from core.interfaces import IDataSource
class IngestionEngine(IDataSource):
    def __init__(self, config_markers: Dict[str, str]):
        self.markers = config_markers
        self.aliases = {'amount': ['сумма платежа', 'бн рф руб', 'бн', 'приход', 'расход'], 'income': ['приход'], 'expense': ['расход'], 'customer': ['заказчик', 'агент'], 'contractor': ['исполнитель', 'вторая сторона'], 'total': ['итог', 'итоги дня', 'итог дня', 'формула'], 'commission': ['комиссия', 'ставка/цена'], 'percent_broker': ['% посредника', '%'], 'broker1': ['посредник 1(кэш)', 'посредник 1', 'комиссия посредника 1', 'приходный кассовый ордер'], 'broker2': ['посредник 2', 'комиссия посредника 2', '%.1'], 'filters': ['фильтры', 'фильтр', 'filter']}
        self.xlsx_reader = XlsxReader(self.markers, self.aliases)
        self.xlsb_reader = XlsbReader(self.markers, self.aliases)

    def get_available_dates(self, file_path: Path) -> List[str]:
        dates = set()
        try:
            suffix = file_path.suffix.lower()
            if suffix == '.xlsx':
                wb = openpyxl.load_workbook(file_path, read_only=True, keep_links=False)
                for ws in wb.worksheets:
                    if ws.sheet_state == 'visible':
                        d = extract_date_from_sheet(ws.title)
                        if d: dates.add(d)
                wb.close()
            elif suffix == '.xlsb':
                with open_xlsb(str(file_path)) as wb:
                    for s in wb.sheets:
                        d = extract_date_from_sheet(s)
                        if d: dates.add(d)
        except: pass
        return sorted(list(dates))

    def scan_directory(self, root_path: Path) -> List[Dict[str, Any]]:
        res = []
        if not root_path.exists(): return res
        for root, _, files in os.walk(root_path):
            for f in files:
                if f.startswith('~$') or not f.lower().endswith(('.xlsx', '.xlsb')): continue
                p = (Path(root) / f).resolve()
                try:
                    stat = os.stat(p)
                    with open(p, 'rb') as f_io: fp = hashlib.md5(f_io.read(8192)).hexdigest()
                    res.append({"path": str(p), "id": stat.st_ino, "fp": fp, "size": stat.st_size, "mtime": stat.st_mtime})
                except: pass
        return res

    def read_file(self, file_path: Path) -> List[Dict[str, Any]]:
        if not file_path.exists(): return []
        s = file_path.suffix.lower()
        if s == '.xlsx': return self.xlsx_reader.read(file_path)
        if s == '.xlsb': return self.xlsb_reader.read(file_path)
        return []

"""
Module: ingestion_date_utils
Description: Part of the Master-Report v5.5 architecture.
This module provides specialized functionality for the financial consolidation system.
Maintained for high modularity, testability, and structural integrity.
"""
import re
from datetime import datetime, timedelta
from typing import Optional

def extract_date_from_sheet(sheet_name: str) -> Optional[str]:
    pat = re.compile(r'(^|[^0-9])(\d{1,2})[.,](\d{1,2})([.,](\d{4}))?([^0-9]|$)')
    m = pat.search(sheet_name.strip())
    if m:
        try:
            curr = datetime.now()
            d, month = int(m.group(2)), int(m.group(3))
            y = int(m.group(5)) if m.group(5) else curr.year
            if not m.group(5) and datetime(curr.year, month, d) > curr + timedelta(days=30): y = curr.year - 1
            return datetime(y, month, d).strftime("%d.%m.%Y")
        except Exception: 
            logging.getLogger(__name__).warning(f"TEMPORAL WARNING: Invalid date in sheet '{sheet_name}' (e.g. Feb 29 in non-leap year)")
            return None
    return None




import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import openpyxl
from pyxlsb import open_workbook as open_xlsb

from core.utils_helpers import to_decimal
from core.data_schemas import FinancialRowSchema

logger = logging.getLogger(__name__)

class ExcelReader:
    def __init__(self, markers: Dict[str, Any], aliases: Dict[str, List[str]]):
        self.markers = markers
        self.aliases = aliases

    def _map_columns(self, header_row: List[Any]) -> Dict[str, int]:
        col_map = {}
        header_values = [str(val).lower() if val is not None else "" for val in header_row]
        
        for key, marker in self.markers.items():
            found_idx = None
            marker_list = marker if isinstance(marker, list) else [marker]
            marker_lowers = [str(m).lower() for m in marker_list]
            
            for idx, val in enumerate(header_values):
                if any(m in val for m in marker_lowers):
                    if key == 'commission' and 'посредник' in val: continue
                    found_idx = idx
                    break
            
            if found_idx is None and key in self.aliases:
                for alt in self.aliases[key]:
                    alt_lower = alt.lower()
                    for idx, val in enumerate(header_values):
                        if alt_lower in val:
                            if key == 'commission' and 'посредник' in val: continue
                            found_idx = idx
                            break
                    if found_idx is not None: break
            if found_idx is not None: col_map[key] = found_idx
        return col_map

    def _process_row(self, row: List[Any], col_map: Dict[str, int], sheet_name: str, row_idx: int, file_path: str) -> Optional[Dict[str, Any]]:
        if not row: return None
        non_empty_vals = [v for v in row if v is not None and str(v).strip() != '']
        if non_empty_vals:
            is_only_numbers = True
            for v in non_empty_vals:
                if isinstance(v, (int, float)): continue
                s = str(v).replace(' ', '').replace(',', '.').replace('-', '')
                if not s: continue
                try: float(s)
                except ValueError:
                    is_only_numbers = False
                    break
            if is_only_numbers: return None
        
        has_data = False
        raw_data = {'_sheet_name': sheet_name, '_row_index': row_idx, '_file_path': os.path.abspath(file_path), 'date': extract_date_from_sheet(sheet_name)}
        for key, col_idx in col_map.items():
            if col_idx < len(row):
                val = row[col_idx]
                if val is not None and val != "": has_data = True
                raw_data[key] = val
            else: raw_data[key] = None
        
        if not has_data: return None
        
        try:
            validated = FinancialRowSchema(**raw_data)
            res = validated.model_dump()
            # Add source info for logging
            res['_source_info'] = f"{os.path.basename(file_path)} | {sheet_name} | Row {row_idx}"
            return res
        except Exception as e:
            logger.error(f"VALIDATION ERROR: {e} | File: {file_path} | Sheet: {sheet_name} | Row: {row_idx}")
            return None

class XlsxReader(ExcelReader):
    def read(self, file_path: Path) -> List[Dict[str, Any]]:
        all_rows = []
        f_path_abs = os.path.abspath(str(file_path))
        try:
            wb = openpyxl.load_workbook(f_path_abs, read_only=True, data_only=True)
            for ws in wb.worksheets:
                if ws.sheet_state != 'visible' or ws.title.startswith('_') or ws.title in ("АНАЛИТИКА", "СВОД"): continue
                
                # First pass: find standard keys (limit scan to first 200 rows for efficiency)
                standard_keys, max_score = set(), 0
                for row in ws.iter_rows(min_row=1, max_row=200, values_only=True):
                    if not row: continue
                    row_values_str = [str(v).lower() for v in row if v is not None]
                    score = sum(1 for m in self.aliases.values() if any(alias.lower() in " ".join(row_values_str) for alias in m))
                    if score >= 4 and score > max_score:
                        max_score = score
                        standard_keys = set(self._map_columns(row).keys())
                
                # Second pass: read data using generator
                active_col_map, current_is_warning = None, False
                for i, row in enumerate(ws.iter_rows(values_only=True)):
                    if not row: continue
                    row_values_str = [str(v).lower() for v in row if v is not None]
                    score = sum(1 for m in self.aliases.values() if any(alias.lower() in " ".join(row_values_str) for alias in m))
                    if score >= 4:
                        active_col_map = self._map_columns(row)
                        current_is_warning = (set(active_col_map.keys()) != standard_keys)
                        continue
                    if active_col_map:
                        row_dict = self._process_row(row, active_col_map, ws.title, i + 1, f_path_abs)
                        if row_dict:
                            row_dict['is_template_warning'] = current_is_warning
                            all_rows.append(row_dict)
        except Exception as e: logger.error(f"Error XLSX {f_path_abs}: {e}")
        return all_rows

class XlsbReader(ExcelReader):
    def read(self, file_path: Path) -> List[Dict[str, Any]]:
        all_rows = []
        f_path_abs = os.path.abspath(str(file_path))
        try:
            with open_xlsb(f_path_abs) as wb:
                for sheet_name in wb.sheets:
                    if sheet_name.startswith('_') or sheet_name in ("АНАЛИТИКА", "СВОД"): continue
                    with wb.get_sheet(sheet_name) as ws:
                        # First pass for standard keys
                        standard_keys, max_score = set(), 0
                        # XLSB row iterator is also a generator
                        for i, row_objs in enumerate(ws.rows()):
                            if i > 200: break
                            row = [cell.v for cell in row_objs]
                            if not row: continue
                            row_values_str = [str(v).lower() for v in row if v is not None]
                            score = sum(1 for m in self.aliases.values() if any(alias.lower() in " ".join(row_values_str) for alias in m))
                            if score >= 4 and score > max_score:
                                max_score = score
                                standard_keys = set(self._map_columns(row).keys())
                        
                        # Second pass for data
                        active_col_map, current_is_warning = None, False
                        for i, row_objs in enumerate(ws.rows()):
                            row = [cell.v for cell in row_objs]
                            if not row: continue
                            row_values_str = [str(v).lower() for v in row if v is not None]
                            score = sum(1 for m in self.aliases.values() if any(alias.lower() in " ".join(row_values_str) for alias in m))
                            if score >= 4:
                                active_col_map = self._map_columns(row)
                                current_is_warning = (set(active_col_map.keys()) != standard_keys)
                                continue
                            if active_col_map:
                                row_dict = self._process_row(row, active_col_map, sheet_name, i + 1, f_path_abs)
                                if row_dict:
                                    row_dict['is_template_warning'] = current_is_warning
                                    all_rows.append(row_dict)
        except Exception as e: logger.error(f"Error XLSB {f_path_abs}: {e}")
        return all_rows




