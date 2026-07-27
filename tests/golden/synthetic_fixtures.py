"""Stage 1 / MR-0103 — synthetic, PII-free input fixtures for golden tests.

Each function in this module builds an in-memory openpyxl Workbook that
mimics the SHAPE of a real input book (curator daily Excel), but uses
obviously-fake values:

* customer names: ``"Клиент А"``, ``"Клиент Б"`` …
* contractor names: ``"Подрядчик 1"``, …
* amounts: small round Decimal values that are easy to reason about.

The fixtures intentionally avoid any real employee, customer, contractor
or amount. They are deterministic (no random seeds needed) so two test
runs in different environments produce byte-identical input — and
therefore byte-identical output, which is the whole point of a golden.

Scenarios follow the 14 categories from TZ MR-0103. Each builder returns
a Workbook that can be saved to disk and fed to ``LogicService`` /
``MasterWriter``.

Note: we deliberately do NOT model the curator-of-the-day file format in
exhaustive detail. The point of MR-0103 is to lock the *behaviour* on a
representative input shape, not to mirror the real template byte-for-byte
(that is the job of the operator-side control-date check in MR-0102).
"""
from __future__ import annotations

from decimal import Decimal

import openpyxl
from openpyxl.styles import Font

# Public canonical headers used by every synthetic sheet. These mirror the
# field names of FinancialRowSchema so LogicService can ingest the sheet
# without aliasing gymnastics.
HEADERS = [
    "customer", "contractor", "amount", "total", "commission",
    "filters", "income", "expense",
]


def _new_sheet(title: str = "Сводка") -> tuple[openpyxl.Workbook, openpyxl.worksheet.worksheet.Worksheet]:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    ws.append(HEADERS)
    for c in range(1, len(HEADERS) + 1):
        ws.cell(row=1, column=c).font = Font(bold=True)
    return wb, ws


def _row(customer: str, contractor: str, amount: Decimal | float | int,
         total: Decimal | float | int | None = None,
         commission: Decimal | float | int = 0,
         filters: str = "",
         income: Decimal | float | int = 0,
         expense: Decimal | float | int = 0) -> list:
    """Build a single data row in HEADERS order."""
    if total is None:
        total = amount
    return [customer, contractor, amount, total, commission, filters, income, expense]


# ── 14 scenario builders ────────────────────────────────────────────────

def build_master_day() -> openpyxl.Workbook:
    """Scenario 1: Master report for a single day.

    Plain income + expense rows with absolute commission. No edge cases.
    """
    wb, ws = _new_sheet("17.04.2025")
    ws.append(_row("Клиент А", "Подрядчик 1", Decimal("1000.00"), Decimal("1000.00"),
                   Decimal("50.00")))
    ws.append(_row("Клиент Б", "Подрядчик 2", Decimal("2500.00"), Decimal("2500.00"),
                   Decimal("125.00")))
    ws.append(_row("Клиент В", "Подрядчик 1", Decimal("500.00"), Decimal("500.00"),
                   Decimal("25.00")))
    return wb


def build_master_period() -> openpyxl.Workbook:
    """Scenario 2: Master for a period (multiple dates as separate sheets)."""
    wb = openpyxl.Workbook()
    for i, date in enumerate(["17.04.2025", "18.04.2025", "21.04.2025"]):
        if i == 0:
            ws = wb.active
            ws.title = date
        else:
            ws = wb.create_sheet(date)
        ws.append(HEADERS)
        ws.append(_row("Клиент А", "Подрядчик 1", Decimal(f"{1000 + i*100}.00")))
        ws.append(_row("Клиент Б", "Подрядчик 2", Decimal(f"{2000 + i*100}.00")))
    return wb


def build_master_all_dates() -> openpyxl.Workbook:
    """Scenario 3: Master covering many dates (one row per date per customer)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "All"
    ws.append(HEADERS + ["date"])
    for d in ["17.04.2025", "18.04.2025", "21.04.2025", "22.04.2025", "23.04.2025"]:
        ws.append(_row("Клиент А", "Подрядчик 1", Decimal("100.00")) + [d])
    return wb


def build_curator_report() -> openpyxl.Workbook:
    """Scenario 4: A single curator's report."""
    wb, ws = _new_sheet("Куратор 1")
    for i in range(5):
        ws.append(_row(f"Клиент {chr(65 + i)}", "Подрядчик 1",
                       Decimal(f"{(i + 1) * 100}.00")))
    return wb


def build_rsch_day() -> openpyxl.Workbook:
    """Scenario 5: РСЧ for a single day."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "РСЧ 17.04.2025"
    ws.append(["customer", "amount", "commission", "filters"])
    ws.append(["Клиент А", Decimal("1000.00"), Decimal("50.00"), "платёж"])
    ws.append(["Клиент Б", Decimal("2000.00"), Decimal("100.00"), "платёж"])
    return wb


def build_rsch_period() -> openpyxl.Workbook:
    """Scenario 6: РСЧ for a period."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "РСЧ период"
    ws.append(["date", "customer", "amount", "commission"])
    for d in ["17.04.2025", "18.04.2025"]:
        ws.append([d, "Клиент А", Decimal("500.00"), Decimal("25.00")])
        ws.append([d, "Клиент Б", Decimal("1500.00"), Decimal("75.00")])
    return wb


