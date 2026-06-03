from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from core.infra.excel_hyperlinks import (
    apply_cell_hyperlink,
    extract_hyperlink_formula_parts,
)
from core.infra.excel_backup import backup_existing_excel_output
from core.infra.utils import get_local_copy

MASTER_HEADERS = [
    "Источник",
    "ЗАКАЗЧИК",
    "ИСПОЛНИТЕЛЬ",
    "Приход",
    "Расход",
    "Комиссия",
    "ИТОГ",
    "% посредника",
    "посредник 1(кэш)",
    "посредник 2",
]
_MASTER_HEADER_ALIASES = {
    "Источник": ("Источник", "Сотрудник"),
    "% посредника": ("% посредника", "% посредник 1", "% посредника 1"),
    "посредник 1(кэш)": ("посредник 1(кэш)", "посредник 1"),
}
RSCH_HEADERS = [
    "ИСПОЛНИТЕЛЬ",
    "ЗАКАЗЧИК",
    "Контрагент",
    "Комментарий",
    "Приход",
    "Расход",
]
REASON_HEADER = "Причина"
STATUS_HEADER = "Статус"
RECONCILIATION_HEADERS = [*MASTER_HEADERS, STATUS_HEADER, *RSCH_HEADERS, REASON_HEADER]
REASON_NO_CURATOR = "ОШИБКА НЕТУ У КУРАТОРОВ"
REASON_NO_RSCH = "НЕТ В РСЧ"
REASON_AMOUNT_MISMATCH = "НЕ СОВПАЛА СУММА"
REASON_EXECUTOR_MISMATCH = "НЕ СОВПАЛ ИСПОЛНИТЕЛЬ"
REASON_CUSTOMER_MISMATCH = "ПОХОЖИЙ ЗАКАЗЧИК"
STATUS_VERIFIED = "СВЕРЕНО"
STATUS_REVIEW = "ПРОВЕРИТЬ"
STATUS_ERROR = "ОШИБКА"
_MATCH_TOKEN_STOPWORDS = {
    "альфа",
    "сбер",
    "сби",
    "сти",
    "стинг",
    "ука",
    "реестр",
}
_COMBINED_SHEET_PRIORITY = {"Общий": 0, "Борис": 1, "Иван": 2}
_EXCLUDED_MASTER_FILTER_KEYWORDS = (
    "доп сф",
    "доп сы",
    "касса",
    "зачет",
    "посредник",
    "корректировка",
)
_SUMMARY_REASON_LABELS = {
    REASON_NO_CURATOR: "Нет у кураторов",
    REASON_NO_RSCH: "Нет в РСЧ",
    REASON_AMOUNT_MISMATCH: "Не совпала сумма",
    REASON_EXECUTOR_MISMATCH: "Не совпал исполнитель",
    REASON_CUSTOMER_MISMATCH: "Похожий заказчик",
}

_HEADER_FILL = PatternFill("solid", fgColor="FF1F4E79")
_STATUS_OK_FILL = PatternFill("solid", fgColor="FF00B050")
_STATUS_REVIEW_FILL = PatternFill("solid", fgColor="FFFFEB9C")
_STATUS_ERROR_FILL = PatternFill("solid", fgColor="FFFFC7CE")
_MASTER_EXPENSE_FILL = PatternFill("solid", fgColor="FFFFC7CE")
_HEADER_FONT = Font(color="FFFFFFFF", bold=True)
_STATUS_FONT = Font(color="FF000000", bold=True)
_THIN_SIDE = Side(style="thin", color="FF000000")
_THIN_BORDER = Border(
    left=_THIN_SIDE,
    right=_THIN_SIDE,
    top=_THIN_SIDE,
    bottom=_THIN_SIDE,
)


@dataclass(frozen=True)
class MasterReconciliationRow:
    values: list[Any]
    source: Any
    source_link: str | None
    customer: str
    executor: str
    income: Decimal
    expense: Decimal


@dataclass(frozen=True)
class RschReconciliationRow:
    row_id: str
    executor: str
    customer: str
    contractor: str
    comment: str
    income: Decimal
    expense: Decimal
    source_link: str | None


@dataclass(frozen=True)
class ReconciliationRow:
    master: Optional[MasterReconciliationRow]
    rsch: Optional[RschReconciliationRow]
    status: str
    reason: str = ""


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return _normalize_text_cached(str(value))


@lru_cache(maxsize=65536)
def _normalize_text_cached(text: str) -> str:
    return " ".join(text.replace("\xa0", " ").replace("ё", "е").lower().split())


def _canonical_match_text(value: Any) -> str:
    return _canonical_match_text_cached(_normalize_text(value))


