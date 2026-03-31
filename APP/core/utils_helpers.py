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
    try:
        s = re.sub(r"[^\d.,\-eE+]", "", str(val).strip())
        if not s: return Decimal('0.00')
        s = s.rstrip('.,')
        if not s: return Decimal('0.00')
        if 'e' in s.lower():
            res = Decimal(s).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            return -abs(res) if '(' in str(val) and ')' in str(val) else res
        seps = [i for i, c in enumerate(s) if c in '.,']
        if len(seps) == 1: clean = s.replace(',', '.') if s[seps[0]] == ',' else s
        elif len(seps) >= 2:
            last = seps[-1]
            prefix = s[:last].replace('.', '').replace(',', '')
            clean = f"{prefix}.{s[last+1:]}" if s[last+1:] else prefix
        else: clean = s
        res = Decimal(clean).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return -abs(res) if '(' in str(val) and ')' in str(val) else res
    except: return Decimal('0.00')

def to_decimal_percent(val: Any) -> Decimal:
    d = to_decimal(val)
    if d != 0 and abs(d) <= 1:
        return d * 100
    return d

