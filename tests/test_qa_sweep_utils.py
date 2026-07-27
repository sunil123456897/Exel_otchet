"""Верификационные тесты для нетестированных утилит (QA-sweep Phase 2.3).

Логику НЕ меняем — эти тесты фиксируют текущее (задокументированное)
поведение функций, которые до сих пор не имели покрытия, чтобы:
1. подтвердить, что они работают в точности как задумано;
2. поймать регрессию при будущих правках.

Покрывает пункты D1 (utils_helpers), D2 (path_scrub), D4 (performance)
из docs/qa/qa-sweep-spec.md.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from core.app.performance import default_max_workers, resolve_max_workers
from core.domain.utils_helpers import (
    NumericParsingError,
    normalize_text,
    to_decimal,
    to_decimal_percent,
)
from core.infra.excel_safety import excel_safe_text
from core.shared.path_scrub import safe_file_label, scrub_path

# ---------------------------------------------------------------------------
# D1: core.domain.utils_helpers
# ---------------------------------------------------------------------------


class TestToDecimal:
    def test_none_and_empty_return_zero(self):
        assert to_decimal(None) == Decimal("0.00")
        assert to_decimal("") == Decimal("0.00")

    def test_nan_float_returns_zero(self):
        assert to_decimal(float("nan")) == Decimal("0.00")

    def test_int_and_float_quantized(self):
        assert to_decimal(5) == Decimal("5.00")
        assert to_decimal(3.14159) == Decimal("3.14")
        assert to_decimal(Decimal("7")) == Decimal("7.00")

    def test_string_with_comma_decimal_separator(self):
        # Русский формат «1 234,56»
        assert to_decimal("1 234,56") == Decimal("1234.56")

    def test_string_with_dot_decimal_separator(self):
        assert to_decimal("42.5") == Decimal("42.50")

    def test_accounting_parentheses_are_negative(self):
        # (100) → -100.00 (бухгалтерский формат отрицательных чисел)
        assert to_decimal("(100)") == Decimal("-100.00")
        assert to_decimal("( 50,25 )") == Decimal("-50.25")

    def test_known_invalid_tokens_raise(self):
        for bad in ("nan", "null", "none", "#n/a", "#ref!", "#value!", "error"):
            with pytest.raises(NumericParsingError):
                to_decimal(bad)

    def test_dash_only_is_zero(self):
        assert to_decimal("-") == Decimal("0.00")

    def test_silent_data_loss_on_garbage_raises(self):
        # Текст, который после чистки становится пустым и не содержит
        # цифр → NumericParsingError (защита от тихой потери данных).
        with pytest.raises(NumericParsingError):
            to_decimal("abc")

    def test_thousands_separator_both(self):
        # «1.234,56» → 1234.56 (европейский)
        assert to_decimal("1.234,56") == Decimal("1234.56")
        # «1,234.56» → 1234.56 (англо)
        assert to_decimal("1,234.56") == Decimal("1234.56")


class TestToDecimalPercent:
    def test_none_and_empty(self):
        assert to_decimal_percent(None) == Decimal("0")
        assert to_decimal_percent("") == Decimal("0")

    def test_plain_number(self):
        assert to_decimal_percent("10") == Decimal("10")

    def test_percent_above_one_divides(self):
        # «50%» → 50/100 = 0.5 (т.к. > 1 и есть %)
        assert to_decimal_percent("50%") == Decimal("0.5")

    def test_percent_below_one_unchanged(self):
        # «0.5%» → 0.5 (< 1, не делится)
        assert to_decimal_percent("0.5%") == Decimal("0.5")

    def test_comma_decimal(self):
        assert to_decimal_percent("12,5") == Decimal("12.5")

    def test_garbage_returns_zero(self):
        assert to_decimal_percent("abc") == Decimal("0")


class TestNormalizeText:
    def test_none_returns_empty(self):
        assert normalize_text(None) == ""

    def test_lowercases_and_collapses_whitespace(self):
        assert normalize_text("  Иван   Петров ") == "иван петров"

    def test_nbsp_replaced(self):
        assert normalize_text("иван\xa0петров") == "иван петров"


# ---------------------------------------------------------------------------
# D2: core.shared.path_scrub
# ---------------------------------------------------------------------------


class TestScrubPath:
    def test_redacts_windows_user(self):
        out = scrub_path(r"C:\Users\secretuser\file.xlsx")
        assert "secretuser" not in out
        assert r"C:\Users\<user>" in out

    def test_redacts_smb_share(self):
        out = scrub_path(r"\\fileserver\share$\reports\q.xlsx")
        assert "fileserver" not in out
        assert "share" not in out.replace("<share>", "")
        assert r"\\<server>\<share>" in out

    def test_plain_path_unchanged(self):
        out = scrub_path(r"E:\Dlia Dashi\report.xlsx")
        assert out == r"E:\Dlia Dashi\report.xlsx"

    def test_case_insensitive_user(self):
        out = scrub_path(r"c:\users\BOB\data")
        assert "BOB" not in out


class TestSafeFileLabel:
    def test_filename_with_hash_suffix(self):
        label = safe_file_label(r"C:\data\Отчёт.xlsx")
        assert label.startswith("Отчёт.xlsx#")
        # хэш-суффикс 10 hex-символов
        assert len(label.split("#")[1]) == 10

    def test_deterministic(self):
        # Один и тот же путь → одна и та же метка
        assert safe_file_label("/x/y.xlsx") == safe_file_label("/x/y.xlsx")

    def test_different_paths_different_labels(self):
        assert safe_file_label("/a/x.xlsx") != safe_file_label("/b/x.xlsx")


# ---------------------------------------------------------------------------
# D4: core.app.performance
# ---------------------------------------------------------------------------


class TestResolveMaxWorkers:
    def test_none_config_returns_default(self):
        assert resolve_max_workers(None) == default_max_workers()

    def test_empty_config_returns_default(self):
        assert resolve_max_workers({}) == default_max_workers()

    def test_explicit_value_clamped(self):
        cfg = {"performance": {"max_workers": 100}}
        assert resolve_max_workers(cfg) == 64  # верхний предел

    def test_zero_or_empty_falls_back(self):
        # 0 / None / "" → default (F-PERF-1 исправлен: раньше 0 давало 1,
        # теперь трактуется как «default», как и ожидает комментарий в
        # config.yaml «Empty keeps the current default»).
        assert resolve_max_workers({"performance": {"max_workers": 0}}) == default_max_workers()
        assert resolve_max_workers({"performance": {"max_workers": ""}}) == default_max_workers()
        assert resolve_max_workers({"performance": {"max_workers": None}}) == default_max_workers()

    def test_garbage_falls_back(self):
        assert resolve_max_workers({"performance": {"max_workers": "abc"}}) == default_max_workers()

    def test_minimum_is_one(self):
        assert resolve_max_workers({"performance": {"max_workers": -5}}) == 1

    def test_default_in_sane_range(self):
        d = default_max_workers()
        assert 1 <= d <= 32


# ---------------------------------------------------------------------------
# excel_safe_text — реальный кейс заказчицы (баг «РСЧ за период»)
# ---------------------------------------------------------------------------


class TestExcelSafeText:
    """Фикс бага «РСЧ за период грузит грузит и не выгружается».

    Корневая причина (выявлена по логу заказчицы 01.07.2026):
    openpyxl падал с IllegalCharacterError на значении
    «Диана М_Капстрой\\x07Изначальный реестр_47297 (71 400,00)» — внутри
    строки сидел XML-illegal control-символ (BEL). excel_safe_text ранее
    защищал только от formula injection (= + - @), но не от control-chars.
    Теперь вычищает и их.
    """

    def test_strips_illegal_control_chars(self):
        # Точный кейс заказчицы + типичные control-символы из 1С/банков.
        assert excel_safe_text("Диана М_Капстрой\x07реестр") == "Диана М_Капстройреестр"
        assert excel_safe_text("тест\x00null") == "тестnull"
        assert excel_safe_text("BEL\x08here") == "BELhere"
        assert excel_safe_text("US\x1fend") == "USend"

    def test_keeps_legal_whitespace(self):
        # Tab / newline / CR — легальны в OOXML, не вычищаются.
        assert excel_safe_text("строка\ts табом") == "строка\ts табом"
        assert excel_safe_text("первая\nвторая") == "первая\nвторая"

    def test_formula_injection_still_guarded(self):
        # Существующее поведение (= + - @ → апостроф) сохранено.
        assert excel_safe_text("=SUM(A1)") == "'=SUM(A1)"
        assert excel_safe_text("+5") == "'+5"
        assert excel_safe_text("@cmd") == "'@cmd"

    def test_normal_text_unchanged(self):
        assert excel_safe_text("нормальный текст") == "нормальный текст"
        assert excel_safe_text("Заказчик ООО Ромашка") == "Заказчик ООО Ромашка"

    def test_non_string_passthrough(self):
        from decimal import Decimal

        assert excel_safe_text(None) is None
        assert excel_safe_text(42) == 42
        assert excel_safe_text(Decimal("71.40")) == Decimal("71.40")

    def test_no_crash_when_appended_to_openpyxl(self):
        """End-to-end: значение, падавшее у заказчицы, теперь пишется."""
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        dirty = "Диана М_Капстрой\x07Изначальный реестр_47297 (71 400,00)"
        cleaned = excel_safe_text(dirty)
        ws.append([cleaned])  # не должно падать
        assert ws.cell(1, 1).value == "Диана М_КапстройИзначальный реестр_47297 (71 400,00)"
