import re
import logging
import json
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional
from .interfaces import IValidator, ILogicService, IPersistence

class Validator(IValidator):
    """
    Implements row-level validation and junk detection based on business logic.
    """
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.markers = config.get('sh1', {}).get('markers', {})
        self.errors = []
        self._junk_totals = frozenset({"итого", "всего", "итог"})
        self._junk_markers = ("заказчик", "исполнитель", "приход", "расход")

    def validate_row(self, row: Dict[str, Any]) -> bool:
        """
        Returns True if row is valid, False if it's a header, total, or empty row.
        """
        self.errors = []
        
        # 1. Check if row is empty in key columns
        customer = str(row.get('customer', '')).strip()
        contractor = str(row.get('contractor', '')).strip()
        filters = str(row.get('filters', '')).strip()
        amount = row.get('amount')
        
        # If all key text fields are empty and amount is missing/zero, it's likely junk
        if not customer and not contractor and not filters:
            if amount is None or amount == '' or str(amount).strip() == '0':
                return False

        # 2. Check for "Total" markers in any cell
        for val in row.values():
            if val is not None:
                v_str = str(val).lower().strip(': ')
                if v_str in self._junk_totals:
                    return False

        # 3. Check for header markers (if multiple markers are present, it's a header row)
        row_str = " ".join(str(v).lower() for v in row.values() if v is not None)
        marker_count = 0
        for m in self._junk_markers:
            if m in row_str:
                marker_count += 1
        if marker_count >= 2:
            return False

        # 4. Check if numeric columns contain header words (common in repeated headers)
        header_words = ['% посредника', 'заказчик', 'исполнитель',
                        'сумма платежа', 'комиссия', 'итог', 'фильтры',
                        'посредник', 'приход', 'расход']
        
        # Check columns that should be numeric
        for key in ['amount', 'income', 'expense', 'commission', 'total']:
            val = row.get(key)
            if val is not None:
                val_str = str(val).strip().lower()
                if any(hw in val_str for hw in header_words):
                    return False

        return True

    def get_errors(self) -> List[str]:
        return self.errors