@lru_cache(maxsize=65536)
def _canonical_match_text_cached(text: str) -> str:
    text = re.sub(r"([а-я])([a-z])", r"\1 \2", text)
    text = re.sub(r"([a-z])([а-я])", r"\1 \2", text)
    text = text.replace("gabriel", "габриэль")
    # UKA: "УК Альянс", "УКАльянс", "УК А", "УКА_Альфа", "УКА_Сбер", "УКА_ВТБ", "УК_ВТБ", "УК_Альфа"
    # Note: input is already lowercased+collapsed by _normalize_text, but `_` survives
    # and is a word char in Python regex (\b does NOT trigger after "с" in "сбер" when
    # followed by "_"). So we use a lookbehind for non-cyrillic instead of \b.
    text = re.sub(r"(?<![а-я])ук(?:а_альфа|а_сбер|а_втб|альянс|альфа|втб)", "ука", text)
    text = re.sub(r"\bук[\s_]+альянс\b", "ука", text)
    text = re.sub(r"\bукальянс\b", "ука", text)
    text = re.sub(r"(?<![а-я])укалинс(?![а-я])", "ука", text)  # common typo
    text = re.sub(r"\bул[\s_]+альянс\b", "ука", text)  # "Ул альянс" = УК Альянс
    text = re.sub(r"\bук[\s_]+а\b", "ука", text)
    text = re.sub(r"\bук[\s_]+аф\b", "ука", text)  # "УК Аф..." (shorthand for УК А + bank)
    text = re.sub(r"\bук[\s_]+(?=(альфа|сбер|втб|сб)\b)", "ука ", text)
    # Catch-all: any word starting with ука+letters (optionally _bank suffix)
    text = re.sub(r"(?<![а-я])ука[а-я]*(?:_[а-я]+)?(?![а-я])", "ука", text)
    # "Сбер_РН" used as a synonym for УК Альянс routed via Sber settlement account
    text = re.sub(r"(?<![а-я])сбер[\s_]*рн(?![а-я])", "ука", text)
    # Tinkoff: "Тина", "Тинадар", "Тинадар", "Тина Сбер"
    # Note: re.sub replaces the matched text verbatim; "[\s_]*" with trailing \b
    # would eat a trailing space. Anchor with explicit lookahead or use \b before/after.
    text = re.sub(r"\bтина(?:[\s_]*(?:дар|да|бизнес))?(?![а-я])", "тина", text)
    text = re.sub(r"\bтина[\s_]+сбер\b", "тина", text)
    # Billtrade: "Билл", "Билтрейд", "Биллтрейд"
    text = re.sub(r"\bбилл?трейд\b", "биллтрейд", text)
    text = re.sub(r"\bбилл(?!\w)", "биллтрейд", text)
    text = re.sub(r"\bбилтрейд\b", "биллтрейд", text)
    # ANO Техникум: "АНО ТСК", "АНО ТЕХНИКУМ"
    text = re.sub(r"\bано[\s_]+тск\b", "анотехникум", text)
    text = re.sub(r"\bано[\s_]+техникум\b", "анотехникум", text)
    text = re.sub(r"(?<![а-я])тск(?:(?:[\s_]+сбер)|(?:[\s_]+альфа)|(?:[\s_]+втб)|(?:[\s_]+сб))?(?![а-я])", "анотехникум", text)
    # SB Защита: "СБ ЗАЩИТА", "Защита РРБ", "Защита"
    text = re.sub(r"\bсб[\s_]+защита\b", "сбзащита", text)
    text = re.sub(r"\bзащита[\s_]+ррб\b", "сбзащита", text)
    # Стинг: "Стип", "СтипСбер", "Стинг", "СТИ Сбер"
    text = re.sub(r"\bстип[\s_]*сбер\b", "стинг", text)
    text = re.sub(r"(?<![а-я])стип(?![а-я])", "стинг", text)
    text = re.sub(r"\bстинг[\s_]*сбер\b", "стинг сбер", text)
    text = re.sub(r"(?<![а-я])сти(?:[\s_]+сбер|[\s_]+альфа|[\s_]+втб|[\s_]+сб)?(?![а-я])", "стинг", text)
    # Прайм = Прессбук (один банк)
    text = re.sub(r"\bпрайм\b", "прессбук", text)
    # ПБ = Прессбук (compact form)
    text = re.sub(r"(?<![а-я])пб(?:[\s_]+альфа|[\s_]+сбер|[\s_]+втб)?(?![а-я])", "прессбук", text)
    # Fuzzy typos for Прессбук: преессбук, прссбук, перссбук, прессбук
    text = re.sub(r"(?<![а-я])пр[её]+?ссбук(?![а-я])", "прессбук", text)
    text = re.sub(r"(?<![а-я])пе?рссбук(?![а-я])", "прессбук", text)
    # Пиплкрафт: "Пип", "ПипКрафт", "Пипл Сбер", "Пип крафт Альфа"
    # NOTE: (?!л) prevents matching "пип" inside "пипл" which would
    # leave trailing characters (e.g. "пипл крафт" → "пипл крафтл крафт").
    text = re.sub(r"(?<![а-я])пип(?!л)(?:[\s_]*крафт)?(?:[\s_]+альфа|[\s_]+сбер|[\s_]+втб)?", "пипл крафт", text)
    # Normalise "Пипл" (the full short form) with a bank suffix to canonical form.
    # "Пипл сбер" → "пипл крафт сбер", "Пипл Альфа" → "пипл крафт альфа"
    text = re.sub(r"(?<![а-я])пипл(?:[\s_]+крафт)?[\s_]+(альфа|сбер|втб|сб)\b", r"пипл крафт \1", text)
    # Standalone "пипл" without банк suffix: keep as is, tokens will match via alias keys
    # ПУ = Пиплкрафт (ПК в одном контексте)
    text = re.sub(r"\bпу[\s_]*(альфа|сбер|втб)\b", r"пипл крафт \1", text)
    text = re.sub(r"\bпу\b", "пиплкрафт", text)
    # ПК = Пиплкрафт
    text = re.sub(r"\bпк[\s_]*(альфа|сбер|втб|аф)?\b", r"пипл крафт", text)
    # СБ = СБИ (СтройБизнесИнвест)
    text = re.sub(r"(?<![а-я])стройбизнесинвест(?![а-я])", "сби", text)
    # СТ = Спецстаффсервис
    text = re.sub(r"\bст[\s_]*(втб|альфа|сбер|бизнес)\b", r"ссс \1", text)
    text = re.sub(r"\bст\b", "ссс", text)
    # ВоркБрайт = ВБ (Slot WorkBright)
    text = re.sub(r"(?<![а-я])слот[\s_]*воркбрайт(?![а-я])", "вб", text)
    text = re.sub(r"(?<![а-я])воркбрайт(?![а-я])", "вб", text)
    return text


def _compact_text(value: Any) -> str:
    return _compact_text_cached(_canonical_match_text(value))


@lru_cache(maxsize=65536)
def _compact_text_cached(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum())


def _text_tokens(value: Any) -> set[str]:
    return set(_text_tokens_cached(_canonical_match_text(value)))


@lru_cache(maxsize=65536)
def _text_tokens_cached(text: str) -> frozenset[str]:
    tokens = set()
    for token in re.split(r"[^0-9a-zа-я]+", text):
        if len(token) >= 4 and not token.isdigit() and token not in _MATCH_TOKEN_STOPWORDS:
            tokens.add(token)
    return frozenset(tokens)


def _weak_customer_tokens(value: Any) -> set[str]:
    ignored = {
        "готово",
        "корр",
        "проект",
        "труд",
        "нетруд",
        "выплата",
        "зарплатного",
    }
    return {token for token in _text_tokens(value) if token not in ignored}


def _executor_tokens(value: Any) -> list[str]:
    return list(_executor_tokens_cached(_canonical_match_text(value)))


@lru_cache(maxsize=65536)
def _executor_tokens_cached(text: str) -> tuple[str, ...]:
    return tuple(token for token in re.split(r"[^0-9a-zа-я]+", text) if len(token) >= 2)


