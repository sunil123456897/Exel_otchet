"""RSCH report package — decomposed from rsch_report.py.

Layout:
    _format.py   — constants, pure utilities (formatting, text helpers, ...)
    _collect.py  — reading from workbooks (calamine, openpyxl)
    _template.py — template handling, style constants
    _build.py    — writing to Excel, public build_rsch_report entry point
"""

from ._build import build_rsch_report

__all__ = ["build_rsch_report"]
