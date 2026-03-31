from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

class ExcelStyles:
    def __init__(self):
        self.clr_header_bg = "1F4E79"
        self.clr_header_text = "FFFFFF"
        self.clr_row_odd = "F2F2F2"
        self.clr_row_even = "FFFFFF"
        self.clr_income_bg = "C6EFCE"
        self.clr_income_text = "006100"
        self.clr_expense_bg = "FFC7CE"
        self.clr_expense_text = "9C0006"
        self.clr_total_bg = "D9E1F2"
        self.clr_warning_bg = "FFFF0000"
        
        self.fill_header = PatternFill(start_color=self.clr_header_bg, end_color=self.clr_header_bg, fill_type="solid")
        self.fill_odd = PatternFill(start_color=self.clr_row_odd, end_color=self.clr_row_odd, fill_type="solid")
        self.fill_even = PatternFill(start_color=self.clr_row_even, end_color=self.clr_row_even, fill_type="solid")
        self.fill_income = PatternFill(start_color=self.clr_income_bg, end_color=self.clr_income_bg, fill_type="solid")
        self.fill_expense = PatternFill(start_color=self.clr_expense_bg, end_color=self.clr_expense_bg, fill_type="solid")
        self.fill_total = PatternFill(start_color=self.clr_total_bg, end_color=self.clr_total_bg, fill_type="solid")
        self.fill_warning = PatternFill(start_color=self.clr_warning_bg, end_color=self.clr_warning_bg, fill_type="solid")
        
        self.font_header = Font(color=self.clr_header_text, bold=True, size=11)
        self.font_standard = Font(size=10)
        self.font_bold = Font(bold=True, size=10)
        self.font_income = Font(color=self.clr_income_text, bold=True)
        self.font_expense = Font(color=self.clr_expense_text, bold=True)
        self.font_total = Font(bold=True, size=11)
        
        thin = Side(style='thin', color="000000")
        self.border_thin = Border(left=thin, right=thin, top=thin, bottom=thin)
        self.border_medium = Border(left=Side(style='medium'), right=Side(style='medium'), top=Side(style='medium'), bottom=Side(style='medium'))
        self.align_center = Alignment(horizontal='center', vertical='center', wrap_text=True)
        self.align_left = Alignment(horizontal='left', vertical='center', wrap_text=True)
        self.align_right = Alignment(horizontal='right', vertical='center')

