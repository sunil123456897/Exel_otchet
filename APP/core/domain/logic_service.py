"""Бизнес-логика: финансовые правила и валидация."""

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional

from core.domain.interfaces import IValidator, ILogicService, IPersistence
from core.domain.utils_helpers import (
    to_decimal,
    to_decimal_percent,
    NumericParsingError,
)

logger = logging.getLogger(__name__)

# Default junk/header detection strings (configurable via config.validation)
_DEFAULT_JUNK_TOTALS = frozenset({"итого", "всего", "итог"})
_DEFAULT_JUNK_MARKERS = ("заказчик", "исполнитель", "приход", "расход")
_DEFAULT_HEADER_WORDS = (
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
)


class Validator(IValidator):
    """Валидатор строк данных — отбрасывает мусор и заголовки."""

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        v_cfg = config.get("validation", {})
        self._junk_totals = frozenset(
            v_cfg.get("junk_totals", _DEFAULT_JUNK_TOTALS)
        )
        self._junk_markers = tuple(
            v_cfg.get("junk_markers", _DEFAULT_JUNK_MARKERS)
        )
        self._header_words = v_cfg.get("header_words", _DEFAULT_HEADER_WORDS)

    def validate_row(self, row: Dict[str, Any]) -> bool:
        """Return True if row contains valid financial data, False if junk/header."""
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
        for key in ["amount", "income", "expense", "commission", "total"]:
            v = row.get(key)
            if v is not None and any(w in str(v).lower() for w in self._header_words):
                return False
        return True

    def get_errors(self) -> List[str]:
        """Вернуть список ошибок валидации (пусто — заглушка)."""
        return []


# ──────────────────────────────────────────────────────────────
# Curator Strategy Registry (Item 7 — replaces hardcoded if/elif)
# ──────────────────────────────────────────────────────────────

class CuratorStrategy:
    """Base strategy — no extra broker calculations."""

    def apply(
        self,
        curator_config: Dict[str, Any],
        pb_val: Any,
        amt: Decimal,
        tot: Decimal,
    ) -> tuple:
        """Return (pb_val, pb2_val, broker2_calc)."""
        return pb_val, Decimal("0.00"), Decimal("0.00")


class BorisCuratorStrategy(CuratorStrategy):
    """Boris-specific: calculates intermediary2 broker commission."""

    def apply(self, curator_config, pb_val, amt, tot):
        rate2 = Decimal(str(curator_config.get("intermediary2_rate", 0.05)))
        base = tot if tot != 0 else amt
        broker2_calc = (base * rate2).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return pb_val, rate2, broker2_calc


class IvanCuratorStrategy(CuratorStrategy):
    """Ivan-specific: overrides both intermediary1 and intermediary2 rates."""

    def apply(self, curator_config, pb_val, amt, tot):
        rate1 = Decimal(str(curator_config.get("intermediary1_rate", 0.05)))
        rate2 = Decimal(str(curator_config.get("intermediary2_rate", 0.05)))
        base = tot if tot != 0 else amt
        broker2_calc = (base * rate2).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return rate1, rate2, broker2_calc


# Global registry — add new curators here without modifying LogicService
CURATOR_STRATEGIES: Dict[str, CuratorStrategy] = {
    "boris": BorisCuratorStrategy(),
    "ivan": IvanCuratorStrategy(),
}

_DEFAULT_STRATEGY = CuratorStrategy()