def _executor_alias_keys(value: Any) -> set[str]:
    compact = _compact_text(value)
    tokens = set(_executor_tokens(value))
    aliases = {compact} if compact else set()

    if compact in {"мосальфа", "моссбер", "мосвтб"} or "мос" in tokens:
        aliases.add("мос")
    if (
        compact in {"пк", "пкальфа", "пксбер", "пксб"}
        or compact.startswith(("пиплкрафт", "пилпкрафт"))
        or {"пипл", "крафт"}.issubset(tokens)
        or {"пилп", "крафт"}.issubset(tokens)
    ):
        aliases.add("пиплкрафт")
    if (
        compact in {"пб", "пбальфа", "пбсбер", "пбсб"}
        or compact.startswith(("прессбук", "пресс", "прес"))
    ):
        aliases.add("прессбук")
    if compact.startswith(("ссс", "спецстафф", "спецстаф")):
        aliases.add("спецстаффсервис")
    if compact.startswith("воркбрайт") or compact == "вб":
        aliases.add("вб")
    if compact.startswith("ук") and len(compact) >= 3:
        aliases.add("ук")
    return aliases


def _is_filter_header(value: Any) -> bool:
    return _normalize_text(value) in {"фильтр", "фильтры", "filter", "filters"}


def _is_excluded_master_filter(value: Any) -> bool:
    normalized = _normalize_text(value)
    collapsed = normalized.replace(".", " ").replace(",", " ")
    collapsed = " ".join(collapsed.split())
    return any(
        keyword in collapsed
        for keyword in _EXCLUDED_MASTER_FILTER_KEYWORDS
    ) or any(keyword in normalized for keyword in _EXCLUDED_MASTER_FILTER_KEYWORDS)


def _is_excluded_master_header(value: Any) -> bool:
    return _normalize_text(value) in {
        "отправка транзитных обязательств",
        "курс",
        "сумма",
        "валюта",
    }


def _is_excluded_customer(value: Any) -> bool:
    normalized = _normalize_text(value)
    return any(
        keyword in normalized
        for keyword in (
            "налог",
            "расход",
            "% по депозиту",
            "по депозиту",
            "% по выплате",
            "по выплате",
            "комиссия",
        )
    )


def _is_excluded_rsch_comment(value: Any) -> bool:
    return "перевод" in re.split(r"[^0-9a-zа-я]+", _normalize_text(value))


def _is_numeric_header(value: Any) -> bool:
    normalized = _normalize_text(value)
    return any(
        keyword in normalized
        for keyword in (
            "приход",
            "расход",
            "комиссия",
            "итог",
            "посредник",
            "транзит",
            "сумма",
        )
    )


def _is_percent_header(value: Any) -> bool:
    return "%" in str(value or "")


def _to_decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = str(value).replace(" ", "").replace(",", ".").strip()
    if not text or text.startswith("="):
        return Decimal("0")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        raise ValueError(f"Некорректное числовое значение в сверке: {value}") from None


def _amount_equal(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) <= Decimal("0.01")


def _row_amount_matches(master: MasterReconciliationRow, rsch: RschReconciliationRow) -> bool:
    income_matches = master.income != 0 and _amount_equal(master.income, rsch.income)
    expense_matches = master.expense != 0 and _amount_equal(master.expense, rsch.expense)
    return income_matches or expense_matches


def _executor_matches(master_executor: str, rsch_executor: str) -> bool:
    left = _canonical_match_text(master_executor)
    right = _canonical_match_text(rsch_executor)
    if not left or not right:
        return False
    if left == right or _compact_text(left) == _compact_text(right):
        return True
    if _executor_alias_keys(left) & _executor_alias_keys(right):
        return True
    left_tokens = set(_executor_tokens(left))
    right_tokens = set(_executor_tokens(right))
    if not left_tokens or not right_tokens:
        return False
    return left_tokens.issubset(right_tokens) or right_tokens.issubset(left_tokens)


def _customer_matches(master_customer: str, rsch_customer: str) -> bool:
    left = _normalize_text(master_customer)
    right = _normalize_text(rsch_customer)
    return bool(left and right and (left in right or right in left))


def _customer_matches_loose(left_value: str, right_value: str) -> bool:
    if _customer_matches(left_value, right_value):
        return True
    left = _compact_text(left_value)
    right = _compact_text(right_value)
    if len(left) >= 6 and len(right) >= 6 and (left in right or right in left):
        return True
    common_tokens = _text_tokens(left_value) & _text_tokens(right_value)
    return len(common_tokens) >= 2


def _rsch_customer_matches(master_customer: str, rsch_row: RschReconciliationRow) -> bool:
    return any(
        _customer_matches_loose(master_customer, candidate)
        for candidate in (rsch_row.customer, rsch_row.contractor, rsch_row.comment)
    )


def _customer_matches_weak(left_value: str, right_value: str) -> bool:
    if _customer_matches_loose(left_value, right_value):
        return False
    common_tokens = _weak_customer_tokens(left_value) & _weak_customer_tokens(right_value)
    return bool(common_tokens)


def _rsch_customer_matches_weak(master_customer: str, rsch_row: RschReconciliationRow) -> bool:
    return any(
        _customer_matches_weak(master_customer, candidate)
        for candidate in (rsch_row.customer, rsch_row.contractor, rsch_row.comment)
    )


def _sheet_candidates(target_date: date) -> tuple[str, str]:
    return target_date.strftime("%d.%m.%Y"), target_date.strftime("%d.%m")


def _coerce_date(value: date) -> date:
    if isinstance(value, datetime):
        return value.date()
    return value


def _parse_full_sheet_date(sheet_title: str) -> date | None:
    try:
        return datetime.strptime(sheet_title, "%d.%m.%Y").date()
    except ValueError:
        return None


def _parse_day_month_sheet(sheet_title: str) -> tuple[int, int] | None:
    try:
        parsed = datetime.strptime(sheet_title, "%d.%m")
    except ValueError:
        return None
    return parsed.day, parsed.month


def _has_sheet_for_date(wb, target_date: date) -> bool:
    candidates = set(_sheet_candidates(target_date))
    return any(ws.title in candidates for ws in wb.worksheets)


