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
_DEFAULT_JUNK_TOTALS = frozenset({"итого", "всего", "итог", "итог дня", "итоги дня"})
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
        self._junk_totals = frozenset(v_cfg.get("junk_totals", _DEFAULT_JUNK_TOTALS))
        self._junk_markers = tuple(v_cfg.get("junk_markers", _DEFAULT_JUNK_MARKERS))
        self._header_words = v_cfg.get("header_words", _DEFAULT_HEADER_WORDS)

    def validate_row(self, row: Dict[str, Any]) -> bool:
        """Return True if row contains valid financial data, False if junk/header."""
        customer, contractor, filters = (
            str(row.get("customer", "")).strip(),
            str(row.get("contractor", "")).strip(),
            str(row.get("filters", "")).strip(),
        )
        amount_val = row.get("amount")
        total_val = row.get("total")
        if (
            not customer
            and not contractor
            and not filters
            and (amount_val is None or str(amount_val).strip() == "0")
        ):
            return False
        if (
            not customer
            and not contractor
            and not filters
            and amount_val is not None
            and str(amount_val).strip() not in {"", "0"}
            and total_val is not None
            and str(total_val).strip() not in {"", "0"}
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
        raw_b2: Decimal,
        pb2_raw: Any,
    ) -> tuple:
        """Return (pb_val, pb2_val, broker2_calc)."""
        return pb_val, Decimal("0.00"), Decimal("0.00")


class BorisCuratorStrategy(CuratorStrategy):
    """Boris-specific: keeps intermediary2 values from the source report."""

    def apply(self, curator_config, pb_val, amt, tot, raw_b2, pb2_raw):
        if raw_b2 == 0:
            return pb_val, Decimal("0.00"), Decimal("0.00")

        pb2_val = to_decimal_percent(pb2_raw or 0)
        if isinstance(pb2_val, Decimal):
            pb2_val = abs(pb2_val)
        else:
            pb2_val = abs(to_decimal(pb2_val))
        return pb_val, pb2_val, abs(raw_b2)


