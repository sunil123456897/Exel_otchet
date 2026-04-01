import re
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

def extract_date_from_sheet(sheet_name: str, file_path: Optional[str] = None, fallback_year: Optional[int] = None) -> Optional[str]:
    """
    Extracts a date from a sheet name string.
    Priority for Year Detection:
    1. Year explicitly in sheet name (e.g. '01.01.2026')
    2. 4-digit year in file path (e.g. '.../Reports/2025/...')
    3. Provided fallback year (e.g. from workbook metadata or header row)
    4. Current year (final fallback)
    """
    # 1. Try to find year in file path first if available
    path_year = None
    if file_path:
        # Match 4-digit years between 2020 and 2035 in the path
        path_matches = re.findall(r'[/\\](202[0-9]|203[0-5])[/\\]', file_path)
        if path_matches:
            path_year = int(path_matches[-1]) # Take the last one (closest to file)
        else:
            # Try file name if folder didn't have it
            name_matches = re.findall(r'(202[0-9]|203[0-5])', file_path)
            if name_matches:
                path_year = int(name_matches[-1])

    # 2. Extract DD.MM from sheet name
    pat = re.compile(r'(^|[^0-9])(\d{1,2})[.,](\d{1,2})([.,](\d{4}))?([^0-9]|$)')
    m = pat.search(sheet_name.strip())
    if m:
        try:
            curr = datetime.now()
            d, month = int(m.group(2)), int(m.group(3))
            
            # Order of year precedence:
            if m.group(5): y = int(m.group(5)) # Year explicitly in sheet name
            elif path_year: y = path_year       # Year in folder/filename
            elif fallback_year: y = fallback_year # Year from workbook metadata/header
            else: y = curr.year                # Current year
            
            return datetime(y, month, d).strftime("%d.%m.%Y")
        except Exception: 
            logger.warning(f"TEMPORAL WARNING: Invalid date in sheet '{sheet_name}' (e.g. Feb 29 in non-leap year)")
            return None
    return None