class LogicService(ILogicService):
    """Сервис консолидации — применяет финансовые правила к данным."""

    def __init__(self, persistence: IPersistence, config: Dict[str, Any]) -> None:
        self.persistence = persistence
        self.config = config
        l_cfg = config.get("logic", {})
        self.inc_over = l_cfg.get("income_overrides", ["доп", "доп сф", "% посред"])
        self.ret_kw = l_cfg.get("return_keywords", ["возврат"])
        self.commission_is_percent = l_cfg.get("commission_is_percent", True)

    _SANITIZE_CHARS = frozenset(("=", "+", "-", "@", "\t", "\r", "\n"))

    def _sanitize(self, val: Any) -> str:
        """Sanitize cell value to prevent Excel formula injection."""
        s = str(val) if val is not None else ""
        s_stripped = s.strip()
        if s_stripped and (
            s_stripped[0] in self._SANITIZE_CHARS
            or any(c in s_stripped for c in ("\t", "\r", "\n"))
        ):
            return "'" + s
        return s

    def _build_error_row(self, r: Dict[str, Any], is_critical: bool = True) -> Dict[str, Any]:
        """Build a row dict that marks a critical data integrity error.

        The row is included in the output so it appears in the final report
        highlighted in red, rather than being silently dropped.
        """
        return {
            "Дата": r.get("date", ""),
            "Источник": r.get("_source_info", "Unknown"),
            "ЗАКАЗЧИК (название проекта, наименование ЮЛ)": self._sanitize(
                r.get("customer", "")
            ),
            "ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)": self._sanitize(
                r.get("contractor", "")
            ),
            "сумма платежа ПРИХОД": Decimal("0.00"),
            "сумма платежа РАСХОД": Decimal("0.00"),
            "комиссия": Decimal("0.00"),
            "ИТОГ": Decimal("0.00"),
            "% посредника": Decimal("0.00"),
            "посредник 1(кэш)": Decimal("0.00"),
            "посредник 2": Decimal("0.00"),
            "% посредник 2": Decimal("0.00"),
            "Посредник 2 (сумма)": Decimal("0.00"),
            "фильтры": self._sanitize(r.get("filters", "")),
            "is_critical": is_critical,
            "is_template_warning": r.get("is_template_warning", False),
        }

    def _get_curator_strategy(self, curator: Optional[str]) -> CuratorStrategy:
        """Look up curator strategy from the registry."""
        if not curator:
            return _DEFAULT_STRATEGY
        return CURATOR_STRATEGIES.get(curator, _DEFAULT_STRATEGY)

    def apply_financial_rules(
        self, raw_rows: List[Dict[str, Any]], curator=None, curator_config=None
    ) -> List[Dict[str, Any]]:
        """Apply commissions, returns, and other business rules to raw rows."""
        res = []
        strategy = self._get_curator_strategy(curator)

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
                if isinstance(e, NumericParsingError):
                    # Critical parse error — record the row with is_critical flag
                    # but do NOT silently substitute zero
                    res.append(self._build_error_row(r, is_critical=True))
                    continue
                amt = Decimal("0.00")

            try:
                tot = to_decimal(r.get("total", 0))
            except (NumericParsingError, ValueError) as e:
                logger.error(
                    f"DATA INTEGRITY ERROR (Logic): {e} | Source: {r.get('_source_info')}"
                )
                # Critical parse error on total — record and skip
                res.append(self._build_error_row(r, is_critical=True))
                continue

            if amt == 0 and tot == 0 and not is_add and not is_critical:
                continue

            # Financial routing
            if is_add:
                inc, exp = amt, Decimal("0.00")
            elif is_ret:
                inc, exp = Decimal("0.00"), -abs(amt)
            elif amt < 0:
                inc, exp = Decimal("0.00"), abs(amt)
            else:
                inc, exp = amt, Decimal("0.00")

            c_raw = to_decimal_percent(r.get("commission", 0))
            try:
                if self.commission_is_percent and c_raw != 0 and abs(c_raw) <= 1:
                    comm = (c_raw * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                else:
                    comm = c_raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            except (TypeError, ArithmeticError):
                # If c_raw is a string or math fails, try to convert to Decimal or use 0
                try:
                    comm = to_decimal(c_raw)
                except (NumericParsingError, ValueError):
                    comm = Decimal("0.00")

            pb_raw = r.get("percent_broker")
            try:
                pb_val = to_decimal(pb_raw)
            except ValueError:
                pb_val = pb_raw

            # Apply curator-specific broker logic via strategy
            if curator_config:
                pb_val, pb2_val, broker2_calc = strategy.apply(
                    curator_config, pb_val, amt, tot
                )
            else:
                pb2_val = Decimal("0.00")
                broker2_calc = Decimal("0.00")

            is_warn = r.get("is_template_warning", False)
            if is_warn:
                logger.warning(f"Template warning: {r.get('_source_info')}")
            try:
                b1_val = to_decimal(r.get("broker1"))
            except (NumericParsingError, ValueError):
                b1_val = Decimal("0.00")

            try:
                b2_val = to_decimal(r.get("broker2"))
            except (NumericParsingError, ValueError):
                b2_val = Decimal("0.00")

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
                    "посредник 1(кэш)": b1_val,
                    "посредник 2": b2_val,
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
        """Perform SQL-based aggregation for the final report.

        The curator/curator_config parameters are kept for backward
        compatibility but are not used in the standard single-report flow.
        """
        return self.apply_financial_rules(
            self.persistence.get_consolidated_data(session_id),
        )
