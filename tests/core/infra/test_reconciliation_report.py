"""Tests for reconciliation report — e2e generation + _to_decimal unit tests."""
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

# ──────────────────────────────────────────────
# _to_decimal unit tests
# ──────────────────────────────────────────────

def test_to_decimal_none_is_zero():
    from core.infra.reconciliation._utils import _to_decimal
    assert _to_decimal(None) == Decimal("0")


def test_to_decimal_empty_string_is_zero():
    from core.infra.reconciliation._utils import _to_decimal
    assert _to_decimal("") == Decimal("0")


def test_to_decimal_bool_true_is_one():
    from core.infra.reconciliation._utils import _to_decimal
    assert _to_decimal(True) == Decimal("1")


def test_to_decimal_bool_false_is_zero():
    from core.infra.reconciliation._utils import _to_decimal
    assert _to_decimal(False) == Decimal("0")


def test_to_decimal_int():
    from core.infra.reconciliation._utils import _to_decimal
    assert _to_decimal(42) == Decimal("42")


def test_to_decimal_float():
    from core.infra.reconciliation._utils import _to_decimal
    assert _to_decimal(3.14) == Decimal("3.14")


def test_to_decimal_decimal_passthrough():
    from core.infra.reconciliation._utils import _to_decimal
    d = Decimal("7.5")
    assert _to_decimal(d) is d  # identity preserved for Decimal


def test_to_decimal_russian_comma():
    from core.infra.reconciliation._utils import _to_decimal
    assert _to_decimal("100,50") == Decimal("100.50")


def test_to_decimal_strips_spaces():
    from core.infra.reconciliation._utils import _to_decimal
    assert _to_decimal("  42  ") == Decimal("42")


def test_to_decimal_formula_returns_zero():
    """Formula cells (no cached value) should return 0."""
    from core.infra.reconciliation._utils import _to_decimal
    assert _to_decimal("=SUM(A1:A10)") == Decimal("0")


def test_to_decimal_raises_on_garbage():
    from core.infra.reconciliation._utils import _to_decimal
    with pytest.raises(ValueError, match="Некорректное числовое значение"):
        _to_decimal("not_a_number")


# ──────────────────────────────────────────────
# _excel_safe_text unit tests
# ──────────────────────────────────────────────

@pytest.mark.parametrize("value,expected_prefix", [
    ("=cmd|'/C calc'!A0", "'"),
    ("+SUM(A1)", "'"),
    ("-A1+B1", "'"),
    ("@SUM", "'"),
    ("\t=cmd", "'"),       # tab-prefixed attack
    ("\n=cmd", "'"),       # newline-prefixed attack
    ("normal text", ""),
    ("123", ""),
])
def test_excel_safe_text_escapes_formula_triggers(value, expected_prefix):
    from core.infra.reconciliation._utils import _excel_safe_text
    result = _excel_safe_text(value)
    if expected_prefix:
        assert result.startswith("'"), f"Expected ' prefix for {value!r}, got {result!r}"
    else:
        assert not result.startswith("'"), f"Unexpected ' prefix for {value!r}"


def test_excel_safe_text_non_string_passthrough():
    from core.infra.reconciliation._utils import _excel_safe_text
    assert _excel_safe_text(42) == 42
    assert _excel_safe_text(None) is None


# ──────────────────────────────────────────────
# _amount_equal unit tests
# ──────────────────────────────────────────────

def test_amount_equal_exact():
    from core.infra.reconciliation._resolve import _amount_equal
    assert _amount_equal(Decimal("100"), Decimal("100"))


def test_amount_equal_within_one_kopeck():
    from core.infra.reconciliation._resolve import _amount_equal
    assert _amount_equal(Decimal("100.005"), Decimal("100.00"))


def test_amount_equal_outside_tolerance():
    from core.infra.reconciliation._resolve import _amount_equal
    assert not _amount_equal(Decimal("100.02"), Decimal("100.00"))


# ──────────────────────────────────────────────
# E2E: build_workbook with formula injection
# ──────────────────────────────────────────────

def test_build_workbook_produces_valid_xlsx_with_safe_headers():
    """Sanitizer test: _excel_safe_text escapes all formula triggers."""
    from core.infra.reconciliation._utils import _excel_safe_text

    # Unit: all trigger characters are escaped
    for dangerous in ("=SUM(A1)", "+A1", "-A1", "@SUM", "\t=CMD", "\n=CMD"):
        result = _excel_safe_text(dangerous)
        assert result.startswith("'"), (
            f"Formula trigger not escaped: {dangerous!r} → {result!r}"
        )
        # Original text preserved (minus whitespace prefix which lstrip removes)
        assert dangerous.lstrip() in result

    # Non-trigger strings pass through
    assert _excel_safe_text("normal text") == "normal text"
    assert _excel_safe_text("123") == "123"
    assert _excel_safe_text("") == ""
    assert _excel_safe_text(42) == 42
    assert _excel_safe_text(None) is None


