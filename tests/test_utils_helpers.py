"""Расширенные тесты для utils_helpers.py — to_decimal, to_decimal_percent, open_path."""

import pytest
import os
import subprocess
import traceback
from decimal import Decimal
from unittest.mock import patch, MagicMock
from core.domain.utils_helpers import to_decimal, to_decimal_percent
from core.infra.utils import open_path


class TestToDecimal:
    """Тесты to_decimal — преобразование в Decimal."""

    def test_none_returns_zero(self):
        assert to_decimal(None) == Decimal("0.00")

    def test_empty_string_returns_zero(self):
        assert to_decimal("") == Decimal("0.00")

    def test_nan_float_returns_zero(self):
        import math

        assert to_decimal(float("nan")) == Decimal("0.00")

    def test_int_converts(self):
        assert to_decimal(42) == Decimal("42.00")

    def test_float_converts(self):
        assert to_decimal(3.14) == Decimal("3.14")

    def test_decimal_passthrough(self):
        assert to_decimal(Decimal("10.50")) == Decimal("10.50")

    def test_string_number(self):
        assert to_decimal("100") == Decimal("100.00")

    def test_string_decimal(self):
        assert to_decimal("99.99") == Decimal("99.99")

    def test_string_with_spaces(self):
        assert to_decimal("  123.45  ") == Decimal("123.45")

    def test_string_with_non_breaking_space(self):
        assert to_decimal("123\xa0456.78") == Decimal("123456.78")

    def test_comma_as_decimal(self):
        """Одна запятая — десятичный разделитель (RU формат)."""
        assert to_decimal("12,5") == Decimal("12.50")

    def test_comma_as_thousands(self):
        """Множество запятых — разделитель тысяч."""
        assert to_decimal("1,000,000") == Decimal("1000000.00")

    def test_mixed_comma_dot_comma_decimal(self):
        """1.000,50 — запятая как десятичный."""
        assert to_decimal("1.000,50") == Decimal("1000.50")

    def test_mixed_comma_dot_dot_decimal(self):
        """1,000.50 — точка как десятичный."""
        assert to_decimal("1,000.50") == Decimal("1000.50")

    def test_scientific_notation(self):
        assert to_decimal("1.5e2") == Decimal("150.00")

    def test_trailing_comma_stripped(self):
        assert to_decimal("100,") == Decimal("100.00")

    def test_trailing_dot_stripped(self):
        assert to_decimal("100.") == Decimal("100.00")

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError):
            to_decimal("not_a_number")

    def test_internal_numeric_error_preserves_original_traceback(self):
        with pytest.raises(ValueError) as exc_info:
            to_decimal("abc")

        to_decimal_frames = [
            frame.name
            for frame in traceback.extract_tb(exc_info.value.__traceback__)
            if frame.name == "to_decimal"
        ]
        assert to_decimal_frames == ["to_decimal"]

    def test_internal_decimal_error_chains_original_exception(self):
        with pytest.raises(ValueError) as exc_info:
            to_decimal("1e")

        assert exc_info.value.__cause__ is not None

    def test_nan_string_raises(self):
        with pytest.raises(ValueError):
            to_decimal("nan")

    def test_null_string_raises(self):
        with pytest.raises(ValueError):
            to_decimal("null")

    def test_error_string_raises(self):
        with pytest.raises(ValueError):
            to_decimal("error")

    def test_excel_error_n_a(self):
        with pytest.raises(ValueError):
            to_decimal("#N/A")

    def test_excel_error_ref(self):
        with pytest.raises(ValueError):
            to_decimal("#REF!")

    def test_rounding_half_up(self):
        """ROUND_HALF_UP: 2.555 → 2.56."""
        result = to_decimal("2.555")
        assert result == Decimal("2.56")

    def test_rounding_half_down(self):
        result = to_decimal("2.554")
        assert result == Decimal("2.55")

    def test_zero_returns_zero(self):
        assert to_decimal("0") == Decimal("0.00")

    def test_negative_number(self):
        assert to_decimal("-42.5") == Decimal("-42.50")

    def test_very_small_number(self):
        assert to_decimal("0.001") == Decimal("0.00")

    def test_very_large_number(self):
        assert to_decimal("999999999.99") == Decimal("999999999.99")

    def test_whitespace_only(self):
        assert to_decimal("   ") == Decimal("0.00")


class TestToDecimalPercent:
    """Тесты to_decimal_percent."""

    def test_none_returns_zero(self):
        assert to_decimal_percent(None) == Decimal("0")

    def test_empty_string_returns_zero(self):
        assert to_decimal_percent("") == Decimal("0")

    def test_nan_returns_zero(self):
        assert to_decimal_percent(float("nan")) == Decimal("0")

    def test_int_returns_decimal(self):
        assert to_decimal_percent(25) == Decimal("25")

    def test_float_returns_decimal(self):
        assert to_decimal_percent(0.25) == Decimal("0.25")

    def test_string_number(self):
        assert to_decimal_percent("15") == Decimal("15")

    def test_comma_to_dot(self):
        assert to_decimal_percent("12,5") == Decimal("12.5")

    def test_percent_value_gt_1_divided_by_100(self):
        """50% → 0.5."""
        result = to_decimal_percent("50%")
        assert result == Decimal("0.5")

    def test_percent_value_lt_1_not_divided(self):
        """0.25 — уже в долях, не делить."""
        result = to_decimal_percent("0.25")
        assert result == Decimal("0.25")

    def test_no_percent_sign_not_divided(self):
        result = to_decimal_percent("50")
        assert result == Decimal("50")

    def test_with_spaces(self):
        result = to_decimal_percent("  25%  ")
        assert result == Decimal("0.25")

    def test_invalid_returns_original(self):
        """Нечисловое значение — вернуть как есть."""
        result = to_decimal_percent("N/A")
        assert result == "N/A"

    def test_empty_after_clean_returns_original(self):
        result = to_decimal_percent("---")
        assert result == "---"


class TestOpenPath:
    """Тесты open_path."""

    @patch("core.infra.utils.platform")
    def test_windows_opens_file(self, mock_platform):
        mock_platform.system.return_value = "Windows"
        with patch("os.startfile") as mock_start:
            open_path("C:/test")
            mock_start.assert_called_once_with("C:/test")

    @patch("core.infra.utils.platform")
    def test_mac_opens_open(self, mock_platform):
        mock_platform.system.return_value = "Darwin"
        with patch("subprocess.run") as mock_run:
            open_path("/Users/test")
            mock_run.assert_called_once_with(["open", "/Users/test"], check=False)

    @patch("core.infra.utils.platform")
    def test_linux_opens_xdg(self, mock_platform):
        mock_platform.system.return_value = "Linux"
        with patch("subprocess.run") as mock_run:
            open_path("/home/test")
            mock_run.assert_called_once_with(["xdg-open", "/home/test"], check=False)
