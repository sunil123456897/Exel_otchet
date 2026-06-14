"""Ingestion Core — движок чтения Excel файлов.

Объединяет:
- CalamineReader — парсинг Excel через python-calamine
- extract_date_from_sheet — извлечение даты из имени листа
"""

import os
import re
import logging
from pathlib import Path
from datetime import datetime, date
from decimal import Decimal
from typing import List, Dict, Any, Optional

from python_calamine import CalamineWorkbook

from core.domain.utils_helpers import to_decimal, to_decimal_percent
from core.infra.utils import get_local_copy

logger = logging.getLogger(__name__)
MAX_HEADER_SCAN_ROWS = 6000
_TRASH_KEYWORDS = (
    "c16",
    "d16",
    "название клиента",
    "согласно платежному",
    "процентном формате",
    "итого",
    "всего",
    "итог:",
    "итог дня",
    "итоги дня",
)
# Pre-compiled trash-row detector: _is_trash_row used to rebuild this
# regex (re.escape + re.search) once per cell × keyword — the profiler
# showed it dominated ingestion (~86% of wall time on a 10-file batch,
# 2.27M re.escape calls). Compiling the alternation once collapses
# that to a single regex search per cell. Word boundaries are kept via
# the same lookarounds so matching semantics are unchanged.
_TRASH_PATTERN = re.compile(
    r"(?<![а-яёa-z0-9])(?:"
    + "|".join(re.escape(tk) for tk in _TRASH_KEYWORDS if tk)
    + r")(?![а-яёa-z0-9])"
)
_NUMERIC_FIELDS = frozenset(
    {
        "amount",
        "income",
        "expense",
        "total",
        "transit_obligation",
        "commission",
        "percent_broker",
        "percent_broker2",
        "broker1",
        "broker2",
        "exchange_rate",
        "currency_amount",
    }
)
_PREFERRED_HEADER_ORDER = (
    "customer",
    "contractor",
    "amount",
    "income",
    "expense",
    "commission",
    "total",
    "transit_obligation",
    "percent_broker",
    "broker1",
    "percent_broker2",
    "broker2",
    "exchange_rate",
    "currency_amount",
    "currency",
    "filters",
)
_STRICT_TEMPLATE_ORDER = (
    "customer",
    "contractor",
    "amount",
    "income",
    "expense",
    "commission",
    "total",
    "transit_obligation",
    "percent_broker",
    "broker1",
    "percent_broker2",
    "broker2",
    "exchange_rate",
    "currency_amount",
    "currency",
    "filters",
)
_STRICT_OPTIONAL_KEYS = frozenset(
    {
        "filters",
        "transit_obligation",
        "percent_broker2",
        "exchange_rate",
        "currency_amount",
        "currency",
        "income",
        "expense",
    }
)
_STRICT_SOFT_MISSING_KEYS = frozenset({"filters"})
_STRICT_HELPER_HEADERS = frozenset(
    {
        "итог дня",
        "итоги дня",
        "итоги дня (данные колонка должна быть скрытой)",
        "итоги дня (данная колонка должна быть скрытой)",
        "оплата постащику, выплата зарплатного реестра",
    }
)


def _normalize_header_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).lower()
    text = text.replace("\xa0", " ").replace("\u200b", "").replace("\ufeff", "")
    text = "".join(ch for ch in text if ch.isprintable())
    text = re.sub(r"\s+", " ", text).strip()
    return text.rstrip(": ")


