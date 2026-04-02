import re
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

def extract_date_from_sheet(sheet_name: str, **kwargs) -> Optional[str]:
    """
    Extracts a date from a sheet name string.
    Supports formats like DD.MM, DD.MM.YYYY, etc.
    """
    if not sheet_name: return None
    # Fix 11: Clean invisible and non-printable Unicode
    clean_name = "".join(c for c in str(sheet_name) if c.isprintable()).strip()
    clean_name = clean_name.replace('\u200b', '').replace('\ufeff', '')
    
    pat = re.compile(r'(^|[^0-9])(\d{1,2})[.,](\d{1,2})([.,](\d{4}))?([^0-9]|$)')
    m = pat.search(clean_name)
    if m:
        try:
            curr = datetime.now()
            d, month = int(m.group(2)), int(m.group(3))
            y = int(m.group(5)) if m.group(5) else curr.year
            return datetime(y, month, d).strftime("%d.%m.%Y")
        except Exception: 
            logger.debug(f"Invalid date in sheet '{sheet_name}' (e.g. Feb 29 in non-leap year)")
            return None
    return None