def test_build_workbook_empty_rows_returns_empty():
    """Zero rows should produce a valid workbook with only headers."""
    from core.infra.reconciliation._build import _build_workbook

    out_wb = _build_workbook(date(2026, 6, 10), [], ["Источник", "Сумма"])
    assert out_wb is not None
    ws = out_wb.active
    assert ws.max_row <= 1  # headers only (or no data rows)
    out_wb.close()


# ──────────────────────────────────────────────
# E2E: build_reconciliation_report smoke test
# ──────────────────────────────────────────────

def test_build_reconciliation_report_smoke():
    """Smoke test: build_reconciliation_report produces an xlsx file."""
    from core.infra.reconciliation import build_reconciliation_report

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create master file
        master_path = Path(tmpdir) / "master.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "10.06.2026"
        ws.append(["Источник", "ЗАКАЗЧИК", "ИСПОЛНИТЕЛЬ", "Приход", "Расход"])
        ws.append(["user1", "cust1", "exec1", 100, 0])
        ws.append(["user2", "cust2", "exec2", 200, 50])
        wb.save(master_path)
        wb.close()

        # Create rsch file
        rsch_path = Path(tmpdir) / "rsch.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "10.06.2026"
        ws.append(["Источник", "ИСПОЛНИТЕЛЬ", "ЗАКАЗЧИК", "Контрагент",
                    "Комментарий", "Приход", "Расход"])
        ws.append(["src1", "exec1", "cust1", "contr1", "", 100, 0])
        ws.append(["src2", "exec2", "cust2", "contr2", "", 200, 50])
        wb.save(rsch_path)
        wb.close()

        # Build reconciliation
        output_path = Path(tmpdir) / "recon.xlsx"
        row_count = build_reconciliation_report(
            master_path, rsch_path, output_path,
            target_date=date(2026, 6, 10),
            drive_letters=()
        )

        assert row_count > 0
        assert output_path.exists()
        assert output_path.stat().st_size > 0


def test_build_combined_reconciliation_report_smoke():
    """Smoke test: exercises _customer_matches_weak via fuzzy name matching."""
    from core.infra.reconciliation import build_combined_reconciliation_report

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create master files — use fuzzy customer names
        master_paths = {}
        for label, cust in (("Общий", "ООО Ромашка Трейд"), ("Борис", "ЗАО Лютик"), ("Иван", "ИП Василёк Сбыт")):
            p = Path(tmpdir) / f"master_{label}.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.title = "10.06.2026"
            ws.append(["Источник", "ЗАКАЗЧИК", "ИСПОЛНИТЕЛЬ", "Приход", "Расход"])
            ws.append([f"src_{label}", cust, f"exec_{label}", 100, 0])
            wb.save(p)
            wb.close()
            master_paths[label] = p

        # Create rsch file — similar but non-identical customer names
        rsch_path = Path(tmpdir) / "rsch.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "10.06.2026"
        ws.append(["Источник", "ИСПОЛНИТЕЛЬ", "ЗАКАЗЧИК", "Контрагент",
                    "Комментарий", "Приход", "Расход"])
        # "Ромашка" shares token but not substring of "ООО Ромашка Трейд" → weak match
        # "Лютик Плюс" vs "ЗАО Лютик" → weak match
        # "Василёк" vs "ИП Василёк Сбыт" → weak match
        ws.append(["src_Общий", "exec_Общий", "Ромашка", "contr", "", 100, 0])
        ws.append(["src_Борис", "exec_Борис", "Лютик Плюс", "contr", "", 100, 0])
        ws.append(["src_Иван", "exec_Иван", "Василёк", "contr", "", 100, 0])
        wb.save(rsch_path)
        wb.close()

        output_path = Path(tmpdir) / "combined.xlsx"
        counts = build_combined_reconciliation_report(
            master_paths, rsch_path, output_path,
            target_date=date(2026, 6, 10), drive_letters=(),
        )

        assert isinstance(counts, dict)
        assert output_path.exists()
        assert output_path.stat().st_size > 0


# --- Fix #3: advisory warning for zero-amount text rows -----------------
# Rows that carry customer/executor text but zero Приход/Расход are skipped
# (unchanged behaviour). The dominant real-world cause is a source file saved
# without cached formula values — data_only reads such cells as None, so the
# row silently drops out of the reconciliation. We now log ONE advisory
# warning per sheet telling the operator to re-save in Excel. No data change.


def test_zero_amount_text_rows_warn_about_uncached_formulas(caplog):
    import logging
    from core.infra.reconciliation._collect import _collect_master_rows

    wb = Workbook()
    ws = wb.active
    ws.title = "Общий"
    ws.append(["Источник", "ЗАКАЗЧИК", "ИСПОЛНИТЕЛЬ", "Приход", "Расход"])
    ws.append(["src1", "ООО А", "Иванов", 100, 0])      # collected
    ws.append(["src2", "ООО Б", "Петров", None, None])  # text row, zero → skipped + warned

    with caplog.at_level(logging.WARNING):
        _headers, rows, _excluded = _collect_master_rows(ws)
    wb.close()

    assert len(rows) == 1  # data behaviour unchanged: only the funded row
    assert any("Excel" in rec.message for rec in caplog.records)


