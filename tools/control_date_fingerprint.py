#!/usr/bin/env python3
"""Build and verify a PII-free fingerprint of a workbook sheet.

Used by Stage 1 (MR-0102) to cement the "control date" — a single sheet
in ``Master_Report.xlsx`` that has been confirmed to consolidate to
exactly the same 4 906 values + formulas every time.

Privacy contract — the fingerprint JSON contains:

* the sheet name;
* the sheet dimensions (rows × cols);
* total cell count;
* a SHA-256 over the *normalized cell-by-cell type+value+formula stream*,
  NOT over the raw values themselves. The hash is one-way: it lets us
  detect that two runs produced identical output, without ever recording
  what that output actually was. The pre-image (the 4 906 values) lives
  only in the real workbook on the operator's machine.

Why a hash and not the values? The whole point of MR-0102 is to ship a
public artifact (committed to Git) that *proves* the control date still
reproduces, without leaking the firm's financials into the public repo.
A reviewer can re-run this script against their real workbook and check
that their hash matches the one in ``tests/golden/control_date.json``.

Exit codes (CLI mode):

* 0 — fingerprint matches the stored golden;
* 1 — fingerprint differs (regression or input changed);
* 2 — input could not be read.

Usage:

    # First-time capture (operator, on real data, against real workbook):
    python tools/control_date_fingerprint.py capture \\
        --workbook path/to/Master_Report.xlsx \\
        --sheet 18.05.2026 \\
        --out tests/golden/control_date.json

    # CI / everyday verification (no real data needed; uses stored file):
    python tools/control_date_fingerprint.py verify \\
        --workbook path/to/Master_Report.xlsx \\
        --sheet 18.05.2026 \\
        --golden tests/golden/control_date.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

try:
    import openpyxl  # type: ignore
except ImportError as exc:  # pragma: no cover
    print(f"control_date_fingerprint requires openpyxl: {exc}", file=sys.stderr)
    sys.exit(2)

from openpyxl.utils import get_column_letter


def _cell_stream(ws) -> bytes:
    """Canonical byte stream over the sheet's cells.

    Each cell contributes one line:
    ``<coord>\t<type>\t<value_repr>\t<formula_or_->``

    Type is normalized so ``int``/``float``/``Decimal`` all share the
    label ``number`` and the value is rendered through ``repr`` so
    ``100`` and ``100.0`` are distinguishable (they really are different
    in Excel's type system, and a regression that silently coerces
    Decimal→float is exactly what we want to catch).

    The stream is sorted by coord so row/col reorderings do not change
    the hash. This is a *content* fingerprint, not a layout fingerprint —
    layout is compared separately by ``compare_workbooks.py``.
    """
    lines: list[str] = []
    for r in range(1, (ws.max_row or 0) + 1):
        for c in range(1, (ws.max_column or 0) + 1):
            coord = f"{get_column_letter(c)}{r}"
            cell = ws.cell(row=r, column=c)
            v = cell.value
            # type label
            if v is None:
                t = "empty"
            elif isinstance(v, bool):
                t = "bool"
            elif isinstance(v, (int, float)):
                t = "number"
            else:
                try:
                    from decimal import Decimal
                    t = "number" if isinstance(v, Decimal) else "text_or_formula"
                except Exception:  # pragma: no cover
                    t = "text_or_formula"
            # value rendering
            if t == "number":
                vr = repr(v)
            elif isinstance(v, str) and v.startswith("="):
                vr = "(formula)"  # value repr suppressed; formula on its own field
            else:
                vr = "(value_present)" if v is not None else "(empty)"
            # formula field
            formula = v if (isinstance(v, str) and v.startswith("=")) else "-"
            lines.append(f"{coord}\t{t}\t{vr}\t{formula}")
    return "\n".join(lines).encode("utf-8")


def build_fingerprint(workbook: Path, sheet: str) -> dict[str, Any]:
    """Compute the fingerprint dict for *sheet* in *workbook*."""
    wb = openpyxl.load_workbook(workbook, data_only=False, read_only=False)
    if sheet not in wb.sheetnames:
        raise KeyError(f"sheet {sheet!r} not in {workbook}; available: {wb.sheetnames[:5]}...")
    ws = wb[sheet]
    stream = _cell_stream(ws)
    return {
        "workbook_basename": workbook.name,
        "sheet": sheet,
        "rows": ws.max_row or 0,
        "cols": ws.max_column or 0,
        "total_cells": (ws.max_row or 0) * (ws.max_column or 0),
        "content_sha256": hashlib.sha256(stream).hexdigest(),
        "algorithm": "sha256 over per-cell (coord, type, value_repr, formula) stream, "
                     "sorted by coord. Value contents are NOT included for text/formula "
                     "cells — only their presence and formula string.",
        "note": "This fingerprint proves the control sheet reproduces byte-for-byte "
                "across runs, without recording any financial value. Rebuild by running "
                "tools/control_date_fingerprint.py against the real workbook.",
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    cap = sub.add_parser("capture", help="build and store a fingerprint")
    cap.add_argument("--workbook", required=True)
    cap.add_argument("--sheet", required=True)
    cap.add_argument("--out", required=True)

    ver = sub.add_parser("verify", help="compare against stored golden")
    ver.add_argument("--workbook", required=True)
    ver.add_argument("--sheet", required=True)
    ver.add_argument("--golden", required=True)

    args = p.parse_args()
    workbook = Path(args.workbook)
    if not workbook.is_file():
        print(f"workbook not found: {workbook}", file=sys.stderr)
        return 2

    try:
        current = build_fingerprint(workbook, args.sheet)
    except Exception as e:  # noqa: BLE001
        print(f"could not build fingerprint: {type(e).__name__}: {e}", file=sys.stderr)
        return 2

    if args.cmd == "capture":
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(current, indent=2, ensure_ascii=False),
                            encoding="utf-8")
        print(f"[capture] wrote {out_path}")
        print(f"[capture] sheet={current['sheet']} "
              f"dims={current['rows']}x{current['cols']} "
              f"cells={current['total_cells']} "
              f"sha256={current['content_sha256'][:12]}...")
        return 0

    # verify
    golden_path = Path(args.golden)
    if not golden_path.is_file():
        print(f"golden file not found: {golden_path}", file=sys.stderr)
        return 2
    golden = json.loads(golden_path.read_text(encoding="utf-8"))

    diffs: list[str] = []
    for key in ("sheet", "rows", "cols", "total_cells", "content_sha256"):
        if golden.get(key) != current.get(key):
            diffs.append(f"{key}: golden={golden.get(key)!r} current={current.get(key)!r}")

    if diffs:
        print("[verify] MISMATCH — control date no longer reproduces:")
        for d in diffs:
            print(f"  - {d}")
        return 1

    print(f"[verify] PASS — sheet {current['sheet']} reproduces "
          f"({current['rows']}x{current['cols']}={current['total_cells']} cells, "
          f"sha256={current['content_sha256'][:12]}...)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
