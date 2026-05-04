from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl.cell.cell import Cell
from openpyxl.styles import Font

_LINK_FONT = Font(color="FF0563C1", underline="single")


def build_excel_hyperlink(
    file_path: Any,
    sheet_name: Any = None,
    row_index: Any = None,
) -> str | None:
    if not file_path:
        return None
    try:
        return str(Path(str(file_path)).resolve())
    except (OSError, RuntimeError, ValueError):
        return str(file_path)


def extract_hyperlink_formula_parts(value: Any) -> tuple[str, str] | None:
    if not isinstance(value, str) or not value.startswith("=HYPERLINK("):
        return None
    inner = value.removeprefix("=HYPERLINK(").removesuffix(")")
    if not inner.startswith('"'):
        return None
    parts: list[str] = []
    curr: list[str] = []
    idx = 1
    while idx < len(inner):
        char = inner[idx]
        if char == '"':
            if idx + 1 < len(inner) and inner[idx + 1] == '"':
                curr.append('"')
                idx += 2
                continue
            parts.append("".join(curr))
            idx += 1
            if idx >= len(inner) or inner[idx] != ",":
                break
            idx += 1
            if idx >= len(inner) or inner[idx] != '"':
                break
            curr = []
            idx += 1
            continue
        curr.append(char)
        idx += 1
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


def apply_cell_hyperlink(
    cell: Cell,
    file_path: Any,
    sheet_name: Any = None,
    row_index: Any = None,
) -> None:
    hyperlink = build_excel_hyperlink(file_path, sheet_name, row_index)
    if not hyperlink:
        return
    cell.hyperlink = hyperlink
    cell.font = _LINK_FONT
