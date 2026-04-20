"""Ingestion Core — движок чтения Excel файлов.

Объединяет:
- CalamineReader — парсинг Excel через python-calamine
- extract_date_from_sheet — извлечение даты из имени листа
"""

import os
import re
import logging
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
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
_NUMERIC_FIELDS = frozenset(
    {
        "amount",
        "income",
        "expense",
        "total",
        "commission",
        "percent_broker",
        "broker1",
        "broker2",
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
    "percent_broker",
    "broker1",
    "broker2",
    "filters",
)
_STRICT_TEMPLATE_ORDER = (
    "customer",
    "contractor",
    "amount",
    "commission",
    "total",
    "percent_broker",
    "broker1",
    "broker2",
    "filters",
)
_STRICT_OPTIONAL_KEYS = frozenset({"filters"})
_STRICT_HELPER_HEADERS = frozenset(
    {
        "итог дня",
        "итоги дня",
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

    Поддерживаемые форматы: DD.MM, DD.MM.YYYY, DD.MM.YY, DD,MM,YY и т.д.
    Если год не указан — возвращается только DD.MM (без навязывания года).
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
            if year_token is None:
                datetime(2000, month, d)
                if kwargs.get("with_year_hint"):
                    return {
                        "date": f"{d:02d}.{month:02d}",
                        "year_hint": None,
                    }
                return f"{d:02d}.{month:02d}"

            y = int(year_token)
            if len(year_token) == 2:
                y += 2000
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
            )
            return None
    return None


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
        self._strict_template_enabled = set(_STRICT_TEMPLATE_ORDER).issubset(
            set(markers)
        )
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
        mapped_by_index = {
            col_idx: key
            for key, col_idx in col_map.items()
            if key in _STRICT_TEMPLATE_ORDER and col_idx < len(normalized_headers)
        }
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

        unexpected_headers = [
            str(header_row[idx]).strip()
            for idx, value in enumerate(normalized_headers)
            if value and idx not in mapped_by_index
        ]
        helper_headers = [
            header
            for header in unexpected_headers
            if _normalize_header_text(header) in _STRICT_HELPER_HEADERS
        ]
        real_unexpected_headers = [
            header
            for header in unexpected_headers
            if _normalize_header_text(header) not in _STRICT_HELPER_HEADERS
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
            if key in _STRICT_OPTIONAL_KEYS
        ]
        if soft_missing:
            soft_reasons.append("missing optional columns: " + ", ".join(soft_missing))
        if soft_reasons:
            return ("soft_structure", "; ".join(soft_reasons))

        return None, None

    def _map_columns(self, header_row: List[Any]) -> tuple[Dict[str, int], bool]:
        """Сопоставить колонки заголовка с известными маркерами.

        Returns:
            (col_map, used_aliases) — словарь маппинга и флаг использования алиасов.
        """
        col_map = {}
        used_aliases = False
        header_values = [_normalize_header_text(val) for val in header_row]

        for key, marker in self.markers.items():
            found_idx = None
            marker_lowers = self._normalized_markers.get(key, [])

            for idx, val in enumerate(header_values):
                if any(m in val for m in marker_lowers):
                    if key == "commission" and "посредник" in val:
                        continue
                    found_idx = idx
                    break

            if found_idx is None and key in self.aliases:
                for alt_lower in self._normalized_aliases.get(key, []):
                    for idx, val in enumerate(header_values):
                        if alt_lower in val or (
                            key == "broker1"
                            and val == "посредник"
                            and "посредник 2" not in val
                        ):
                            if key == "commission" and "посредник" in val:
                                continue
                            found_idx = idx
                            used_aliases = True
                            break
                    if found_idx is not None:
                        break

            if found_idx is not None:
                col_map[key] = found_idx

        return col_map, used_aliases

    def read(self, file_path: Path, strict_io: bool = False) -> List[Dict[str, Any]]:
        """Прочитать все листы файла и вернуть список строк.

        Алгоритм:
        1. Для сетевых файлов — создать локальную копию
        2. Первый проход (первые 6000 строк) — найти заголовки
        3. Второй проход — извлечь данные с маппингом
        """
        all_rows = []
        f_path_abs = os.path.abspath(str(file_path))
        file_basename = os.path.basename(f_path_abs)

        header_search_terms = self._header_search_terms

        try:
            target_path, temp_file = get_local_copy(f_path_abs, self.drive_letters)
        except (OSError, IOError, PermissionError) as e:
            if strict_io:
                raise
            logger.error(f"Calamine error {f_path_abs}: {e}")
            return all_rows
        except Exception as e:
            logger.error(f"Calamine error {f_path_abs}: {e}")
            return all_rows

        try:
            wb = CalamineWorkbook.from_path(target_path)
            for sheet_name in wb.sheet_names:
                if sheet_name.startswith("_") or sheet_name in ("АНАЛИТИКА", "СВОД"):
                    continue

                try:
                    sheet = wb.get_sheet_by_name(sheet_name)
                except Exception as e:
                    logger.debug(f"Could not load sheet {sheet_name}: {e}")
                    continue
                except BaseException as e:
                    if isinstance(e, (KeyboardInterrupt, SystemExit, GeneratorExit)):
                        raise
                    logger.debug(f"PanicException loading sheet {sheet_name}: {e}")
                    continue

                sheet_date_meta = extract_date_from_sheet(sheet_name, with_year_hint=True)
                if not sheet_date_meta:
                    logger.debug(f"Skipping sheet {sheet_name}: no date found")
                    continue

                if isinstance(sheet_date_meta, dict):
                    sheet_date = sheet_date_meta.get("date")
                    sheet_year_hint = sheet_date_meta.get("year_hint")
                else:
                    sheet_date = sheet_date_meta
                    sheet_year_hint = None

                if not sheet_date:
                    logger.debug(f"Skipping sheet {sheet_name}: no date found")
                    continue

                # Первый проход: поиск стандартных ключей (не загружаем лист целиком в память)
                use_to_python = False
                try:
                    rows_sample = []
                    for idx, row in enumerate(sheet.iter_rows()):
                        rows_sample.append(row)
                        if idx >= MAX_HEADER_SCAN_ROWS - 1:
                            break
                except BaseException as iter_err:
                    if isinstance(
                        iter_err, (KeyboardInterrupt, SystemExit, GeneratorExit)
                    ):
                        raise
                    logger.debug(
                        f"iter_rows failed for sheet {sheet_name} with {type(iter_err).__name__}: {iter_err}. "
                        f"Falling back to to_python()."
                    )
                    use_to_python = True
                    try:
                        rows_sample = sheet.to_python()[:MAX_HEADER_SCAN_ROWS]
                    except Exception as e:
                        logger.debug(f"Could not read sheet {sheet_name}: {e}")
                        continue
                    except BaseException as e:
                        if isinstance(
                            e, (KeyboardInterrupt, SystemExit, GeneratorExit)
                        ):
                            raise
                        logger.debug(f"PanicException reading sheet {sheet_name}: {e}")
                        continue

                if not rows_sample:
                    continue

                standard_keys, max_score = set(), 0
                best_header_idx = None
                best_col_map = None
                best_structure_kind = None
                best_structure_reason = None
                for idx, row in enumerate(rows_sample[:MAX_HEADER_SCAN_ROWS]):
                    if not any(v is not None and v != "" for v in row):
                        continue
                    row_str = " ".join(
                        [_normalize_header_text(v) for v in row if v is not None]
                    )
                    score = sum(
                        1
                        for m in header_search_terms
                        if any(alias in row_str for alias in m)
                    )
                    if score >= 2 and score > max_score:
                        map_res, _ = self._map_columns(row)
                        if "amount" in map_res and (
                            "customer" in map_res or "contractor" in map_res
                        ):
                            structure_kind, structure_reason = (
                                self._classify_header_structure(row, map_res)
                            )
                            max_score = score
                            standard_keys = set(map_res.keys())
                            best_header_idx = idx
                            best_col_map = map_res
                            best_structure_kind = structure_kind
                            best_structure_reason = structure_reason
                            # Strong header match found early; no need to scan more rows.
                            if score >= 5 or len(standard_keys) >= 5:
                                break

                if not standard_keys:
                    logger.debug(
                        f"No headers found in sheet {sheet_name} (max score: {max_score})"
                    )
                    continue

                # Второй проход: чтение данных через итератор для экономии памяти
                active_col_map, current_is_warning = None, False
                current_warning_kind, current_warning_reason = None, None
                active_col_items = ()
                amount_idx = None
                commission_idx = None
                total_idx = None

                row_iterator = enumerate(
                    sheet.to_python() if use_to_python else sheet.iter_rows()
                )
                while True:
                    try:
                        i, row = next(row_iterator)
                    except StopIteration:
                        break
                    except BaseException as second_pass_err:
                        if isinstance(
                            second_pass_err,
                            (KeyboardInterrupt, SystemExit, GeneratorExit),
                        ):
                            raise
                        logger.warning(
                            f"Error during second pass in sheet {sheet_name}: {type(second_pass_err).__name__} - {second_pass_err}"
                        )
                        break
                    if not any(v is not None and v != "" for v in row):
                        continue

                    if not active_col_map:
                        if best_header_idx is not None and i == best_header_idx:
                            tmp_map, _used_aliases = self._map_columns(row)
                            active_col_map = tmp_map or best_col_map
                            active_col_items = tuple(active_col_map.items())
                            amount_idx = active_col_map.get("amount")
                            commission_idx = active_col_map.get("commission")
                            total_idx = active_col_map.get("total")
                            logger.debug(
                                f"DEBUG: Found header in {sheet_name} row {i + 1}: {active_col_map}"
                            )
                            structure_kind, structure_reason = (
                                self._classify_header_structure(row, active_col_map)
                            )
                            current_warning_kind = structure_kind or best_structure_kind
                            current_warning_reason = (
                                structure_reason or best_structure_reason
                            )
                            current_is_warning = (
                                current_warning_kind == "hard_structure"
                            )
                        continue

                    row_values_lower = [
                        _normalize_header_text(v) for v in row if v is not None
                    ]

                    is_trash = False
                    for val_lower in row_values_lower:
                        for tk in _TRASH_KEYWORDS:
                            if tk in val_lower:
                                is_trash = True
                                break
                        if is_trash:
                            break
                    if is_trash:
                        continue

                    raw_data = {
                        "_sheet_name": sheet_name,
                        "_row_index": i + 1,
                        "_file_path": f_path_abs,
                        "date": sheet_date,
                        "_sheet_year_hint": sheet_year_hint,
                    }

                    has_data, has_financial = False, False
                    row_has_numeric_text_warning = False
                    row_warning_reason = None
                    row_len = len(row)
                    for key, col_idx in active_col_items:
                        if col_idx < row_len:
                            val = row[col_idx]
                            if val is not None and val != "":
                                has_data = True
                                if key in _NUMERIC_FIELDS:
                                    if isinstance(val, (int, float)):
                                        d_val = Decimal(str(val))
                                        if d_val != 0:
                                            has_financial = True
                                        raw_data[key] = d_val
                                    else:
                                        try:
                                            d_val = (
                                                to_decimal(val)
                                                if key != "percent_broker"
                                                else to_decimal_percent(val)
                                            )
                                            if d_val != 0:
                                                has_financial = True
                                            raw_data[key] = d_val
                                        except Exception:
                                            raw_data[key] = None
                                            if key != "amount":
                                                row_has_numeric_text_warning = True
                                                if row_warning_reason is None:
                                                    row_warning_reason = (
                                                        f"text in numeric field: {key}"
                                                    )
                                            else:
                                                raw_data[key] = val
                                else:
                                    raw_data[key] = val

                        # Some malformed rows shift one cell right after the amount column:
                        # amount becomes bank text, commission holds the amount, total holds percent,
                        # and the next physical cell contains the real total.
                    amount_val = raw_data.get("amount")
                    commission_val = raw_data.get("commission")
                    total_val = raw_data.get("total")
                    next_total_val = (
                        row[total_idx + 1]
                        if total_idx is not None and total_idx + 1 < row_len
                        else None
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

                    if has_data and has_financial:
                        try:
                            if row_has_numeric_text_warning:
                                raw_data["is_template_warning"] = True
                                raw_data["_template_warning_kind"] = "template_warning"
                                raw_data["_template_warning_reason"] = (
                                    row_warning_reason
                                    or "numeric text in numeric field"
                                )
                            else:
                                raw_data["is_template_warning"] = current_is_warning
                                if current_warning_kind:
                                    raw_data["_template_warning_kind"] = (
                                        current_warning_kind
                                    )
                                    raw_data["_template_warning_reason"] = (
                                        current_warning_reason
                                    )
                            raw_data["_source_info"] = (
                                f"{file_basename} | {sheet_name} | Row {i + 1}"
                            )
                            all_rows.append(raw_data)
                        except Exception as ve:
                            logger.debug(
                                f"Row {i + 1} in {sheet_name} failed: {ve}"
                            )
                    elif has_data:
                        logger.debug(
                            f"Row {i + 1} in {sheet_name} has data but no financial values"
                        )

        except (OSError, IOError, PermissionError) as e:
            if strict_io:
                raise
            logger.error(f"Calamine error {f_path_abs}: {e}")
        except Exception as e:
            logger.error(f"Calamine error {f_path_abs}: {e}")
        except BaseException as e:
            if isinstance(e, (KeyboardInterrupt, SystemExit, GeneratorExit)):
                raise
            logger.error(f"Calamine PanicException {f_path_abs}: {e}")
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

        return all_rows
