"""Characterization (golden) tests for the reconciliation fuzzy matching.

``_canonical_match_text`` is the most fragile code in the project: ~35
order-dependent regex rewrites that fold many real-world executor/customer
spellings onto canonical forms (the order is SEMANTIC — e.g. the "ука"
catch-all must run before the "тск"/"ст" rules, and "тск"→"анотехникум"
interacts with "ст"→"ссс"). Any refactor (e.g. tabling the rules) can shift
a result by accident, and because matching drives the reconciliation
verdicts, a silent shift means rows flip between "совпало" and "проверить".

These tests pin the CURRENT behaviour on a representative corpus (one input
per rule family + edge cases) so a refactor is safe IFF every output below
stays byte-identical. They do not change any logic — they freeze it.

To regenerate after an INTENTIONAL behaviour change, re-run the corpus
through the functions and update EXPECTED here (with review).
"""
from __future__ import annotations

import pytest

from core.infra.reconciliation._utils import (
    _canonical_match_text,
    _compact_text,
    _executor_alias_keys,
    _text_tokens,
)

# (raw input, expected canonical text, expected alias-key set)
CORPUS: list[tuple[str, str, set[str]]] = [
    # ── УК Альянс family → "ука" ────────────────────────────────
    ("УК Альянс", "ука", {"ук", "ука"}),
    ("УКАльянс", "ука", {"ук", "ука"}),
    ("УК А", "ука", {"ук", "ука"}),
    ("УКА_Альфа", "ука", {"ук", "ука"}),
    ("УКА_Сбер", "ука", {"ук", "ука"}),
    ("УКА_ВТБ", "ука", {"ук", "ука"}),
    ("УК_ВТБ", "ука втб", {"ук", "укавтб"}),
    ("УК_Альфа", "ука альфа", {"ук", "укаальфа"}),
    ("УК Аф", "ука", {"ук", "ука"}),
    ("УК Альфа", "ука альфа", {"ук", "укаальфа"}),
    ("УК Сбер", "ука сбер", {"ук", "укасбер"}),
    ("УК ВТБ", "ука втб", {"ук", "укавтб"}),
    ("УКАлинс", "ука", {"ук", "ука"}),  # common typo
    ("Ул альянс", "ука", {"ук", "ука"}),
    ("Сбер_РН", "ука", {"ук", "ука"}),  # documented synonym (Sber settlement)
    # ── Tinkoff → "тина" ────────────────────────────────────────
    ("Тина", "тина", {"тина"}),
    ("Тинадар", "тина", {"тина"}),
    ("Тина Сбер", "тина", {"тина"}),
    ("Тина бизнес", "тина", {"тина"}),
    # ── Billtrade → "биллтрейд" ─────────────────────────────────
    ("Билл", "биллтрейд", {"биллтрейд"}),
    ("Билтрейд", "биллтрейд", {"биллтрейд"}),
    ("Биллтрейд", "биллтрейд", {"биллтрейд"}),
    # ── АНО Техникум → "анотехникум" ────────────────────────────
    ("АНО ТСК", "анотехникум", {"анотехникум"}),
    ("АНО ТЕХНИКУМ", "анотехникум", {"анотехникум"}),
    ("ТСК", "анотехникум", {"анотехникум"}),
    ("ТСК Сбер", "анотехникум", {"анотехникум"}),
    ("ТСК Альфа", "анотехникум", {"анотехникум"}),
    # ── СБ Защита → "сбзащита" ──────────────────────────────────
    ("СБ Защита", "сбзащита", {"сбзащита"}),
    ("Защита РРБ", "сбзащита", {"сбзащита"}),
    # ── Стинг → "стинг" ─────────────────────────────────────────
    ("Стип", "стинг", {"стинг"}),
    ("СтипСбер", "стинг", {"стинг"}),
    ("Стинг", "стинг", {"стинг"}),
    ("СТИ Сбер", "стинг", {"стинг"}),
    ("СТИ Альфа", "стинг", {"стинг"}),
    ("Стинг Сбер", "стинг сбер", {"стингсбер"}),
    # ── Прайм / Прессбук → "прессбук" ───────────────────────────
    ("Прайм", "прессбук", {"прессбук"}),
    ("ПБ", "прессбук", {"прессбук"}),
    ("ПБ Альфа", "прессбук", {"прессбук"}),
    ("преессбук", "прессбук", {"прессбук"}),  # typo
    ("прссбук", "прессбук", {"прессбук"}),  # typo
    ("перссбук", "прессбук", {"прессбук"}),  # typo
    ("прессбук", "прессбук", {"прессбук"}),
    # ── Пиплкрафт → "пипл крафт" ────────────────────────────────
    ("Пип", "пипл крафт", {"пиплкрафт"}),
    ("ПипКрафт", "пипл крафт", {"пиплкрафт"}),
    ("Пипл Сбер", "пипл крафт сбер", {"пиплкрафт", "пиплкрафтсбер"}),
    ("Пип крафт Альфа", "пипл крафт", {"пиплкрафт"}),
    ("Пипл сбер", "пипл крафт сбер", {"пиплкрафт", "пиплкрафтсбер"}),
    ("ПУ", "пиплкрафт", {"пиплкрафт"}),
    ("ПУ альфа", "пипл крафт альфа", {"пиплкрафт", "пиплкрафтальфа"}),
    ("ПК", "пипл крафт", {"пиплкрафт"}),
    ("ПК альфа", "пипл крафт", {"пиплкрафт"}),
    # ── СБИ / ССС ───────────────────────────────────────────────
    ("СтройБизнесИнвест", "сби", {"сби"}),
    ("СТ", "ссс", {"спецстаффсервис", "ссс"}),
    ("СТ втб", "ссс втб", {"спецстаффсервис", "сссвтб"}),
    ("СТ бизнес", "ссс бизнес", {"спецстаффсервис", "сссбизнес"}),
    # ── WorkBright → "вб" ───────────────────────────────────────
    ("Слот ВоркБрайт", "вб", {"вб"}),
    ("ВоркБрайт", "вб", {"вб"}),
    # ── ЛАЙН / ДЕЛИВЕРИ / ГЕТВОРК (abbreviations kept) ──────────
    ("ЛАЙН", "лайн", {"лайн"}),
    ("ЛАЙН альфа", "лайн", {"лайн"}),
    ("ДЕЛИВЕРИ", "деливери", {"деливери"}),
    ("ДЕЛИВЕРИ сбер", "деливери", {"деливери"}),
    ("ГЕТВОРК", "гетворк", {"гетворк"}),
    ("ГЕТВОРК втб", "гетворк", {"гетворк"}),
    # ── latin → cyrillic ────────────────────────────────────────
    ("Gabriel", "габриэль", {"габриэль"}),
    # ── ordinary names: normalise only, no rewrite ──────────────
    ("ООО Ромашка", "ооо ромашка", {"оооромашка"}),
    ("ИП Иванов", "ип иванов", {"ипиванов"}),
    ("Гетворк Мерч", "гетворк мерч", {"гетворк", "гетворкмерч"}),
    ("гетворк анкор", "гетворк анкор", {"гетворк", "гетворканкор"}),
]


