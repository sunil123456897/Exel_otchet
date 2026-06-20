from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Any

from openpyxl.styles import Font, PatternFill

from core.infra.excel_styles import (
    HEADER_FILL,
    HEADER_FONT,
    THIN_SIDE,
    THIN_BORDER,
)
from core.infra.excel_utils import excel_safe_text
from ._types import ReconciliationRow


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
REASON_AMOUNT_ONLY_MATCH = "СОВПАЛА СУММА"
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
    REASON_AMOUNT_ONLY_MATCH: "Совпала сумма",
}

_HEADER_FILL = HEADER_FILL
_STATUS_OK_FILL = PatternFill("solid", fgColor="FF00B050")
_STATUS_REVIEW_FILL = PatternFill("solid", fgColor="FFFFEB9C")
_STATUS_ERROR_FILL = PatternFill("solid", fgColor="FFFFC7CE")
_MASTER_EXPENSE_FILL = PatternFill("solid", fgColor="FFFFC7CE")
_HEADER_FONT = HEADER_FONT
_STATUS_FONT = Font(color="FF000000", bold=True)
_THIN_SIDE = THIN_SIDE
_THIN_BORDER = THIN_BORDER



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
    if compact.startswith("воркбрайт") or compact == "вб" or "вб" in tokens:
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
    if isinstance(value, bool):
        return Decimal("1") if value else Decimal("0")
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


def _is_total_row(value: Any) -> bool:
    return _normalize_text(value).startswith("итого")


def _excel_safe_text(value: Any) -> Any:
    return excel_safe_text(value)


def _row_id(row: ReconciliationRow) -> str:
    """Stable ID for a reconciliation row based on master/rsch content."""
    parts: list[str] = []
    if row.master is not None:
        parts.extend([
            _normalize_text(row.master.customer),
            _normalize_text(row.master.executor),
            str(row.master.income),
            str(row.master.expense),
        ])
    if row.rsch is not None:
        parts.extend([
            _normalize_text(row.rsch.customer),
            _normalize_text(row.rsch.executor),
            str(row.rsch.income),
            str(row.rsch.expense),
        ])
    return "|".join(parts) if parts else f"status:{row.status}:{row.reason}"