def extract_date_from_sheet(sheet_name: str, **kwargs) -> Optional[str]:
    """Извлечь дату из имени листа.

    Поддерживаемые форматы: DD.MM.YYYY, DD.MM.YY, DD,MM,YY и т.д.
    Если год не указан — лист считается некорректным и игнорируется.
    """
    if not sheet_name:
        return None
    # Очистка невидимых и непечатаемых Unicode символов
    clean_name = "".join(c for c in str(sheet_name) if c.isprintable()).strip()
    clean_name = clean_name.replace("\u200b", "").replace("\ufeff", "")

    pat = re.compile(r"(^|[^0-9])(\d{1,2})[.,](\d{1,2})(?:[.,](\d{2}|\d{4}))?([^0-9]|$)")
    m = pat.search(clean_name)
    if m:
        try:
            d, month = int(m.group(2)), int(m.group(3))
            year_token = m.group(4)
            year_hint = kwargs.get("year_hint")
            if year_token is None and year_hint is None:
                return None

            if year_token is not None:
                y = int(year_token)
                if len(year_token) == 2:
                    y += 2000
            else:
                y = int(year_hint)
            normalized = datetime(y, month, d).strftime("%d.%m.%Y")
            if kwargs.get("with_year_hint"):
                return {
                    "date": normalized,
                    "year_hint": y,
                }
            return normalized
        except Exception:
            logger.warning(
                "INVALID DATE in sheet '%s'. Date will be skipped.",
                sheet_name,
                exc_info=True,
            )
            return None
    return None


def _parse_scope_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%d.%m.%Y").date()
    except ValueError:
        return None


def _sheet_date_matches_scope(
    sheet_date: str,
    target_date_str: Optional[str] = None,
    start_date_str: Optional[str] = None,
    end_date_str: Optional[str] = None,
) -> bool:
    target = _parse_scope_date(target_date_str)
    start = _parse_scope_date(start_date_str)
    end = _parse_scope_date(end_date_str)
    if target is None and (start is None or end is None):
        return True

    if len(sheet_date) != 10:
        return False
    try:
        sheet_dt = datetime.strptime(sheet_date, "%d.%m.%Y").date()
    except ValueError:
        return False
    if target is not None:
        return sheet_dt == target
    return start <= sheet_dt <= end