def build_reconciliation_no_diff() -> openpyxl.Workbook:
    """Scenario 7: Reconciliation where Master and РСЧ agree exactly."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Сверка"
    ws.append(["customer", "amount_master", "amount_rsch", "diff"])
    ws.append(["Клиент А", Decimal("1000.00"), Decimal("1000.00"), Decimal("0.00")])
    ws.append(["Клиент Б", Decimal("2000.00"), Decimal("2000.00"), Decimal("0.00")])
    return wb


def build_reconciliation_with_diff() -> openpyxl.Workbook:
    """Scenario 8: Reconciliation with controlled, known differences."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Сверка"
    ws.append(["customer", "amount_master", "amount_rsch", "diff"])
    ws.append(["Клиент А", Decimal("1000.00"), Decimal("990.00"), Decimal("10.00")])
    ws.append(["Клиент Б", Decimal("2000.00"), Decimal("2000.00"), Decimal("0.00")])
    return wb


def build_returns() -> openpyxl.Workbook:
    """Scenario 9: Returns (negative amounts)."""
    wb, ws = _new_sheet("Возвраты")
    ws.append(_row("Клиент А", "Подрядчик 1", Decimal("-500.00"),
                   Decimal("-500.00"), Decimal("0.00"), "возврат"))
    ws.append(_row("Клиент Б", "Подрядчик 2", Decimal("1000.00")))
    return wb


def build_currency() -> openpyxl.Workbook:
    """Scenario 10: Currency fields populated."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Валютные"
    ws.append(["customer", "amount", "currency", "exchange_rate", "currency_amount"])
    ws.append(["Клиент А", Decimal("100.00"), "USD", Decimal("90.00"), Decimal("9000.00")])
    ws.append(["Клиент Б", Decimal("200.00"), "EUR", Decimal("100.00"), Decimal("20000.00")])
    return wb


def build_transit_obligations() -> openpyxl.Workbook:
    """Scenario 11: Transit obligations present."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Транзит"
    ws.append(["customer", "amount", "transit_obligation", "filters"])
    ws.append(["Клиент А", Decimal("1000.00"), Decimal("200.00"), "транзит"])
    ws.append(["Клиент Б", Decimal("500.00"), Decimal("0.00"), "платёж"])
    return wb


def build_duplicates() -> openpyxl.Workbook:
    """Scenario 12: Duplicate + ambiguous matches."""
    wb, ws = _new_sheet("Дубли")
    # Identical row repeated — duplicate detection should flag this.
    for _ in range(2):
        ws.append(_row("Клиент А", "Подрядчик 1", Decimal("1000.00")))
    # Near-duplicate (different amount) — ambiguous.
    ws.append(_row("Клиент А", "Подрядчик 1", Decimal("1100.00")))
    return wb


def build_formulas_and_links() -> openpyxl.Workbook:
    """Scenario 13: Formulas and hyperlinks present.

    The point of this scenario is to ensure formulas survive the
    consolidation pipeline (they should NOT be replaced by cached values).
    """
    wb, ws = _new_sheet("Формулы")
    ws.append(_row("Клиент А", "Подрядчик 1", Decimal("100.00")))
    # Add a formula cell that references another cell.
    ws["F2"] = "=E2*0.1"  # commission as 10% of total
    ws["F3"] = "=E2+E3"
    # Add a hyperlink (without leaking any real URL).
    ws["A4"] = "документация"
    ws["A4"].hyperlink = "#Сводка!A1"
    return wb


def build_empty_partial() -> openpyxl.Workbook:
    """Scenario 14: Empty + partially-filled rows.

    A common real-world shape: header followed by some empty rows then
    real data then more blanks. The pipeline must not silently drop the
    real rows nor crash on the blanks.
    """
    wb, ws = _new_sheet("Частичный")
    ws.append(_row("Клиент А", "Подрядчик 1", Decimal("500.00")))
    ws.append(_row("", "", Decimal("0.00")))  # blank
    ws.append(_row("Клиент Б", "Подрядчик 2", Decimal("1500.00")))
    ws.append([])  # fully empty row
    ws.append(_row("Клиент В", "Подрядчик 1", Decimal("300.00")))
    return wb


# Registry for parameterized tests. Each entry maps a stable id to a builder.
# Order matches TZ MR-0103 numbering.
SCENARIOS: dict[str, callable] = {
    "master_day": build_master_day,
    "master_period": build_master_period,
    "master_all_dates": build_master_all_dates,
    "curator_report": build_curator_report,
    "rsch_day": build_rsch_day,
    "rsch_period": build_rsch_period,
    "reconciliation_no_diff": build_reconciliation_no_diff,
    "reconciliation_with_diff": build_reconciliation_with_diff,
    "returns": build_returns,
    "currency": build_currency,
    "transit_obligations": build_transit_obligations,
    "duplicates": build_duplicates,
    "formulas_and_links": build_formulas_and_links,
    "empty_partial": build_empty_partial,
}


def save_all(target_dir: openpyxl.worksheet.worksheet.Path | str) -> dict[str, str]:
    """Persist every scenario as ``<id>.xlsx`` under *target_dir*.

    Returns ``{scenario_id: path}``. Used by the golden-snapshot bootstrap
    test the first time the suite is run.
    """
    from pathlib import Path
    out: dict[str, str] = {}
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    for sid, builder in SCENARIOS.items():
        path = target / f"{sid}.xlsx"
        builder().save(path)
        out[sid] = str(path)
    return out
