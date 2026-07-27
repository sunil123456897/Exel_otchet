from __future__ import annotations

import re
from typing import Any

from openpyxl.cell.cell import Cell
from openpyxl.styles import Font

_LINK_FONT = Font(color="FF0563C1", underline="single")

# A URL scheme prefix such as http://, https://, ftp://, file://. Used to
# strip external hyperlink targets read from UNTRUSTED input workbooks.
_URL_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*://")


def sanitize_external_hyperlink(target: Any) -> str | None:
    """Neutralise dangerous hyperlink targets read from untrusted input files.

    Curator/master workbooks are external input: a malicious author can embed a
    ``=HYPERLINK(...)`` (or a cell hyperlink) whose target, once copied into a
    generated report and clicked, phones home or exfiltrates data. External URL
    schemes (``http(s)://``, ``ftp://``, ``file://``, any ``scheme://``) and
    ``mailto:`` have no legitimate use as a report "source" link and are
    dropped (returns ``None``).

    Local drive-letter paths (``Q:\\...``) and UNC paths (``\\\\server\\share``)
    are kept: both are supported source-root forms in this application, and
    blocking them would break legitimate links to files on the company file
    server. Internal in-document anchors (``#...``) are harmless and kept.

    (Residual risk: a UNC target still triggers NTLM auth on click. UNC is a
    first-class supported path form here, so it is intentionally allowed;
    tighten to a trusted-server allowlist if the threat model requires it.)
    """
    if not target:
        return None
    text = str(target).strip()
    if not text:
        return None
    if text.startswith("#"):
        return text
    lowered = text.lower()
    if lowered.startswith("mailto:"):
        return None
    if _URL_SCHEME_RE.match(text):
        return None
    return text


def build_excel_hyperlink(
    file_path: Any,
    sheet_name: Any = None,
    row_index: Any = None,
) -> str | None:
    if not file_path:
        return None
    # IMPORTANT: do NOT call Path.resolve() here. Until this was changed,
    # every row built its hyperlink via resolve(), which issues an os.stat
    # on the path. For RSCH reports with ~120k rows whose source_path
    # points at a network drive, that is ~120k synchronous SMB round-trips
    # — observed on a customer PC as a 10-minute hang after the 85%
    # progress mark (file collection finished fast; the freeze was here,
    # in sheet writing). The stored path is already absolute; Excel only
    # needs the string for its HYPERLINK formula, so we normalise purely
    # in-memory.
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
