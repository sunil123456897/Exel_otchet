import logging
from typing import List, Dict, Any, Set
from openpyxl.utils import get_column_letter
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

        self.fill_header = PatternFill(
            start_color=self.clr_header_bg,
            end_color=self.clr_header_bg,
            fill_type="solid",
        )
        self.fill_odd = PatternFill(
            start_color=self.clr_row_odd, end_color=self.clr_row_odd, fill_type="solid"
        )
        self.fill_even = PatternFill(
            start_color=self.clr_row_even,
            end_color=self.clr_row_even,
            fill_type="solid",
        )
        self.fill_income = PatternFill(
            start_color=self.clr_income_bg,
            end_color=self.clr_income_bg,
            fill_type="solid",
        )
        self.fill_expense = PatternFill(
            start_color=self.clr_expense_bg,
            end_color=self.clr_expense_bg,
            fill_type="solid",
        )
        self.fill_total = PatternFill(
            start_color=self.clr_total_bg,
            end_color=self.clr_total_bg,
            fill_type="solid",
        )
        self.fill_warning = PatternFill(
            start_color=self.clr_warning_bg,
            end_color=self.clr_warning_bg,
            fill_type="solid",
        )

        self.font_header = Font(color=self.clr_header_text, bold=True, size=11)
        self.font_standard = Font(size=10)
        self.font_bold = Font(bold=True, size=10)
        self.font_income = Font(color=self.clr_income_text, bold=True)
        self.font_expense = Font(color=self.clr_expense_text, bold=True)
        self.font_total = Font(bold=True, size=11)

        thin = Side(style="thin", color="000000")
        self.border_thin = Border(left=thin, right=thin, top=thin, bottom=thin)
        self.border_medium = Border(
            left=Side(style="medium"),
            right=Side(style="medium"),
            top=Side(style="medium"),
            bottom=Side(style="medium"),
        )
        self.align_center = Alignment(
            horizontal="center", vertical="center", wrap_text=True
        )
        self.align_left = Alignment(
            horizontal="left", vertical="center", wrap_text=True
        )
        self.align_right = Alignment(horizontal="right", vertical="center")


logger = logging.getLogger(__name__)


def detect_header_columns(ws) -> tuple:
    num_kw = ["приход", "расход", "комиссия", "итог", "посредник"]
    cols = {kw: -1 for kw in num_kw}
    num_indices = set()
    percent_broker_cols = set()

    for i, cell in enumerate(ws[1], 1):
        val = str(cell.value or "").lower()
        if any(kw in val for kw in num_kw):
            num_indices.add(i)
        for kw in num_kw:
            if kw in val:
                if kw == "комиссия" and "посред" in val:
                    continue
                cols[kw] = i
        if val == "% посредника" or val.startswith("% посредник"):
            percent_broker_cols.add(i)

    return cols, num_indices, percent_broker_cols


def apply_cell_styling(
    ws, rows_data, warning_rows, cols, num_indices, percent_broker_cols, st: ExcelStyles
):
    fill_yellow = PatternFill(patternType="solid", fgColor="FFFF00")

    for r_idx, row_cells in enumerate(ws.iter_rows(min_row=2, max_row=ws.max_row)):
        is_warning = (r_idx + 2) in warning_rows
        fill_row = st.fill_odd if (r_idx + 1) % 2 == 1 else st.fill_even

        i_val = (
            float(row_cells[cols["приход"] - 1].value or 0) if cols["приход"] > 0 else 0
        )
        e_val = (
            float(row_cells[cols["расход"] - 1].value or 0) if cols["расход"] > 0 else 0
        )
        t_val = float(row_cells[cols["итог"] - 1].value or 0) if cols["итог"] > 0 else 0
        c_val = (
            abs(float(row_cells[cols["комиссия"] - 1].value or 0))
            if cols["комиссия"] > 0
            else 0
        )

        is_critical = rows_data[r_idx].get("is_critical", False)
        fill_critical = PatternFill(patternType="solid", fgColor="FF9999")

        expected_total_no_comm = i_val - e_val
        has_money = abs(i_val) > 0.02 or abs(e_val) > 0.02
        
        is_math_err = False
        if has_money:
            if abs(t_val) < 0.02:
                # Total is 0 / empty
                is_math_err = True
            elif abs(c_val) < 0.02 and abs(t_val - expected_total_no_comm) > 0.02:
                # Commission is 0, but total doesn't match income-expense (forgot to write commission)
                is_math_err = True

        for c_idx, cell in enumerate(row_cells, 1):
            cell.border = st.border_thin

            if is_critical:
                cell.fill = fill_critical
            elif is_math_err:
                cell.fill = fill_yellow
            else:
                cell.fill = fill_row
            cell.font = st.font_standard

            if c_idx in num_indices:
                format_numeric_cell(
                    cell, c_idx, cols, ws, percent_broker_cols, is_warning, is_critical, st
                )
            else:
                cell.alignment = st.align_left
                if is_warning and not is_critical and c_idx == 2:
                    cell.fill = st.fill_warning


def format_numeric_cell(
    cell, c_idx, cols, ws, percent_broker_cols, is_warning, is_critical, st: ExcelStyles
):
    val = cell.value or 0

    if c_idx == cols["приход"] and isinstance(val, (int, float)) and val > 0.01:
        if not is_critical:
            cell.fill = st.fill_income
        cell.font = st.font_income
    elif c_idx == cols["расход"] and isinstance(val, (int, float)) and abs(val) > 0.01:
        if not is_critical:
            cell.fill = st.fill_expense
        cell.font = st.font_expense

    is_percent_err = False
    if c_idx in percent_broker_cols:
        try:
            v_float = float(val)
            if abs(v_float) <= 1.0:
                cell.value = v_float
            elif abs(v_float) <= 100.0:
                cell.value = v_float / 100.0
            else:
                is_percent_err = True
                cell.value = v_float
        except (ValueError, TypeError):
            is_percent_err = True
            cell.value = val

        if is_percent_err:
            cell.fill = st.fill_warning

    h = str(ws.cell(1, c_idx).value or "").lower()
    if "%" in h and "посред" in h:
        fmt = (
            "General" if is_percent_err and isinstance(cell.value, str) else "#,##0.00"
        )
        if not is_percent_err:
            fmt = "0.00%"
    elif "комиссия" in h:
        fmt = '0.00"%"'
    else:
        fmt = "#,##0.00"

    cell.alignment, cell.number_format = st.align_right, fmt

    if is_warning and not is_critical and c_idx == 2:
        cell.fill = st.fill_warning


def build_total_row(ws, num_indices, st: ExcelStyles):
    total_row = ws.max_row + 1
    total_label = ws.cell(total_row, 1, "ИТОГО:")
    total_label.font, total_label.fill, total_label.border = (
        st.font_total,
        st.fill_total,
        st.border_medium,
    )

    for c in range(1, ws.max_column + 1):
        if c not in num_indices:
            continue
        h = str(ws.cell(1, c).value or "").lower()
        if (
            any(kw in h for kw in ["приход", "расход", "итог", "посредник"])
            and "%" not in h
        ):
            let = get_column_letter(c)
            cell = ws.cell(total_row, c)
            cell.value = f"=SUM({let}2:{let}{total_row - 1})"
            cell.fill, cell.font, cell.border, cell.number_format = (
                st.fill_total,
                st.font_total,
                st.border_medium,
                "#,##0.00",
            )

    return total_row
