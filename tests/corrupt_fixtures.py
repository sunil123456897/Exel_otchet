"""Stage 3 / MR-0302 — fixtures for corrupted / bloated workbooks.

We do NOT commit binary .xlsx fixtures (they bloat the repo and would
have to be hand-edited). Instead every fixture is built programmatically
from a tiny in-memory template so a regression is reproducible and
inspector-friendly.

Each builder writes a single ``.xlsx`` (or malformed file) into a target
directory and returns its path. The paths are designed to be fed
straight into ``IngestionEngine.read_file`` / ``CalamineReader.read`` to
verify the reader fails soft instead of crashing the process.

The categories mirror TZ MR-0302:

1. invalid_zip_signature     — random bytes, not an xlsx
2. truncated_archive         — real xlsx truncated mid-stream
3. missing_xml               — zip intact but xl/workbook.xml removed
4. huge_used_range           — sheet claims 1 048 576 rows
5. many_empty_formatted_rows — thousands of styled but empty rows
6. hidden_sheet              — a sheet with ``sheetState="hidden"``
7. formula_without_cache     — formula cell whose cached value is missing
8. protected_workbook        — workbook protection flag set (no password)
9. temp_dollar_lock          — Excel-editor lock file ``~$book.xlsx``
"""
from __future__ import annotations

import struct
import zipfile
from pathlib import Path

import openpyxl


def build_invalid_zip_signature(target_dir: Path, name: str = "invalid_sig.xlsx") -> Path:
    """Random bytes that don't have the xlsx ZIP magic."""
    p = target_dir / name
    p.write_bytes(b"NOT_AN_XLSX_FILE" * 64)
    return p


def build_truncated_archive(target_dir: Path, name: str = "truncated.xlsx") -> Path:
    """Real xlsx chopped at ~50% so the ZIP central directory is missing."""
    src = target_dir / "_src_for_trunc.xlsx"
    openpyxl.Workbook().save(src)
    raw = src.read_bytes()
    src.unlink()
    half = len(raw) // 2
    p = target_dir / name
    p.write_bytes(raw[:half])
    return p


def build_missing_xml(target_dir: Path, name: str = "missing_xml.xlsx") -> Path:
    """Valid zip but ``xl/workbook.xml`` removed — openpyxl/calamine can't
    enumerate sheets."""
    src = target_dir / "_src_for_missing.xlsx"
    openpyxl.Workbook().save(src)
    p = target_dir / name
    with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == "xl/workbook.xml":
                continue
            zout.writestr(item, zin.read(item.filename))
    src.unlink()
    return p


def build_huge_used_range(target_dir: Path, name: str = "huge_used_range.xlsx") -> Path:
    """Sheet whose ``<dimension ref>`` claims the full 1 048 576 rows.

    We don't actually fill a million rows (that would be a multi-MB file);
    we just lie in the dimension tag. A naive reader that pre-allocates
    ``max_row`` rows will OOM. The test asserts the reader handles this
    gracefully instead of allocating."""
    src = target_dir / "_src_for_huge.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "x"
    wb.save(src)

    p = target_dir / name
    raw = src.read_bytes()
    src.unlink()
    patched = raw.replace(
        b'<dimension ref="A1:A1"',
        b'<dimension ref="A1:A1048576"',
    )
    if patched == raw:
        patched = raw.replace(
            b"<sheetData",
            b'<dimension ref="A1:A1048576"/><sheetData',
            1,
        )
    p.write_bytes(patched)
    return p


def build_many_empty_formatted_rows(
    target_dir: Path, name: str = "many_empty_formatted.xlsx", rows: int = 2000,
) -> Path:
    """Thousands of styled but empty rows."""
    wb = openpyxl.Workbook()
    ws = wb.active
    fill = openpyxl.styles.PatternFill(fill_type="solid", fgColor="FFFF00")
    for r in range(1, rows + 1):
        for c in range(1, 6):
            ws.cell(row=r, column=c).fill = fill
    p = target_dir / name
    wb.save(p)
    return p


def build_hidden_sheet(target_dir: Path, name: str = "hidden_sheet.xlsx") -> Path:
    """A workbook with one visible and one hidden sheet."""
    wb = openpyxl.Workbook()
    ws_vis = wb.active
    ws_vis.title = "01.01.2026"
    ws_vis["A1"] = "visible"
    ws_hid = wb.create_sheet("hidden")
    ws_hid["A1"] = "hidden"
    ws_hid.sheet_state = "hidden"
    p = target_dir / name
    wb.save(p)
    return p


def build_formula_without_cache(
    target_dir: Path, name: str = "formula_no_cache.xlsx",
) -> Path:
    """A formula cell with no cached value."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws["A1"] = "=1+1"
    p = target_dir / name
    wb.save(p)
    return p


def build_protected_workbook(target_dir: Path, name: str = "protected.xlsx") -> Path:
    """Set the workbook protection flag (no password)."""
    wb = openpyxl.Workbook()
    try:
        wb.security.workbookPassword = ""  # type: ignore[attr-defined]
        wb.security.lockStructure = True   # type: ignore[attr-defined]
    except Exception:
        pass
    p = target_dir / name
    wb.save(p)
    return p


def build_temp_dollar_lock(
    target_dir: Path, original_name: str = "book.xlsx",
) -> tuple[Path, Path]:
    """Create a real ``book.xlsx`` plus its Excel-editor lock file ``~$book.xlsx``.

    The ``~$`` file is a tiny OLE Compound Document signature — Excel uses
    it as an ownership marker, not a workbook. Any directory walker must
    skip ``~$`` files to avoid trying to parse them.
    """
    book = target_dir / original_name
    openpyxl.Workbook().save(book)
    lock = target_dir / f"~${original_name}"
    # First 8 bytes mimic an OLE2 compound document header.
    lock.write_bytes(struct.pack("<BBB", 0xD0, 0xCF, 0x11) + b"\x00" * 100)
    return book, lock


CORRUPT_FIXTURE_BUILDERS: dict[str, callable] = {
    "invalid_zip_signature": build_invalid_zip_signature,
    "truncated_archive": build_truncated_archive,
    "missing_xml": build_missing_xml,
    "huge_used_range": build_huge_used_range,
    "many_empty_formatted_rows": build_many_empty_formatted_rows,
    "hidden_sheet": build_hidden_sheet,
    "formula_without_cache": build_formula_without_cache,
    "protected_workbook": build_protected_workbook,
}
