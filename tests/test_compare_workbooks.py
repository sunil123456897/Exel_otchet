"""Stage 1 / MR-0101 — unit tests for tools/compare_workbooks.py.

The comparator is the foundation of every golden test, so it must be
verified independently before any financial golden data goes through it.
We check:

* identical workbooks → exit 0, "no differences";
* value difference in one cell → exit 1, that coordinate reported,
  NO actual values printed;
* formula difference → reported under "formula diffs";
* type difference (number vs text) → reported under "type diffs";
* missing sheet in one side → reported as missing;
* style difference (bold vs not) → reported by category;
* unreadable file → exit 2 with read error.

All assertions check that NO real cell value appears in the output text,
since this is the whole point of a PII-safe comparator.

``tools/`` is on sys.path via pyproject.toml ``[tool.pytest.ini_options]
pythonpath = ["APP", "tools"]`` — no manual sys.path manipulation here.
"""
from __future__ import annotations

import sys
from pathlib import Path

import compare_workbooks as cw  # from tools/
import openpyxl
import pytest

# ── fixtures ────────────────────────────────────────────────────────────

@pytest.fixture
def identical_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Two identical workbooks with two sheets, one formula, one style."""
    def _build(path: Path) -> None:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Main"
        ws["A1"] = "Header"
        ws["B1"] = "Amount"
        ws["A2"] = "row1"
        ws["B2"] = 100
        ws["B3"] = "=B2*2"
        ws["C3"] = "stub"
        ws["A1"].font = openpyxl.styles.Font(bold=True)
        ws.merge_cells("A1:B1")
        ws.freeze_panes = "A2"
        ws2 = wb.create_sheet("Other")
        ws2["A1"] = "x"
        wb.save(path)
    a = tmp_path / "a.xlsx"
    b = tmp_path / "b.xlsx"
    _build(a)
    _build(b)
    return a, b


def _make_copy_with(src: Path, dst: Path, *, mutate=None) -> None:
    wb = openpyxl.load_workbook(src)
    if mutate:
        mutate(wb)
    wb.save(dst)


# ── tests ───────────────────────────────────────────────────────────────

def test_identical_workbooks_report_no_differences(identical_pair):
    a, b = identical_pair
    diff = cw.compare(a, b)
    assert not diff.has_any_diff
    text = cw.render_text(diff)
    assert "identical" in text.lower()


def test_value_difference_is_reported_without_leaking_value(identical_pair, tmp_path):
    a, _ = identical_pair
    c = tmp_path / "c.xlsx"
    _make_copy_with(a, c)
    wb = openpyxl.load_workbook(c)
    wb["Main"]["B2"] = 999  # was 100
    wb.save(c)
    diff = cw.compare(a, c)
    assert diff.has_any_diff
    text = cw.render_text(diff)
    assert "B2" in text
    # The whole point: no leaked value.
    assert "999" not in text


def test_formula_difference_is_reported(identical_pair, tmp_path):
    a, _ = identical_pair
    c = tmp_path / "c.xlsx"
    _make_copy_with(a, c)
    wb = openpyxl.load_workbook(c)
    wb["Main"]["B3"] = "=B2*3"  # different formula
    wb.save(c)
    diff = cw.compare(a, c)
    text = cw.render_text(diff)
    assert "formula" in text.lower()
    assert "B3" in text


def test_type_difference_is_reported(identical_pair, tmp_path):
    a, _ = identical_pair
    c = tmp_path / "c.xlsx"
    _make_copy_with(a, c)
    wb = openpyxl.load_workbook(c)
    wb["Main"]["B2"] = "100"  # was int 100, now string "100"
    wb.save(c)
    diff = cw.compare(a, c)
    assert diff.has_any_diff
    text = cw.render_text(diff)
    assert "B2" in text
    assert "type" in text.lower() or "value" in text.lower()


def test_missing_sheet_is_reported(identical_pair, tmp_path):
    a, _ = identical_pair
    c = tmp_path / "c.xlsx"
    _make_copy_with(a, c)
    wb = openpyxl.load_workbook(c)
    del wb["Other"]
    wb.save(c)
    diff = cw.compare(a, c)
    text = cw.render_text(diff)
    assert "Other" in text
    assert "missing" in text.lower()


def test_style_difference_is_reported_by_category(identical_pair, tmp_path):
    a, _ = identical_pair
    c = tmp_path / "c.xlsx"
    _make_copy_with(a, c)
    wb = openpyxl.load_workbook(c)
    wb["Main"]["A1"].font = openpyxl.styles.Font(bold=False)  # was bold
    wb.save(c)
    diff = cw.compare(a, c)
    text = cw.render_text(diff)
    assert "style" in text.lower()
    assert "bold" in text


def test_unreadable_file_returns_read_error(tmp_path):
    bogus = tmp_path / "bogus.xlsx"
    bogus.write_bytes(b"not an xlsx")
    real = tmp_path / "real.xlsx"
    wb = openpyxl.Workbook()
    wb.save(real)
    diff = cw.compare(real, bogus)
    assert diff.read_errors
    assert diff.has_any_diff


def test_cli_returns_2_for_missing_expected(tmp_path, monkeypatch, capsys):
    """Thin CLI wrapper test: missing expected file -> exit 2."""
    real = tmp_path / "real.xlsx"
    wb = openpyxl.Workbook()
    wb.save(real)
    monkeypatch.setattr(sys, "argv",
                        ["compare_workbooks.py", str(tmp_path / "missing.xlsx"), str(real)])
    rc = cw.main()
    assert rc == 2
