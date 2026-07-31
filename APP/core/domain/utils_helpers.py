import re
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any


class NumericParsingError(ValueError):
    """Raised when numeric string cannot be parsed and isn't a known zero pattern."""

    pass


RE_NUMERIC_CLEAN = re.compile(r"[^\d., \-eEP]")
RE_NUMERIC_PERCENT_CLEAN = re.compile(r"[^\d.,\-]")
TRANS_REMOVE_SPACE = str.maketrans({" ": None, "\xa0": None})


def to_decimal(val: Any) -> Decimal:
    if val is None or val == "" or (isinstance(val, float) and val != val):
        return Decimal("0.00")
    if isinstance(val, (int, float, Decimal)):
        return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    s_raw = str(val).strip()
    if s_raw.lower() in ("nan", "null", "none", "#n/a", "#ref!", "#value!", "error"):
        raise NumericParsingError(f"Invalid numeric value: {s_raw}")

    try:
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

        if "," in s and "." in s:
            last_dot = s.rfind(".")
            last_comma = s.rfind(",")
            if last_comma > last_dot:
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif "," in s:
            if s.count(",") == 1:
                s = s.replace(",", ".")
            else:
                s = s.replace(",", "")

        res = Decimal(s).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return -abs(res) if "(" in s_raw and ")" in s_raw else res
    except Exception as e:
        if isinstance(e, NumericParsingError):
            raise
        raise NumericParsingError(f"Could not parse numeric value {val}: {e!s}") from e


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
            return Decimal("0")
        res = Decimal(s.replace(",", "."))
        if "%" in raw and res > 1:
            res = res / Decimal("100")
        return res
    except (ValueError, TypeError, ArithmeticError):
        return Decimal("0")


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").lower().split())


def to_decimal_lenient(
    value: Any, *, error_label: str = "Некорректное числовое значение"
) -> Decimal:
    """Lenient amount parser shared by the RSCh and reconciliation pipelines.

    Unlike :func:`to_decimal` (strict, quantized, accounting-aware), this
    parser is designed for raw Excel cells that may be booleans, pre-formatted
    strings or empty: it never quantizes, preserves the exact Decimal, treats
    ``bool``/``Decimal``/``int``/``float`` directly, strips spaces and NBSP,
    maps ``,`` to ``.``, and converts empty or ``=``-prefixed cells to zero.
    Raises ``ValueError`` (with *error_label*) only for genuinely unparseable
    values so callers can decide how to fail.
    """
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, bool):
        return Decimal("1") if value else Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip().replace(" ", "").replace("\xa0", "").replace(",", ".")
    if not text or text.startswith("="):
        return Decimal("0")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError(f"{error_label}: {value}") from None
