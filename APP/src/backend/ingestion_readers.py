import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import openpyxl
from pyxlsb import open_workbook as open_xlsb
from .ingestion_date_utils import extract_date_from_sheet
from .utils_helpers import to_decimal

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
        res = {'_sheet_name': sheet_name, '_row_index': row_idx, '_file_path': file_path, 'date': extract_date_from_sheet(sheet_name)}
        for key, col_idx in col_map.items():
            if col_idx < len(row):
                val = row[col_idx]
                if val is not None and val != "": has_data = True
                financial_keys = {'amount', 'income', 'expense', 'total', 'commission', 'percent_broker', 'broker1', 'broker2'}
                res[key] = to_decimal(val) if key in financial_keys else val
            else: res[key] = None
        return res if has_data else None

class XlsxReader(ExcelReader):
    def read(self, file_path: Path) -> List[Dict[str, Any]]:
        all_rows = []
        try:
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            for ws in wb.worksheets:
                if ws.sheet_state != 'visible' or ws.title.startswith('_') or ws.title in ("АНАЛИТИКА", "СВОД"): continue
                rows = list(ws.iter_rows(values_only=True))
                standard_keys, max_score = set(), 0
                for row in rows:
                    if not row: continue
                    row_values_str = [str(v).lower() for v in row if v is not None]
                    score = sum(1 for m in self.aliases.values() if any(alias.lower() in " ".join(row_values_str) for alias in m))
                    if score >= 4 and score > max_score:
                        max_score = score
                        standard_keys = set(self._map_columns(row).keys())
                active_col_map, current_is_warning = None, False
                for i, row in enumerate(rows):
                    if not row: continue
                    row_values_str = [str(v).lower() for v in row if v is not None]
                    score = sum(1 for m in self.aliases.values() if any(alias.lower() in " ".join(row_values_str) for alias in m))
                    if score >= 4:
                        active_col_map = self._map_columns(row)
                        current_is_warning = (set(active_col_map.keys()) != standard_keys)
                        continue
                    if active_col_map:
                        row_dict = self._process_row(row, active_col_map, ws.title, i + 1, str(file_path))
                        if row_dict:
                            row_dict['is_template_warning'] = current_is_warning
                            all_rows.append(row_dict)
        except Exception as e: logger.error(f"Error XLSX {file_path}: {e}")
        return all_rows

class XlsbReader(ExcelReader):
    def read(self, file_path: Path) -> List[Dict[str, Any]]:
        all_rows = []
        try:
            with open_xlsb(str(file_path)) as wb:
                for sheet_name in wb.sheets:
                    if sheet_name.startswith('_') or sheet_name in ("АНАЛИТИКА", "СВОД"): continue
                    with wb.get_sheet(sheet_name) as ws:
                        rows_objs_list = list(ws.rows())
                        standard_keys, max_score = set(), 0
                        for row_objs in rows_objs_list:
                            row = [cell.v for cell in row_objs]
                            if not row: continue
                            row_values_str = [str(v).lower() for v in row if v is not None]
                            score = sum(1 for m in self.aliases.values() if any(alias.lower() in " ".join(row_values_str) for alias in m))
                            if score >= 4 and score > max_score:
                                max_score = score
                                standard_keys = set(self._map_columns(row).keys())
                        active_col_map, current_is_warning = None, False
                        for i, row_objs in enumerate(rows_objs_list):
                            row = [cell.v for cell in row_objs]
                            if not row: continue
                            row_values_str = [str(v).lower() for v in row if v is not None]
                            score = sum(1 for m in self.aliases.values() if any(alias.lower() in " ".join(row_values_str) for alias in m))
                            if score >= 4:
                                active_col_map = self._map_columns(row)
                                current_is_warning = (set(active_col_map.keys()) != standard_keys)
                                continue
                            if active_col_map:
                                row_dict = self._process_row(row, active_col_map, sheet_name, i + 1, str(file_path))
                                if row_dict:
                                    row_dict['is_template_warning'] = current_is_warning
                                    all_rows.append(row_dict)
        except Exception as e: logger.error(f"Error XLSB {file_path}: {e}")
        return all_rows