class IvanCuratorStrategy(CuratorStrategy):
    """Ivan-specific layout keeps manually entered intermediary values."""

    def apply(self, curator_config, pb_val, amt, tot, raw_b2, pb2_raw):
        return pb_val, Decimal("0.00"), Decimal("0.00")


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
        self.inc_over = l_cfg.get("income_overrides", ["доп", "доп сф", "доп.сф", "% посред"])
        self.ret_kw = l_cfg.get("return_keywords", ["возврат"])
        self.commission_is_percent = l_cfg.get("commission_is_percent", True)

    _SANITIZE_CHARS = frozenset(("=", "+", "-", "@", "\t", "\r", "\n"))

    @staticmethod
    def _abs_decimal(value: Any) -> Any:
        if isinstance(value, Decimal):
            return abs(value)
        return value

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

    def _build_error_row(
        self, r: Dict[str, Any], is_critical: bool = True
    ) -> Dict[str, Any]:
        """Build a row dict that marks a critical data integrity error.

        The row is included in the output so it appears in the final report
        highlighted in red, rather than being silently dropped.
        """
        return {
            "Дата": r.get("date", ""),
            "Источник": r.get("_source_info", "Unknown"),
            "Сотрудник": self._sanitize(r.get("employee_name", "")),
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
            "ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ": Decimal("0.00"),
            "курс": Decimal("0.00"),
            "сумма": Decimal("0.00"),
            "валюта": self._sanitize(r.get("currency", "")),
            "фильтры": self._sanitize(r.get("filters", "")),
            "is_critical": is_critical,
            "is_template_warning": r.get("is_template_warning", False),
        }

    def _get_curator_strategy(self, curator: Optional[str]) -> CuratorStrategy:
        """Look up curator strategy from the registry."""
        if not curator:
            return _DEFAULT_STRATEGY
        return CURATOR_STRATEGIES.get(curator, _DEFAULT_STRATEGY)

    @staticmethod
    def _parse_decimal_or_warn(value: Any) -> tuple[Decimal, bool]:
        try:
            return to_decimal(value), False
        except (NumericParsingError, ValueError):
            return Decimal("0.00"), True

    @staticmethod
    def _has_transit_values(r: Dict[str, Any]) -> bool:
        values = [
            to_decimal(r.get(field, 0))
            for field in ("transit_obligation", "exchange_rate", "currency_amount")
        ]
        return any(value != 0 for value in values) or bool(str(r.get("currency", "")).strip())

    @staticmethod
    def _resolve_flow(amount: Decimal, is_add: bool, is_ret: bool) -> tuple[Decimal, Decimal]:
        if is_add:
            return amount, Decimal("0.00")
        if is_ret:
            return Decimal("0.00"), -abs(amount)
        if amount < 0:
            return Decimal("0.00"), abs(amount)
        return amount, Decimal("0.00")

    def _resolve_commission(self, raw_value: Any) -> tuple[Decimal, bool]:
        c_raw = to_decimal_percent(raw_value or 0)
        try:
            if self.commission_is_percent and c_raw != 0 and abs(c_raw) <= 1:
                return (
                    abs(c_raw * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                    False,
                )
            return abs(c_raw).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), False
        except (TypeError, ArithmeticError):
            try:
                return abs(to_decimal(c_raw)), False
            except (NumericParsingError, ValueError):
                return Decimal("0.00"), True

    def _build_result_row(
        self,
        r: Dict[str, Any],
        *,
        inc: Decimal,
        exp: Decimal,
        comm: Decimal,
        tot: Decimal,
        pb_val: Decimal,
        b1_val: Decimal,
        b2_val: Decimal,
        pb2_val: Decimal,
        broker2_calc: Decimal,
        is_critical: bool,
        is_warn: bool,
    ) -> Dict[str, Any]:
        return {
            "Дата": r.get("date", ""),
            "Источник": r.get("_source_info", "Unknown"),
            "Сотрудник": self._sanitize(r.get("employee_name", "")),
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
            "ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ": to_decimal(
                r.get("transit_obligation", 0)
            ),
            "курс": to_decimal(r.get("exchange_rate", 0)),
            "сумма": to_decimal(r.get("currency_amount", 0)),
            "валюта": self._sanitize(r.get("currency", "")),
            "фильтры": self._sanitize(r.get("filters", "")),
            "is_critical": is_critical,
            "is_template_warning": is_warn,
            "_template_warning_kind": r.get("_template_warning_kind"),
            "_template_warning_reason": r.get("_template_warning_reason"),
            "_source_file_path": r.get("_file_path"),
            "_source_sheet_name": r.get("_sheet_name"),
            "_source_row_index": r.get("_row_index"),
        }

    def apply_financial_rules(
        self, raw_rows: List[Dict[str, Any]], curator=None, curator_config=None
    ) -> List[Dict[str, Any]]:
        """Apply commissions, returns, and other business rules to raw rows."""
        res = []
        strategy = self._get_curator_strategy(curator)
        template_warning_count = 0

        for r in raw_rows:
            f_val = str(r.get("filters", "")).lower()
            is_add, is_ret = (
                any(kw in f_val for kw in self.inc_over),
                any(kw in f_val for kw in self.ret_kw),
            )
            is_critical = False
            is_warn = False

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

            raw_b1, broker1_warn = self._parse_decimal_or_warn(r.get("broker1"))
            raw_b2, broker2_warn = self._parse_decimal_or_warn(r.get("broker2"))
            is_warn = is_warn or broker1_warn or broker2_warn

            has_broker_values = raw_b1 != 0 or raw_b2 != 0
            try:
                has_transit_values = self._has_transit_values(r)
            except (NumericParsingError, ValueError) as e:
                logger.error(
                    f"DATA INTEGRITY ERROR (Logic): {e} | Source: {r.get('_source_info')}"
                )
                res.append(self._build_error_row(r, is_critical=True))
                continue

            if (
                amt == 0
                and tot == 0
                and not has_broker_values
                and not has_transit_values
                and not is_add
                and not is_critical
            ):
                continue

            inc, exp = self._resolve_flow(amt, is_add, is_ret)
            comm, commission_warn = self._resolve_commission(r.get("commission", 0))
            is_warn = is_warn or commission_warn

            pb_raw = r.get("percent_broker")
            pb_val = to_decimal_percent(pb_raw)
            pb_val = self._abs_decimal(pb_val)

            # Apply curator-specific broker logic via strategy
            if curator_config:
                pb2_raw = r.get("percent_broker2")
                pb_val, pb2_val, broker2_calc = strategy.apply(
                    curator_config, pb_val, amt, tot, raw_b2, pb2_raw
                )
            else:
                pb2_val = Decimal("0.00")
                broker2_calc = Decimal("0.00")

            pb2_val = self._abs_decimal(pb2_val)
            broker2_calc = self._abs_decimal(broker2_calc)

            is_warn = r.get("is_template_warning", False) or is_warn
            if is_warn:
                template_warning_count += 1
            b1_val = abs(raw_b1)
            b2_val = abs(raw_b2)

            res.append(
                self._build_result_row(
                    r,
                    inc=inc,
                    exp=exp,
                    comm=comm,
                    tot=tot,
                    pb_val=pb_val,
                    b1_val=b1_val,
                    b2_val=b2_val,
                    pb2_val=pb2_val,
                    broker2_calc=broker2_calc,
                    is_critical=is_critical,
                    is_warn=is_warn,
                )
            )
        if template_warning_count:
            logger.warning("Template warnings: %s row(s) affected", template_warning_count)
        return res

    def consolidate(
        self, session_id: str, curator=None, curator_config=None
    ) -> List[Dict[str, Any]]:
        """Perform SQL-based aggregation for the final report.

        The curator/curator_config parameters enable separate curator-specific
        reports without affecting the standard single-report flow.
        """
        return self.apply_financial_rules(
            self.persistence.get_consolidated_data(session_id),
            curator=curator,
            curator_config=curator_config,
        )
