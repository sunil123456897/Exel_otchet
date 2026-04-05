"""Тесты для ExcelStyles."""
import pytest
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from core.infra.export_styles import ExcelStyles


class TestExcelStyles:
    """Тесты создания и настройки стилей Excel."""

    def test_init_creates_all_fills(self):
        st = ExcelStyles()
        assert isinstance(st.fill_header, PatternFill)
        assert isinstance(st.fill_odd, PatternFill)
        assert isinstance(st.fill_even, PatternFill)
        assert isinstance(st.fill_income, PatternFill)
        assert isinstance(st.fill_expense, PatternFill)
        assert isinstance(st.fill_total, PatternFill)
        assert isinstance(st.fill_warning, PatternFill)

    def test_init_creates_all_fonts(self):
        st = ExcelStyles()
        assert isinstance(st.font_header, Font)
        assert isinstance(st.font_standard, Font)
        assert isinstance(st.font_bold, Font)
        assert isinstance(st.font_income, Font)
        assert isinstance(st.font_expense, Font)
        assert isinstance(st.font_total, Font)

    def test_init_creates_borders(self):
        st = ExcelStyles()
        assert isinstance(st.border_thin, Border)
        assert isinstance(st.border_medium, Border)

    def test_init_creates_alignments(self):
        st = ExcelStyles()
        assert isinstance(st.align_center, Alignment)
        assert isinstance(st.align_left, Alignment)
        assert isinstance(st.align_right, Alignment)

    def test_header_fill_color(self):
        st = ExcelStyles()
        assert st.fill_header.start_color.rgb == "001F4E79"  # openpyxl adds 00 prefix

    def test_income_fill_color(self):
        st = ExcelStyles()
        assert st.fill_income.start_color.rgb == "00C6EFCE"

    def test_expense_fill_color(self):
        st = ExcelStyles()
        assert st.fill_expense.start_color.rgb == "00FFC7CE"

    def test_warning_fill_color(self):
        st = ExcelStyles()
        assert st.fill_warning.start_color.rgb == "00FFFF0000"

    def test_header_font_is_bold(self):
        st = ExcelStyles()
        assert st.font_header.bold is True

    def test_header_font_is_white(self):
        st = ExcelStyles()
        assert st.font_header.color.rgb == "00FFFFFF"

    def test_standard_font_size(self):
        st = ExcelStyles()
        assert st.font_standard.size == 10

    def test_total_font_is_bold(self):
        st = ExcelStyles()
        assert st.font_total.bold is True

    def test_income_font_is_green(self):
        st = ExcelStyles()
        assert st.font_income.color.rgb == "00006100"

    def test_expense_font_is_red(self):
        st = ExcelStyles()
        assert st.font_expense.color.rgb == "009C0006"

    def test_align_center_wrap(self):
        st = ExcelStyles()
        assert st.align_center.horizontal == 'center'
        assert st.align_center.wrap_text is True

    def test_align_left(self):
        st = ExcelStyles()
        assert st.align_left.horizontal == 'left'
        assert st.align_left.wrap_text is True

    def test_align_right(self):
        st = ExcelStyles()
        assert st.align_right.horizontal == 'right'

    def test_border_thin_has_all_sides(self):
        st = ExcelStyles()
        assert st.border_thin.left.style == 'thin'
        assert st.border_thin.right.style == 'thin'
        assert st.border_thin.top.style == 'thin'
        assert st.border_thin.bottom.style == 'thin'

    def test_border_medium_has_all_sides(self):
        st = ExcelStyles()
        assert st.border_medium.left.style == 'medium'
        assert st.border_medium.right.style == 'medium'
        assert st.border_medium.top.style == 'medium'
        assert st.border_medium.bottom.style == 'medium'

    def test_color_constants(self):
        st = ExcelStyles()
        assert st.clr_header_bg == "1F4E79"
        assert st.clr_header_text == "FFFFFF"
        assert st.clr_row_odd == "F2F2F2"
        assert st.clr_row_even == "FFFFFF"
        assert st.clr_income_bg == "C6EFCE"
        assert st.clr_income_text == "006100"
        assert st.clr_expense_bg == "FFC7CE"
        assert st.clr_expense_text == "9C0006"
        assert st.clr_total_bg == "D9E1F2"
        assert st.clr_warning_bg == "FFFF0000"

    def test_fill_types_are_solid(self):
        st = ExcelStyles()
        fills = [st.fill_header, st.fill_odd, st.fill_even, st.fill_income,
                 st.fill_expense, st.fill_total, st.fill_warning]
        for fill in fills:
            assert fill.fill_type == 'solid'

    def test_odd_even_different(self):
        """Чётные и нечётные строки должны иметь разные цвета."""
        st = ExcelStyles()
        assert st.fill_odd.start_color.rgb != st.fill_even.start_color.rgb
