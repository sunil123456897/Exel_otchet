import os
import logging
import shutil
import tempfile
from pathlib import Path
from decimal import Decimal
from typing import List, Dict, Any, Optional
from python_calamine import CalamineWorkbook

from core.domain.utils_helpers import to_decimal, to_decimal_percent
from core.domain.data_schemas import FinancialRowSchema
from core.infra.ingestion_utils import extract_date_from_sheet

logger = logging.getLogger(__name__)

class CalamineReader:
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

    def read(self, file_path: Path) -> List[Dict[str, Any]]:
        all_rows = []
        f_path_abs = os.path.abspath(str(file_path))
        
        # Precompute search terms for the entire file
        all_search_terms = []
        for key in self.markers:
            m_val = self.markers[key]
            m_list = [str(v).lower() for v in (m_val if isinstance(m_val, list) else [m_val])]
            if key in self.aliases:
                m_list.extend([str(v).lower() for v in self.aliases[key]])
            all_search_terms.append(list(set(m_list)))
        aliases_lower_list = all_search_terms
        
        trash_keywords = ['c16', 'd16', 'название клиента', 'согласно платежному', 'процентном формате']

        # LOCAL COPY OPTIMIZATION for network drives
        is_network = str(f_path_abs).startswith('\\\\') or f_path_abs[0].upper() in ('Q', 'Z')
        temp_file = None
        
        try:
            target_path = f_path_abs
            if is_network:
                fd, temp_file = tempfile.mkstemp(suffix=file_path.suffix)
                os.close(fd)
                shutil.copy2(f_path_abs, temp_file)
                target_path = temp_file
            
            wb = CalamineWorkbook.from_path(target_path)
            for sheet_name in wb.sheet_names:
                if sheet_name.startswith('_') or sheet_name in ("АНАЛИТИКА", "СВОД"): continue
                
                rows = wb.get_sheet_by_name(sheet_name).to_python()
                if not rows: continue
                
                # Precompute sheet-level metadata
                sheet_date = extract_date_from_sheet(sheet_name)
                if not sheet_date:
                    logger.debug(f"Skipping sheet {sheet_name}: no date found")
                    continue

                # First pass: find standard keys (scan first 6000 rows)
                standard_keys, max_score = set(), 0
                for row in rows[:6000]:
                    if not any(v is not None and v != "" for v in row): continue
                    row_str = " ".join([str(v).lower() for v in row if v is not None])
                    score = sum(1 for m in aliases_lower_list if any(alias in row_str for alias in m))
                    # Threshold lowered to 2 to support minimalistic files (e.g. tests)
                    if score >= 2 and score > max_score:
                        map_res, _ = self._map_columns(row)
                        # Ensure we have at least amount and customer/contractor
                        if 'amount' in map_res and ('customer' in map_res or 'contractor' in map_res):
                            max_score = score
                            standard_keys = set(map_res.keys())
                            if score >= 5: break
                
                if not standard_keys:
                    logger.debug(f"No headers found in sheet {sheet_name} (max score: {max_score})")
                    continue

                # Second pass: read data
                active_col_map, current_is_warning = None, False
                trash_keywords_set = set(trash_keywords)
                
                for i, row in enumerate(rows):
                    if not any(v is not None and v != "" for v in row): continue
                    
                    # Optimization: faster check for headers and trash
                    row_values_lower = [str(v).lower() for v in row if v is not None]
                    
                    if not active_col_map:
                        row_combined = " ".join(row_values_lower)
                        score = sum(1 for m in aliases_lower_list if any(alias in row_combined for alias in m))
                        
                        if score >= 2:
                            tmp_map, used_aliases = self._map_columns(row)
                            if 'amount' in tmp_map and ('customer' in tmp_map or 'contractor' in tmp_map):
                                active_col_map = tmp_map
                                current_is_warning = used_aliases or (set(active_col_map.keys()) != standard_keys)
                                continue
                    
                    if active_col_map:
                        is_trash = False
                        for val_lower in row_values_lower:
                            for tk in trash_keywords:
                                if tk in val_lower:
                                    is_trash = True
                                    break
                            if is_trash: break
                        if is_trash: continue

                        raw_data = {
                            '_sheet_name': sheet_name, 
                            '_row_index': i + 1, 
                            '_file_path': f_path_abs, 
                            'date': sheet_date
                        }
                        
                        has_data, has_financial = False, False
                        numeric_fields = {'amount', 'income', 'expense', 'total', 'commission', 'percent_broker', 'broker1', 'broker2'}
                        for key, col_idx in active_col_map.items():
                            if col_idx < len(row):
                                val = row[col_idx]
                                if val is not None and val != "":
                                    has_data = True
                                    if key in numeric_fields:
                                        if isinstance(val, (int, float)):
                                            d_val = Decimal(str(val))
                                            if d_val != 0: has_financial = True
                                            raw_data[key] = d_val
                                        else:
                                            try:
                                                d_val = to_decimal(val) if key != 'percent_broker' else to_decimal_percent(val)
                                                if d_val != 0: has_financial = True
                                                raw_data[key] = d_val
                                            except: raw_data[key] = val
                                    else:
                                        raw_data[key] = val
                        
                        if has_data and has_financial:
                            try:
                                # Optimization: bypass Pydantic model_dump entirely
                                raw_data['is_template_warning'] = current_is_warning
                                raw_data['_source_info'] = f"{os.path.basename(f_path_abs)} | {sheet_name} | Row {i+1}"
                                all_rows.append(raw_data)
                            except Exception as ve:
                                logger.debug(f"Row {i+1} in {sheet_name} failed: {ve}")
                        elif has_data:
                            logger.debug(f"Row {i+1} in {sheet_name} has data but no financial values")
                            
        except Exception as e: logger.error(f"Calamine error {f_path_abs}: {e}")
        finally:
            if temp_file and os.path.exists(temp_file):
                try: os.remove(temp_file)
                except: pass
        return all_rows