def _workbook_sheet_dates(wb) -> tuple[set[date], set[tuple[int, int]]]:
    full_dates: set[date] = set()
    day_months: set[tuple[int, int]] = set()
    for ws in wb.worksheets:
        full_date = _parse_full_sheet_date(ws.title)
        if full_date is not None:
            full_dates.add(full_date)
            continue
        day_month = _parse_day_month_sheet(ws.title)
        if day_month is not None:
            day_months.add(day_month)
    return full_dates, day_months


def _common_sheet_dates(master_wb, rsch_wb) -> list[date]:
    master_dates, master_day_months = _workbook_sheet_dates(master_wb)
    rsch_dates, rsch_day_months = _workbook_sheet_dates(rsch_wb)
    common = set(master_dates & rsch_dates)
    common.update(
        d for d in master_dates if (d.day, d.month) in rsch_day_months
    )
    common.update(
        d for d in rsch_dates if (d.day, d.month) in master_day_months
    )
    return sorted(common)


def _format_dates(dates: list[date]) -> str:
    return ", ".join(d.strftime("%d.%m.%Y") for d in dates)


def _resolve_target_date(master_wb, rsch_wb, target_date: date | None) -> date:
    if target_date is not None:
        target_date = _coerce_date(target_date)
        if _has_sheet_for_date(master_wb, target_date) and _has_sheet_for_date(
            rsch_wb,
            target_date,
        ):
            return target_date
        raise ValueError(
            f"Не найден лист за дату {target_date.strftime('%d.%m.%Y')} "
            "в выбранной паре мастер- и РСЧ-файлов"
        )

    common_dates = _common_sheet_dates(master_wb, rsch_wb)
    if len(common_dates) == 1:
        return common_dates[0]

    if not common_dates:
        raise ValueError("Не найдена общая дата в выбранных мастер- и РСЧ-файлах")

    raise ValueError(
        "В выбранных файлах найдено несколько общих дат: "
        f"{_format_dates(common_dates)}. Выберите нужную дату в панели слева."
    )


def _find_sheet(wb, target_date: date) -> Worksheet:
    target_date = _coerce_date(target_date)
    candidates = set(_sheet_candidates(target_date))
    for ws in wb.worksheets:
        if ws.title in candidates:
            return ws
    raise ValueError(
        f"Не найден лист за дату {target_date.strftime('%d.%m.%Y')}"
    )


def _header_map(ws: Worksheet, *, prefer_last: bool = False) -> dict[str, int]:
    headers: dict[str, int] = {}
    for col_idx in range(1, ws.max_column + 1):
        value = ws.cell(1, col_idx).value
        if value in (None, ""):
            continue
        header = str(value).strip()
        if prefer_last or header not in headers:
            headers[header] = col_idx
    return headers


def _master_output_headers(ws: Worksheet) -> list[str]:
    headers: list[str] = []
    for col_idx in range(1, ws.max_column + 1):
        value = ws.cell(1, col_idx).value
        if value in (None, "") or _is_filter_header(value) or _is_excluded_master_header(value):
            continue
        headers.append(str(value).strip())
    return headers


def _header_index(
    headers: dict[str, int],
    header: str,
    *,
    required: bool = True,
) -> int | None:
    aliases = _MASTER_HEADER_ALIASES.get(header, (header,))
    for alias in aliases:
        if alias in headers:
            return headers[alias]

    normalized_headers = {_normalize_text(key): value for key, value in headers.items()}
    for alias in aliases:
        normalized_alias = _normalize_text(alias)
        if normalized_alias in normalized_headers:
            return normalized_headers[normalized_alias]

    if required:
        raise KeyError(header)
    return None


def _master_cell_value(
    ws: Worksheet,
    row_idx: int,
    headers: dict[str, int],
    header: str,
) -> Any:
    col_idx = _header_index(headers, header, required=False)
    if col_idx is None:
        return None
    return _cell_display_value(ws, row_idx, col_idx)


def _is_total_row(value: Any) -> bool:
    return _normalize_text(value).startswith("итого")


def _cell_hyperlink_target(ws: Worksheet, row_idx: int, col_idx: int) -> str | None:
    formula_parts = extract_hyperlink_formula_parts(ws.cell(row_idx, col_idx).value)
    if formula_parts is not None:
        return formula_parts[0]
    hyperlink = ws.cell(row_idx, col_idx).hyperlink
    if hyperlink is None:
        return None
    target = hyperlink.target or hyperlink.location
    if target is None:
        return None
    return target.split("#", 1)[0]


def _cell_display_value(ws: Worksheet, row_idx: int, col_idx: int) -> Any:
    value = ws.cell(row_idx, col_idx).value
    formula_parts = extract_hyperlink_formula_parts(value)
    if formula_parts is not None:
        return formula_parts[1]
    return value


def _collect_master_rows(
    ws: Worksheet,
) -> tuple[list[str], list[MasterReconciliationRow], list[MasterReconciliationRow]]:
    headers = _header_map(ws)
    output_headers = _master_output_headers(ws)
    source_col = _header_index(headers, "Источник")
    customer_col = _header_index(headers, "ЗАКАЗЧИК")
    executor_col = _header_index(headers, "ИСПОЛНИТЕЛЬ")
    income_col = _header_index(headers, "Приход")
    expense_col = _header_index(headers, "Расход")
    filter_col = _header_index(headers, "Фильтры", required=False)
    rows: list[MasterReconciliationRow] = []
    excluded_rows: list[MasterReconciliationRow] = []
    for row_idx in range(2, ws.max_row + 1):
        source = _cell_display_value(ws, row_idx, source_col)
        if _is_total_row(source):
            continue
        customer = str(ws.cell(row_idx, customer_col).value or "").strip()
        executor = str(ws.cell(row_idx, executor_col).value or "").strip()
        if not customer and not executor:
            continue
        income = _to_decimal(ws.cell(row_idx, income_col).value)
        expense = _to_decimal(ws.cell(row_idx, expense_col).value)
        if income == 0 and expense == 0:
            continue
        values = [
            _master_cell_value(ws, row_idx, headers, header) for header in output_headers
        ]
        row = MasterReconciliationRow(
            values=values,
            source=source,
            source_link=_cell_hyperlink_target(ws, row_idx, source_col),
            customer=customer,
            executor=executor,
            income=income,
            expense=expense,
        )
        if filter_col is not None and _is_excluded_master_filter(
            _cell_display_value(ws, row_idx, filter_col)
        ):
            excluded_rows.append(row)
        else:
            rows.append(row)
    return output_headers, rows, excluded_rows


