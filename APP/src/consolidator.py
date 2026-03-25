import os
import pandas as pd
import re
import hashlib
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from audit_logic import audit
import openpyxl
import zipfile
import threading
from xml.etree import ElementTree

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("consolidation.log", encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

class Config:
    def __init__(self, config_path):
        self.config_path = config_path
        try:
            from ruamel.yaml import YAML as _YAML
            _yaml_reader = _YAML(typ='safe')
            with open(config_path, 'r', encoding='utf-8') as f:
                self.data = _yaml_reader.load(f)
            if self.data is None:
                self.data = {}
        except Exception as e:
            logger.error(f"Failed to load config from {config_path}: {e}")
            self.data = {}
            
        self.paths = self.data.get('paths', {})
        base_path = os.path.dirname(os.path.abspath(config_path))
        for key, val in self.paths.items():
            if val and isinstance(val, str) and not os.path.isabs(val):
                self.paths[key] = os.path.abspath(os.path.join(base_path, val))
                
        self.sh1 = self.data.get('sh1', {})
        self.sh2 = self.data.get('sh2', {})
        self.logic = self.data.get('logic', {})
        self.employees = self.data.get('employees', [])

    def get(self, key, default=None):
        return self.data.get(key, default)

class Template1Reader:
    def __init__(self, config):
        self.config = config
        self.markers = config.sh1.get('markers', {})

    def find_header_row(self, rows):
        markers = ["дата", "заказчик", "исполнитель", "приход", "расход", "сумма платежа", "комиссия", "итог"]
        best_score = 0
        best_idx = None
        # Scan first 150 rows
        for i, row in enumerate(rows):
            row_values = [str(val).lower() for val in row if val is not None]
            score = 0
            for m in markers:
                if any(m in val for val in row_values):
                    score += 1
            if score >= 3 and score > best_score:
                best_score = score
                best_idx = i
        return best_idx

    def read_file(self, file_path, target_dates=None):
        """
        Reads Excel file efficiently by scanning headers with openpyxl first,
        then loading data with Pandas using dtype=str for precision.
        """
        try:
            # 1. Scan headers with openpyxl (fast, low memory)
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            
            # Prepare robust regex patterns for target dates
            date_patterns = []
            if target_dates:
                for d in target_dates:
                    # Pattern: (start or non-digit) (optional zero) (day) . (optional zero) (month) (end or non-digit)
                    pattern = re.compile(rf"(^|[^0-9])0?{d.day}\.0?{d.month}([^0-9]|$)")
                    date_patterns.append((d, pattern))

            to_process = []
            for ws in wb.worksheets:
                if ws.sheet_state != 'visible':
                    continue
                
                sh = ws.title
                clean_sh = sh.strip()
                matched_date = None
                
                if not target_dates:
                    if not (sh.startswith('_') or sh == "АНАЛИТИКА" or sh == "СВОД"):
                        matched_date = sh
                else:
                    for d_obj, p in date_patterns:
                        if p.search(clean_sh):
                            matched_date = d_obj
                            break
                
                if not matched_date:
                    continue

                # Read first 150 rows for header detection
                rows_preview = []
                for i, row in enumerate(ws.iter_rows(max_row=150, values_only=True)):
                    rows_preview.append(row)
                
                header_idx = self.find_header_row(rows_preview)
                if header_idx is not None:
                    to_process.append((sh, matched_date, header_idx))
                else:
                    logger.warning(f"Header not found in file {file_path} sheet {sh}. Skipping.")
            
            wb.close()

            if not to_process:
                return None

            # 2. Load data with Pandas
            xl = pd.ExcelFile(file_path, engine='openpyxl')
            all_dfs_by_date = {}

            try:
                for sh, matched_date, header_idx in to_process:
                    # CRITICAL: dtype=str for 100% precision
                    df = pd.read_excel(xl, sheet_name=sh, header=header_idx, dtype=str)
                    
                    # Column mapping
                    col_map = {}
                    for key, marker in self.markers.items():
                        found_col = None
                        for col in df.columns:
                            if marker.lower() in str(col).lower():
                                found_col = col
                                break
                        if found_col is None:
                            alts = {'amount': ['сумма платежа', 'приход', 'расход'], 'income': ['приход'], 'expense': ['расход']}
                            for alt in alts.get(key, []):
                                for col in df.columns:
                                    if alt.lower() in str(col).lower():
                                        found_col = col
                                        break
                                if found_col: break
                        if found_col is not None:
                            col_map[key] = found_col
                    
                    if any(k in col_map for k in ['amount', 'income', 'expense']):
                        if hasattr(matched_date, 'strftime'):
                            date_key = matched_date.strftime("%d.%m.%Y")
                        else:
                            date_key = str(matched_date)
                            
                        if date_key not in all_dfs_by_date:
                            all_dfs_by_date[date_key] = []
                        all_dfs_by_date[date_key].append((df, col_map, sh, header_idx))
            finally:
                xl.close()

            return all_dfs_by_date if all_dfs_by_date else None
        except Exception as e:
            logger.error(f"Error reading {file_path}: {e}")
            return None

class Consolidator:
    def __init__(self, config_path):
        self.config = Config(config_path)
        self.reader = Template1Reader(self.config)
        self._sheet_cache = {}


    def _get_sheetnames_fast(self, file_path):
        try:
            mtime = os.path.getmtime(file_path) if os.path.exists(file_path) else 0
            if file_path in self._sheet_cache:
                cached_mtime, cached_sheets = self._sheet_cache[file_path]
                if cached_mtime == mtime:
                    return cached_sheets
            
            sheetnames = []
            try:
                with zipfile.ZipFile(file_path, 'r') as zf:
                    if 'xl/workbook.xml' in zf.namelist():
                        with zf.open('xl/workbook.xml') as f:
                            tree = ElementTree.parse(f)
                            root = tree.getroot()
                            for sheet in root.findall('.//{*}sheet'):
                                state = sheet.attrib.get('state', 'visible')
                                if state == 'visible':
                                    sheetnames.append(sheet.attrib.get('name'))
            except Exception as zip_e:
                logger.debug(f"Fast zip parsing failed for {file_path} ({zip_e}), falling back to openpyxl")
                wb = openpyxl.load_workbook(file_path, read_only=True, keep_links=False)
                sheetnames = [s.title for s in wb.worksheets if s.sheet_state == 'visible']
                wb.close()
            
            self._sheet_cache[file_path] = (mtime, sheetnames)
            return sheetnames
        except Exception as e:
            logger.error(f"Error getting sheet names for {file_path}: {e}")
            return []

    def discover_employees(self):
        source_root = self.config.paths.get('source_root')
        employee_map = {}
        if not source_root or not os.path.exists(source_root):
            return employee_map

        for root, dirs, files in os.walk(source_root):
            for file in files:
                if "шаблон" in file.lower() or file.startswith('~$') or not file.endswith('.xlsx'):
                    continue
                file_name_no_ext = os.path.splitext(file)[0]
                parent_dir = os.path.basename(root)
                name = file_name_no_ext if root == source_root else parent_dir
                if name not in employee_map:
                    employee_map[name] = []
                employee_map[name].append(os.path.join(root, file))
        return employee_map

    def get_employees(self):
        """
        Logic: Prioritizes explicit manual mappings from config.yaml.
        Uses 'Smart Tracking' (File ID + Fuzzy Prefix) to follow renamed/replaced files.
        """
        config_list = self.config.get('employees', [])
        custom_paths = self.config.get('employee_paths', {})
        discovered = self.discover_employees()
        result = {}
        
        target_names = config_list if config_list else sorted(list(set(list(discovered.keys()) + list(custom_paths.keys()))))
        
        self.rename_detected = False

        for target_name in target_names:
            paths_for_emp = []
            seen_for_emp = set()
            
            if target_name in custom_paths:
                p_val = custom_paths[target_name]
                p_list = p_val if isinstance(p_val, list) else [p_val]
                
                updated_paths = []
                for entry in p_list:
                    path = entry['path'] if isinstance(entry, dict) else entry
                    file_id = entry.get('id') if isinstance(entry, dict) else None
                    p_abs = os.path.abspath(path)
                    
                    # 1. SMART RECOVERY (If file missing or name changed)
                    if not os.path.exists(p_abs):
                        parent = os.path.dirname(p_abs)
                        if os.path.exists(parent):
                            found_path = None
                            
                            # A. Try exact ID match (Fast & Reliable on NTFS)
                            if file_id and file_id > 0:
                                for f in os.listdir(parent):
                                    full_f = os.path.join(parent, f)
                                    try:
                                        if os.path.isfile(full_f) and os.stat(full_f).st_ino == file_id:
                                            found_path = full_f
                                            logger.info(f"[Smart] File '{os.path.basename(path)}' was renamed to '{f}' (ID match)")
                                            break
                                    except: continue
                            
                            # B. Try Fuzzy Prefix match (For daily "Save As" users)
                            if not found_path:
                                old_name = os.path.basename(p_abs)
                                # Extract meaningful prefix (letters/digits before symbols)
                                prefix_match = re.match(r'^([a-zA-Zа-яА-Я0-9_]+)', old_name)
                                prefix = prefix_match.group(1).lower()[:7] if prefix_match else ""
                                
                                if len(prefix) >= 3:
                                    candidates = []
                                    for f in os.listdir(parent):
                                        if f.lower().startswith(prefix) and f.endswith('.xlsx') and not f.startswith('~$'):
                                            candidates.append(os.path.join(parent, f))
                                    
                                    if candidates:
                                        # Pick the most recently modified file among candidates
                                        found_path = max(candidates, key=os.path.getmtime)
                                        logger.info(f"[Smart] File '{old_name}' not found. Using newest substitute: '{os.path.basename(found_path)}'")
                            
                            if found_path:
                                p_abs = found_path
                                self.rename_detected = True

                    # 2. FINALIZE & UPDATE METADATA
                    if os.path.exists(p_abs) and not os.path.isdir(p_abs):
                        if p_abs not in seen_for_emp:
                            paths_for_emp.append(p_abs)
                            seen_for_emp.add(p_abs)
                            try:
                                curr_id = os.stat(p_abs).st_ino
                                updated_paths.append({"path": p_abs, "id": curr_id})
                            except:
                                updated_paths.append(p_abs)
                
                # Update in-memory config
                if updated_paths:
                    self.config.data.setdefault('employee_paths', {})[target_name] = updated_paths

            # 3. Fallback: Folder-based discovery (only if exact match)
            t_lower = target_name.lower()
            for d_name, paths in discovered.items():
                if t_lower == d_name.lower():
                    for p in paths:
                        p_abs = os.path.abspath(p)
                        if p_abs not in seen_for_emp:
                            paths_for_emp.append(p_abs)
                            seen_for_emp.add(p_abs)
            
            # Final deduplication
            unique_paths = []
            seen_hashes = set()
            for p in paths_for_emp:
                try:
                    st = os.stat(p)
                    h_source = f"{st.st_size}-{st.st_mtime}"
                    if h_source not in seen_hashes:
                        unique_paths.append(p)
                        seen_hashes.add(h_source)
                except:
                    if p not in unique_paths: unique_paths.append(p)
            
            result[target_name] = unique_paths
            
        return result

    def get_all_available_dates(self):
        employees = self.get_employees()
        unique_dates = set()
        date_pattern = re.compile(r'(\d{1,2})\.(\d{1,2})(\.(\d{4}))?')
        for name, paths in employees.items():
            for path in paths:
                try:
                    # PERFORMANCE: Use cached sheet names
                    visible_sheets = self._get_sheetnames_fast(path)
                    for sheet_name in visible_sheets:
                        match = date_pattern.search(sheet_name.strip())
                        if match:
                            try:
                                current = datetime.now()
                                year = int(match.group(4)) if match.group(4) else current.year
                                # If month is in the future relative to current month -> use previous year
                                if not match.group(4):  # only when year is inferred
                                    candidate = datetime(current.year, int(match.group(2)), int(match.group(1)))
                                    if candidate > current + timedelta(days=15):
                                        year = current.year - 1
                                d = datetime(year, int(match.group(2)), int(match.group(1)))
                                unique_dates.add(d)
                            except: continue
                except: continue
        return sorted(list(unique_dates))

    _JUNK_TOTALS = frozenset({"итого", "всего", "итог"})
    _JUNK_MARKERS = ("заказчик", "исполнитель", "приход", "расход")

    def is_junk_row(self, row_dict, col_map):
        # Handle pandas Series gracefully during transition
        vals = row_dict.values() if isinstance(row_dict, dict) else row_dict.tolist()

        v_strs = []
        for val in vals:
            if pd.isna(val): continue
            v_str = str(val).lower()
            if v_str.strip(': ') in self._JUNK_TOTALS:
                return True
            v_strs.append(v_str)

        # STRICT FILTER: If there is no text context at all, it's a floating calculator number
        c_val = row_dict.get(col_map.get('customer'))
        contr_val = row_dict.get(col_map.get('contractor'))
        f_val = row_dict.get(col_map.get('filters'))
        
        def is_empty(val):
            return pd.isna(val) or str(val).strip() == ''
            
        if is_empty(c_val) and is_empty(contr_val) and is_empty(f_val):
            return True

        row_str = " ".join(v_strs)
        marker_count = 0
        for m in self._JUNK_MARKERS:
            if m in row_str:
                marker_count += 1
                if marker_count >= 2:
                    return True
        return False

    def consolidate_multiple(self, target_dates):
        """
        HIGH PERFORMANCE: Multi-threaded file reading + batch processing.
        """
        employees = self.get_employees()
        results_by_date = {}
        results_lock = threading.Lock()
        
        # Build flat list of (display_name, path)
        work_items = []
        for name, paths in employees.items():
            display_name = name.replace("Ежедневынй отчет", "").replace("Ежедневный отчет", "").strip()
            for path in paths:
                work_items.append((display_name, path))

        # PERFORMANCE: PARALLEL PROCESSING
        max_w = min(6, (os.cpu_count() or 2) + 2)
        with ThreadPoolExecutor(max_workers=max_w) as executor:
            future_to_item = {executor.submit(self.reader.read_file, path, target_dates): (name, path) for name, path in work_items}
            
            for future in as_completed(future_to_item):
                display_name, path = future_to_item[future]
                try:
                    file_results = future.result()
                    if not file_results: continue
                    
                    for date_str, sheets in file_results.items():
                        for df, col_map, sh_name, header_idx in sheets:
                            logger.info(f"[*] Processing {display_name} | {sh_name}")
                            c_col = col_map.get('customer')
                            a_col = col_map.get('amount')
                            i_col = col_map.get('income')
                            e_col = col_map.get('expense')

                            # Pre-filter: remove completely empty key columns
                            key_cols = [col for col in [c_col, a_col, i_col, e_col] if col and col in df.columns]
                            if key_cols:
                                df = df.dropna(subset=key_cols, how='all')

                            records = df.to_dict('records')
                            batch = []
                            for idx, row_dict in enumerate(records):
                                v_c = row_dict.get(c_col)
                                v_a = row_dict.get(a_col)
                                v_i = row_dict.get(i_col)
                                v_e = row_dict.get(e_col)

                                # PERFORMANCE: Python inline NaN check is significantly faster than pd.isna
                                if (v_c != v_c or v_c is None) and \
                                   (v_a != v_a or v_a is None) and \
                                   (v_i != v_i or v_i is None) and \
                                   (v_e != v_e or v_e is None):
                                    continue

                                if self.is_junk_row(row_dict, col_map): continue

                                actual_row_idx = idx + 1
                                transformed = self.transform_row(
                                    row_dict, col_map, display_name, sh_name,
                                    row_index=actual_row_idx,
                                    filename=os.path.basename(path)
                                )
                                if transformed: batch.append(transformed)

                            if batch:
                                with results_lock:
                                    if date_str not in results_by_date:
                                        results_by_date[date_str] = []
                                    results_by_date[date_str].extend(batch)
                except Exception as e:
                    logger.error(f"Failed to process {path}: {e}")

        audit.save()
        return results_by_date

    def to_decimal(self, val):
        if pd.isna(val) or val == "": return Decimal('0.00')
        if isinstance(val, (int, float, Decimal)):
            return Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        try:
            # Detect accounting negative notation: (number)
            raw_str = str(val).strip()
            is_accounting_negative = raw_str.startswith('(') and raw_str.endswith(')')

            s = re.sub(r"[^\d.,\-eE+]", "", str(val))
            if not s: return Decimal('0.00')
            
            # PERFORMANCE & BUG FIX: Strip trailing punctuation that is not part of the number
            s = s.rstrip('.,')
            if not s: return Decimal('0.00')

            if 'e' in s.lower(): 
                result = Decimal(s).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                if is_accounting_negative:
                    result = -abs(result)
                return result
            
            separators = [i for i, char in enumerate(s) if char in '.,']
            if len(separators) == 1:
                sep_idx = separators[0]
                char = s[sep_idx]
                suffix = s[sep_idx + 1:]
                if char == '.' and len(suffix) == 3:
                    # Treat as thousands separator
                    clean_val = s.replace('.', '')
                elif char == '.':
                    # Treat as decimal point
                    clean_val = s
                elif char == ',':
                    # Always treat as decimal point
                    clean_val = s.replace(',', '.')
                else:
                    clean_val = s
            elif len(separators) >= 2:
                last_sep_idx = separators[-1]
                prefix = s[:last_sep_idx].replace('.', '').replace(',', '')
                suffix = s[last_sep_idx + 1:]
                clean_val = f"{prefix}.{suffix}" if suffix else prefix
            else: clean_val = s

            result = Decimal(clean_val).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if is_accounting_negative:
                result = -abs(result)
            return result
        except: return Decimal('0.00')

    def to_decimal_percent(self, val):
        if pd.isna(val) or val == "": return Decimal('0')
        if isinstance(val, (int, float, Decimal)): return Decimal(str(val))
        try:
            raw_s = str(val)
            s = re.sub(r"[^\d.,-]", "", raw_s)
            if not s: return Decimal('0')
            clean_val = s.replace(',', '.')
            res = Decimal(clean_val)
            if "%" in raw_s and res > 1:
                res = res / Decimal('100')
            return res
        except: return Decimal('0')

    def transform_row(self, row_dict, col_map, employee_name, sheet_name, row_index, log_audit=True, filename=None):
        def get_text(v):
            if pd.isna(v): return ""
            return str(v)

        raw_val = row_dict.get(col_map.get('amount'))
        filters_val = get_text(row_dict.get(col_map.get('filters', ''), '')).lower()
        income_overrides = self.config.logic.get('income_overrides', ['доп', 'доп сф', '% посред'])
        return_keywords = self.config.logic.get('return_keywords', ['возврат'])
        
        is_additional = any(kw.lower() in filters_val for kw in income_overrides)
        if pd.isna(raw_val) and not is_additional: return None
            
        raw_amount = self.to_decimal(raw_val)
        source_total = self.to_decimal(row_dict.get(col_map.get('total'), 0))
        if raw_amount == 0 and source_total == 0 and not is_additional: return None

        income = Decimal('0.00'); expense = Decimal('0.00')
        if is_additional: income = raw_amount
        elif any(kw.lower() in filters_val for kw in return_keywords): 
            expense = abs(raw_amount)
        elif raw_amount < 0: expense = abs(raw_amount)
        else: income = raw_amount

        customer_val = get_text(row_dict.get(col_map.get('customer'), ''))
        contractor_val = get_text(row_dict.get(col_map.get('contractor'), ''))

        # ANTI-FORMULA PROTECTION
        def sanitize(v):
            v_str = get_text(v)
            if v_str.strip().startswith(('=', '+', '-', '@')): return "'" + v_str
            return v_str

        emp_label = get_text(employee_name)
        if filename:
            emp_label = f"{emp_label} [{filename}]"

        res = {
            'Дата': get_text(sheet_name),
            'Сотрудник': f"{emp_label} (стр. {row_index})",
            'ЗАКАЗЧИК (название проекта, наименование ЮЛ)': sanitize(customer_val),
            'ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)': sanitize(contractor_val),
            'сумма платежа ПРИХОД': income,
            'сумма платежа РАСХОД': expense,
            'комиссия': self.to_decimal_percent(row_dict.get(col_map.get('commission'), 0)),
            'ИТОГ': source_total,
            '% посредника': self.to_decimal_percent(row_dict.get(col_map.get('percent_broker'))),
            'посредник 1(кэш)': self.to_decimal(row_dict.get(col_map.get('broker1'))),
            'посредник 2': self.to_decimal(row_dict.get(col_map.get('broker2'))),
            'фильтры': sanitize(filters_val),
            'is_critical': False
        }
        if log_audit:
            audit.log_action(get_text(employee_name), get_text(sheet_name), res['ЗАКАЗЧИК (название проекта, наименование ЮЛ)'], "OK", "ЗЕРКАЛО")
        return res

    def check_date_exists(self, file_path, target_date):
        """PERFORMANCE: Use cached sheet names for instant checking."""
        try:
            sheetnames = self._get_sheetnames_fast(file_path)
            # Robust regex: matches day.month with optional leading zeros
            # Ensures no partial matches like '16.03' for '6.03' using word boundaries/non-digits
            day = target_date.day
            month = target_date.month
            # Pattern: (start or non-digit) (optional zero) (day) . (optional zero) (month) (end or non-digit)
            pattern = re.compile(rf"(^|[^0-9])0?{day}\.0?{month}([^0-9]|$)")
            
            for sh in sheetnames:
                if pattern.search(sh):
                    return True
        except: pass
        return False

    def process_file(self, file_path, target_date):
        res_by_date = self.reader.read_file(file_path, [target_date])
        if not res_by_date: return []
        all_rows = []
        for d_str, sheets in res_by_date.items():
            for df, col_map, sh_name, header_idx in sheets:
                c_col = col_map.get('customer')
                a_col = col_map.get('amount')
                i_col = col_map.get('income')
                e_col = col_map.get('expense')

                # Pre-filter: remove completely empty key columns
                key_cols = [col for col in [c_col, a_col, i_col, e_col] if col and col in df.columns]
                if key_cols:
                    df = df.dropna(subset=key_cols, how='all')

                records = df.to_dict('records')
                for idx, row_dict in enumerate(records):
                    v_c = row_dict.get(c_col)
                    v_a = row_dict.get(a_col)
                    v_i = row_dict.get(i_col)
                    v_e = row_dict.get(e_col)

                    # PERFORMANCE: Python inline NaN check is significantly faster than pd.isna
                    if (v_c != v_c or v_c is None) and \
                       (v_a != v_a or v_a is None) and \
                       (v_i != v_i or v_i is None) and \
                       (v_e != v_e or v_e is None):
                        continue
                    if self.is_junk_row(row_dict, col_map): continue

                    actual_row_idx = idx + 1
                    transformed = self.transform_row(
                        row_dict, col_map, "Preview", sh_name,
                        actual_row_idx, log_audit=False,
                        filename=os.path.basename(file_path)
                    )
                    if transformed: all_rows.append(transformed)
        return all_rows

if __name__ == "__main__":
    pass
