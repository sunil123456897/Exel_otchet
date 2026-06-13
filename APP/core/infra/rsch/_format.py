
from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Optional

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side


logger = logging.getLogger(__name__)

RSCH_HEADERS = [
    "ИСПОЛНИТЕЛЬ",
    "ЗАКАЗЧИК",
    "Контрагент",
    "Комментарий",
    "Приход",
    "Расход",
    "р/с",
    "Источник",
]
RSCH_TEMPLATE_HEADERS = RSCH_HEADERS

RSCH_TABLE_HEADERS = [
    "Дата",
    "ИСПОЛНИТЕЛЬ",
    "ЗАКАЗЧИК",
    "Контрагент",
    "Комментарий",
    "Приход",
    "Расход",
    "р/с",
    "Источник",
]

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RSCH_TEMPLATE_PATH = _REPO_ROOT / "РСЧ" / "шаблон отчета.xlsx"

_INCOME_FILL = PatternFill(
    start_color="FFC6EFCE", end_color="FFC6EFCE", fill_type="solid"
)
_EXPENSE_FILL = PatternFill(
    start_color="FFFFC7CE", end_color="FFFFC7CE", fill_type="solid"
)
_WARNING_FILL = PatternFill(
    start_color="FFFFFF00", end_color="FFFFFF00", fill_type="solid"
)
_INCOME_FONT = Font(color="FF006100", bold=True)
_EXPENSE_FONT = Font(color="FF9C0006", bold=True)
_HEADER_FILL = PatternFill(start_color="FF1F4E79", end_color="FF1F4E79", fill_type="solid")
_TOTAL_FILL = PatternFill(start_color="FFD9E1F2", end_color="FFD9E1F2", fill_type="solid")
_HEADER_FONT = Font(color="FFFFFFFF", bold=True)
_THIN_SIDE = Side(style="thin", color="FF000000")
_MEDIUM_SIDE = Side(style="medium", color="FF000000")
_THIN_BORDER = Border(
    left=_THIN_SIDE,
    right=_THIN_SIDE,
    top=_THIN_SIDE,
    bottom=_THIN_SIDE,
)
_TOTAL_BORDER = Border(
    left=_MEDIUM_SIDE,
    right=_MEDIUM_SIDE,
    top=_MEDIUM_SIDE,
    bottom=_MEDIUM_SIDE,
)
_HEADER_ALIGNMENT = Alignment(horizontal="center", vertical="center", wrap_text=True)
_TEXT_ALIGNMENT = Alignment(horizontal="left", vertical="top", wrap_text=True)
_ACCOUNT_ALIGNMENT = Alignment(horizontal="left", vertical="center")
_AMOUNT_ALIGNMENT = Alignment(horizontal="right", vertical="center")
_DATE_ALIGNMENT = Alignment(horizontal="left", vertical="center")
_DEFAULT_AMOUNT_NUMBER_FORMAT = "#,##0.00"
_SPECIAL_CUSTOMER_MARKERS = (
    "% по депозиту",
    "% по выплате",
    "комиссия",
    "налог",
)
_NO_ACCOUNT_MARKERS = (
    "факторинг",
    "факторнинг",
    "вф",
    "вафт фокс",
    "гетворк",
)


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\xa0", " ").lower().split())


def _is_rsch_sheet_title(sheet_title: str) -> bool:
    normalized = _normalize_text(sheet_title)
    return "рсч" in normalized and "шаблон" not in normalized


def _to_decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, bool):
        return Decimal("1") if value else Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).strip().replace(" ", "").replace("\xa0", "").replace(",", ".")
    if not text:
        return Decimal("0")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError(f"Некорректное числовое значение в РСЧ: {value}") from None


def _as_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d"):
            try:
                return datetime.strptime(stripped, fmt).date()
            except ValueError:
                continue
    return None


def _clean_executor_name(sheet_name: str) -> str:
    tokens = [
        token for token in str(sheet_name).strip().split() if token.lower() != "рсч"
    ]
    cleaned = " ".join(tokens).strip()
    return (cleaned or str(sheet_name).strip()).upper()



def _cell_text_from_row(row_values: tuple, col_idx: Optional[int]) -> str:
    if not col_idx:
        return ""
    value = row_values[col_idx - 1] if col_idx <= len(row_values) else None
    return "" if value is None else str(value).strip()


def _pick_text(primary: str, secondary: str) -> str:
    return primary if primary else secondary


def _is_special_customer_label(customer: str) -> bool:
    normalized = _normalize_text(customer)
    return any(marker in normalized for marker in _SPECIAL_CUSTOMER_MARKERS)


def _is_account_optional_row(row: Dict[str, Any]) -> bool:
    searchable = " ".join(
        _normalize_text(row.get(key))
        for key in ("executor", "customer", "contractor", "comment")
    )
    return any(marker in searchable for marker in _NO_ACCOUNT_MARKERS)


def _is_problem_row(row: Dict[str, Any]) -> bool:
    income = row["income"]
    expense = row["expense"]
    contractor = str(row["contractor"] or "").strip()
    customer = str(row["customer"] or "").strip()
    executor = str(row["executor"] or "").strip()
    account = str(row["account"] or "").strip()

    if income != 0 and expense != 0:
        return True

    is_getwork_customer = "гетворк" in _normalize_text(customer)
    if (
        not contractor
        and customer
        and not _is_special_customer_label(customer)
        and not is_getwork_customer
    ):
        return True

    if not customer or not executor:
        return True

    if not account and not _is_account_optional_row(row):
        return True

    return income == 0 and expense == 0



def _format_source_label(source_name: str, sheet_name: str, row_idx: int) -> str:
    return f"{source_name} | {sheet_name} | строка {row_idx}"



def _display_len(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, datetime):
        return 10
    if isinstance(value, Decimal):
        return len(f"{value:,.2f}")
    if isinstance(value, (int, float)):
        return len(f"{value:,.2f}")
    return len(str(value))


def _excel_safe_text(value: Any) -> Any:
    if isinstance(value, str):
        stripped = value.lstrip()
        if stripped and stripped[0] in ("=", "+", "-", "@"):
            return "'" + value
    return value


