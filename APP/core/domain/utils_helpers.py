import os
import subprocess
import platform
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

def open_path(path: str):
    if platform.system() == "Windows":
        os.startfile(path)
    elif platform.system() == "Darwin":
        subprocess.run(["open", path])
    else:
        subprocess.run(["xdg-open", path])

def to_decimal(val: Any) -> Decimal:
    if val is None or val == "" or (isinstance(val, float) and val != val):
        return Decimal('0.00')
    if isinstance(val, (int, float, Decimal)):
        return Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    s_raw = str(val).strip()
    if s_raw.lower() in ('nan', 'null', 'none', '#n/a', '#ref!', '#value!', 'error'):
        raise ValueError(f"Invalid numeric value: '{s_raw}'")

    try:
        s = re.sub(r"[^\d.,\-eE+]", "", s_raw)
        if not s:
            if s_raw: raise ValueError(f"Could not parse numeric value: '{s_raw}'")
            return Decimal('0.00')
        s = s.rstrip('.,')
        if not s: return Decimal('0.00')
        if 'e' in s.lower():
            res = Decimal(s).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            return -abs(res) if '(' in s_raw and ')' in s_raw else res
        seps = [i for i, c in enumerate(s) if c in '.,']
        if len(seps) == 1: clean = s.replace(',', '.') if s[seps[0]] == ',' else s
        elif len(seps) >= 2:
            last = seps[-1]
            prefix = s[:last].replace('.', '').replace(',', '')
            clean = f"{prefix}.{s[last+1:]}" if s[last+1:] else prefix
        else: clean = s
        res = Decimal(clean).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return -abs(res) if '(' in s_raw and ')' in s_raw else res
    except Exception as e:
        if isinstance(e, ValueError): raise e
        raise ValueError(f"Could not parse numeric value '{val}': {str(e)}")


def to_decimal_percent(val: Any) -> Any:
    if val is None or val == "" or (isinstance(val, float) and val != val): return Decimal('0')
    if isinstance(val, (int, float, Decimal)): return Decimal(str(val))
    try:
        raw = str(val)
        s = re.sub(r"[^\d.,-]", "", raw)
        if not s: return val
        res = Decimal(s.replace(',', '.'))
        if "%" in raw and res > 1: res = res / Decimal('100')
        return res
    except: return val

