from decimal import Decimal
from typing import Optional, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict
from datetime import datetime


class FinancialRowSchema(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True, extra="allow")

    date: Optional[str] = None
    customer: Optional[str] = Field(None, alias="customer")
    contractor: Optional[str] = Field(None, alias="contractor")
    amount: Decimal = Decimal("0.00")
    income: Decimal = Decimal("0.00")
    expense: Decimal = Decimal("0.00")
    total: Decimal = Decimal("0.00")
    transit_obligation: Decimal = Decimal("0.00")
    commission: Decimal = Decimal("0.00")
    percent_broker: Any = Decimal("0.00")
    broker1: Decimal = Decimal("0.00")
    broker2: Decimal = Decimal("0.00")
    percent_broker2: Any = Decimal("0.00")
    exchange_rate: Decimal = Decimal("0.00")
    currency_amount: Decimal = Decimal("0.00")
    currency: Optional[str] = ""
    filters: Optional[str] = ""

    _sheet_name: Optional[str] = None
    _row_index: Optional[int] = None
    _file_path: Optional[str] = None
    is_template_warning: bool = False

    @field_validator("date", mode="before")
    @classmethod
    def validate_date(cls, v):
        if v is None:
            return None
        try:
            datetime.strptime(str(v), "%d.%m.%Y")
            return str(v)
        except ValueError:
            # If it's not in DD.MM.YYYY, we don't fail, but we might want to log it.
            # For now, let's just return it as is if it's a string, or None if it's invalid.
            return str(v)

    @field_validator(
        "amount",
        "income",
        "expense",
        "total",
        "transit_obligation",
        "commission",
        "percent_broker",
        "broker1",
        "broker2",
        "percent_broker2",
        "exchange_rate",
        "currency_amount",
        mode="before",
    )
    @classmethod
    def to_decimal(cls, v):
        if v is None or v == "":
            return Decimal("0.00")
        if isinstance(v, Decimal):
            return v
        try:
            # Handle string with comma, spaces, etc.
            s = str(v).replace(" ", "").replace(",", ".")
            # Remove any non-numeric characters except . and -
            s_clean = "".join(c for c in s if c.isdigit() or c in ".-")
            if not s_clean or s_clean == "-":
                # For percent_broker, if it's a non-empty string that resulted in empty s_clean,
                # it's likely a text like 'high'. Preserve it.
                if v and str(v).strip():
                    return v
                return Decimal("0.00")
            # Sanitize: remove extra dots/minus signs to avoid invalid Decimal
            parts = s_clean.split(".")
            if len(parts) > 2:
                s_clean = parts[0] + "." + "".join(parts[1:])
            if s_clean.count("-") > 1:
                s_clean = ("-" if s_clean.startswith("-") else "") + s_clean.replace("-", "")
            return Decimal(s_clean)
        except (ValueError, TypeError, ArithmeticError):
            return v if v and str(v).strip() else Decimal("0.00")
