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
from core.domain.data_schemas import FinancialRowSchema

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

        def _is_empty_zero(v: Any) -> bool:
            if v is None:
                return True
            return str(v).strip() in {"", "0", "0.00", "0.0", "0,00", "0,0"}

        if not customer and not contractor and not filters and _is_empty_zero(amount_val):
            return False

        # Service metadata fields (private keys starting with '_') carry
        # diagnostics like _template_warning_reason = 'unsupported header
        # name: % -> % посредника; ...'. Those descriptions legitimately
        # contain header words ('комиссия', 'фильтры', 'посредник'). The
        # header-word filter used to scan EVERY field, so it matched the
        # diagnostic text and rejected the whole row — which silently
        # zeroed out the Boris/Ivan curator batches in auto-reconciliation
        # (both files use aliased headers that trigger soft warnings).
        # Skip private fields in the junk/header heuristics below.
        def _is_service_field(key: str) -> bool:
            return isinstance(key, str) and key.startswith("_")

        for key, val in row.items():
            if _is_service_field(key) or val is None:
                continue
            s_norm = " ".join(str(val).lower().split())
            if any(w in s_norm for w in self._header_words):
                return False

        name_field_keys = ["customer", "contractor"]
        name_fields_filled = sum(
            1
            for k in name_field_keys
            if row.get(k) and str(row.get(k)).strip()
        )

        non_name_marker_hits = 0
        for k, v in row.items():
            if v is None or k in name_field_keys or _is_service_field(k):
                continue
            v_str = " ".join(str(v).lower().split())
            if any(m in v_str for m in self._junk_totals):
                non_name_marker_hits += 1

        if non_name_marker_hits >= 2:
            return False

        for key in ["amount", "income", "expense", "commission", "total"]:
            v = row.get(key)
            if v is None:
                continue
            v_str = " ".join(str(v).lower().split())
            if any(w in v_str for w in self._header_words):
                return False

        if name_fields_filled >= 2:
            row_str = " ".join(
                " ".join(str(v).lower().split())
                for k, v in row.items()
                if v is not None and not _is_service_field(k)
            )
            if sum(1 for m in self._junk_markers if m in row_str) >= 3:
                return False

        try:
            from pydantic import ValidationError
            FinancialRowSchema(**row)
            return True
        except ValidationError as e:
            logger.warning("Pydantic validation failed for data row: %s | Row: %s", e, row)
            return False

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
        self.exclude_kw = l_cfg.get(
            "exclude_keywords", ["недопустимо", "исключить", "исключение"]
        )

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
            "Источник": self._sanitize(r.get("_source_info", "Unknown")),
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
    def _has_transit_values(r: FinancialRowSchema) -> bool:
        values = [
            to_decimal(getattr(r, field, 0))
            for field in ("transit_obligation", "exchange_rate", "currency_amount")
        ]
        return any(value != 0 for value in values) or bool(str(r.currency or "").strip())

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
        # transit/rate/currency_amount may carry garbage (e.g. a header
        # label that leaked into a data cell like ' ОТПРАВКА ТРАНЗИТНЫХ
        # ОБЯЗАТЕЛЬСТВ'). The strict to_decimal() raises NumericParsingError
        # on such values, which is wrapped for amount/total/brokers above
        # but was NOT wrapped here — so one dirty transit cell crashed the
        # whole curator batch (and with it the Ivan sheet of auto-recon).
        # Use the same fail-soft helper the brokers use.
        transit_val, _ = self._parse_decimal_or_warn(r.get("transit_obligation", 0))
        rate_val, _ = self._parse_decimal_or_warn(r.get("exchange_rate", 0))
        cur_amt_val, _ = self._parse_decimal_or_warn(r.get("currency_amount", 0))
        return {
            "Дата": r.get("date", ""),
            "Источник": self._sanitize(r.get("_source_info", "Unknown")),
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
            "ОТПРАВКА ТРАНЗИТНЫХ ОБЯЗАТЕЛЬСТВ": transit_val,
            "курс": rate_val,
            "сумма": cur_amt_val,
            "валюта": self._sanitize(r.get("currency", "")),
            "фильтры": self._sanitize(r.get("filters", "")),
            "is_critical": is_critical,
            "is_template_warning": is_warn,
            "_template_warning_kind": r.get("_template_warning_kind"),
            "_template_warning_reason": r.get("_template_warning_reason"),
            "_source_file_path": r.get("_file_path"),
            "_source_sheet_name": r.get("_source_sheet_name"),
            "_source_row_index": r.get("_source_row_index"),
        }

    def apply_financial_rules(
        self, raw_rows: List[Dict[str, Any]], curator=None, curator_config=None
    ) -> List[Dict[str, Any]]:
        """Apply commissions, returns, and other business rules to raw rows."""
        res = []
        strategy = self._get_curator_strategy(curator)
        template_warning_count = 0

        for r in raw_rows:
            row_model = FinancialRowSchema(**r)
            f_val = str(row_model.filters or "").lower()
            is_add, is_ret = (
                any(kw in f_val for kw in self.inc_over),
                any(kw in f_val for kw in self.ret_kw),
            )
            is_excluded = any(kw in f_val for kw in self.exclude_kw)
            is_critical = False
            is_warn = False

            source_info = row_model.model_extra.get("_source_info", "Unknown") if row_model.model_extra else "Unknown"

            try:
                amt = to_decimal(row_model.amount)
            except (NumericParsingError, ValueError) as e:
                logger.error(
                    f"DATA INTEGRITY ERROR (Logic): {e} | Source: {source_info}"
                )
                if isinstance(e, NumericParsingError):
                    # Critical parse error — record the row with is_critical flag
                    # but do NOT silently substitute zero
                    res.append(self._build_error_row(r, is_critical=True))
                    continue
                amt = Decimal("0.00")

            try:
                tot = to_decimal(row_model.total)
            except (NumericParsingError, ValueError) as e:
                logger.error(
                    f"DATA INTEGRITY ERROR (Logic): {e} | Source: {source_info}"
                )
                # Critical parse error on total — record and skip
                res.append(self._build_error_row(r, is_critical=True))
                continue

            raw_b1, broker1_warn = self._parse_decimal_or_warn(row_model.broker1)
            raw_b2, broker2_warn = self._parse_decimal_or_warn(row_model.broker2)
            is_warn = is_warn or broker1_warn or broker2_warn

            has_broker_values = raw_b1 != 0 or raw_b2 != 0
            try:
                has_transit_values = self._has_transit_values(row_model)
            except (NumericParsingError, ValueError) as e:
                # Transit fields contain unparseable text (e.g. a header
                # label that leaked into a data cell).  Previously this
                # discarded the entire row as a critical error — but the
                # amount/total/broker fields may be perfectly valid.
                # Downgrade to a warning so the financial data is preserved.
                logger.warning(
                    "Transit parse error (non-fatal): %s | Source: %s",
                    e, source_info,
                )
                has_transit_values = True  # Assume transit might exist — don't drop
                is_warn = True

            if (
                amt == 0
                and tot == 0
                and not has_broker_values
                and not has_transit_values
                and not is_add
                and not is_critical
            ):
                continue

            if is_excluded:
                amt = Decimal("0.00")

            inc, exp = self._resolve_flow(amt, is_add, is_ret)
            comm, commission_warn = self._resolve_commission(row_model.commission)
            is_warn = is_warn or commission_warn

            pb_raw = row_model.percent_broker
            pb_val = to_decimal_percent(pb_raw)
            pb_val = self._abs_decimal(pb_val)

            # Apply curator-specific broker logic via strategy
            if curator_config:
                pb2_raw = row_model.percent_broker2
                pb_val, pb2_val, broker2_calc = strategy.apply(
                    curator_config, pb_val, amt, tot, raw_b2, pb2_raw
                )
            else:
                pb2_val = Decimal("0.00")
                broker2_calc = Decimal("0.00")

            pb2_val = self._abs_decimal(pb2_val)
            broker2_calc = self._abs_decimal(broker2_calc)

            is_warn = bool(row_model.is_template_warning or is_warn)
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