def _collect_rsch_rows(ws: Worksheet) -> list[RschReconciliationRow]:
    headers = _header_map(ws, prefer_last=True)
    rows: list[RschReconciliationRow] = []
    for row_idx in range(2, ws.max_row + 1):
        first = ws.cell(row_idx, 1).value
        if _is_total_row(first):
            continue
        income = _to_decimal(ws.cell(row_idx, headers["Приход"]).value)
        expense = _to_decimal(ws.cell(row_idx, headers["Расход"]).value)
        if income == 0 and expense == 0:
            continue
        customer = str(ws.cell(row_idx, headers["ЗАКАЗЧИК"]).value or "").strip()
        if _is_excluded_customer(customer):
            continue
        comment = str(ws.cell(row_idx, headers["Комментарий"]).value or "").strip()
        if _is_excluded_rsch_comment(comment):
            continue
        rows.append(
            RschReconciliationRow(
                row_id=f"{ws.title}:{row_idx}",
                executor=str(ws.cell(row_idx, headers["ИСПОЛНИТЕЛЬ"]).value or "").strip(),
                customer=customer,
                contractor=str(ws.cell(row_idx, headers["Контрагент"]).value or "").strip(),
                comment=comment,
                income=income,
                expense=expense,
                source_link=_cell_hyperlink_target(ws, row_idx, headers.get("Источник", 1)),
            )
        )
    return rows


def _find_best_rsch_match(
    master_row: MasterReconciliationRow,
    customer_candidates: list[tuple[int, RschReconciliationRow]],
    used_indexes: set[int],
) -> tuple[Optional[int], Optional[RschReconciliationRow]]:
    amount_candidates = [
        (idx, row)
        for idx, row in customer_candidates
        if idx not in used_indexes and _row_amount_matches(master_row, row)
    ]
    for idx, row in amount_candidates:
        if _executor_matches(master_row.executor, row.executor):
            return idx, row
    return None, None


def _find_likely_executor_mismatch(
    master_row: MasterReconciliationRow,
    customer_candidates: list[tuple[int, RschReconciliationRow]],
    used_indexes: set[int],
) -> tuple[Optional[int], Optional[RschReconciliationRow]]:
    for idx, row in customer_candidates:
        if idx not in used_indexes and _row_amount_matches(master_row, row):
            return idx, row
    return None, None


def _find_likely_rsch_mismatch(
    master_row: MasterReconciliationRow,
    customer_candidates: list[tuple[int, RschReconciliationRow]],
    used_indexes: set[int],
) -> tuple[Optional[int], Optional[RschReconciliationRow]]:
    for idx, row in customer_candidates:
        if idx not in used_indexes and _executor_matches(master_row.executor, row.executor):
            return idx, row
    return None, None


def _weak_customer_review_candidate_matches(
    master_row: MasterReconciliationRow,
    rsch_row: RschReconciliationRow,
) -> bool:
    return (
        _row_amount_matches(master_row, rsch_row)
        and _executor_matches(master_row.executor, rsch_row.executor)
        and _rsch_customer_matches_weak(master_row.customer, rsch_row)
    )


def _find_likely_customer_mismatch(
    master_idx: int,
    master_count: int,
    get_weak_candidates: Callable[[int], list[tuple[int, RschReconciliationRow]]],
    used_indexes: set[int],
    exact_master_indexes: set[int],
) -> tuple[Optional[int], Optional[RschReconciliationRow]]:
    candidates = [
        (idx, row)
        for idx, row in get_weak_candidates(master_idx)
        if idx not in used_indexes
    ]
    if len(candidates) != 1:
        return None, None

    candidate_idx, candidate = candidates[0]
    competing_masters = [
        idx
        for idx in range(master_count)
        if idx != master_idx
        and idx not in exact_master_indexes
        and any(
            other_candidate_idx == candidate_idx
            for other_candidate_idx, _ in get_weak_candidates(idx)
        )
    ]
    if competing_masters:
        return None, None
    return candidate_idx, candidate


def _surname_tokens(value: str) -> set[str]:
    raw = re.split(r"[^a-zа-яёA-ZА-ЯЁ]+", str(value))
    return {
        w.lower() for w in raw
        if len(w) >= 3 and w[0].isalpha() and w[0].upper() == w[0]
    }


def _customer_surname_matches(
    master_customer: str,
    rsch_row: RschReconciliationRow,
) -> bool:
    master_surnames = _surname_tokens(master_customer)
    if not master_surnames:
        return False
    rsch_text = f"{rsch_row.comment or ''} {rsch_row.contractor or ''}".lower()
    return any(surname in rsch_text for surname in master_surnames)


def _find_surname_rsch_match(
    master_row: MasterReconciliationRow,
    rsch_rows: list[RschReconciliationRow],
    used_indexes: set[int],
) -> tuple[int | None, RschReconciliationRow | None]:
    candidates = [
        (idx, row)
        for idx, row in enumerate(rsch_rows)
        if idx not in used_indexes
        and _row_amount_matches(master_row, row)
        and _executor_matches(master_row.executor, row.executor)
        and _customer_surname_matches(master_row.customer, row)
    ]
    if not candidates:
        return None, None
    return candidates[0]


