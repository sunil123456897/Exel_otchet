"""Trace scoring for СБИ rows — fully inline, no imports from project."""
import sys
from decimal import Decimal, InvalidOperation
from openpyxl import load_workbook
from functools import lru_cache
import re
from collections import defaultdict

# ── Inline all needed functions from _utils.py ───────────────

def _normalize_text(value):
    if value is None:
        return ""
    return _normalize_text_cached(str(value))

@lru_cache(maxsize=65536)
def _normalize_text_cached(text):
    return " ".join(text.replace("\xa0", " ").replace("ё", "е").lower().split())

@lru_cache(maxsize=65536)
def _canonical_match_text_cached(text):
    if not text:
        return ""
    text = re.sub(r"([а-я])([a-z])", r"\1 \2", text)
    text = re.sub(r"([a-z])([а-я])", r"\1 \2", text)
    text = re.sub(r"(?<![а-я])ук(?:а_альфа|а_сбер|а_втб|альянс|альфа|втб)", "ука", text)
    text = re.sub(r"\bук[\s_]+альянс\b", "ука", text)
    text = re.sub(r"\bукальянс\b", "ука", text)
    text = re.sub(r"(?<![а-я])укалинс(?![а-я])", "ука", text)
    text = re.sub(r"\bул[\s_]+альянс\b", "ука", text)
    text = re.sub(r"\bук[\s_]+а\b", "ука", text)
    text = re.sub(r"\bук[\s_]+аф\b", "ука", text)
    text = re.sub(r"\bук[\s_]+(?=(альфа|сбер|втб|сб)\b)", "ука ", text)
    text = re.sub(r"(?<![а-я])ука[а-я]*(?:_[а-я]+)?(?![а-я])", "ука", text)
    text = re.sub(r"(?<![а-я])сбер[\s_]*рн(?![а-я])", "ука", text)
    text = re.sub(r"\bтина(?:[\s_]*(?:дар|да|бизнес))?(?![а-я])", "тина", text)
    text = re.sub(r"\bтина[\s_]+сбер\b", "тина", text)
    text = re.sub(r"\bбилл?трейд\b", "биллтрейд", text)
    text = re.sub(r"\bбилл(?!\w)", "биллтрейд", text)
    text = re.sub(r"\bбилтрейд\b", "биллтрейд", text)
    text = re.sub(r"\bано[\s_]+тск\b", "анотехникум", text)
    text = re.sub(r"\bано[\s_]+техникум\b", "анотехникум", text)
    text = re.sub(r"(?<![а-я])тск(?:[\s_]*(?:сбер|альфа|втб|сб))?(?![а-я])", "анотехникум", text)
    text = re.sub(r"\bсб[\s_]+защита\b", "сбзащита", text)
    text = re.sub(r"\bзащита[\s_]+ррб\b", "сбзащита", text)
    text = re.sub(r"\bстип[\s_]*сбер\b", "стинг", text)
    text = re.sub(r"(?<![а-я])стип(?![а-я])", "стинг", text)
    text = re.sub(r"\bстинг[\s_]*сбер\b", "стинг сбер", text)
    text = re.sub(r"(?<![а-я])сти(?:[\s_]+(?:сбер|альфа|втб|сб))?(?![а-я])", "стинг", text)
    text = re.sub(r"\bпрайм\b", "прессбук", text)
    text = re.sub(r"(?<![а-я])пб(?:[\s_]+(?:альфа|сбер|втб))?(?![а-я])", "прессбук", text)
    text = re.sub(r"(?<![а-я])пр[её]+?ссбук(?![а-я])", "прессбук", text)
    text = re.sub(r"(?<![а-я])пе?рссбук(?![а-я])", "прессбук", text)
    text = re.sub(r"(?<![а-я])пип(?!л)(?:[\s_]*крафт)?(?:[\s_]+(?:альфа|сбер|втб))?", "пипл крафт", text)
    text = re.sub(r"(?<![а-я])пипл(?:[\s_]+крафт)?[\s_]+(альфа|сбер|втб|сб)\b", r"пипл крафт \1", text)
    text = re.sub(r"\bпу[\s_]*(альфа|сбер|втб)\b", r"пипл крафт \1", text)
    text = re.sub(r"\bпу\b", "пиплкрафт", text)
    text = re.sub(r"\bпк[\s_]*(альфа|сбер|втб|аф)?\b", r"пипл крафт", text)
    text = re.sub(r"(?<![а-я])стройбизнесинвест(?![а-я])", "сби", text)
    text = re.sub(r"\bст[\s_]*(втб|альфа|сбер|бизнес)\b", r"ссс \1", text)
    text = re.sub(r"\bст\b", "ссс", text)
    text = re.sub(r"(?<![а-я])слот[\s_]*воркбрайт(?![а-я])", "вб", text)
    text = re.sub(r"(?<![а-я])воркбрайт(?![а-я])", "вб", text)
    text = re.sub(r"(?<![а-я])лайн(?:[\s_]+(?:альфа|сбер|втб|сб))?(?![а-я])", "лайн", text)
    text = re.sub(r"(?<![а-я])деливери(?:[\s_]+(?:альфа|сбер|втб|сб))?(?![а-я])", "деливери", text)
    text = re.sub(r"(?<![а-я])гетворк(?:[\s_]+(?:альфа|сбер|втб|сб))?(?![а-я])", "гетворк", text)
    return text

