import re
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

def extract_date_from_sheet(sheet_name: str) -> Optional[str]:
    """
    Extracts a date from a sheet name string.
    Supports formats like DD.MM, DD.MM.YYYY, etc.
    """
    pat = re.compile(r'(^|[^0-9])(\d{1,2})[.,](\d{1,2})([.,](\d{4}))?([^0-9]|$)')
    m = pat.search(sheet_name.strip())
    if m:
        try:
            curr = datetime.now()
            d, month = int(m.group(2)), int(m.group(3))
            y = int(m.group(5)) if m.group(5) else curr.year
            if not m.group(5) and datetime(curr.year, month, d) > curr + timedelta(days=30): 
                y = curr.year - 1
            return datetime(y, month, d).strftime("%d.%m.%Y")
        except Exception: 
            logger.warning(f"TEMPORAL WARNING: Invalid date in sheet '{sheet_name}' (e.g. Feb 29 in non-leap year)")
            return None
    return None
