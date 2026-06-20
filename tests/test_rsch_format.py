"""Tests for core.infra.rsch._format — RSCH helpers and formatters."""

from datetime import date, datetime
from decimal import Decimal

from core.infra.rsch._format import (
    _as_date,
    _cell_text_from_row,
    _clean_executor_name,
    _display_len,
    _excel_safe_text,
    _format_source_label,
    _is_account_optional_row,
    _is_problem_row,
    _is_rsch_sheet_title,
    _is_special_customer_label,
    _normalize_text,
    _pick_text,
    _to_decimal,
)


class TestNormalizeText:
    def test_none(self):
        assert _normalize_text(None) == ""

    def test_whitespace_collapsed(self):
        assert _normalize_text("  hello   world  ") == "hello world"

    def test_nbsp_replaced(self):
        assert _normalize_text("hello\xa0world") == "hello world"

    def test_lowercased(self):
        assert _normalize_text("HELLO") == "hello"


class TestIsRschSheetTitle:
    def test_valid_rsch(self):
        assert _is_rsch_sheet_title("РСЧ Иванов") is True

    def test_template_excluded(self):
        assert _is_rsch_sheet_title("шаблон РСЧ") is False

    def test_no_rsch_keyword(self):
        assert _is_rsch_sheet_title("Лист1") is False


class TestToDecimalRsch:
    def test_none(self):
        assert _to_decimal(None) == Decimal("0")

    def test_empty_string(self):
        assert _to_decimal("") == Decimal("0")

    def test_bool_true(self):
        assert _to_decimal(True) == Decimal("1")

    def test_bool_false(self):
        assert _to_decimal(False) == Decimal("0")

    def test_decimal_passthrough(self):
        assert _to_decimal(Decimal("3.14")) == Decimal("3.14")

    def test_int(self):
        assert _to_decimal(42) == Decimal("42")

    def test_float(self):
        assert _to_decimal(3.5) == Decimal("3.5")

    def test_string_with_comma(self):
        assert _to_decimal("1 234,56") == Decimal("1234.56")

    def test_invalid_raises(self):
        import pytest
        with pytest.raises(ValueError):
            _to_decimal("abc")


class TestAsDate:
    def test_datetime_input(self):
        dt = datetime(2024, 1, 15, 12, 30)
        assert _as_date(dt) == date(2024, 1, 15)

    def test_date_input(self):
        d = date(2024, 6, 1)
        assert _as_date(d) == d

    def test_string_dd_mm_yyyy(self):
        assert _as_date("15.01.2024") == date(2024, 1, 15)

    def test_string_dd_mm_yy(self):
        assert _as_date("15.01.24") == date(2024, 1, 15)

    def test_string_iso(self):
        assert _as_date("2024-06-15") == date(2024, 6, 15)

    def test_empty_string(self):
        assert _as_date("") is None
        assert _as_date("  ") is None

    def test_invalid_string(self):
        assert _as_date("not-a-date") is None

    def test_none(self):
        assert _as_date(None) is None

    def test_integer_returns_none(self):
        assert _as_date(12345) is None


class TestCleanExecutorName:
    def test_strip_rsch(self):
        assert _clean_executor_name("РСЧ Иванов") == "ИВАНОВ"

    def test_uppercase(self):
        assert _clean_executor_name("иванов") == "ИВАНОВ"

    def test_only_rsch(self):
        result = _clean_executor_name("рсч")
        assert result == "РСЧ"


class TestCellTextFromRow:
    def test_valid_column(self):
        row = ("a", "b", "c")
        assert _cell_text_from_row(row, 2) == "b"

    def test_none_value(self):
        row = ("a", None, "c")
        assert _cell_text_from_row(row, 2) == ""

    def test_zero_col_idx(self):
        assert _cell_text_from_row(("x",), 0) == ""

    def test_out_of_range(self):
        assert _cell_text_from_row(("x",), 5) == ""


class TestPickText:
    def test_primary_used(self):
        assert _pick_text("hello", "world") == "hello"

    def test_fallback_to_secondary(self):
        assert _pick_text("", "world") == "world"


class TestIsSpecialCustomerLabel:
    def test_tax(self):
        assert _is_special_customer_label("Налог на прибыль") is True

    def test_commission(self):
        assert _is_special_customer_label("Комиссия банка") is True

    def test_normal_customer(self):
        assert _is_special_customer_label("ООО Ромашка") is False


class TestIsAccountOptionalRow:
    def test_factoring_row(self):
        row = {"executor": "Факторинг", "customer": "", "contractor": "", "comment": ""}
        assert _is_account_optional_row(row) is True

    def test_normal_row(self):
        row = {"executor": "Иванов", "customer": "ООО", "contractor": "x", "comment": ""}
        assert _is_account_optional_row(row) is False


class TestIsProblemRow:
    def test_both_income_and_expense(self):
        row = {"income": 100, "expense": 50, "contractor": "c", "customer": "q", "executor": "e", "account": "a"}
        assert _is_problem_row(row) is True

    def test_no_customer(self):
        row = {"income": 100, "expense": 0, "contractor": "c", "customer": "", "executor": "e", "account": "a"}
        assert _is_problem_row(row) is True

    def test_no_executor(self):
        row = {"income": 100, "expense": 0, "contractor": "c", "customer": "q", "executor": "", "account": "a"}
        assert _is_problem_row(row) is True

    def test_zero_income_and_expense(self):
        row = {"income": 0, "expense": 0, "contractor": "c", "customer": "q", "executor": "e", "account": "a"}
        assert _is_problem_row(row) is True

    def test_normal_row(self):
        row = {"income": 100, "expense": 0, "contractor": "c", "customer": "q", "executor": "e", "account": "a"}
        assert _is_problem_row(row) is False

    def test_no_contractor_with_customer(self):
        row = {"income": 100, "expense": 0, "contractor": "", "customer": "ООО Ромашка", "executor": "e", "account": "a"}
        assert _is_problem_row(row) is True

    def test_no_account_non_optional(self):
        row = {"income": 100, "expense": 0, "contractor": "c", "customer": "q", "executor": "e", "account": ""}
        assert _is_problem_row(row) is True

    def test_getwork_customer_no_contractor(self):
        row = {"income": 100, "expense": 0, "contractor": "", "customer": "Гетворк", "executor": "e", "account": "a"}
        assert _is_problem_row(row) is False


class TestFormatSourceLabel:
    def test_format(self):
        result = _format_source_label("report.xlsx", "Sheet1", 5)
        assert result == "report.xlsx | Sheet1 | строка 5"


class TestDisplayLen:
    def test_none(self):
        assert _display_len(None) == 0

    def test_datetime(self):
        assert _display_len(datetime(2024, 1, 1)) == 10

    def test_decimal(self):
        length = _display_len(Decimal("1234.56"))
        assert length > 0

    def test_int(self):
        length = _display_len(12345)
        assert length > 0

    def test_string(self):
        assert _display_len("hello") == 5


class TestExcelSafeTextRsch:
    def test_formula_escaped(self):
        assert _excel_safe_text("=SUM(A1:A2)") == "'=SUM(A1:A2)"

    def test_plus_escaped(self):
        assert _excel_safe_text("+100") == "'+100"

    def test_minus_escaped(self):
        assert _excel_safe_text("-100") == "'-100"

    def test_at_escaped(self):
        assert _excel_safe_text("@SUM") == "'@SUM"

    def test_normal_text_unchanged(self):
        assert _excel_safe_text("Hello") == "Hello"

    def test_non_string_passthrough(self):
        assert _excel_safe_text(42) == 42
        assert _excel_safe_text(None) is None