def _canonical_match_text(value):
    if value is None:
        return ""
    return _canonical_match_text_cached(_normalize_text(value))

def _compact_text(value):
    if value is None:
        return ""
    text = _canonical_match_text(value)
    return "".join(ch for ch in text if ch.isalnum())

@lru_cache(maxsize=65536)
def _text_tokens_cached(text):
    tokens = set()
    ignored = {"альфа", "сбер", "сби", "сти", "стинг", "ука", "реестр"}
    for token in re.split(r"[^0-9a-zа-я]+", text):
        if len(token) >= 4 and not token.isdigit() and token not in ignored:
            tokens.add(token)
    return frozenset(tokens)

def _text_tokens(value):
    canon = _canonical_match_text(value)
    return set(_text_tokens_cached(canon))

def _executor_tokens(value):
    canon = _canonical_match_text(value)
    return [t for t in re.split(r"[^0-9a-zа-я]+", canon) if len(t) >= 2]

def _executor_alias_keys(value):
    canon = _canonical_match_text(value)
    compact = "".join(ch for ch in canon if ch.isalnum())
    tokens = set(t for t in re.split(r"[^0-9a-zа-я]+", canon) if len(t) >= 2)
    aliases = {compact} if compact else set()
    if compact in {"мосальфа", "моссбер", "мосвтб"} or "мос" in tokens:
        aliases.add("мос")
    if (compact in {"пк", "пкальфа", "пксбер", "пксб"} or compact.startswith(("пиплкрафт", "пилпкрафт"))
        or {"пипл", "крафт"}.issubset(tokens) or {"пилп", "крафт"}.issubset(tokens)):
        aliases.add("пиплкрафт")
    if compact in {"пб", "пбальфа", "пбсбер", "пбсб"} or compact.startswith(("прессбук", "пресс", "прес")):
        aliases.add("прессбук")
    if compact.startswith(("ссс", "спецстафф", "спецстаф")):
        aliases.add("спецстаффсервис")
    if compact.startswith("воркбрайт") or compact == "вб" or "вб" in tokens:
        aliases.add("вб")
    if compact.startswith("лайн") or "лайн" in tokens:
        aliases.add("лайн")
    if compact.startswith("деливери") or "деливери" in tokens:
        aliases.add("деливери")
    if compact.startswith("гетворк") or "гетворк" in tokens:
        aliases.add("гетворк")
    if compact.startswith("ук") and len(compact) >= 3:
        aliases.add("ук")
    return aliases

def _executor_matches(master_executor, rsch_executor):
    left = _canonical_match_text(master_executor)
    right = _canonical_match_text(rsch_executor)
    if not left or not right:
        return False
    if left == right or _compact_text(left) == _compact_text(right):
        return True
    if _executor_alias_keys(left) & _executor_alias_keys(right):
        return True
    left_tokens = {t for t in _executor_tokens(left) if len(t) >= 2}
    right_tokens = {t for t in _executor_tokens(right) if len(t) >= 2}
    if not left_tokens or not right_tokens:
        return False
    return left_tokens.issubset(right_tokens) or right_tokens.issubset(left_tokens)

def _amount_equal(left, right):
    return abs(left - right) <= Decimal("0.01")

def _row_amount_matches(master, rsch):
    income_matches = master["income"] != 0 and _amount_equal(master["income"], rsch["income"])
    expense_matches = master["expense"] != 0 and _amount_equal(master["expense"], rsch["expense"])
    if income_matches or expense_matches:
        return True
    if master["income"] < 0 and _amount_equal(abs(master["income"]), rsch["expense"]):
        return True
    if master["expense"] < 0 and _amount_equal(abs(master["expense"]), rsch["income"]):
        return True
    return False

def _jaccard_similarity(left_tokens, right_tokens):
    if not left_tokens or not right_tokens:
        return 0.0
    inter = left_tokens & right_tokens
    union = left_tokens | right_tokens
    return len(inter) / len(union)

def _token_substring_match(master_tokens, cand_tokens):
    if not master_tokens or not cand_tokens:
        return False
    for mt in master_tokens:
        if len(mt) < 3: continue
        for ct in cand_tokens:
            if len(ct) < 3: continue
            if mt in ct or ct in mt:
                return True
    return False