class CalamineReader:
    """Чтение Excel файлов через python-calamine с маппингом колонок.

    Оптимизации:
    - Локальная копия для сетевых дисков
    - Двухпроходный алгоритм (поиск заголовков → чтение данных)
    - Пропуск Pydantic model_dump для производительности
    """

    def __init__(
        self,
        markers: Dict[str, Any],
        aliases: Dict[str, List[str]],
        drive_letters: tuple = ("Q", "Z"),
    ) -> None:
        self.markers = markers
        self.aliases = aliases
        self.drive_letters = tuple(d.upper() for d in drive_letters)
        self._canonical_order = [
            key for key in _PREFERRED_HEADER_ORDER if key in markers
        ] + [key for key in markers if key not in _PREFERRED_HEADER_ORDER]
        required_strict_keys = set(_STRICT_TEMPLATE_ORDER) - _STRICT_OPTIONAL_KEYS
        self._strict_template_enabled = required_strict_keys.issubset(set(markers))
        self._normalized_markers = {
            key: [
                _normalize_header_text(v)
                for v in (val if isinstance(val, list) else [val])
            ]
            for key, val in markers.items()
        }
        self._normalized_aliases = {
            key: [_normalize_header_text(v) for v in values]
            for key, values in aliases.items()
        }
        self._header_search_terms = []
        for key in self.markers:
            terms = []
            terms.extend(self._normalized_markers.get(key, []))
            terms.extend(self._normalized_aliases.get(key, []))
            seen = set()
            uniq = []
            for term in terms:
                if term and term not in seen:
                    seen.add(term)
                    uniq.append(term)
            self._header_search_terms.append(tuple(uniq))

    def _preferred_header_name(self, key: str) -> str:
        values = self.markers.get(key, [])
        if isinstance(values, list):
            return str(values[0]) if values else key
        return str(values)

    def _matches_any_header_token(self, header_value: str, tokens: List[str]) -> bool:
        return any(token and token in header_value for token in tokens)

    def _classify_header_structure(
        self, header_row: List[Any], col_map: Dict[str, int]
    ) -> tuple[Optional[str], Optional[str]]:
        if not self._strict_template_enabled:
            return None, None

        normalized_headers = [_normalize_header_text(v) for v in header_row]
        mapped_by_index = {}
        for key in _STRICT_TEMPLATE_ORDER:
            col_idx = col_map.get(key)
            if (
                col_idx is not None
                and col_idx < len(normalized_headers)
                and col_idx not in mapped_by_index
            ):
                mapped_by_index[col_idx] = key
        if not mapped_by_index:
            return None, None

        missing_keys = [
            key for key in _STRICT_TEMPLATE_ORDER if key not in mapped_by_index.values()
        ]
        hard_missing = [key for key in missing_keys if key not in _STRICT_OPTIONAL_KEYS]
        if hard_missing:
            return (
                "hard_structure",
                "missing columns: "
                + ", ".join(self._preferred_header_name(key) for key in hard_missing),
            )

        unexpected_header_items = [
            (idx, str(header_row[idx]).strip())
            for idx, value in enumerate(normalized_headers)
            if value and idx not in mapped_by_index
        ]
        helper_headers = [
            header
            for idx, header in unexpected_header_items
            if self._is_soft_extra_header(idx, header, mapped_by_index)
        ]
        real_unexpected_headers = [
            header
            for idx, header in unexpected_header_items
            if not self._is_soft_extra_header(idx, header, mapped_by_index)
        ]
        if real_unexpected_headers:
            return (
                "hard_structure",
                f"unexpected columns: {', '.join(real_unexpected_headers)}",
            )

        present_keys = [key for _, key in sorted(mapped_by_index.items())]
        expected_order = [key for key in _STRICT_TEMPLATE_ORDER if key in present_keys]
        if present_keys != expected_order:
            return (
                "hard_structure",
                "column order mismatch: " + " -> ".join(present_keys),
            )

        alias_only_headers = []
        for idx, key in sorted(mapped_by_index.items()):
            header_value = normalized_headers[idx]
            if self._matches_any_header_token(
                header_value, self._normalized_markers.get(key, [])
            ):
                continue
            alias_match = next(
                (
                    alias
                    for alias in self._normalized_aliases.get(key, [])
                    if alias and alias in header_value
                ),
                None,
            )
            if alias_match is None and key == "broker1" and header_value == "посредник":
                alias_match = header_value
            if alias_match:
                alias_only_headers.append(
                    f"{str(header_row[idx]).strip()} -> {self._preferred_header_name(key)}"
                )

        if alias_only_headers:
            return (
                "soft_structure",
                "unsupported header name: " + "; ".join(alias_only_headers),
            )

        soft_reasons = []
        if helper_headers:
            soft_reasons.append("helper columns: " + ", ".join(helper_headers))
        soft_missing = [
            self._preferred_header_name(key)
            for key in missing_keys
            if key in _STRICT_SOFT_MISSING_KEYS
        ]
        if soft_missing:
            soft_reasons.append("missing optional columns: " + ", ".join(soft_missing))
        if soft_reasons:
            return ("soft_structure", "; ".join(soft_reasons))

        return None, None

    @staticmethod
    def _should_skip_commission_match(key: str, value: str) -> bool:
        return key == "commission" and "посредник" in value

    @staticmethod
    def _should_skip_currency_amount_match(key: str, value: str) -> bool:
        return key == "currency_amount" and "сумма платеж" in value

    @staticmethod
    def _is_boris_second_percent_header(
        idx: int,
        normalized_header: str,
        mapped_by_index: Dict[int, str],
    ) -> bool:
        if normalized_header != "%":
            return False

        positions = {key: col_idx for col_idx, key in mapped_by_index.items()}
        percent_idx = positions.get("percent_broker")
        broker1_idx = positions.get("broker1")
        broker2_idx = positions.get("broker2")
        if percent_idx is None or broker1_idx is None or broker2_idx is None:
            return False

        return percent_idx < broker1_idx < idx < broker2_idx

    def _is_soft_extra_header(
        self,
        idx: int,
        header: str,
        mapped_by_index: Dict[int, str],
    ) -> bool:
        normalized_header = _normalize_header_text(header)
        return (
            normalized_header in _STRICT_HELPER_HEADERS
            or self._is_boris_second_percent_header(
                idx,
                normalized_header,
                mapped_by_index,
            )
        )

    def _find_header_index(
        self,
        header_values: List[str],
        tokens: List[str],
        key: str,
        *,
        exact: bool,
    ) -> Optional[int]:
        for idx, value in enumerate(header_values):
            if self._should_skip_commission_match(key, value):
                continue
            if self._should_skip_currency_amount_match(key, value):
                continue
            if exact and value in tokens:
                return idx
            if not exact and any(token in value for token in tokens):
                return idx
        return None

    def _find_alias_index(
        self,
        header_values: List[str],
        alias_lowers: List[str],
        key: str,
    ) -> Optional[int]:
        found_idx = self._find_header_index(
            header_values, alias_lowers, key, exact=True
        )
        if found_idx is not None:
            return found_idx

        for alias in alias_lowers:
            for idx, value in enumerate(header_values):
                if self._should_skip_commission_match(key, value):
                    continue
                if self._should_skip_currency_amount_match(key, value):
                    continue
                if alias in value or (
                    key == "broker1"
                    and value == "посредник"
                    and "посредник 2" not in value
                ):
                    return idx
        return None

    def _map_columns(self, header_row: List[Any]) -> tuple[Dict[str, int], bool]:
        """Сопоставить колонки заголовка с известными маркерами.

        Returns:
            (col_map, used_aliases) — словарь маппинга и флаг использования алиасов.
        """
        col_map = {}
        used_aliases = False
        header_values = [_normalize_header_text(val) for val in header_row]

        for key in self.markers:
            marker_lowers = self._normalized_markers.get(key, [])
            found_idx = self._find_header_index(
                header_values, marker_lowers, key, exact=True
            )
            if found_idx is None:
                found_idx = self._find_header_index(
                    header_values, marker_lowers, key, exact=False
                )

            if found_idx is None and key in self.aliases:
                alias_lowers = self._normalized_aliases.get(key, [])
                found_idx = self._find_alias_index(header_values, alias_lowers, key)
                if found_idx is not None:
                    used_aliases = True

            if found_idx is not None:
                col_map[key] = found_idx

        second_percent_idx = self._find_boris_second_percent_index(header_values, col_map)
        if second_percent_idx is not None:
            col_map["percent_broker2"] = second_percent_idx

        return col_map, used_aliases

    @classmethod
    def _find_boris_second_percent_index(
        cls,
        header_values: List[str],
        col_map: Dict[str, int],
    ) -> Optional[int]:
        mapped_by_index = {col_idx: key for key, col_idx in col_map.items()}
        for idx, value in enumerate(header_values):
            if cls._is_boris_second_percent_header(idx, value, mapped_by_index):
                return idx
        return None

    @staticmethod
    def _row_has_values(row: List[Any]) -> bool:
        return any(v is not None and v != "" for v in row)

    @staticmethod
    def _is_trash_row(row: List[Any]) -> bool:
        # One pre-compiled alternation search per cell (see _TRASH_PATTERN).
        # The previous version rebuilt re.escape+re.search per cell×keyword.
        for v in row:
            if v is None:
                continue
            if _TRASH_PATTERN.search(_normalize_header_text(v)):
                return True
        return False

    @staticmethod
    def _record_data_loss(
        source: str,
        kind: str,
        reason: str,
        row_index: Optional[int] = None,
        sheet: Optional[str] = None,
        field: Optional[str] = None,
        original_value: Any = None,
    ) -> None:
        from core.domain.data_loss_log import record_loss

        try:
            record_loss(
                source=source,
                kind=kind,
                reason=reason,
                row_index=row_index,
                sheet=sheet,
                field=field,
                original_value=original_value,
            )
        except Exception:
            logger.warning(
                "Failed to record data loss for source=%s kind=%s reason=%s",
                source, kind, reason, exc_info=True,
            )

    @staticmethod
    def _should_skip_sheet(sheet_name: str) -> bool:
        return sheet_name.startswith("_") or sheet_name in ("АНАЛИТИКА", "СВОД")

    @staticmethod
    def _unpack_sheet_date_meta(sheet_name: str) -> tuple[Optional[str], Optional[int]]:
        sheet_date_meta = extract_date_from_sheet(sheet_name, with_year_hint=True)
        if not sheet_date_meta:
            return None, None
        if isinstance(sheet_date_meta, dict):
            return sheet_date_meta.get("date"), sheet_date_meta.get("year_hint")
        return sheet_date_meta, None

    def _load_sheet_sample_rows(
        self,
        sheet,
        sheet_name: str,
        strict_io: bool = False,
    ) -> tuple[Optional[List[Any]], bool]:
        use_to_python = False
        try:
            rows_sample = []
            for idx, row in enumerate(sheet.iter_rows()):
                rows_sample.append(row)
                if idx >= MAX_HEADER_SCAN_ROWS - 1:
                    break
            return rows_sample, use_to_python
        except Exception as iter_err:
            logger.debug(
                f"iter_rows failed for sheet {sheet_name} with {type(iter_err).__name__}: {iter_err}. "
                f"Falling back to to_python()."
            )

        use_to_python = True
        try:
            rows_sample = sheet.to_python()[:MAX_HEADER_SCAN_ROWS]
            return rows_sample, use_to_python
        except Exception as e:
            if strict_io:
                raise
            logger.debug(f"Could not read sheet {sheet_name}: {e}")
            return None, use_to_python

    @staticmethod
    def _header_match_score(row_str: str, header_search_terms: List[tuple[str, ...]]) -> int:
        return sum(1 for terms in header_search_terms if any(alias in row_str for alias in terms))

    @staticmethod
    def _is_valid_header_map(map_res: Dict[str, int]) -> bool:
        return "amount" in map_res and ("customer" in map_res or "contractor" in map_res)

    def _find_best_header_candidate(
        self,
        rows_sample: List[Any],
        header_search_terms: List[tuple[str, ...]],
    ) -> tuple[Optional[int], Optional[Dict[str, int]], Optional[str], Optional[str], set, int]:
        max_score = 0
        standard_keys = set()
        best_header_idx = None
        best_col_map = None
        best_structure_kind = None
        best_structure_reason = None

        for idx, row in enumerate(rows_sample[:MAX_HEADER_SCAN_ROWS]):
            if not self._row_has_values(row):
                continue

            row_str = " ".join(_normalize_header_text(v) for v in row if v is not None)
            score = self._header_match_score(row_str, header_search_terms)
            if score < 2 or score <= max_score:
                continue

            map_res, _ = self._map_columns(row)
            if not self._is_valid_header_map(map_res):
                continue

            structure_kind, structure_reason = self._classify_header_structure(row, map_res)
            max_score = score
            standard_keys = set(map_res.keys())
            best_header_idx = idx
            best_col_map = map_res
            best_structure_kind = structure_kind
            best_structure_reason = structure_reason

            if score >= 5 or len(standard_keys) >= 5:
                break

        return (
            best_header_idx,
            best_col_map,
            best_structure_kind,
            best_structure_reason,
            standard_keys,
            max_score,
        )

    def _activate_header_state(
        self,
        row: List[Any],
        i: int,
        sheet_name: str,
        best_header_idx: Optional[int],
        best_col_map: Optional[Dict[str, int]],
        best_structure_kind: Optional[str],
        best_structure_reason: Optional[str],
    ) -> Optional[tuple[Dict[str, int], tuple, Optional[int], Optional[int], Optional[int], bool, Optional[str], Optional[str]]]:
        if best_header_idx is None or i != best_header_idx:
            return None

        tmp_map, _used_aliases = self._map_columns(row)
        active_col_map = tmp_map or best_col_map
        if not active_col_map:
            return None

        active_col_items = tuple(active_col_map.items())
        amount_idx = active_col_map.get("amount")
        commission_idx = active_col_map.get("commission")
        total_idx = active_col_map.get("total")
        logger.debug(f"DEBUG: Found header in {sheet_name} row {i + 1}: {active_col_map}")

        structure_kind, structure_reason = self._classify_header_structure(row, active_col_map)
        current_warning_kind = structure_kind or best_structure_kind
        current_warning_reason = structure_reason or best_structure_reason
        current_is_warning = current_warning_kind == "hard_structure"

        return (
            active_col_map,
            active_col_items,
            amount_idx,
            commission_idx,
            total_idx,
            current_is_warning,
            current_warning_kind,
            current_warning_reason,
        )

    def _coerce_numeric_cell(self, key: str, val: Any) -> tuple[Any, bool, bool]:
        if isinstance(val, (int, float)):
            d_val = Decimal(str(val))
            return d_val, d_val != 0, False

        try:
            d_val = (
                to_decimal_percent(val)
                if key in {"percent_broker", "percent_broker2"}
                else to_decimal(val)
            )
            return d_val, d_val != 0, False
        except Exception:
            logger.debug(
                "Decimal conversion failed for key=%s val=%s, falling back to text match",
                key, repr(val), exc_info=True,
            )
            normalized_value = _normalize_header_text(val)
            header_terms = {
                term
                for term in (
                    self._normalized_markers.get(key, [])
                    + self._normalized_aliases.get(key, [])
                )
                if term
            }
            if normalized_value in header_terms:
                return val, False, False
            self._record_data_loss(
                source=getattr(self, "_current_file_path", "") or "",
                kind="numeric_coercion",
                reason=f"could not parse {key!r} value as number",
                field=key,
                original_value=val,
            )
            if key == "amount":
                return val, False, True
            return None, False, True

    @staticmethod
    def _apply_shifted_columns_fix(
        raw_data: Dict[str, Any],
        row: List[Any],
        row_len: int,
        amount_idx: Optional[int],
        commission_idx: Optional[int],
        total_idx: Optional[int],
        row_has_numeric_text_warning: bool,
        row_warning_reason: Optional[str],
    ) -> tuple[Dict[str, Any], bool, Optional[str]]:
        amount_val = raw_data.get("amount")
        commission_val = raw_data.get("commission")
        total_val = raw_data.get("total")
        next_total_val = (
            row[total_idx + 1] if total_idx is not None and total_idx + 1 < row_len else None
        )

        if (
            isinstance(amount_val, str)
            and commission_idx is not None
            and total_idx is not None
            and amount_idx is not None
            and commission_idx == amount_idx + 1
            and total_idx == commission_idx + 1
            and isinstance(commission_val, Decimal)
            and isinstance(total_val, Decimal)
            and abs(total_val) <= Decimal("1")
            and isinstance(next_total_val, (int, float))
        ):
            raw_data["amount"] = commission_val
            raw_data["commission"] = total_val
            raw_data["total"] = Decimal(str(next_total_val))
            row_has_numeric_text_warning = True
            row_warning_reason = "shifted columns after amount"

        return raw_data, row_has_numeric_text_warning, row_warning_reason

    @staticmethod
    def _attach_warning_metadata(
        raw_data: Dict[str, Any],
        row_has_numeric_text_warning: bool,
        row_warning_reason: Optional[str],
        current_is_warning: bool,
        current_warning_kind: Optional[str],
        current_warning_reason: Optional[str],
    ) -> None:
        if row_has_numeric_text_warning:
            raw_data["is_template_warning"] = True
            raw_data["_template_warning_kind"] = "template_warning"
            raw_data["_template_warning_reason"] = (
                row_warning_reason or "numeric text in numeric field"
            )
            return

        raw_data["is_template_warning"] = current_is_warning
        if current_warning_kind:
            raw_data["_template_warning_kind"] = current_warning_kind
            raw_data["_template_warning_reason"] = current_warning_reason

    def _build_data_row_payload(
        self,
        row: List[Any],
        i: int,
        sheet_name: str,
        f_path_abs: str,
        sheet_date: str,
        sheet_year_hint: Optional[int],
        active_col_items: tuple,
        amount_idx: Optional[int],
        commission_idx: Optional[int],
        total_idx: Optional[int],
        current_is_warning: bool,
        current_warning_kind: Optional[str],
        current_warning_reason: Optional[str],
        file_basename: str,
    ) -> Optional[Dict[str, Any]]:
        raw_data = {
            "_sheet_name": sheet_name,
            "_row_index": i + 1,
            "_file_path": f_path_abs,
            "date": sheet_date,
            "_sheet_year_hint": sheet_year_hint,
        }

        has_data = False
        has_financial = False
        row_has_numeric_text_warning = False
        row_warning_reason = None
        row_len = len(row)

        for key, col_idx in active_col_items:
            if col_idx >= row_len:
                continue
            val = row[col_idx]
            if val is None or val == "":
                continue

            has_data = True
            if key in _NUMERIC_FIELDS:
                parsed_val, has_financial_value, numeric_text_warning = self._coerce_numeric_cell(
                    key, val
                )
                raw_data[key] = parsed_val
                if has_financial_value:
                    has_financial = True
                if numeric_text_warning:
                    row_has_numeric_text_warning = True
                    if row_warning_reason is None:
                        row_warning_reason = f"text in numeric field: {key}"
            else:
                raw_data[key] = val

        raw_data, row_has_numeric_text_warning, row_warning_reason = self._apply_shifted_columns_fix(
            raw_data,
            row,
            row_len,
            amount_idx,
            commission_idx,
            total_idx,
            row_has_numeric_text_warning,
            row_warning_reason,
        )

        if not (has_data and (has_financial or row_has_numeric_text_warning)):
            if has_data:
                logger.debug(
                    f"Row {i + 1} in {sheet_name} has data but no financial values"
                )
            return None

        if row_has_numeric_text_warning and not has_financial:
            unique_texts = set()
            for val in row:
                if val is None or val == "":
                    continue
                text = str(val).strip().strip("\"'").strip()
                if text:
                    unique_texts.add(text.lower())
            if len(unique_texts) <= 1:
                logger.debug(
                    f"Row {i + 1} in {sheet_name} looks like a section header "
                    f"(text in numeric column, no real numbers)"
                )
                return None
            customer_idx = None
            for key, ci in active_col_items:
                if key == "customer":
                    customer_idx = ci
                    break
            if customer_idx is not None and customer_idx < len(row):
                cust_text = str(row[customer_idx]).strip() if row[customer_idx] is not None else ""
                if cust_text.startswith('"') and len(cust_text) < 30:
                    logger.debug(
                        f"Row {i + 1} in {sheet_name} looks like a section header "
                        f"(quoted customer '{cust_text}', no financial data)"
                    )
                    return None

        self._attach_warning_metadata(
            raw_data,
            row_has_numeric_text_warning,
            row_warning_reason,
            current_is_warning,
            current_warning_kind,
            current_warning_reason,
        )
        raw_data["_source_info"] = f"{file_basename} | {sheet_name} | Row {i + 1}"
        return raw_data

    def _iter_sheet_rows_safe(
        self,
        sheet,
        use_to_python: bool,
        sheet_name: str,
        strict_io: bool = False,
    ):
        row_iterator = enumerate(sheet.to_python() if use_to_python else sheet.iter_rows())
        while True:
            try:
                yield next(row_iterator)
            except StopIteration:
                return
            except Exception as second_pass_err:
                if strict_io:
                    raise
                logger.warning(
                    f"Error during second pass in sheet {sheet_name}: "
                    f"{type(second_pass_err).__name__} - {second_pass_err}"
                )
                return

    def _process_workbook_sheet(
        self,
        wb,
        sheet_name: str,
        f_path_abs: str,
        file_basename: str,
        header_search_terms: List[tuple[str, ...]],
        all_rows: List[Dict[str, Any]],
        target_date_str: Optional[str] = None,
        start_date_str: Optional[str] = None,
        end_date_str: Optional[str] = None,
        strict_io: bool = False,
    ) -> None:
        if self._should_skip_sheet(sheet_name):
            return

        sheet_date, sheet_year_hint = self._unpack_sheet_date_meta(sheet_name)
        if not sheet_date:
            logger.debug(f"Skipping sheet {sheet_name}: no date found")
            return
        if not _sheet_date_matches_scope(
            sheet_date,
            target_date_str=target_date_str,
            start_date_str=start_date_str,
            end_date_str=end_date_str,
        ):
            return

        try:
            sheet = wb.get_sheet_by_name(sheet_name)
        except Exception as e:
            if strict_io:
                raise
            logger.debug(f"Could not load sheet {sheet_name}: {e}")
            return

        rows_sample, use_to_python = self._load_sheet_sample_rows(
            sheet,
            sheet_name,
            strict_io=strict_io,
        )
        if not rows_sample:
            return

        (
            best_header_idx,
            best_col_map,
            best_structure_kind,
            best_structure_reason,
            standard_keys,
            max_score,
        ) = self._find_best_header_candidate(rows_sample, header_search_terms)

        if not standard_keys:
            logger.debug(f"No headers found in sheet {sheet_name} (max score: {max_score})")
            return

        active_col_map = None
        active_col_items = ()
        amount_idx = None
        commission_idx = None
        total_idx = None
        current_is_warning = False
        current_warning_kind = None
        current_warning_reason = None

        for i, row in self._iter_sheet_rows_safe(
            sheet,
            use_to_python,
            sheet_name,
            strict_io=strict_io,
        ):
            if not self._row_has_values(row):
                continue

            if not active_col_map:
                header_state = self._activate_header_state(
                    row,
                    i,
                    sheet_name,
                    best_header_idx,
                    best_col_map,
                    best_structure_kind,
                    best_structure_reason,
                )
                if header_state:
                    (
                        active_col_map,
                        active_col_items,
                        amount_idx,
                        commission_idx,
                        total_idx,
                        current_is_warning,
                        current_warning_kind,
                        current_warning_reason,
                    ) = header_state
                continue

            if self._is_trash_row(row):
                self._record_data_loss(
                    source=f_path_abs,
                    kind="trash_filter",
                    reason="row matched trash keyword",
                    row_index=i + 1,
                    sheet=sheet_name,
                )
                continue

            payload = self._build_data_row_payload(
                row,
                i,
                sheet_name,
                f_path_abs,
                sheet_date,
                sheet_year_hint,
                active_col_items,
                amount_idx,
                commission_idx,
                total_idx,
                current_is_warning,
                current_warning_kind,
                current_warning_reason,
                file_basename,
            )
            if payload is None:
                continue
            try:
                all_rows.append(payload)
            except Exception as ve:
                logger.debug(f"Row {i + 1} in {sheet_name} failed: {ve}")

    @staticmethod
    def _cleanup_temp_file(temp_file: Optional[str]) -> None:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                logger.debug("Failed to remove temp file %s", temp_file, exc_info=True)

    def read(
        self,
        file_path: Path,
        strict_io: bool = False,
        target_date_str: Optional[str] = None,
        start_date_str: Optional[str] = None,
        end_date_str: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Прочитать все листы файла и вернуть список строк.

        Алгоритм:
        1. Для сетевых файлов — создать локальную копию
        2. Первый проход (первые 6000 строк) — найти заголовки
        3. Второй проход — извлечь данные с маппингом
        """
        all_rows: List[Dict[str, Any]] = []
        f_path_abs = os.path.abspath(str(file_path))
        file_basename = os.path.basename(f_path_abs)
        self._current_file_path = f_path_abs
        header_search_terms = self._header_search_terms

        try:
            target_path, temp_file = get_local_copy(f_path_abs, self.drive_letters)
        except (OSError, IOError, PermissionError) as e:
            if strict_io:
                raise
            logger.error(f"Calamine error {f_path_abs}: {e}")
            return all_rows
        except Exception as e:
            if strict_io:
                raise
            logger.error(f"Calamine error {f_path_abs}: {e}")
            return all_rows

        # Validate file signature (Magic Bytes)
        try:
            with open(target_path, "rb") as f:
                header_bytes = f.read(4)
            if header_bytes != b"PK\x03\x04":
                raise ValueError("Invalid file signature: expected Excel ZIP archive (XLSX)")
        except Exception as sig_err:
            self._cleanup_temp_file(temp_file)
            if strict_io:
                raise
            logger.error(f"File signature validation failed for {f_path_abs}: {sig_err}")
            return all_rows

        try:
            wb = CalamineWorkbook.from_path(target_path)
            try:
                for sheet_name in wb.sheet_names:
                    self._process_workbook_sheet(
                        wb,
                        sheet_name,
                        f_path_abs,
                        file_basename,
                        header_search_terms,
                        all_rows,
                        target_date_str=target_date_str,
                        start_date_str=start_date_str,
                        end_date_str=end_date_str,
                        strict_io=strict_io,
                    )
            finally:
                wb.close()

        except Exception as e:
            if strict_io:
                raise
            logger.error(f"Calamine error {f_path_abs}: {e}")
        finally:
            self._cleanup_temp_file(temp_file)

        return all_rows