@pytest.mark.parametrize(
    "raw, expected_canonical, _",
    CORPUS,
    ids=[c[0] for c in CORPUS],
)
def test_canonical_match_is_stable(raw: str, expected_canonical: str, _) -> None:
    """The canonical form of every corpus input must not drift."""
    assert _canonical_match_text(raw) == expected_canonical


@pytest.mark.parametrize(
    "raw, _, expected_aliases",
    CORPUS,
    ids=[c[0] for c in CORPUS],
)
def test_executor_alias_keys_are_stable(raw: str, _, expected_aliases: set[str]) -> None:
    """The alias-key set of every corpus input must not drift."""
    assert _executor_alias_keys(raw) == expected_aliases


# ── derived helpers built on the canonical form ───────────────────────


def test_compact_text_strips_non_alnum() -> None:
    assert _compact_text("УК_Альфа") == "укаальфа"
    assert _compact_text("Пипл Сбер") == "пиплкрафтсбер"


def test_text_tokens_drops_short_and_stop_tokens() -> None:
    # "ук"/"сбер" semantics aside, tokens <4 chars are dropped by the helper.
    tokens = _text_tokens("гетворк анкор мерч")
    assert "гетворк" in tokens and "анкор" in tokens and "мерч" in tokens


# ── intent documentation (the WHY behind a few surprising folds) ──────


def test_sber_rn_is_uka_synonym() -> None:
    # Documented business rule: "Сбер_РН" is УК Альянс routed via a Sber
    # settlement account — it must fold to "ука", not stay "сбер рн".
    assert _canonical_match_text("Сбер_РН") == "ука"


def test_tsk_bank_suffix_still_folds_to_anotekhnikum() -> None:
    # Order-dependent: the ТСК rule (with optional bank suffix) must run so
    # that "ТСК Сбер" → "анотехникум", not leak the bank token.
    assert _canonical_match_text("ТСК Сбер") == "анотехникум"