class LogicService(ILogicService):
    """
    Implements financial transformations and consolidation logic.
    """
    def __init__(self, persistence: IPersistence, config: Dict[str, Any]):
        self.persistence = persistence
        self.config = config
        self.logic_config = config.get('logic', {})
        self.income_overrides = self.logic_config.get('income_overrides', ['доп', 'доп сф', '% посред'])
        self.return_keywords = self.logic_config.get('return_keywords', ['возврат'])
        self.logger = logging.getLogger(__name__)

    def _to_decimal(self, val: Any) -> Decimal:
        """Converts various input types to Decimal with 0.01 precision."""
        if val is None or val == "" or (isinstance(val, float) and val != val):
            return Decimal('0.00')
        if isinstance(val, (int, float, Decimal)):
            return Decimal(str(val)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        try:
            raw_str = str(val).strip()
            # Handle accounting negative notation: (100.00) -> -100.00
            is_accounting_negative = raw_str.startswith('(') and raw_str.endswith(')')
            
            # Remove non-numeric characters except separators and signs
            s = re.sub(r"[^\d.,\-eE+]", "", raw_str)
            if not s: return Decimal('0.00')
            s = s.rstrip('.,')
            if not s: return Decimal('0.00')
            
            # Handle scientific notation
            if 'e' in s.lower():
                res = Decimal(s).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                return -abs(res) if is_accounting_negative else res

            # Handle decimal separators (dot vs comma)
            separators = [i for i, char in enumerate(s) if char in '.,']
            if len(separators) == 1:
                sep_idx = separators[0]
                if s[sep_idx] == ',':
                    clean_val = s.replace(',', '.')
                else:
                    clean_val = s
            elif len(separators) >= 2:
                # Multiple separators: assume last one is decimal, others are thousands
                last_sep_idx = separators[-1]
                prefix = s[:last_sep_idx].replace('.', '').replace(',', '')
                suffix = s[last_sep_idx + 1:]
                clean_val = f"{prefix}.{suffix}" if suffix else prefix
            else:
                clean_val = s

            res = Decimal(clean_val).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            return -abs(res) if is_accounting_negative else res
        except Exception:
            return Decimal('0.00')

    def _to_decimal_percent(self, val: Any) -> Decimal:
        """Converts percentage strings or fractions to Decimal."""
        if val is None or val == "" or (isinstance(val, float) and val != val):
            return Decimal('0')
        if isinstance(val, (int, float, Decimal)):
            return Decimal(str(val))
        try:
            raw_s = str(val)
            s = re.sub(r"[^\d.,-]", "", raw_s)
            if not s: return Decimal('0')
            clean_val = s.replace(',', '.')
            res = Decimal(clean_val)
            # If value is > 1 and contains %, it's likely a percentage (e.g. "20%")
            if "%" in raw_s and res > 1:
                res = res / Decimal('100')
            return res
        except Exception:
            return Decimal('0')

    def _sanitize(self, val: Any) -> str:
        """Prevents Excel formula injection by adding a leading quote."""
        v_str = str(val) if val is not None else ""
        if v_str.strip().startswith(('=', '+', '-', '@')):
            return "'" + v_str
        return v_str

    def apply_financial_rules(self, raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Applies commissions, returns, and other business rules to raw rows.
        """
        transformed_rows = []
        for row in raw_rows:
            # 1. Extract and normalize values
            raw_amount_val = row.get('amount')
            filters_val = str(row.get('filters', '')).lower()
            
            # 2. Determine transaction type
            is_additional = any(kw.lower() in filters_val for kw in self.income_overrides)
            is_return = any(kw.lower() in filters_val for kw in self.return_keywords)
            
            raw_amount = self._to_decimal(raw_amount_val)
            source_total = self._to_decimal(row.get('total', 0))
            
            # Skip rows with no financial data unless they are marked as additional income
            if raw_amount == 0 and source_total == 0 and not is_additional:
                continue

            income = Decimal('0.00')
            expense = Decimal('0.00')
            
            if is_additional:
                income = raw_amount
            elif is_return:
                # Returns are always expenses
                expense = abs(raw_amount)
            elif raw_amount < 0:
                # Negative amounts are expenses
                expense = abs(raw_amount)
            else:
                # Positive amounts are income
                income = raw_amount

            # 3. Format commission (convert fraction to percentage for display)
            comm_raw = self._to_decimal_percent(row.get('commission', 0))
            commission = (
                comm_raw * 100
                if comm_raw != Decimal('0') and abs(comm_raw) <= Decimal('1')
                else comm_raw
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            # 4. Format broker percentage
            broker_pct = self._to_decimal(row.get('percent_broker'))

            # 5. Build transformed row with sanitized strings
            is_warning = row.get('is_template_warning', False)
            if is_warning:
                self.logger.warning(f"Нарушение шаблона (повторная шапка): {row.get('_source_info')}")

            transformed = {
                'Дата': row.get('date', ''),
                'Источник': row.get('_source_info', 'Unknown'), # Filename : Row
                'ЗАКАЗЧИК (название проекта, наименование ЮЛ)': self._sanitize(row.get('customer', '')),
                'ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)': self._sanitize(row.get('contractor', '')),
                'сумма платежа ПРИХОД': income,
                'сумма платежа РАСХОД': expense,
                'комиссия': commission,
                'ИТОГ': source_total,
                '% посредника': broker_pct,
                'посредник 1(кэш)': self._to_decimal(row.get('broker1')),
                'посредник 2': self._to_decimal(row.get('broker2')),
                'фильтры': self._sanitize(row.get('filters', '')),
                'is_critical': False,
                'is_template_warning': is_warning
            }
            transformed_rows.append(transformed)
            
        return transformed_rows

    def consolidate(self, session_id: str) -> List[Dict[str, Any]]:
        """
        Performs SQL-based aggregation for the final report.
        Retrieves data from persistence and applies financial rules.
        """
        # 1. Retrieve raw staging data from persistence
        raw_rows = self.persistence.get_consolidated_data(session_id)
        
        # 2. Apply financial rules to transform raw data
        transformed = self.apply_financial_rules(raw_rows)
        
        # 3. Return the consolidated list
        return transformed
