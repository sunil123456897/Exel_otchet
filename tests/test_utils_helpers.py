"""Tests for core.domain.utils_helpers — numeric parsing and text normalization."""

from decimal import Decimal

import pytest

from core.domain.utils_helpers import (
    NumericParsingError,
    normalize_text,
    to_decimal,
    to_decimal_percent,
)


class TestToDecimal:
    def test_none(self):
        assert to_decimal(None) == Decimal("0.00")

    def test_empty_string(self):
        assert to_decimal("") == Decimal("0.00")

    def test_nan_float(self):
        assert to_decimal(float("nan")) == Decimal("0.00")

    def test_int(self):
        assert to_decimal(42) == Decimal("42.00")

    def test_float(self):
        assert to_decimal(3.14) == Decimal("3.14")

    def test_decimal(self):
        assert to_decimal(Decimal("10.555")) == Decimal("10.56")

    def test_string_simple(self):
        assert to_decimal("100") == Decimal("100.00")

    def test_string_with_comma(self):
        assert to_decimal("1,234.56") == Decimal("1234.56")

    def test_european_format(self):
        assert to_decimal("1.234,56") == Decimal("1234.56")

    def test_multiple_commas_as_thousands(self):
        assert to_decimal("1,234,567") == Decimal("1234567.00")

    def test_single_comma_decimal(self):
        assert to_decimal("123,45") == Decimal("123.45")

    def test_dash_is_zero(self):
        assert to_decimal("-") == Decimal("0.00")

    def test_parentheses_negative(self):
        assert to_decimal("(100)") == Decimal("-100.00")

    def test_scientific_notation(self):
        result = to_decimal("1e2")
        assert result == Decimal("100.00")

    def test_nan_string_raises(self):
        with pytest.raises(NumericParsingError):
            to_decimal("nan")

    def test_null_string_raises(self):
        with pytest.raises(NumericParsingError):
            to_decimal("null")

    def test_ref_error_raises(self):
        with pytest.raises(NumericParsingError):
            to_decimal("#REF!")

    def test_value_error_raises(self):
        with pytest.raises(NumericParsingError):
            to_decimal("#VALUE!")

    def test_spaces_stripped(self):
        assert to_decimal("  100  ") == Decimal("100.00")

    def test_nbsp_stripped(self):
        assert to_decimal("1\xa0000") == Decimal("1000.00")

    def test_trailing_dots_stripped(self):
        assert to_decimal("100.") == Decimal("100.00")


class TestToDecimalPercent:
    def test_none(self):
        assert to_decimal_percent(None) == Decimal("0")

    def test_empty_string(self):
        assert to_decimal_percent("") == Decimal("0")

    def test_nan_float(self):
        assert to_decimal_percent(float("nan")) == Decimal("0")

    def test_int(self):
        assert to_decimal_percent(5) == Decimal("5")

    def test_float(self):
        assert to_decimal_percent(0.15) == Decimal("0.15")

    def test_decimal(self):
        assert to_decimal_percent(Decimal("0.10")) == Decimal("0.10")

    def test_percent_string_converts(self):
        result = to_decimal_percent("15%")
        assert result == Decimal("0.15")

    def test_small_percent(self):
        result = to_decimal_percent("0.5%")
        assert result == Decimal("0.5")

    def test_invalid_returns_zero(self):
        assert to_decimal_percent("abc") == Decimal("0")

    def test_comma_replaced(self):
        result = to_decimal_percent("3,5")
        assert result == Decimal("3.5")


class TestNormalizeText:
    def test_none(self):
        assert normalize_text(None) == ""

    def test_whitespace(self):
        assert normalize_text("  hello   world  ") == "hello world"

    def test_nbsp(self):
        assert normalize_text("a\xa0b") == "a b"

    def test_lowercased(self):
        assert normalize_text("HELLO") == "hello"