def _score_pair(master, rsch):
    from difflib import SequenceMatcher
    if not _row_amount_matches(master, rsch):
        return -1.0
    score = 0.0
    if _executor_matches(master["executor"], rsch["executor"]):
        score += 50.0
    elif master["executor"] and rsch["executor"]:
        left_keys = _executor_alias_keys(master["executor"])
        right_keys = _executor_alias_keys(rsch["executor"])
        if left_keys & right_keys:
            score += 30.0
    master_norm = _normalize_text(master["customer"])
    master_canon = _canonical_match_text(master["customer"])
    master_tokens = _text_tokens(master["customer"])
    
    best_customer_score = 0.0
    for candidate in (rsch["customer"], rsch.get("contractor", ""), rsch.get("comment", "")):
        if not candidate:
            continue
        cand_norm = _normalize_text(candidate)
        cand_canon = _canonical_match_text(candidate)
        cand_tokens = _text_tokens(candidate)
        
        if master_canon and master_canon == cand_canon:
            best_customer_score = 50.0
            break
        if master_norm and cand_norm and (master_norm in cand_norm or cand_norm in master_norm):
            best_customer_score = 45.0
            continue
        mast_comp = _compact_text(master["customer"])
        cand_comp = _compact_text(candidate)
        if len(mast_comp) >= 6 and len(cand_comp) >= 6 and (mast_comp in cand_comp or cand_comp in mast_comp):
            best_customer_score = max(best_customer_score, 40.0)
            continue
        if _token_substring_match(master_tokens, cand_tokens):
            best_customer_score = max(best_customer_score, 38.0)
            continue
        if master_tokens and cand_tokens:
            master_text = " ".join(master_tokens)
            for ct in cand_tokens:
                if len(ct) >= 4 and ct in master_text:
                    best_customer_score = max(best_customer_score, 35.0)
                    break
        j = _jaccard_similarity(master_tokens, cand_tokens)
        if j >= 0.3:
            best_customer_score = max(best_customer_score, 35.0 * j)
        if master_norm and cand_norm:
            r = SequenceMatcher(None, master_norm, cand_norm).ratio()
            if r >= 0.6:
                best_customer_score = max(best_customer_score, 30.0 * r)
    score += best_customer_score
    return score

# ── Now test with actual data ───────────────────────────────

master = {
    "customer": "Су_90_СтройБизнесИнвест_Альфа_РТ_15_05_2026_436170 Каримбоев счет (1) скорректир",
    "executor": "СБИ Альфа",
    "income": Decimal("0"),
    "expense": Decimal("129880"),
}

print("=== EXECUTOR INFO ===")
print(f"Canon exec: '{_canonical_match_text(master['executor'])}'")
print(f"Exec tokens: {_executor_tokens(master['executor'])}")
print(f"Alias keys: {_executor_alias_keys(master['executor'])}")
print(f"Cust tokens: {sorted(_text_tokens(master['customer']))}")
print(f"Cust canon: '{_canonical_match_text(master['customer'])[:80]}'")

rwb = load_workbook('РСЧ/РСЧ_отчет_25.05.2026.xlsx', data_only=True)
ws = rwb['25.05.2026']
h = {}
for c in range(1, 20):
    v = ws.cell(1, c).value
    if v: h[str(v).strip()] = c

found = False
for r in range(2, ws.max_row + 1):
    expense_val = ws.cell(r, h['Расход']).value
    executor_val = str(ws.cell(r, h['ИСПОЛНИТЕЛЬ']).value or '').strip()
    customer_val = str(ws.cell(r, h['ЗАКАЗЧИК']).value or '').strip()
    contractor_val = str(ws.cell(r, h['Контрагент']).value or '').strip()
    comment_val = str(ws.cell(r, h['Комментарий']).value or '').strip()
    income_val = ws.cell(r, h['Приход']).value
    
    try: exp_f = float(expense_val) if expense_val is not None else 0
    except: exp_f = 0
    try: inc_f = float(income_val) if income_val is not None else 0
    except: inc_f = 0
    
    if abs(exp_f - 129880) < 0.01 or abs(inc_f - 129880) < 0.01:
        rsch = {
            "customer": customer_val,
            "executor": executor_val,
            "contractor": contractor_val,
            "comment": comment_val,
            "income": Decimal(str(income_val or 0)),
            "expense": Decimal(str(expense_val or 0)),
        }
        s = _score_pair(master, rsch)
        print(f"\nRSCH Row{r}: customer='{customer_val[:50]}' executor='{executor_val}'")
        print(f"  Score: {s:.1f}")
        print(f"  Exec matches: {_executor_matches(master['executor'], rsch['executor'])}")
        print(f"  Canon exec: '{_canonical_match_text(master['executor'])}' vs '{_canonical_match_text(rsch['executor'])}'")
        print(f"  Cust tokens R: {sorted(_text_tokens(rsch['customer']))}")
        found = True

if not found:
    print("\nNo matching amount found in RSCH for 129880!")
    print("All СБИ rows in RSCH 25.05:")
    for r in range(2, ws.max_row + 1):
        ev = str(ws.cell(r, h['ИСПОЛНИТЕЛЬ']).value or '').strip()
        if 'сби' in ev.lower():
            cv = str(ws.cell(r, h['ЗАКАЗЧИК']).value or '').strip()
            iv = ws.cell(r, h['Приход']).value
            ev2 = ws.cell(r, h['Расход']).value
            print(f"  R{r}: cust='{cv[:50]}' exec='{ev}' inc={iv} exp={ev2}")

rwb.close()
