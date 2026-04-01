import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any
from core.domain.interfaces import IValidator, ILogicService, IPersistence
from core.domain.utils_helpers import to_decimal, to_decimal_percent

logger = logging.getLogger(__name__)

class Validator(IValidator):
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._junk_totals = frozenset({"итого", "всего", "итог"})
        self._junk_markers = ("заказчик", "исполнитель", "приход", "расход")

    def validate_row(self, row: Dict[str, Any]) -> bool:
        customer, contractor, filters = str(row.get('customer', '')).strip(), str(row.get('contractor', '')).strip(), str(row.get('filters', '')).strip()
        if not customer and not contractor and not filters and (row.get('amount') is None or str(row.get('amount')).strip() == '0'): return False
        for val in row.values():
            if val is not None and str(val).lower().strip(': ') in self._junk_totals: return False
        row_str = " ".join(str(v).lower() for v in row.values() if v is not None)
        if sum(1 for m in self._junk_markers if m in row_str) >= 2: return False
        hw = ['% посредника', 'заказчик', 'исполнитель', 'сумма платежа', 'комиссия', 'итог', 'фильтры', 'посредник', 'приход', 'расход']
        for key in ['amount', 'income', 'expense', 'commission', 'total']:
            v = row.get(key)
            if v is not None and any(w in str(v).lower() for w in hw): return False
        return True
    def get_errors(self) -> List[str]: return []

class LogicService(ILogicService):
    def __init__(self, persistence: IPersistence, config: Dict[str, Any]):
        self.persistence, self.config = persistence, config
        l_cfg = config.get('logic', {})
        self.inc_over = l_cfg.get('income_overrides', ['доп', 'доп сф', '% посред'])
        self.ret_kw = l_cfg.get('return_keywords', ['возврат'])

    def _sanitize(self, val: Any) -> str:
        s = str(val) if val is not None else ""
        return "'" + s if s.strip().startswith(('=', '+', '-', '@')) else s

    def apply_financial_rules(self, raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        res = []
        for r in raw_rows:
            f_val = str(r.get('filters', '')).lower()
            is_add, is_ret = any(kw in f_val for kw in self.inc_over), any(kw in f_val for kw in self.ret_kw)
            try:
                amt = to_decimal(r.get('amount'))
            except ValueError as e:
                logger.error(f"DATA INTEGRITY ERROR (Logic): {e} | Source: {r.get('_source_info')}")
                amt = Decimal('0.00')
                
            try:
                tot = to_decimal(r.get('total', 0))
            except ValueError as e:
                logger.error(f"DATA INTEGRITY ERROR (Logic): {e} | Source: {r.get('_source_info')}")
                tot = Decimal('0.00')

            if amt == 0 and tot == 0 and not is_add: continue
            
            # Financial routing:
            # - is_add (keywords like 'доп'): goes to INCOME
            # - is_ret (keywords like 'возврат'): goes to EXPENSE as NEGATIVE
            # - amt < 0 (standard expense): goes to EXPENSE as POSITIVE
            # - standard: goes to INCOME
            if is_add:
                inc, exp = amt, Decimal('0.00')
            elif is_ret:
                inc, exp = Decimal('0.00'), -abs(amt)
            elif amt < 0:
                inc, exp = Decimal('0.00'), abs(amt)
            else:
                inc, exp = amt, Decimal('0.00')
                
            c_raw = to_decimal_percent(r.get('commission', 0))
            comm = (c_raw * 100 if c_raw != 0 and abs(c_raw) <= 1 else c_raw).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            is_warn = r.get('is_template_warning', False)
            if is_warn: logger.warning(f"Template warning: {r.get('_source_info')}")
            res.append({'Дата': r.get('date', ''), 'Источник': r.get('_source_info', 'Unknown'), 'ЗАКАЗЧИК (название проекта, наименование ЮЛ)': self._sanitize(r.get('customer', '')), 'ИСПОЛНИТЕЛЬ (наименование ЮЛ, банк)': self._sanitize(r.get('contractor', '')), 'сумма платежа ПРИХОД': inc, 'сумма платежа РАСХОД': exp, 'комиссия': comm, 'ИТОГ': tot, '% посредника': to_decimal(r.get('percent_broker')), 'посредник 1(кэш)': to_decimal(r.get('broker1')), 'посредник 2': to_decimal(r.get('broker2')), 'фильтры': self._sanitize(r.get('filters', '')), 'is_critical': False, 'is_template_warning': is_warn})
        return res

    def consolidate(self, session_id: str) -> List[Dict[str, Any]]:
        return self.apply_financial_rules(self.persistence.get_consolidated_data(session_id))