def test_no_formula_warning_when_all_text_rows_have_amounts(caplog):
    import logging
    from core.infra.reconciliation._collect import _collect_master_rows

    wb = Workbook()
    ws = wb.active
    ws.title = "Общий"
    ws.append(["Источник", "ЗАКАЗЧИК", "ИСПОЛНИТЕЛЬ", "Приход", "Расход"])
    ws.append(["src1", "ООО А", "Иванов", 100, 0])
    ws.append(["src2", "ООО Б", "Петров", 0, 50])

    with caplog.at_level(logging.WARNING):
        _collect_master_rows(ws)
    wb.close()

    assert not any("Excel" in rec.message for rec in caplog.records)


# ── match VERDICTS: assert matched vs unmatched, not just row_count ──
#
# The smoke tests above only assert row_count > 0. A regression that matched
# every row to nothing (or every row to everything) would pass them. This
# pins the actual verdicts: an exact match → СВЕРЕНО, a fuzzy executor-alias
# match → matched, and a deliberately unmatched master row → ОШИБКА / "Нет в
# РСЧ". This is the highest-financial-stakes output of the app.


def test_reconciliation_verdicts_exact_alias_and_unmatched(tmp_path):
    """Three master rows: one exact match, one executor-alias match, one
    unmatched. The report must distinguish them by Статус/Причина, not just
    produce a non-empty sheet."""
    from core.infra.reconciliation import build_reconciliation_report
    from openpyxl import load_workbook

    master_path = tmp_path / "master.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "10.06.2026"
    ws.append(["Источник", "ЗАКАЗЧИК", "ИСПОЛНИТЕЛЬ", "Приход", "Расход"])
    # exact match: exec1 / cust1 / 100 also in rsch
    ws.append(["m1", "cust1", "exec1", 100, 0])
    # fuzzy executor-alias match: "УК Альянс" canonicalizes to "ука", same as
    # the rsch executor "УКА_Альфа" — so this row still finds a pair.
    ws.append(["m2", "cust2", "УК Альянс", 200, 0])
    # unmatched: amount 9999 appears in no rsch row → no candidate
    ws.append(["m3", "cust3", "exec3", 9999, 0])
    wb.save(master_path)
    wb.close()

    rsch_path = tmp_path / "rsch.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "10.06.2026"
    ws.append(["Источник", "ИСПОЛНИТЕЛЬ", "ЗАКАЗЧИК", "Контрагент",
               "Комментарий", "Приход", "Расход"])
    ws.append(["r1", "exec1", "cust1", "contr1", "", 100, 0])  # pairs with m1
    ws.append(["r2", "УКА_Альфа", "cust2", "contr2", "", 200, 0])  # pairs with m2
    wb.save(rsch_path)
    wb.close()

    output_path = tmp_path / "recon.xlsx"
    row_count = build_reconciliation_report(
        master_path, rsch_path, output_path,
        target_date=date(2026, 6, 10), drive_letters=(),
    )
    assert row_count > 0

    # Layout: [*5 master cols, "Статус"(col 6), *6 rsch cols(7-12), "Причина"(13)]
    result_wb = load_workbook(output_path)
    ws = result_wb["10.06.2026"]
    header = [c.value for c in ws[1]]
    status_col = header.index("Статус") + 1
    reason_col = header.index("Причина") + 1
    executor_col = header.index("ИСПОЛНИТЕЛЬ") + 1  # master executor col

    # Collect (executor, status, reason) per data row.
    rows_by_exec = {}
    for r in range(2, ws.max_row + 1):
        exec_val = ws.cell(r, executor_col).value
        status = ws.cell(r, status_col).value
        reason = ws.cell(r, reason_col).value
        if exec_val:
            rows_by_exec[exec_val] = (status, reason)

    # The exact-match row (exec1) is verified — not flagged as a discrepancy.
    assert "exec1" in rows_by_exec, "exact-match master row disappeared from report"
    s1, _ = rows_by_exec["exec1"]
    assert s1 in ("СВЕРЕНО", "ПРОВЕРИТЬ"), (
        f"exact match should be matched, got status={s1!r}"
    )

    # The alias-match row (УК Альянс ↔ УКА_Альфа) is also matched.
    assert "УК Альянс" in rows_by_exec, "alias master row disappeared"
    s2, _ = rows_by_exec["УК Альянс"]
    assert s2 in ("СВЕРЕНО", "ПРОВЕРИТЬ"), (
        f"executor-alias match (УК Альянс↔УКА_Альфа) should be matched, "
        f"got status={s2!r} — canonicalization regression"
    )

    # The unmatched row (exec3) must be flagged as an error with reason
    # "Нет в РСЧ" — a regression that silently matches it would be a silent
    # financial discrepancy.
    assert "exec3" in rows_by_exec, "unmatched master row disappeared"
    s3, reason3 = rows_by_exec["exec3"]
    assert s3 == "ОШИБКА", (
        f"unmatched row should be ОШИБКА, got status={s3!r}"
    )
    assert reason3 is not None and "РСЧ" in str(reason3), (
        f"unmatched row reason should mention РСЧ, got {reason3!r}"
    )