def _build_reconciliation_rows(
    master_rows: list[MasterReconciliationRow],
    rsch_rows: list[RschReconciliationRow],
) -> list[ReconciliationRow]:
    result: list[ReconciliationRow] = []
    used_rsch_indexes: set[int] = set()
    exact_matches: dict[int, int] = {}
    customer_candidates_by_master = [
        [
            (idx, row)
            for idx, row in enumerate(rsch_rows)
            if _rsch_customer_matches(master_row.customer, row)
        ]
        for master_row in master_rows
    ]
    weak_candidates_by_master: dict[int, list[tuple[int, RschReconciliationRow]]] = {}

    def get_weak_candidates(master_idx: int) -> list[tuple[int, RschReconciliationRow]]:
        candidates = weak_candidates_by_master.get(master_idx)
        if candidates is None:
            master_row = master_rows[master_idx]
            candidates = [
                (idx, row)
                for idx, row in enumerate(rsch_rows)
                if _weak_customer_review_candidate_matches(master_row, row)
            ]
            weak_candidates_by_master[master_idx] = candidates
        return candidates

    for master_idx, master_row in enumerate(master_rows):
        match_idx, rsch_row = _find_best_rsch_match(
            master_row,
            customer_candidates_by_master[master_idx],
            used_rsch_indexes,
        )
        if rsch_row is not None and match_idx is not None:
            used_rsch_indexes.add(match_idx)
            exact_matches[master_idx] = match_idx

    for master_idx, master_row in enumerate(master_rows):
        if master_idx in exact_matches:
            rsch_row = rsch_rows[exact_matches[master_idx]]
            ok = _executor_matches(master_row.executor, rsch_row.executor)
            result.append(
                ReconciliationRow(
                    master=master_row,
                    rsch=rsch_row,
                    status=STATUS_VERIFIED if ok else STATUS_REVIEW,
                    reason="" if ok else REASON_EXECUTOR_MISMATCH,
                )
            )
            continue

        match_idx, rsch_row = _find_likely_executor_mismatch(
            master_row,
            customer_candidates_by_master[master_idx],
            used_rsch_indexes,
        )
        if rsch_row is not None and match_idx is not None:
            used_rsch_indexes.add(match_idx)
            result.append(
                ReconciliationRow(
                    master=master_row,
                    rsch=rsch_row,
                    status=STATUS_REVIEW,
                    reason=REASON_EXECUTOR_MISMATCH,
                )
            )
            continue

        match_idx, rsch_row = _find_likely_rsch_mismatch(
            master_row,
            customer_candidates_by_master[master_idx],
            used_rsch_indexes,
        )
        if rsch_row is not None and match_idx is not None:
            used_rsch_indexes.add(match_idx)
            result.append(
                ReconciliationRow(
                    master=master_row,
                    rsch=rsch_row,
                    status=STATUS_REVIEW,
                    reason=REASON_AMOUNT_MISMATCH,
                )
            )
            continue

        match_idx, rsch_row = _find_likely_customer_mismatch(
            master_idx,
            len(master_rows),
            get_weak_candidates,
            used_rsch_indexes,
            set(exact_matches),
        )
        if rsch_row is not None and match_idx is not None:
            used_rsch_indexes.add(match_idx)
            result.append(
                ReconciliationRow(
                    master=master_row,
                    rsch=rsch_row,
                    status=STATUS_REVIEW,
                    reason=REASON_CUSTOMER_MISMATCH,
                )
            )
            continue

        match_idx, rsch_row = _find_surname_rsch_match(
            master_row,
            rsch_rows,
            used_rsch_indexes,
        )
        if rsch_row is not None and match_idx is not None:
            used_rsch_indexes.add(match_idx)
            result.append(
                ReconciliationRow(
                    master=master_row,
                    rsch=rsch_row,
                    status=STATUS_REVIEW,
                    reason=REASON_CUSTOMER_MISMATCH,
                )
            )
            continue

        result.append(
            ReconciliationRow(
                master=master_row,
                rsch=None,
                status=STATUS_ERROR,
                reason=REASON_NO_RSCH,
            )
        )

    for idx, row in enumerate(rsch_rows):
        if idx in used_rsch_indexes:
            continue
        result.append(
            ReconciliationRow(
                master=None,
                rsch=row,
                status=STATUS_ERROR,
                reason=REASON_NO_CURATOR,
            )
        )
    return result


def _suppress_rsch_rows_matched_by_excluded_master_filters(
    rsch_rows: list[RschReconciliationRow],
    excluded_master_rows: list[MasterReconciliationRow],
) -> list[RschReconciliationRow]:
    if not excluded_master_rows:
        return rsch_rows

    suppressed_indexes: set[int] = set()
    for master_row in excluded_master_rows:
        candidates = [
            (idx, row)
            for idx, row in enumerate(rsch_rows)
            if idx not in suppressed_indexes
            and _rsch_customer_matches(master_row.customer, row)
        ]
        match_idx, _rsch_row = _find_best_rsch_match(
            master_row,
            candidates,
            suppressed_indexes,
        )
        if match_idx is not None:
            suppressed_indexes.add(match_idx)

    if not suppressed_indexes:
        return rsch_rows
    return [
        row
        for idx, row in enumerate(rsch_rows)
        if idx not in suppressed_indexes
    ]


def _rsch_values(row: Optional[RschReconciliationRow]) -> list[Any]:
    if row is None:
        return [None, None, None, None, None, None]
    return [
        _excel_safe_text(row.executor),
        _excel_safe_text(row.customer),
        _excel_safe_text(row.contractor),
        _excel_safe_text(row.comment),
        row.income if row.income != 0 else None,
        row.expense if row.expense != 0 else None,
    ]


def _excel_safe_text(value: Any) -> Any:
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def _master_values(row: ReconciliationRow, master_headers: list[str]) -> list[Any]:
    if row.master is not None:
        return [_excel_safe_text(value) for value in row.master.values]
    values: list[Any] = [None for _ in master_headers]
    if values:
        values[0] = _excel_safe_text(row.reason)
    return values


def _reason_label(reason: str) -> str:
    return _SUMMARY_REASON_LABELS.get(reason, reason)


def _write_headers(ws: Worksheet, headers: list[str]) -> None:
    ws.append(headers)
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(1, col_idx)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = _THIN_BORDER


def _update_column_widths(widths: dict[int, int], values: list[Any]) -> None:
    for col_idx, value in enumerate(values, start=1):
        widths[col_idx] = max(
            widths.get(col_idx, 0),
            len(str(value)) if value is not None else 0,
        )


def _apply_column_widths(ws: Worksheet, widths: dict[int, int]) -> None:
    wide_text_headers = ("заказчик", "исполнитель", "контрагент", "комментар", "источник")
    compact_min_widths = {
        "статус": 14,
        "причина": 18,
    }
    for col_idx in range(1, ws.max_column + 1):
        header = _normalize_text(ws.cell(1, col_idx).value)
        max_len = widths.get(col_idx, 0)
        min_width = 18 if _is_numeric_header(header) else 10
        for key, width in compact_min_widths.items():
            if key in header:
                min_width = max(min_width, width)
        max_width = 70 if any(key in header for key in wide_text_headers) else 45
        ws.column_dimensions[get_column_letter(col_idx)].width = max(
            min_width,
            min(max_width, max_len + 2),
        )


