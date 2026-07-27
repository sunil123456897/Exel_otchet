"""Tests for RSCH report — unit (_format.py) + E2E smoke (build_rsch_report)."""
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook, load_workbook

# ═══════════════════════════════════════════════
# _format.py unit tests
# ═══════════════════════════════════════════════

def test_normalize_text_lowercases_and_collapses_whitespace():
    from core.infra.rsch._format import _normalize_text
    assert _normalize_text("  HELLO   WORLD  ") == "hello world"
    assert _normalize_text(None) == ""
    assert _normalize_text("Тест\xa0Пробел") == "тест пробел"  # nbsp


def test_is_rsch_sheet_title():
    from core.infra.rsch._format import _is_rsch_sheet_title
    assert _is_rsch_sheet_title("РСЧ отчет 10.06")
    assert _is_rsch_sheet_title("рсч итоги")
    assert not _is_rsch_sheet_title("шаблон РСЧ")
    assert not _is_rsch_sheet_title("итоги")


def test_display_len_numbers():
    from core.infra.rsch._format import _display_len
    # int/float formatted as "XX.00" (with 2 decimal places)
    assert _display_len(42) == len("42.00")  # 5
    assert _display_len(3.14) == len("3.14")
    assert _display_len("hello") == 5
    assert _display_len(None) == 0


def test_to_decimal_bool():
    from core.infra.rsch._format import _to_decimal
    assert _to_decimal(True) == Decimal("1")
    assert _to_decimal(False) == Decimal("0")


def test_excel_safe_text_triggers():
    from core.infra.rsch._format import _excel_safe_text
    assert _excel_safe_text("=SUM(A1)").startswith("'")
    assert _excel_safe_text("\t=CMD").startswith("'")
    assert _excel_safe_text("normal") == "normal"
    assert _excel_safe_text(42) == 42


def test_clean_executor_name():
    from core.infra.rsch._format import _clean_executor_name
    assert _clean_executor_name("рсч ИВАНОВ") == "ИВАНОВ"
    assert _clean_executor_name("  Петров  ") == "ПЕТРОВ"


def test_as_date():
    from datetime import date, datetime

    from core.infra.rsch._format import _as_date
    assert _as_date(date(2026, 6, 10)) == date(2026, 6, 10)
    assert _as_date(datetime(2026, 6, 10, 12, 0)) == date(2026, 6, 10)
    assert _as_date("10.06.2026") == date(2026, 6, 10)
    assert _as_date("2026-06-10") == date(2026, 6, 10)
    assert _as_date("") is None


# ═══════════════════════════════════════════════
# E2E smoke: build_rsch_report with minimal template
# ═══════════════════════════════════════════════

def test_build_rsch_report_smoke():
    """Minimal valid RSCH report generation with tempfile template."""
    from core.infra.rsch import build_rsch_report

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a minimal source file matching RSCH format
        source_path = Path(tmpdir) / "source.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "рсч Иванов"
        ws.append(["Дата", "ИСПОЛНИТЕЛЬ", "ЗАКАЗЧИК", "Контрагент",
                    "Комментарий", "Приход РСЧ", "Расход РСЧ", "р/с", "Источник",
                    "Проект левый", "Проект правый", "account"])
        ws.append(["10.06.2026", "exec1", "cust1", "contr1", "comment1",
                    100.00, 0.00, "acc1", "src1", "", "", ""])
        ws.append(["10.06.2026", "exec2", "cust2", "contr2", "",
                    200.00, 50.00, "acc2", "src2", "", "", ""])
        wb.save(source_path)
        wb.close()

        # Create minimal template matching RSCH format
        template_path = Path(tmpdir) / "template.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.append(["Дата", "ИСПОЛНИТЕЛЬ", "ЗАКАЗЧИК", "Контрагент",
                    "Комментарий", "Приход РСЧ", "Расход РСЧ", "р/с", "Источник"])
        wb.save(template_path)
        wb.close()

        # Build RSCH report
        output_path = Path(tmpdir) / "output.xlsx"
        written = build_rsch_report(
            source_path=[source_path],
            output_path=output_path,
            target_date=date(2026, 6, 10),
            template_path=template_path,
            drive_letters=(),
        )

        assert written > 0
        assert output_path.exists()
        assert output_path.stat().st_size > 0

        # Verify output is readable
        result_wb = load_workbook(output_path)
        ws = result_wb.active
        assert ws.max_row >= 2  # header + at least 1 data row
        result_wb.close()


def test_is_problem_row_for_vznosy():
    from core.infra.rsch._format import _is_problem_row

    # Case 1: Row with customer "взносы", empty contractor and comment
    # Should NOT be problem row (should not "светить")
    row_vznosy = {
        "income": 0,
        "expense": 1000,
        "contractor": "",
        "customer": "взносы",
        "executor": "Иванов",
        "account": "123456789",
        "comment": "",
    }
    assert not _is_problem_row(row_vznosy)

    # Case 2: Regular row with missing contractor
    # Should be problem row (should "светить")
    row_regular = {
        "income": 0,
        "expense": 1000,
        "contractor": "",
        "customer": "обычный заказчик",
        "executor": "Иванов",
        "account": "123456789",
        "comment": "",
    }
    assert _is_problem_row(row_regular)


def test_is_excluded_customer_vznosy():
    from core.infra.reconciliation._utils import _is_excluded_customer
    assert _is_excluded_customer("взносы")
    assert _is_excluded_customer("налог")
    assert not _is_excluded_customer("обычный заказчик")


def test_one_bad_amount_cell_does_not_kill_whole_sheet():
    """Regression: a single unparseable amount cell used to raise ValueError
    from ``_to_decimal`` that propagated out of ``_collect_rows_from_sheet``
    into the per-sheet ``except`` — silently dropping ALL rows of the
    executor's sheet (hundreds of valid transactions lost for one bad cell).

    Parsing is now fail-soft per row (mirrors reconciliation's
    ``_to_decimal_soft``): the bad cell is logged via ``record_loss`` and
    coerced to 0, so the healthy rows survive. This test drives the sheet
    collector directly and asserts the healthy rows are still returned."""
    from core.infra.rsch._collect import _collect_rows_from_sheet

    wb = Workbook()
    ws = wb.active
    ws.title = "рсч Иванов"
    ws.append(["Дата", "ИСПОЛНИТЕЛЬ", "ЗАКАЗЧИК", "Контрагент",
               "Комментарий", "Приход РСЧ", "Расход РСЧ", "р/с", "Источник",
               "Проект левый", "Проект правый", "account"])
    # Healthy row.
    ws.append(["10.06.2026", "e1", "c1", "k1", "ok1", 100.00, 0.00, "a1", "s1", "", "", ""])
    # Corrupt income cell — must NOT abort the sheet.
    ws.append(["10.06.2026", "e2", "c2", "k2", "ok2", "#BAD!", 0.00, "a2", "s2", "", "", ""])
    # Healthy row.
    ws.append(["10.06.2026", "e3", "c3", "k3", "ok3", 300.00, 0.00, "a3", "s3", "", "", ""])

    rows = _collect_rows_from_sheet(
        ws, date(2026, 6, 10), "source.xlsx", Path("source.xlsx")
    )
    wb.close()

    # The sheet was NOT aborted: both healthy rows survived with their amounts.
    incomes = [r["income"] for r in rows]
    assert Decimal("100") in incomes
    assert Decimal("300") in incomes
    # The corrupt row is retained (it has business text) but zeroed, not lost
    # along with the whole sheet.
    assert len(rows) == 3

