#!/usr/bin/env python3
"""PII-safe workbook comparator for golden tests.

Compares two ``.xlsx`` workbooks and reports *where* they differ, without
ever printing the actual cell values. This is critical for a financial
product: a diff that printed real amounts or employee names would leak
PII into test logs, CI artifacts and screen shares.

Modes (all on by default; toggle with flags):

* sheet set       — extra / missing sheets
* table size      — row × column dimensions per sheet
* values          — cell-by-cell value comparison (``data_only=False``,
                    so formulas are kept as formulas)
* types           — Python type of each cell value
* formulas        — formula string comparison (separate from values so a
                    formula vs cached-value mismatch is visible)
* merged cells    — merged ranges per sheet
* freeze panes    — ``ws.freeze_panes`` per sheet
* auto filter     — ``ws.auto_filter.ref`` per sheet
* print area      — ``ws.print_area`` per sheet
* styles          — canonical style fingerprint (font name/size/bold/italic,
                    fill foreground, alignment, number format). Internal
                    ``style_id`` and shared-style-table indices are
                    deliberately NOT compared, because openpyxl rewrites
                    them across save cycles and they carry no semantic
                    meaning.

Exit codes:

* 0 — no differences found (within the compared modes)
* 1 — at least one content difference found
* 2 — could not read one of the inputs (corrupt workbook, missing file,
      wrong format). Distinct from "1" so CI can tell a real diff from a
      fixture problem.

Output is plain text on stdout, JSON on request (``--json``). Either way,
NO cell values are emitted — only coordinates, types and counts.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import openpyxl  # type: ignore
except ImportError as exc:  # pragma: no cover
    print(f"compare_workbooks requires openpyxl: {exc}", file=sys.stderr)
    sys.exit(2)

from openpyxl.utils import get_column_letter


# ── data model ──────────────────────────────────────────────────────────

@dataclass
class SheetDiff:
    """Per-sheet comparison result. Coordinates only — never values."""
    sheet: str
    missing_in_expected: bool = False
    missing_in_actual: bool = False
    only_in_expected: list[str] = field(default_factory=list)
    only_in_actual: list[str] = field(default_factory=list)
    dimension_expected: tuple[int, int] | None = None  # (rows, cols)
    dimension_actual: tuple[int, int] | None = None
    value_diffs: list[tuple[str, str, str]] = field(default_factory=list)  # (coord, type_ex, type_ac)
    formula_diffs: list[str] = field(default_factory=list)  # coords where formula strings differ
    type_diffs: list[tuple[str, str, str]] = field(default_factory=list)  # (coord, type_ex, type_ac)
    merged_diff: bool = False
    freeze_diff: bool = False
    auto_filter_diff: bool = False
    print_area_diff: bool = False
    style_diffs: list[tuple[str, str]] = field(default_factory=list)  # (coord, category)

    @property
    def has_any_diff(self) -> bool:
        return bool(
            self.missing_in_expected or self.missing_in_actual
            or self.only_in_expected or self.only_in_actual
            or self.value_diffs or self.formula_diffs
            or self.type_diffs or self.merged_diff or self.freeze_diff
            or self.auto_filter_diff or self.print_area_diff
            or self.style_diffs
        )


@dataclass
class WorkbookDiff:
    expected_path: str
    actual_path: str
    sheets: list[SheetDiff] = field(default_factory=list)
    read_errors: list[str] = field(default_factory=list)

    @property
    def has_any_diff(self) -> bool:
        return any(s.has_any_diff for s in self.sheets) or bool(self.read_errors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "expected": self.expected_path,
            "actual": self.actual_path,
            "read_errors": self.read_errors,
            "has_differences": self.has_any_diff,
            "sheets": [
                {
                    "name": s.sheet,
                    "missing_in_expected": s.missing_in_expected,
                    "missing_in_actual": s.missing_in_actual,
                    "dim_expected": s.dimension_expected,
                    "dim_actual": s.dimension_actual,
                    "value_diff_count": len(s.value_diffs),
                    "value_diff_coords": [d[0] for d in s.value_diffs][:200],
                    "formula_diff_coords": s.formula_diffs[:200],
                    "type_diffs": s.type_diffs[:200],
                    "merged_diff": s.merged_diff,
                    "freeze_diff": s.freeze_diff,
                    "auto_filter_diff": s.auto_filter_diff,
                    "print_area_diff": s.print_area_diff,
                    "style_diff_count": len(s.style_diffs),
                    "style_diff_categories": sorted({c for _, c in s.style_diffs}),
                }
                for s in self.sheets
            ],
        }


# ── helpers ─────────────────────────────────────────────────────────────

def _load_workbook(path: Path, errors: list[str]) -> openpyxl.Workbook | None:
    """Load a workbook in data_only=False mode (keep formulas)."""
    try:
        return openpyxl.load_workbook(path, data_only=False, read_only=False)
    except Exception as e:  # noqa: BLE001 — we want any openpyxl failure to be reported
        errors.append(f"could not read {path}: {type(e).__name__}: {e}")
        return None


def _coord_iter(ws) -> tuple[int, int]:
    """Return (max_row, max_col) used by *ws*."""
    # openpyxl reports ws.max_row / ws.max_column even when they include
    # empty trailing cells (common for formatted sheets). We keep them as-is;
    # this is exactly the dimension we want to flag if it drifts.
    return ws.max_row or 0, ws.max_column or 0


def _cell_value_type(v: Any) -> str:
    """Canonical type label that ignores Decimal-vs-float noise.

    Both Decimal and float are reported as ``"number"`` so that an
    expected ``Decimal("100.00")`` matches an actual ``100.0`` that
    openpyxl read back as float. Excel stores all numbers as IEEE-754
    doubles anyway, so this is the honest comparison.
    """
    if v is None:
        return "empty"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "number"
    # Decimal imported by openpyxl on read is rare; treat as number too.
    try:
        from decimal import Decimal
        if isinstance(v, Decimal):
            return "number"
    except Exception:  # pragma: no cover
        pass
    if isinstance(v, str):
        # Distinguish a formula string from a literal string only if the
        # caller stored it that way. openpyxl keeps formulas as strings
        # starting with "=".
        return "formula" if v.startswith("=") else "text"
    return type(v).__name__


def _values_equal(a: Any, b: Any) -> bool:
    """Numeric-aware equality. ``100`` == ``100.0`` == ``Decimal("100")``."""
    ta, tb = _cell_value_type(a), _cell_value_type(b)
    if ta != tb:
        return False
    if ta == "number":
        try:
            return abs(float(a) - float(b)) < 1e-9
        except (TypeError, ValueError):
            return False
    return a == b


def _style_fingerprint(cell) -> dict[str, Any]:
    """Canonical, save-cycle-stable view of a cell's style.

    Internal ``style_id`` and shared-table indices are intentionally
    excluded — openpyxl rewrites them on save.
    """
    font = cell.font
    fill = cell.fill
    align = cell.alignment
    return {
        "font_name": font.name,
        "font_size": font.sz,
        "bold": bool(font.b),
        "italic": bool(font.i),
        "fill_fg": str(fill.fgColor.rgb) if fill and fill.fgColor else None,
        "fill_pattern": fill.patternType if fill else None,
        "align_h": align.horizontal if align else None,
        "align_v": align.vertical if align else None,
        "align_wrap": bool(align.wrap_text) if align else None,
        "number_format": cell.number_format,
    }


# ── core comparator ────────────────────────────────────────────────────

def compare(
    expected: Path,
    actual: Path,
    *,
    compare_values: bool = True,
    compare_formulas: bool = True,
    compare_types: bool = True,
    compare_styles: bool = True,
    compare_merged: bool = True,
    compare_freeze: bool = True,
    compare_filter: bool = True,
    compare_print: bool = True,
) -> WorkbookDiff:
    diff = WorkbookDiff(expected_path=str(expected), actual_path=str(actual))

    wb_ex = _load_workbook(expected, diff.read_errors)
    wb_ac = _load_workbook(actual, diff.read_errors)
    if wb_ex is None or wb_ac is None:
        return diff

    ex_sheets = set(wb_ex.sheetnames)
    ac_sheets = set(wb_ac.sheetnames)

    # 1) Sheet-set differences
    for name in sorted(ex_sheets | ac_sheets):
        if name not in ex_sheets:
            diff.sheets.append(SheetDiff(sheet=name, missing_in_expected=True))
        elif name not in ac_sheets:
            diff.sheets.append(SheetDiff(sheet=name, missing_in_actual=True))

    # 2) Per-sheet content comparison
    for name in sorted(ex_sheets & ac_sheets):
        ws_ex = wb_ex[name]
        ws_ac = wb_ac[name]
        sd = SheetDiff(sheet=name)
        sd.dimension_expected = _coord_iter(ws_ex)
        sd.dimension_actual = _coord_iter(ws_ac)

        max_row = max(sd.dimension_expected[0], sd.dimension_actual[0])
        max_col = max(sd.dimension_expected[1], sd.dimension_actual[1])

        for r in range(1, max_row + 1):
            for c in range(1, max_col + 1):
                coord = f"{get_column_letter(c)}{r}"
                v_ex = ws_ex.cell(row=r, column=c).value
                v_ac = ws_ac.cell(row=r, column=c).value
                cell_ex = ws_ex.cell(row=r, column=c)
                cell_ac = ws_ac.cell(row=r, column=c)

                # value comparison
                if compare_values and not _values_equal(v_ex, v_ac):
                    t_ex = _cell_value_type(v_ex)
                    t_ac = _cell_value_type(v_ac)
                    sd.value_diffs.append((coord, t_ex, t_ac))
                    if compare_types and t_ex != t_ac:
                        sd.type_diffs.append((coord, t_ex, t_ac))

                # formula-specific comparison (only meaningful if both look like formulas)
                if compare_formulas:
                    f_ex = v_ex if isinstance(v_ex, str) and v_ex.startswith("=") else None
                    f_ac = v_ac if isinstance(v_ac, str) and v_ac.startswith("=") else None
                    if (f_ex is not None) or (f_ac is not None):
                        if f_ex != f_ac:
                            sd.formula_diffs.append(coord)

                # style comparison
                if compare_styles:
                    fp_ex = _style_fingerprint(cell_ex)
                    fp_ac = _style_fingerprint(cell_ac)
                    for key in fp_ex:
                        if fp_ex.get(key) != fp_ac.get(key):
                            sd.style_diffs.append((coord, key))

        # structural comparisons
        if compare_merged:
            merged_ex = {str(m) for m in ws_ex.merged_cells.ranges}
            merged_ac = {str(m) for m in ws_ac.merged_cells.ranges}
            sd.merged_diff = merged_ex != merged_ac

        if compare_freeze:
            sd.freeze_diff = bool(ws_ex.freeze_panes) != bool(ws_ac.freeze_panes) or (
                str(ws_ex.freeze_panes) != str(ws_ac.freeze_panes)
            )

        if compare_filter:
            af_ex = ws_ex.auto_filter.ref if ws_ex.auto_filter else None
            af_ac = ws_ac.auto_filter.ref if ws_ac.auto_filter else None
            sd.auto_filter_diff = (af_ex or "") != (af_ac or "")

        if compare_print:
            pa_ex = ws_ex.print_area
            pa_ac = ws_ac.print_area
            sd.print_area_diff = (pa_ex or "") != (pa_ac or "")

        diff.sheets.append(sd)

    return diff


# ── rendering ───────────────────────────────────────────────────────────

def render_text(diff: WorkbookDiff) -> str:
    lines: list[str] = []
    lines.append(f"expected: {diff.expected_path}")
    lines.append(f"actual:   {diff.actual_path}")
    if diff.read_errors:
        lines.append("")
        lines.append("READ ERRORS:")
        for e in diff.read_errors:
            lines.append(f"  - {e}")
        return "\n".join(lines)

    if not diff.has_any_diff:
        lines.append("RESULT: identical (no differences in compared modes)")
        return "\n".join(lines)

    lines.append("")
    lines.append("DIFFERENCES:")
    total_value = 0
    total_formula = 0
    for s in diff.sheets:
        if not s.has_any_diff:
            continue
        lines.append(f"  [{s.sheet}]")
        if s.missing_in_expected:
            lines.append("    sheet missing in expected")
            continue
        if s.missing_in_actual:
            lines.append("    sheet missing in actual")
            continue
        if s.dimension_expected != s.dimension_actual:
            lines.append(f"    dimension: expected {s.dimension_expected} "
                         f"actual {s.dimension_actual}")
        if s.value_diffs:
            total_value += len(s.value_diffs)
            lines.append(f"    value diffs: {len(s.value_diffs)} cells")
            for coord, t_ex, t_ac in s.value_diffs[:20]:
                lines.append(f"      {coord}  ({t_ex} → {t_ac})")
            if len(s.value_diffs) > 20:
                lines.append(f"      ... and {len(s.value_diffs) - 20} more")
        if s.formula_diffs:
            total_formula += len(s.formula_diffs)
            lines.append(f"    formula diffs: {len(s.formula_diffs)} cells")
            for coord in s.formula_diffs[:20]:
                lines.append(f"      {coord}")
            if len(s.formula_diffs) > 20:
                lines.append(f"      ... and {len(s.formula_diffs) - 20} more")
        if s.type_diffs:
            lines.append(f"    type diffs: {len(s.type_diffs)}")
        if s.style_diffs:
            cats = sorted({c for _, c in s.style_diffs})
            lines.append(f"    style diffs: {len(s.style_diffs)} cells "
                         f"(categories: {', '.join(cats)})")
        if s.merged_diff:
            lines.append("    merged ranges differ")
        if s.freeze_diff:
            lines.append("    freeze panes differ")
        if s.auto_filter_diff:
            lines.append("    auto filter differs")
        if s.print_area_diff:
            lines.append("    print area differs")

    lines.append("")
    lines.append(f"TOTAL: value={total_value} formula={total_formula} "
                 f"sheets_with_diff={sum(1 for s in diff.sheets if s.has_any_diff)}")
    return "\n".join(lines)


# ── CLI ─────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("expected", help="path to expected (golden) workbook")
    p.add_argument("actual", help="path to actual workbook")
    p.add_argument("--json", action="store_true", help="emit JSON instead of text")
    p.add_argument("--no-values", action="store_true")
    p.add_argument("--no-formulas", action="store_true")
    p.add_argument("--no-types", action="store_true")
    p.add_argument("--no-styles", action="store_true")
    p.add_argument("--no-merged", action="store_true")
    p.add_argument("--no-freeze", action="store_true")
    p.add_argument("--no-filter", action="store_true")
    p.add_argument("--no-print", action="store_true")
    args = p.parse_args()

    exp_path = Path(args.expected)
    act_path = Path(args.actual)
    if not exp_path.is_file():
        print(f"expected file not found: {exp_path}", file=sys.stderr)
        return 2
    if not act_path.is_file():
        print(f"actual file not found: {act_path}", file=sys.stderr)
        return 2

    diff = compare(
        exp_path, act_path,
        compare_values=not args.no_values,
        compare_formulas=not args.no_formulas,
        compare_types=not args.no_types,
        compare_styles=not args.no_styles,
        compare_merged=not args.no_merged,
        compare_freeze=not args.no_freeze,
        compare_filter=not args.no_filter,
        compare_print=not args.no_print,
    )

    if args.json:
        print(json.dumps(diff.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(render_text(diff))

    if diff.read_errors:
        return 2
    return 1 if diff.has_any_diff else 0


if __name__ == "__main__":
    raise SystemExit(main())
