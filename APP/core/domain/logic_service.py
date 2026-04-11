"""Бизнес-логика: финансовые правила и валидация."""

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any

from core.domain.interfaces import IValidator, ILogicService, IPersistence
from core.domain.utils_helpers import (
    to_decimal,
    to_decimal_percent,
    NumericParsingError,
)

logger = logging.getLogger(__name__)


class Validator(IValidator):
    """Валидатор строк данных — отбрасывает мусор и заголовки."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self._junk_totals = frozenset({"итого", "всего", "итог"})
        self._junk_markers = ("заказчик", "исполнитель", "приход", "расход")

    def validate_row(self, row: Dict[str, Any]) -> bool:
        customer, contractor, filters = (
            str(row.get("customer", "")).strip(),
            str(row.get("contractor", "")).strip(),
            str(row.get("filters", "")).strip(),
        )
        if (
            not customer
            and not contractor
            and not filters
            and (row.get("amount") is None or str(row.get("amount")).strip() == "0")
        ):
            return False
        for val in row.values():
            if val is not None and str(val).lower().strip(": ") in self._junk_totals:
                return False
        row_str = " ".join(str(v).lower() for v in row.values() if v is not None)
        if sum(1 for m in self._junk_markers if m in row_str) >= 2:
            return False
        hw = [
            "% посредника",
            "заказчик",
            "исполнитель",
            "сумма платежа",
            "комиссия",
            "итог",
            "фильтры",
            "посредник",
            "приход",
            "расход",
        ]
        for key in ["amount", "income", "expense", "commission", "total"]:
            v = row.get(key)
            if v is not None and any(w in str(v).lower() for w in hw):
                return False
        return True

    def get_errors(self) -> List[str]:
        """Вернуть список ошибок валидации (пусто — заглушка)."""
        return []


class LogicService(ILogicService):
    """Сервис консолидации — применяет финансовые правила к данным."""

    def __init__(self, persistence: IPersistence, config: Dict[str, Any]) -> None:
        self.persistence = persistence
        self.config = config
        l_cfg = config.get("logic", {})
        self.inc_over = l_cfg.get("income_overrides", ["доп", "доп сф", "% посред"])
        self.ret_kw = l_cfg.get("return_keywords", ["возврат"])
        self.commission_is_percent = l_cfg.get("commission_is_percent", True)

    _FORMULA_CHARS = frozenset(("=", "+", "-", "@", "\t", "\r", "\n"))

    def _sanitize(self, val: Any) -> str:
        s = str(val) if val is not None else ""
        s_stripped = s.strip()
        if s_stripped and (
            s_stripped[0] in self._FORMULA_CHARS
            or any(c in s_stripped for c in ("\t", "\r", "\n"))
        ):
            return "'" + s
        return s

    def apply_financial_rules(
        self, raw_rows: List[Dict[str, Any]], curator=None, curator_config=None
    ) -> List[Dict[str, Any]]:
        res = []
        for r in raw_rows:
            f_val = str(r.get("filters", "")).lower()
            is_add, is_ret = (
                any(kw in f_val for kw in self.inc_over),
                any(kw in f_val for kw in self.ret_kw),
            )
            is_critical = False

            try:
                amt = to_decimal(r.get("amount"))
            except (NumericParsingError, ValueError) as e:
                logger.error(
                    f"DATA INTEGRITY ERROR (Logic): {e} | Source: {r.get('_source_info')}"
                )
                amt = Decimal("0.00")
                if isinstance(e, NumericParsingError):
                    is_critical = True

            try:
                tot = to_decimal(r.get("total", 0))
            except (NumericParsingError, ValueError) as e:
                # print(f"DEBUG: Caught error {type(e)}: {e}")
                logger.error(
                    f"DATA INTEGRITY ERROR (Logic): {e} | Source: {r.get('_source_info')}"
                )
                tot = Decimal("0.00")
                is_critical = True  # Simplify: any error here is critical for now

            if amt == 0 and tot == 0 and not is_add and not is_critical:
                continue

            # Financial routing:
            # - is_add (keywords like 'доп'): goes to INCOME
            # - is_ret (keywords like 'возврат'): goes to EXPENSE as NEGATIVE
            # - amt < 0 (standard expense): goes to EXPENSE as POSITIVE
            # - standard: goes to INCOME
            if is_add:
                inc, exp = amt, Decimal("0.00")
            elif is_ret:
                inc, exp = Decimal("0.00"), -abs(amt)
            elif amt < 0:
                inc, exp = Decimal("0.00"), abs(amt)
            else:
                inc, exp = amt, Decimal("0.00")

            c_raw = to_decimal_percent(r.get("commission", 0))
            if self.commission_is_percent and c_raw != 0 and abs(c_raw) <= 1:
                comm = (c_raw * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                comm = c_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            pb_raw = r.get("percent_broker")
            try:
                pb_val = to_decimal(pb_raw)
            except ValueError:
                pb_val = pb_raw

            pb2_val = Decimal("0.00")
            broker2_calc = Decimal("0.00")
            if curator == "boris" and curator_config:
                rate2 = Decimal(str(curator_config.get("intermediary2_rate", 0.05)))
                pb2_val = rate2
                base = tot if tot != 0 else amt
                broker2_calc = (base * rate2).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            elif curator == "ivan" and curator_config:
                rate1 = Decimal(str(curator_config.get("intermediary1_rate", 0.05)))
                rate2 = Decimal(str(curator_config.get("intermediary2_rate", 0.05)))
                pb2_val = rate2
                base = tot if tot != 0 else amt
                pb_val = rate1
                broker2_calc = (base * rate2).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )

            is_warn = r.get("is_template_warning", False)
            if is_warn:
                logger.warning(f"Template warning: {r.get('_source_info')}")
            res.append(
                {
                    "Дата": r.get("date", ""),
                    "Источник": r.get("_source_info", "Unknown"),
                    "ЗАКАЗЧИК (название проекта, наименование ЮЛ)": self._sanitize(
                        r.get("customer", "")
                    ),
                    "ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)": self._sanitize(
                        r.get("contractor", "")
                    ),
                    "сумма платежа ПРИХОД": inc,
                    "сумма платежа РАСХОД": exp,
                    "комиссия": comm,
                    "ИТОГ": tot,
                    "% посредника": pb_val,
                    "посредник 1(кэш)": to_decimal(r.get("broker1")),
                    "посредник 2": to_decimal(r.get("broker2")),
                    "% посредник 2": pb2_val,
                    "Посредник 2 (сумма)": broker2_calc,
                    "фильтры": self._sanitize(r.get("filters", "")),
                    "is_critical": is_critical,
                    "is_template_warning": is_warn,
                }
            )
        return res

    def consolidate(
        self, session_id: str, curator=None, curator_config=None
    ) -> List[Dict[str, Any]]:
        return self.apply_financial_rules(
            self.persistence.get_consolidated_data(session_id),
            curator=curator,
            curator_config=curator_config,
        )
