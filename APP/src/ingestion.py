import os
import hashlib
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
import logging

import openpyxl
from pyxlsb import open_workbook as open_xlsb

try:
    from .interfaces import IDataSource
except ImportError:
    from interfaces import IDataSource

logger = logging.getLogger(__name__)

class IngestionEngine(IDataSource):
    """
    Implementation of IDataSource for scanning and reading Excel reports.
    Supports .xlsx (via openpyxl) and .xlsb (via pyxlsb).
    Uses Smart Tracking (inode + MD5) for file identification.
    """

    def __init__(self, config_markers: Dict[str, str]):
        self.markers = config_markers
        # Standard aliases for markers to improve detection robustness
        self.aliases = {
            'amount':      ['сумма платежа', 'бн рф руб', 'бн', 'приход', 'расход'],
            'income':      ['приход'],
            'expense':     ['расход'],
            'customer':    ['заказчик', 'агент'],
            'contractor':  ['исполнитель', 'вторая сторона'],
            'total':       ['итог', 'итоги дня', 'итог дня', 'формула'],
            'commission':  ['комиссия', 'ставка/цена'],
            'percent_broker': ['% посредника', '%'],
            'broker1':     ['посредник 1(кэш)', 'посредник 1',
                            'комиссия посредника 1', 'приходный кассовый ордер'],
            'broker2':     ['посредник 2', 'комиссия посредника 2', '%.1'],
            'filters':     ['фильтры', 'фильтр', 'filter'],
        }
        self._date_pattern = re.compile(r'(^|[^0-9])(\d{1,2})[.,](\d{1,2})([.,](\d{4}))?([^0-9]|$)')

    def _extract_date(self, sheet_name: str) -> Optional[str]:
        """Extracts date from sheet name and returns it as DD.MM.YYYY string."""
        match = self._date_pattern.search(sheet_name.strip())
        if match:
            try:
                current = datetime.now()
                day = int(match.group(2))
                month = int(match.group(3))
                year = int(match.group(5)) if match.group(5) else current.year
                
                if not match.group(5):
                    candidate = datetime(current.year, month, day)
                    if candidate > current + timedelta(days=30):
                        year = current.year - 1
                
                dt = datetime(year, month, day)
                return dt.strftime("%d.%m.%Y")
            except Exception:
                return None
        return None

    def get_available_dates(self, file_path: Path) -> List[str]:
        """Returns a list of unique DD.MM.YYYY date strings found in sheet names."""
        dates = set()
        try:
            suffix = file_path.suffix.lower()
            if suffix == '.xlsx':
                wb = openpyxl.load_workbook(file_path, read_only=True, keep_links=False)
                for ws in wb.worksheets:
                    if ws.sheet_state == 'visible':
                        d = self._extract_date(ws.title)
                        if d: dates.add(d)
                wb.close()
            elif suffix == '.xlsb':
                with open_xlsb(str(file_path)) as wb:
                    for sheet_name in wb.sheets:
                        d = self._extract_date(sheet_name)
                        if d: dates.add(d)
        except Exception as e:
            logger.debug(f"Failed to get dates from {file_path}: {e}")
        return sorted(list(dates))

    def scan_directory(self, root_path: Path) -> List[Dict[str, Any]]:
        """
        Recursively scans directory for .xlsx and .xlsb files.
        Returns metadata including inode and MD5 fingerprint.
        """
        results = []
        if not root_path.exists():
            logger.warning(f"Scan directory does not exist: {root_path}")
            return results

        for root, _, files in os.walk(root_path):
            for file in files:
                if file.startswith('~$') or not file.lower().endswith(('.xlsx', '.xlsb')):
                    continue
                
                full_path = Path(root) / file
                try:
                    full_path = full_path.resolve()
                    stat = os.stat(full_path)
                    file_id = stat.st_ino
                    
                    # MD5 of first 8KB for fast fingerprinting
                    with open(full_path, 'rb') as f:
                        fp = hashlib.md5(f.read(8192)).hexdigest()
                    
                    results.append({
                        "path": str(full_path),
                        "id": file_id,
                        "fp": fp,
                        "size": stat.st_size,
                        "mtime": stat.st_mtime
                    })
                except Exception as e:
                    logger.error(f"Failed to scan file {full_path}: {e}")
        
        return results

    def read_file(self, file_path: Path) -> List[Dict[str, Any]]:
        """
        Reads Excel file and returns a list of raw row dictionaries.
        """
        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return []

        suffix = file_path.suffix.lower()
        if suffix == '.xlsx':
            return self._read_xlsx(file_path)
        elif suffix == '.xlsb':
            return self._read_xlsb(file_path)
        else:
            logger.warning(f"Unsupported file format: {suffix}")
            return []

    def _read_xlsx(self, file_path: Path) -> List[Dict[str, Any]]:
        all_rows = []
        try:
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            for ws in wb.worksheets:
                if ws.sheet_state != 'visible':
                    continue
                
                if ws.title.startswith('_') or ws.title in ("АНАЛИТИКА", "СВОД"):
                    continue

                rows = list(ws.iter_rows(values_only=True))
                
                # Pre-scan to find the standard template keys for this sheet
                standard_keys = set()
                max_score = 0
                for row in rows:
                    if not row: continue
                    row_values_str = [str(v).lower() for v in row if v is not None]
                    header_score = sum(1 for m in self.aliases.values() if any(alias.lower() in " ".join(row_values_str) for alias in m))
                    if header_score >= 4 and header_score > max_score:
                        max_score = header_score
                        standard_keys = set(self._map_columns(row).keys())

                active_col_map = None
                current_is_warning = False

                for i, row in enumerate(rows):
                    if not row: continue

                    # Check if this row looks like a header
                    row_values_str = [str(v).lower() for v in row if v is not None]
                    header_score = sum(1 for m in self.aliases.values() if any(alias.lower() in " ".join(row_values_str) for alias in m))

                    # If it's a header, update the mapping
                    if header_score >= 4:
                        active_col_map = self._map_columns(row)
                        current_keys = set(active_col_map.keys())
                        current_is_warning = (current_keys != standard_keys)
                        continue

                    # If we have a mapping, process the row
                    if active_col_map:
                        row_dict = self._process_row(row, active_col_map, ws.title, i + 1, str(file_path))
                        if row_dict:
                            row_dict['is_template_warning'] = current_is_warning
                            all_rows.append(row_dict)
        except Exception as e:
            logger.error(f"Error reading XLSX {file_path}: {e}")
        return all_rows

    def _read_xlsb(self, file_path: Path) -> List[Dict[str, Any]]:
        all_rows = []
        try:
            with open_xlsb(str(file_path)) as wb:
                for sheet_name in wb.sheets:
                    if sheet_name.startswith('_') or sheet_name in ("АНАЛИТИКА", "СВОД"):
                        continue
                    
                    with wb.get_sheet(sheet_name) as ws:
                        rows_objs_list = list(ws.rows())
                        
                        # Pre-scan to find the standard template keys for this sheet
                        standard_keys = set()
                        max_score = 0
                        for row_objs in rows_objs_list:
                            row = [cell.v for cell in row_objs]
                            if not row: continue
                            row_values_str = [str(v).lower() for v in row if v is not None]
                            header_score = sum(1 for m in self.aliases.values() if any(alias.lower() in " ".join(row_values_str) for alias in m))
                            if header_score >= 4 and header_score > max_score:
                                max_score = header_score
                                standard_keys = set(self._map_columns(row).keys())

                        active_col_map = None
                        current_is_warning = False
                        
                        for i, row_objs in enumerate(rows_objs_list):
                            row = [cell.v for cell in row_objs]
                            if not row: continue
                            
                            row_values_str = [str(v).lower() for v in row if v is not None]
                            header_score = sum(1 for m in self.aliases.values() if any(alias.lower() in " ".join(row_values_str) for alias in m))
                            
                            if header_score >= 4:
                                active_col_map = self._map_columns(row)
                                current_keys = set(active_col_map.keys())
                                current_is_warning = (current_keys != standard_keys)
                                continue
                                
                            if active_col_map:
                                row_dict = self._process_row(row, active_col_map, sheet_name, i + 1, str(file_path))
                                if row_dict:
                                    row_dict['is_template_warning'] = current_is_warning
                                    all_rows.append(row_dict)
        except Exception as e:
            logger.error(f"Error reading XLSB {file_path}: {e}")
        return all_rows

    def _find_header_row(self, rows: List[List[Any]]) -> Optional[int]:
        """Detects header row index based on markers."""
        best_score = 0
        best_idx = None

        # Combine markers and some aliases for detection
        detection_markers = set()
        for m in self.markers.values():
            if isinstance(m, list):
                for item in m:
                    detection_markers.add(str(item).lower())
            else:
                detection_markers.add(str(m).lower())
        for alist in self.aliases.values():
            for a in alist:
                detection_markers.add(str(a).lower())
        for i, row in enumerate(rows):
            if not row: continue
            row_values = [str(val).lower() for val in row if val is not None]
            score = 0
            for m in detection_markers:
                if any(m in val for val in row_values):
                    score += 1
            if score >= 3 and score > best_score:
                best_score = score
                best_idx = i
        return best_idx

    def _map_columns(self, header_row: List[Any]) -> Dict[str, int]:
        """Maps marker keys to column indices."""
        col_map = {}
        header_values = [str(val).lower() if val is not None else "" for val in header_row]
        
        for key, marker in self.markers.items():
            found_idx = None
            marker_list = marker if isinstance(marker, list) else [marker]
            marker_lowers = [str(m).lower() for m in marker_list]
            
            # Try exact or partial match with marker
            for idx, val in enumerate(header_values):
                if any(m in val for m in marker_lowers):
                    # Special case for commission to avoid matching broker commission
                    if key == 'commission' and 'посредник' in val:
                        continue
                    found_idx = idx
                    break
            
            # Try aliases if not found
            if found_idx is None and key in self.aliases:
                for alt in self.aliases[key]:
                    alt_lower = alt.lower()
                    for idx, val in enumerate(header_values):
                        if alt_lower in val:
                            if key == 'commission' and 'посредник' in val:
                                continue
                            found_idx = idx
                            break
                    if found_idx is not None:
                        break
            
            if found_idx is not None:
                col_map[key] = found_idx
        
        return col_map

    def _process_row(self, row: List[Any], col_map: Dict[str, int], sheet_name: str, row_idx: int, file_path: str) -> Optional[Dict[str, Any]]:
        """Converts a raw row into a dictionary with mapped keys and Decimal values."""
        if not row: return None
        
        # Check if row consists ONLY of numbers (which means it's a totals/summary row)
        non_empty_vals = [v for v in row if v is not None and str(v).strip() != '']
        if non_empty_vals:
            is_only_numbers = True
            for v in non_empty_vals:
                if isinstance(v, (int, float, Decimal)):
                    continue
                s = str(v).replace(' ', '').replace(',', '.').replace('-', '')
                if not s:
                    continue
                try:
                    float(s)
                except ValueError:
                    is_only_numbers = False
                    break
            if is_only_numbers:
                return None
        
        # Check if row is empty in key columns
        has_data = False
        res = {
            '_sheet_name': sheet_name,
            '_row_index': row_idx,
            '_file_path': file_path,
            'date': self._extract_date(sheet_name)
        }
        
        for key, col_idx in col_map.items():
            if col_idx < len(row):
                val = row[col_idx]
                if val is not None and val != "":
                    has_data = True
                
                # Convert financial fields to Decimal
                financial_keys = {'amount', 'income', 'expense', 'total', 'commission', 'percent_broker', 'broker1', 'broker2'}
                if key in financial_keys:
                    res[key] = self._to_decimal(val)
                else:
                    res[key] = val
            else:
                res[key] = None

        if not has_data:
            return None
            
        return res

    def _to_decimal(self, val: Any) -> Decimal:
        """Robust conversion to Decimal."""
        if val is None or val == "":
            return Decimal('0.00')
        if isinstance(val, (int, float, Decimal)):
            return Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        
        try:
            raw_str = str(val).strip()
            # Handle accounting negative notation: (123.45) -> -123.45
            is_accounting_negative = raw_str.startswith('(') and raw_str.endswith(')')
            
            # Remove non-numeric characters except dots, commas, and minus
            s = re.sub(r"[^\d.,\-eE+]", "", raw_str)
            if not s: return Decimal('0.00')
            
            s = s.rstrip('.,')
            if not s: return Decimal('0.00')

            # Handle scientific notation
            if 'e' in s.lower():
                result = Decimal(s).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                return -abs(result) if is_accounting_negative else result

            # Handle European/Russian separators (1.234,56 or 1 234,56)
            separators = [i for i, char in enumerate(s) if char in '.,']
            if len(separators) == 1:
                sep_idx = separators[0]
                if s[sep_idx] == ',':
                    clean_val = s.replace(',', '.')
                else:
                    clean_val = s
            elif len(separators) >= 2:
                last_sep_idx = separators[-1]
                prefix = s[:last_sep_idx].replace('.', '').replace(',', '')
                suffix = s[last_sep_idx + 1:]
                clean_val = f"{prefix}.{suffix}" if suffix else prefix
            else:
                clean_val = s

            result = Decimal(clean_val).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            return -abs(result) if is_accounting_negative else result
        except Exception:
            return Decimal('0.00')
