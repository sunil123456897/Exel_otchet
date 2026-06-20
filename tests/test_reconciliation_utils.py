"""Tests for core.infra.reconciliation._utils — text normalization and matching."""

from decimal import Decimal

import pytest

from core.infra.reconciliation._types import (
    MasterReconciliationRow,
    ReconciliationRow,
    RschReconciliationRow,
)
from core.infra.reconciliation._utils import (
    _canonical_match_text,
    _compact_text,
    _excel_safe_text,
    _executor_alias_keys,
    _executor_tokens,
    _is_excluded_customer,
    _is_excluded_master_filter,
    _is_excluded_master_header,
    _is_excluded_rsch_comment,
    _is_filter_header,
    _is_numeric_header,
    _is_percent_header,
    _is_total_row,
    _normalize_text,
    _row_id,
    _text_tokens,
    _to_decimal,
    _weak_customer_tokens,
)


class TestNormalizeText:
    def test_none(self):
        assert _normalize_text(None) == ""

    def test_whitespace(self):
        assert _normalize_text("  hello   world  ") == "hello world"

    def test_nbsp(self):
        assert _normalize_text("a\xa0b") == "a b"

    def test_yo_replaced(self):
        assert _normalize_text("ёжик") == "ежик"


class TestCanonicalMatchText:
    def test_uka_normalization(self):
        result = _canonical_match_text("УКАльянс")
        assert "ука" in result

    def test_billtrade_normalization(self):
        result = _canonical_match_text("Биллтрейд")
        assert "биллтрейд" in result

    def test_gabriel_translation(self):
        result = _canonical_match_text("Gabriel")
        assert "габриэль" in result

    def test_tina_normalization(self):
        result = _canonical_match_text("Тинадар")
        assert "тина" in result

    def test_prime_is_pressbook(self):
        result = _canonical_match_text("Прайм")
        assert "прессбук" in result

    def test_sting_normalization(self):
        result = _canonical_match_text("Стип")
        assert "стинг" in result

    def test_ano_technikum(self):
        result = _canonical_match_text("АНО ТСК")
        assert "анотехникум" in result

    def test_sb_protection(self):
        result = _canonical_match_text("СБ Защита")
        assert "сбзащита" in result

    def test_sber_rn(self):
        result = _canonical_match_text("Сбер РН")
        assert "ука" in result


class TestCompactText:
    def test_removes_non_alnum(self):
        result = _compact_text("hello - world!")
        assert result.isalnum()

    def test_preserves_content(self):
        result = _compact_text("abc 123")
        assert "abc" in result
        assert "123" in result


class TestTextTokens:
    def test_short_tokens_excluded(self):
        tokens = _text_tokens("ab cd efgh ijklm")
        assert "ab" not in tokens
        assert "cd" not in tokens
        assert "efgh" in tokens
        assert "ijklm" in tokens

    def test_digits_excluded(self):
        tokens = _text_tokens("12345 word hello")
        assert "12345" not in tokens

    def test_stopwords_excluded(self):
        tokens = _text_tokens("альфа сбер реестр тестовое")
        assert "альфа" not in tokens
        assert "сбер" not in tokens
        assert "реестр" not in tokens
        assert "тестовое" in tokens


class TestWeakCustomerTokens:
    def test_filters_additional_stopwords(self):
        tokens = _weak_customer_tokens("готово корр проект тестовое значение")
        assert "готово" not in tokens
        assert "корр" not in tokens
        assert "тестовое" in tokens


class TestExecutorTokens:
    def test_basic(self):
        tokens = _executor_tokens("Иванов Петр")
        assert "иванов" in tokens or any("иванов" in t for t in tokens)

    def test_short_tokens_kept(self):
        tokens = _executor_tokens("АБ ВГ")
        assert len(tokens) == 2


class TestExecutorAliasKeys:
    def test_pk_alias(self):
        aliases = _executor_alias_keys("ПК")
        assert "пиплкрафт" in aliases

    def test_pb_alias(self):
        aliases = _executor_alias_keys("ПБ")
        assert "прессбук" in aliases

    def test_sss_alias(self):
        aliases = _executor_alias_keys("Спецстаффсервис")
        assert "спецстаффсервис" in aliases

    def test_workbright_alias(self):
        aliases = _executor_alias_keys("ВоркБрайт")
        assert "вб" in aliases

    def test_mos_alias(self):
        aliases = _executor_alias_keys("МОС альфа")
        assert "мос" in aliases