def _append_reconciliation_row(
    ws: Worksheet,
    row: ReconciliationRow,
    master_headers: list[str],
    column_widths: dict[int, int] | None = None,
) -> None:
    headers = [*master_headers, STATUS_HEADER, *RSCH_HEADERS, REASON_HEADER]
    status_col = len(master_headers) + 1
    reason = _reason_label(row.reason) if row.reason else None
    values = [
        *_master_values(row, master_headers),
        row.status,
        *_rsch_values(row.rsch),
        reason,
    ]
    if column_widths is not None:
        _update_column_widths(column_widths, values)
    ws.append(values)
    row_idx = ws.max_row
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row_idx, col_idx)
        cell.border = _THIN_BORDER
        cell.alignment = Alignment(
            horizontal="right" if _is_numeric_header(header) else "left",
            vertical="top",
            wrap_text=True,
        )
        if _is_numeric_header(header):
            cell.number_format = "#,##0.00"
        if _is_percent_header(header):
            cell.number_format = "0.##%"
    status_cell = ws.cell(row_idx, status_col)
    status_cell.fill = {
        STATUS_VERIFIED: _STATUS_OK_FILL,
        STATUS_REVIEW: _STATUS_REVIEW_FILL,
    }.get(row.status, _STATUS_ERROR_FILL)
    status_cell.font = _STATUS_FONT
    status_cell.alignment = Alignment(horizontal="center", vertical="center")
    if row.reason:
        status_cell.comment = Comment(_reason_label(row.reason), "Master-Report")
    source_link = row.master.source_link if row.master is not None else None
    if source_link is None and row.rsch is not None:
        source_link = row.rsch.source_link
    if source_link:
        apply_cell_hyperlink(ws.cell(row_idx, 1), source_link)
    for col_idx, header in enumerate(headers, start=1):
        if _normalize_text(header) == "расход" and ws.cell(row_idx, col_idx).value not in (
            None,
            "",
            0,
        ):
            ws.cell(row_idx, col_idx).fill = _MASTER_EXPENSE_FILL


def _autosize_columns(ws: Worksheet) -> None:
    for col_idx in range(1, ws.max_column + 1):
        max_len = 0
        for row in ws.iter_rows(min_col=col_idx, max_col=col_idx):
            value = row[0].value
            max_len = max(max_len, len(str(value)) if value is not None else 0)
        ws.column_dimensions[get_column_letter(col_idx)].width = max(
            10,
            min(45, max_len + 2),
        )


def _build_workbook(
    target_date: date,
    rows: Iterable[ReconciliationRow],
    master_headers: list[str],
) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = target_date.strftime("%d.%m.%Y")
    _write_reconciliation_sheet(ws, rows, master_headers)
    return wb


def _write_reconciliation_sheet(
    ws: Worksheet,
    rows: Iterable[ReconciliationRow],
    master_headers: list[str],
) -> None:
    status_order = {STATUS_VERIFIED: 0, STATUS_REVIEW: 1}
    row_list = sorted(rows, key=lambda row: status_order.get(row.status, 2))
    headers = [*master_headers, STATUS_HEADER, *RSCH_HEADERS, REASON_HEADER]
    _write_headers(ws, headers)
    column_widths: dict[int, int] = {}
    _update_column_widths(column_widths, headers)
    for row in row_list:
        _append_reconciliation_row(ws, row, master_headers, column_widths)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{ws.max_row}"
    _apply_column_widths(ws, column_widths)


def _build_reconciliation_sheet_data(
    master_wb,
    rsch_wb,
    target_date: date | None,
) -> tuple[date, list[str], list[ReconciliationRow]]:
    effective_date = _resolve_target_date(master_wb, rsch_wb, target_date)
    master_ws = _find_sheet(master_wb, effective_date)
    rsch_ws = _find_sheet(rsch_wb, effective_date)
    master_headers, master_rows, excluded_master_rows = _collect_master_rows(master_ws)
    rsch_rows = _suppress_rsch_rows_matched_by_excluded_master_filters(
        _collect_rsch_rows(rsch_ws),
        excluded_master_rows,
    )
    rows = _build_reconciliation_rows(master_rows, rsch_rows)
    return effective_date, master_headers, rows


def _matched_rsch_row_ids(rows: Iterable[ReconciliationRow]) -> set[str]:
    return {
        row.rsch.row_id
        for row in rows
        if row.status in {STATUS_VERIFIED, STATUS_REVIEW}
        and row.master is not None
        and row.rsch is not None
    }


def _is_rsch_only_no_curator_row(row: ReconciliationRow) -> bool:
    return (
        row.master is None
        and row.rsch is not None
        and row.reason == REASON_NO_CURATOR
    )


def _build_curator_routing(sheet_names: Iterable[str]) -> dict[str, str]:
    routing: dict[str, str] = {}
    for name in sheet_names:
        norm = _normalize_text(name)
        if norm and norm not in ("общий", "general", "all"):
            routing[norm] = name
    return routing


def _infer_rsch_row_owner(
    rsch_row: RschReconciliationRow,
    curator_routing: dict[str, str],
) -> str | None:
    comment_norm = _normalize_text(rsch_row.comment or "")
    if not comment_norm:
        return None
    for key, sheet in curator_routing.items():
        if key in comment_norm:
            return sheet
    return None


def _suppress_combined_rsch_only_rows(
    rows: Iterable[ReconciliationRow],
    matched_rsch_ids: set[str],
    seen_unmatched_rsch_ids: set[str],
    current_sheet: str,
    rsch_only_owners: dict[str, str],
) -> list[ReconciliationRow]:
    filtered = []
    for row in rows:
        if not _is_rsch_only_no_curator_row(row):
            filtered.append(row)
            continue
        assert row.rsch is not None
        row_id = row.rsch.row_id
        if row_id in matched_rsch_ids or row_id in seen_unmatched_rsch_ids:
            continue
        owner = rsch_only_owners.get(row_id)
        if owner is not None and owner != current_sheet:
            continue
        seen_unmatched_rsch_ids.add(row_id)
        filtered.append(row)
    return filtered


def _ordered_combined_master_items(
    master_paths: Mapping[str, Path | str],
) -> list[tuple[str, Path | str]]:
    original_order = {name: idx for idx, name in enumerate(master_paths)}
    return sorted(
        master_paths.items(),
        key=lambda item: (
            _COMBINED_SHEET_PRIORITY.get(item[0], len(_COMBINED_SHEET_PRIORITY)),
            original_order[item[0]],
        ),
    )


