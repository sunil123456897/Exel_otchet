import os
import subprocess
import platform
import re
import hashlib
import shutil
import tempfile
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional


class NumericParsingError(ValueError):
    """Raised when numeric string cannot be parsed and isn't a known zero pattern."""

    pass


# Pre-compiled regex for speed - escaping hyphen to avoid ranges
RE_NUMERIC_CLEAN = re.compile(r"[^\d., \-eEP]")
RE_NUMERIC_PERCENT_CLEAN = re.compile(r"[^\d.,\-]")

# Translation table for fast removal of spaces
TRANS_REMOVE_SPACE = str.maketrans({" ": None, "\xa0": None})


def open_path(path: str):
    if platform.system() == "Windows":
        os.startfile(path)
    elif platform.system() == "Darwin":
        subprocess.run(["open", path])
    else:
        subprocess.run(["xdg-open", path])


def to_decimal(val: Any) -> Decimal:
    if val is None or val == "" or (isinstance(val, float) and val != val):
        return Decimal("0.00")
    if isinstance(val, (int, float, Decimal)):
        return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    s_raw = str(val).strip()
    if s_raw.lower() in ("nan", "null", "none", "#n/a", "#ref!", "#value!", "error"):
        raise NumericParsingError(f"Invalid numeric value: {s_raw}")

    try:
        # Fast path: translate spaces then regex clean
        s = s_raw.translate(TRANS_REMOVE_SPACE)
        s = RE_NUMERIC_CLEAN.sub("", s)

        if not s or s == "-":
            if s == "-" or not s_raw or any(c.isdigit() for c in s_raw):
                return Decimal("0.00")
            raise NumericParsingError(
                f"Silent data loss detected: '{val}' cleaned to empty or trash."
            )

        s = s.rstrip(".,")

        if "e" in s.lower():
            res = Decimal(s).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return -abs(res) if "(" in s_raw and ")" in s_raw else res

        # Handle separators faster
        if "," in s and "." in s:
            # Complex case: mixed separators. Use the last one as decimal point
            last_dot = s.rfind(".")
            last_comma = s.rfind(",")
            if last_comma > last_dot:
                # Comma is the decimal point
                s = s.replace(".", "").replace(",", ".")
            else:
                # Dot is the decimal point
                s = s.replace(",", "")
        elif "," in s:
            # Only commas - likely decimal point in RU locale or thousands separator
            # If there's only one comma, it's likely decimal
            if s.count(",") == 1:
                s = s.replace(",", ".")
            else:
                s = s.replace(",", "")

        res = Decimal(s).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return -abs(res) if "(" in s_raw and ")" in s_raw else res
    except Exception as e:
        if isinstance(e, NumericParsingError):
            raise e
        raise NumericParsingError(f"Could not parse numeric value {val}: {str(e)}")


def to_decimal_percent(val: Any) -> Any:
    if val is None or val == "" or (isinstance(val, float) and val != val):
        return Decimal("0")
    if isinstance(val, (int, float, Decimal)):
        return Decimal(str(val))
    try:
        raw = str(val)
        s = raw.translate(TRANS_REMOVE_SPACE)
        if not all(c in "0123456789.,-" for c in s):
            s = RE_NUMERIC_PERCENT_CLEAN.sub("", s)
        if not s:
            return val
        res = Decimal(s.replace(",", "."))
        if "%" in raw and res > 1:
            res = res / Decimal("100")
        return res
    except:
        return val


def is_file_writable(path: str) -> bool:
    p = Path(path)
    if not p.exists():
        return True
    try:
        with open(str(p), "r+b") as f:
            pass
        return True
    except (IOError, PermissionError, OSError):
        return False


_CACHE_DIR = Path(tempfile.gettempdir()) / "master_report_cache"


def get_local_copy(network_path: str, drive_letters: tuple = ("Q", "Z")) -> tuple:
    is_network = (
        network_path.startswith("\\\\") or network_path[0].upper() in drive_letters
    )
    if not is_network:
        return network_path, None

    try:
        stat = os.stat(network_path)
    except OSError:
        return network_path, None

    key = hashlib.md5(
        f"{network_path}_{stat.st_mtime}_{stat.st_size}".encode()
    ).hexdigest()
    suffix = Path(network_path).suffix
    local_path = _CACHE_DIR / f"{key}{suffix}"

    if local_path.exists():
        return str(local_path), None

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(network_path, str(local_path))
        return str(local_path), None
    except Exception:
        fd, temp_file = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        try:
            shutil.copy2(network_path, temp_file)
            return temp_file, temp_file
        except Exception:
            return network_path, None