class TestToDecimal:
    def test_none(self):
        assert _to_decimal(None) == Decimal("0")

    def test_empty(self):
        assert _to_decimal("") == Decimal("0")

    def test_bool(self):
        assert _to_decimal(True) == Decimal("1")
        assert _to_decimal(False) == Decimal("0")

    def test_decimal_passthrough(self):
        assert _to_decimal(Decimal("3.14")) == Decimal("3.14")

    def test_int(self):
        assert _to_decimal(42) == Decimal("42")

    def test_float(self):
        assert _to_decimal(3.5) == Decimal("3.5")

    def test_string_with_comma(self):
        assert _to_decimal("1 234,56") == Decimal("1234.56")

    def test_formula_returns_zero(self):
        assert _to_decimal("=SUM(A1:A2)") == Decimal("0")

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            _to_decimal("abc")


class TestIsTotalRow:
    def test_itogo(self):
        assert _is_total_row("ИТОГО") is True
        assert _is_total_row("итого:") is True
        assert _is_total_row("Итого за день") is True

    def test_not_total(self):
        assert _is_total_row("Иванов") is False


class TestExcelSafeText:
    def test_formula_escaped(self):
        assert _excel_safe_text("=SUM(A1)") == "'=SUM(A1)"

    def test_at_escaped(self):
        assert _excel_safe_text("@fn") == "'@fn"

    def test_normal(self):
        assert _excel_safe_text("hello") == "hello"

    def test_non_string(self):
        assert _excel_safe_text(42) == 42


class TestIsFilterHeader:
    def test_filter_variants(self):
        assert _is_filter_header("Фильтр") is True
        assert _is_filter_header("фильтры") is True
        assert _is_filter_header("filter") is True
        assert _is_filter_header("filters") is True

    def test_non_filter(self):
        assert _is_filter_header("Источник") is False


class TestIsExcludedMasterFilter:
    def test_excluded(self):
        assert _is_excluded_master_filter("доп сф") is True
        assert _is_excluded_master_filter("касса") is True
        assert _is_excluded_master_filter("посредник") is True

    def test_normal(self):
        assert _is_excluded_master_filter("Иванов") is False


class TestIsExcludedMasterHeader:
    def test_excluded(self):
        assert _is_excluded_master_header("отправка транзитных обязательств") is True
        assert _is_excluded_master_header("курс") is True
        assert _is_excluded_master_header("валюта") is True

    def test_normal(self):
        assert _is_excluded_master_header("ЗАКАЗЧИК") is False


class TestIsExcludedCustomer:
    def test_excluded(self):
        assert _is_excluded_customer("Налог") is True
        assert _is_excluded_customer("расход") is True
        assert _is_excluded_customer("% по депозиту") is True
        assert _is_excluded_customer("Комиссия") is True

    def test_normal(self):
        assert _is_excluded_customer("ООО Ромашка") is False


class TestIsExcludedRschComment:
    def test_excluded(self):
        assert _is_excluded_rsch_comment("перевод средств") is True

    def test_normal(self):
        assert _is_excluded_rsch_comment("оплата услуг") is False


class TestIsNumericHeader:
    def test_numeric_headers(self):
        assert _is_numeric_header("Приход") is True
        assert _is_numeric_header("Расход") is True
        assert _is_numeric_header("Комиссия") is True
        assert _is_numeric_header("ИТОГ") is True

    def test_non_numeric(self):
        assert _is_numeric_header("ЗАКАЗЧИК") is False


class TestIsPercentHeader:
    def test_percent(self):
        assert _is_percent_header("% посредника") is True

    def test_no_percent(self):
        assert _is_percent_header("Приход") is False


class TestRowId:
    def test_master_only(self):
        master = MasterReconciliationRow(
            values=[], source="src", source_link=None,
            customer="AAA", executor="BBB",
            income=Decimal("100"), expense=Decimal("0"),
        )
        row = ReconciliationRow(master=master, rsch=None, status="OK")
        rid = _row_id(row)
        assert "aaa" in rid
        assert "bbb" in rid

    def test_rsch_only(self):
        rsch = RschReconciliationRow(
            row_id="r1", executor="EXE", customer="CUST",
            contractor="CON", comment="", income=Decimal("50"),
            expense=Decimal("0"), source_link=None,
        )
        row = ReconciliationRow(master=None, rsch=rsch, status="REVIEW")
        rid = _row_id(row)
        assert "|" in rid

    def test_empty_row(self):
        row = ReconciliationRow(master=None, rsch=None, status="ERROR", reason="test")
        rid = _row_id(row)
        assert "status:" in rid