def _resolve_combined_target_date(
    master_paths: list[tuple[str, Path | str]],
    rsch_wb,
    target_date: date | None,
    drive_letters: tuple[str, ...],
) -> date | None:
    if target_date is not None:
        return _coerce_date(target_date)

    common_dates: set[date] = set()
    for sheet_name, master_path_value in master_paths:
        master_path = Path(master_path_value)
        if not master_path.exists():
            raise FileNotFoundError(f"Не найден мастер-отчет {sheet_name}: {master_path}")
        with _local_read_path(master_path, drive_letters) as master_read_path:
            master_wb = None
            try:
                master_wb = load_workbook(master_read_path, data_only=False)
                common_dates.update(_common_sheet_dates(master_wb, rsch_wb))
            finally:
                if master_wb is not None:
                    master_wb.close()

    if len(common_dates) == 1:
        return next(iter(common_dates))
    if not common_dates:
        raise ValueError("Не найдена общая дата в выбранных мастер- и РСЧ-файлах")
    raise ValueError(
        "В выбранных файлах найдено несколько общих дат: "
        f"{_format_dates(sorted(common_dates))}. Выберите нужную дату в панели слева."
    )


@contextmanager
def _local_read_path(path: Path, drive_letters: tuple[str, ...] = ("Q", "Z")):
    target_path, temp_file = get_local_copy(str(path), drive_letters)
    try:
        yield target_path
    finally:
        if temp_file:
            Path(temp_file).unlink(missing_ok=True)


def build_reconciliation_report(
    master_path: Path | str,
    rsch_path: Path | str,
    output_path: Path | str,
    *,
    target_date: date | None = None,
    drive_letters: tuple[str, ...] = ("Q", "Z"),
) -> int:
    master_path = Path(master_path)
    rsch_path = Path(rsch_path)
    output_path = Path(output_path)

    if not master_path.exists():
        raise FileNotFoundError(f"Не найден мастер-отчет: {master_path}")
    if not rsch_path.exists():
        raise FileNotFoundError(f"Не найден РСЧ-отчет: {rsch_path}")

    with (
        _local_read_path(master_path, drive_letters) as master_read_path,
        _local_read_path(rsch_path, drive_letters) as rsch_read_path,
    ):
        master_wb = None
        rsch_wb = None
        try:
            master_wb = load_workbook(master_read_path, data_only=False)
            rsch_wb = load_workbook(rsch_read_path, data_only=True)
            effective_date, master_headers, rows = _build_reconciliation_sheet_data(
                master_wb,
                rsch_wb,
                target_date,
            )
            wb_out = _build_workbook(effective_date, rows, master_headers)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            backup_existing_excel_output(output_path)
            wb_out.save(output_path)
            return len(rows)
        finally:
            if master_wb is not None:
                master_wb.close()
            if rsch_wb is not None:
                rsch_wb.close()


def build_combined_reconciliation_report(
    master_paths: Mapping[str, Path | str],
    rsch_path: Path | str,
    output_path: Path | str,
    *,
    target_date: date | None = None,
    drive_letters: tuple[str, ...] = ("Q", "Z"),
) -> dict[str, int]:
    rsch_path = Path(rsch_path)
    output_path = Path(output_path)
    if not master_paths:
        raise ValueError("Не выбраны мастер-отчеты для сверки")
    if not rsch_path.exists():
        raise FileNotFoundError(f"Не найден РСЧ-отчет: {rsch_path}")

    wb_out = Workbook()
    default_ws = wb_out.active
    counts: dict[str, int] = {}
    sheet_rows: list[tuple[str, list[str], list[ReconciliationRow]]] = []
    ordered_master_paths = _ordered_combined_master_items(master_paths)
    with _local_read_path(rsch_path, drive_letters) as rsch_read_path:
        rsch_wb = None
        try:
            rsch_wb = load_workbook(rsch_read_path, data_only=True)
            effective_target_date = _resolve_combined_target_date(
                ordered_master_paths,
                rsch_wb,
                target_date,
                drive_letters,
            )
            for sheet_name, master_path_value in ordered_master_paths:
                master_path = Path(master_path_value)
                if not master_path.exists():
                    raise FileNotFoundError(f"Не найден мастер-отчет {sheet_name}: {master_path}")
                with _local_read_path(master_path, drive_letters) as master_read_path:
                    master_wb = None
                    try:
                        master_wb = load_workbook(master_read_path, data_only=False)
                        (
                            _effective_date,
                            master_headers,
                            rows,
                        ) = _build_reconciliation_sheet_data(
                            master_wb,
                            rsch_wb,
                            effective_target_date,
                        )
                    finally:
                        if master_wb is not None:
                            master_wb.close()
                sheet_rows.append((sheet_name, master_headers, rows))

            matched_rsch_ids = {
                row_id
                for _sheet_name, _master_headers, rows in sheet_rows
                for row_id in _matched_rsch_row_ids(rows)
            }
            rsch_only_owners: dict[str, str] = {}
            curator_routing = _build_curator_routing(master_paths.keys())
            if curator_routing:
                for _sheet_name, _master_headers, rows in sheet_rows:
                    for row in rows:
                        if _is_rsch_only_no_curator_row(row) and row.rsch is not None:
                            owner = _infer_rsch_row_owner(row.rsch, curator_routing)
                            if owner:
                                rsch_only_owners[row.rsch.row_id] = owner
            seen_unmatched_rsch_ids: set[str] = set()
            for idx, (sheet_name, master_headers, rows) in enumerate(sheet_rows):
                rows = _suppress_combined_rsch_only_rows(
                    rows,
                    matched_rsch_ids,
                    seen_unmatched_rsch_ids,
                    sheet_name,
                    rsch_only_owners,
                )

                ws = default_ws if idx == 0 else wb_out.create_sheet()
                ws.title = sheet_name[:31]
                _write_reconciliation_sheet(ws, rows, master_headers)
                counts[sheet_name] = len(rows)

            output_path.parent.mkdir(parents=True, exist_ok=True)
            backup_existing_excel_output(output_path)
            wb_out.save(output_path)
            return counts
        finally:
            if rsch_wb is not None:
                rsch_wb.close()
