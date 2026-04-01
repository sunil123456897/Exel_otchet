import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import openpyxl
from pyxlsb import open_workbook as open_xlsb

from core.domain.utils_helpers import to_decimal
from core.domain.data_schemas import FinancialRowSchema
from core.infra.ingestion_utils import extract_date_from_sheet

logger = logging.getLogger(__name__)

class ExcelReader:
    def __init__(self, markers: Dict[str, Any], aliases: Dict[str, List[str]]):
        self.markers = markers
        self.aliases = aliases

    def _map_columns(self, header_row: List[Any]) -> tuple[Dict[str, int], bool]:
        col_map = {}
        used_aliases = False
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
                            used_aliases = True
                            break
                    if found_idx is not None: break
            if found_idx is not None: col_map[key] = found_idx
        return col_map, used_aliases

    def _process_row(self, row: List[Any], col_map: Dict[str, int], sheet_name: str, row_idx: int, file_path: str) -> Optional[Dict[str, Any]]:
        if not row: return None
        
        # Trash filter: ignore instructions, formulas, or header-like text in data rows
        trash_keywords = ['c16', 'd16', 'название клиента', 'согласно платежному', 'процентном формате']
        row_str = " ".join([str(v).lower() for v in row if v is not None])
        if any(tk in row_str for tk in trash_keywords):
            return None

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
        
        raw_data = {'_sheet_name': sheet_name, '_row_index': row_idx, '_file_path': os.path.abspath(file_path), 'date': extract_date_from_sheet(sheet_name)}
        has_data = False
        has_financial_data = False
        for key, col_idx in col_map.items():
            if col_idx < len(row):
                val = row[col_idx]
                if val is not None and val != "":
                    has_data = True
                    # Check if this is a financial field and has a non-zero value
                    if key in ('amount', 'income', 'expense', 'commission'):
                        try:
                            if abs(float(str(val).replace(' ', '').replace(',', '.'))) > 0.001:
                                has_financial_data = True
                        except: pass
                raw_data[key] = val
            else: raw_data[key] = None
        
        if not has_data or not has_financial_data: return None
        
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
                        standard_keys = set(self._map_columns(row)[0].keys())
                
                # Second pass: read data using generator
                active_col_map, current_is_warning = None, False
                for i, row in enumerate(ws.iter_rows(values_only=True) if hasattr(ws, 'iter_rows') else ws.rows()):
                    if not hasattr(ws, 'iter_rows'): # for xlsb compatibility
                        row = [cell.v for cell in row]
                    if not row: continue
                    row_values_str = [str(v).lower() for v in row if v is not None]
                    score = sum(1 for m in self.aliases.values() if any(alias.lower() in " ".join(row_values_str) for alias in m))
                    if score >= 4:
                        active_col_map, used_aliases = self._map_columns(row)
                        current_is_warning = used_aliases or (set(active_col_map.keys()) != standard_keys)
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
                                standard_keys = set(self._map_columns(row)[0].keys())
                        
                        # Second pass for data
                        active_col_map, current_is_warning = None, False
                        for i, row_objs in enumerate(ws.rows()):
                            row = [cell.v for cell in row_objs]
                            if not row: continue
                            row_values_str = [str(v).lower() for v in row if v is not None]
                            score = sum(1 for m in self.aliases.values() if any(alias.lower() in " ".join(row_values_str) for alias in m))
                            if score >= 4:
                                active_col_map, used_aliases = self._map_columns(row)
                                current_is_warning = used_aliases or (set(active_col_map.keys()) != standard_keys)
                                continue
                            if active_col_map:
                                row_dict = self._process_row(row, active_col_map, sheet_name, i + 1, f_path_abs)
                                if row_dict:
                                    row_dict['is_template_warning'] = current_is_warning
                                    all_rows.append(row_dict)
        except Exception as e: logger.error(f"Error XLSB {f_path_abs}: {e}")
        return all_rows
