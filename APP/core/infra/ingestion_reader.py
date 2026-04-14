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


def extract_date_from_sheet(sheet_name: str, **kwargs) -> Optional[str]:
    """Извлечь дату из имени листа.

    Поддерживаемые форматы: DD.MM, DD.MM.YYYY, DD,MM.YYYY и т.д.
    Если год не указан — используется текущий.
    """
    if not sheet_name:
        return None
    # Очистка невидимых и непечатаемых Unicode символов
    clean_name = "".join(c for c in str(sheet_name) if c.isprintable()).strip()
    clean_name = clean_name.replace("\u200b", "").replace("\ufeff", "")

    pat = re.compile(r"(^|[^0-9])(\d{1,2})[.,](\d{1,2})([.,](\d{4}))?([^0-9]|$)")
    m = pat.search(clean_name)
    if m:
        try:
            curr = datetime.now()
            d, month = int(m.group(2)), int(m.group(3))
            y = int(m.group(5)) if m.group(5) else curr.year
            return datetime(y, month, d).strftime("%d.%m.%Y")
        except Exception:
            logger.warning(
                f"INVALID DATE in sheet '{sheet_name}'. Using 01.01.1900 as placeholder."
            )
            return "01.01.1900"
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

    def _map_columns(self, header_row: List[Any]) -> tuple[Dict[str, int], bool]:
        """Сопоставить колонки заголовка с известными маркерами.

        Returns:
            (col_map, used_aliases) — словарь маппинга и флаг использования алиасов.
        """
        col_map = {}
        used_aliases = False
        header_values = [
            str(val).lower() if val is not None else "" for val in header_row
        ]

        for key, marker in self.markers.items():
            found_idx = None
            marker_list = marker if isinstance(marker, list) else [marker]
            marker_lowers = [str(m).lower() for m in marker_list]

            for idx, val in enumerate(header_values):
                if any(m in val for m in marker_lowers):
                    if key == "commission" and "посредник" in val:
                        continue
                    found_idx = idx
                    break

            if found_idx is None and key in self.aliases:
                for alt in self.aliases[key]:
                    alt_lower = alt.lower()
                    for idx, val in enumerate(header_values):
                        if alt_lower in val:
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

    def read(self, file_path: Path) -> List[Dict[str, Any]]:
        """Прочитать все листы файла и вернуть список строк.

        Алгоритм:
        1. Для сетевых файлов — создать локальную копию
        2. Первый проход (первые 6000 строк) — найти заголовки
        3. Второй проход — извлечь данные с маппингом
        """
        all_rows = []
        f_path_abs = os.path.abspath(str(file_path))

        # Прекомпут поисковых терминов
        all_search_terms = []
        for key in self.markers:
            m_val = self.markers[key]
            m_list = [
                str(v).lower() for v in (m_val if isinstance(m_val, list) else [m_val])
            ]
            if key in self.aliases:
                m_list.extend([str(v).lower() for v in self.aliases[key]])
            all_search_terms.append(list(set(m_list)))
        aliases_lower_list = all_search_terms

        trash_keywords = [
            "c16",
            "d16",
            "название клиента",
            "согласно платежному",
            "процентном формате",
        ]

        target_path, temp_file = get_local_copy(f_path_abs, self.drive_letters)

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

                sheet_date = extract_date_from_sheet(sheet_name)
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
                    if isinstance(iter_err, (KeyboardInterrupt, SystemExit, GeneratorExit)):
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
                        if isinstance(e, (KeyboardInterrupt, SystemExit, GeneratorExit)):
                            raise
                        logger.debug(f"PanicException reading sheet {sheet_name}: {e}")
                        continue

                if not rows_sample:
                    continue

                standard_keys, max_score = set(), 0
                for idx, row in enumerate(rows_sample[:MAX_HEADER_SCAN_ROWS]):
                    if not any(v is not None and v != "" for v in row):
                        continue
                    row_str = " ".join([str(v).lower() for v in row if v is not None])
                    score = sum(
                        1
                        for m in aliases_lower_list
                        if any(alias in row_str for alias in m)
                    )
                    if score >= 2 and score > max_score:
                        map_res, _ = self._map_columns(row)
                        if "amount" in map_res and (
                            "customer" in map_res or "contractor" in map_res
                        ):
                            max_score = score
                            standard_keys = set(map_res.keys())
                            if score >= 5:
                                break

                if not standard_keys:
                    logger.debug(
                        f"No headers found in sheet {sheet_name} (max score: {max_score})"
                    )
                    continue

                # Второй проход: чтение данных через итератор для экономии памяти
                active_col_map, current_is_warning = None, False
                trash_keywords_set = set(trash_keywords)

                row_iterator = enumerate(sheet.to_python() if use_to_python else sheet.iter_rows())
                while True:
                    try:
                        i, row = next(row_iterator)
                    except StopIteration:
                        break
                    except BaseException as second_pass_err:
                        if isinstance(second_pass_err, (KeyboardInterrupt, SystemExit, GeneratorExit)):
                            raise
                        logger.warning(f"Error during second pass in sheet {sheet_name}: {type(second_pass_err).__name__} - {second_pass_err}")
                        break
                    if not any(v is not None and v != "" for v in row):
                        continue

                    row_values_lower = [str(v).lower() for v in row if v is not None]

                    if not active_col_map:
                        row_combined = " ".join(row_values_lower)
                        score = sum(
                            1
                            for m in aliases_lower_list
                            if any(alias in row_combined for alias in m)
                        )

                        if score >= 2:
                            tmp_map, used_aliases = self._map_columns(row)
                            if "amount" in tmp_map and (
                                "customer" in tmp_map or "contractor" in tmp_map
                            ):
                                active_col_map = tmp_map
                                logger.debug(
                                    f"DEBUG: Found header in {sheet_name} row {i + 1}: {active_col_map}"
                                )
                                current_is_warning = used_aliases or (
                                    set(active_col_map.keys()) != standard_keys
                                )
                                continue

                    if active_col_map:
                        is_trash = False
                        for val_lower in row_values_lower:
                            for tk in trash_keywords:
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
                        }

                        has_data, has_financial = False, False
                        numeric_fields = {
                            "amount",
                            "income",
                            "expense",
                            "total",
                            "commission",
                            "percent_broker",
                            "broker1",
                            "broker2",
                        }
                        for key, col_idx in active_col_map.items():
                            if col_idx < len(row):
                                val = row[col_idx]
                                if val is not None and val != "":
                                    has_data = True
                                    if key in numeric_fields:
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
                                                raw_data[key] = val
                                    else:
                                        raw_data[key] = val

                        if has_data and has_financial:
                            try:
                                raw_data["is_template_warning"] = current_is_warning
                                raw_data["_source_info"] = (
                                    f"{os.path.basename(f_path_abs)} | {sheet_name} | Row {i + 1}"
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
