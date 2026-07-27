"""Hyperlink generation must not hit the network per row.

Root cause of the customer's "РСЧ за период hangs after 85%":
build_excel_hyperlink called Path(file_path).resolve() for every row.
For ~120k rows whose source_path points at a network drive (I:\\...),
each resolve() is a synchronous SMB round-trip (~5ms). 120k × 5ms =
600s ≈ the exact 10-minute hang observed in ДИАГНОСТИКА_ОТЧЁТ.

resolve() is pointless here: the stored path is already absolute, and
Excel only needs the string for its HYPERLINK formula. We replace it
with a pure string normalisation that never touches the filesystem.

This test guards the regression by counting os.stat / os.lstat calls
(stubbed) while building hyperlinks for many rows, and by asserting the
output is still a usable absolute path string.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "APP"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from core.infra.excel_hyperlinks import (  # noqa: E402
    apply_cell_hyperlink,
    build_excel_hyperlink,
)

NET_PATH = r"I:\!! РСЧ всех для программиста\!!РСЧ Ханде.xlsx"


def test_build_hyperlink_returns_absolute_path_string():
    """Output must be the path as a usable absolute string."""
    link = build_excel_hyperlink(NET_PATH)
    assert link is not None
    assert isinstance(link, str)
    # Still identifies the same file (absolute, drive letter preserved).
    assert link.lower().replace("\\", "/").endswith("ханде.xlsx")


def test_build_hyperlink_handles_none_and_empty():
    assert build_excel_hyperlink(None) is None
    assert build_excel_hyperlink("") is None


def test_build_hyperlink_does_not_touch_filesystem_for_many_rows():
    """Building N hyperlinks must not make N filesystem (network) calls.

    This is the direct regression guard for the customer hang. Before the
    fix, Path.resolve() issued an os.stat per row on the network path.
    """
    stat_calls = {"count": 0}

    def counting_stat(path, *args, **kwargs):
        stat_calls["count"] += 1
        # Pretend the network path is unreachable so resolve() can't
        # succeed even if it tries — it must not try.
        raise FileNotFoundError(path)

    def counting_lstat(path, *args, **kwargs):
        stat_calls["count"] += 1
        raise FileNotFoundError(path)

    N = 2000
    with patch("os.stat", counting_stat), patch("os.lstat", counting_lstat):
        for _ in range(N):
            build_excel_hyperlink(NET_PATH)

    # Zero filesystem probes: the path is already absolute, nothing to
    # resolve. A non-zero count here means resolve() (or realpath) is
    # back, and the customer's 10-minute hang returns.
    assert stat_calls["count"] == 0, (
        f"build_excel_hyperlink made {stat_calls['count']} filesystem calls "
        f"for {N} rows — must be 0 to avoid per-row network round-trips"
    )


def test_apply_cell_hyperlink_sets_link_without_network():
    """End-to-end: applying a hyperlink to a cell must not stat the path."""
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    stat_calls = {"count": 0}

    def counting_stat(path, *args, **kwargs):
        stat_calls["count"] += 1
        raise FileNotFoundError(path)

    with patch("os.stat", counting_stat), patch("os.lstat", counting_stat):
        for i in range(1, 501):
            ws.cell(i, 1, f"row{i}")
            apply_cell_hyperlink(ws.cell(i, 1), NET_PATH, "Sheet1", i)

    assert stat_calls["count"] == 0
    # And the cell actually got a hyperlink set.
    assert ws.cell(1, 1).hyperlink is not None


# --- Security: external hyperlink targets from untrusted files -----------
# Curator/master workbooks are EXTERNAL input. A malicious author can embed a
# HYPERLINK whose target, once clicked in the generated reconciliation report,
# exfiltrates data (e.g. an http(s) beacon). sanitize_external_hyperlink drops
# external URL schemes and mailto, while keeping legitimate local drive-letter
# and UNC paths (both are supported source-root forms in this app) and internal
# in-document anchors.


def test_sanitize_blocks_external_url_schemes():
    from core.infra.excel_hyperlinks import sanitize_external_hyperlink

    assert sanitize_external_hyperlink("http://evil.example/x") is None
    assert sanitize_external_hyperlink("https://evil.example/x") is None
    assert sanitize_external_hyperlink("HTTP://EVIL.EXAMPLE") is None
    assert sanitize_external_hyperlink("ftp://evil.example/x") is None
    assert sanitize_external_hyperlink("file://C:/secret.xlsx") is None
    assert sanitize_external_hyperlink("mailto:attacker@example.com") is None


def test_sanitize_keeps_legitimate_local_and_unc_paths():
    from core.infra.excel_hyperlinks import sanitize_external_hyperlink

    # Drive-letter path (the normal case for mapped source roots).
    kept = sanitize_external_hyperlink(r"Q:\Отчет кураторов 1\file.xlsx")
    assert kept is not None and kept.endswith("file.xlsx")
    # UNC to a company file server is a supported source-root form — kept.
    assert sanitize_external_hyperlink(r"\\server\share\file.xlsx") is not None
    # Internal in-document anchor — harmless, kept.
    assert sanitize_external_hyperlink("#'Лист1'!A1") == "#'Лист1'!A1"


def test_sanitize_handles_none_and_empty():
    from core.infra.excel_hyperlinks import sanitize_external_hyperlink

    assert sanitize_external_hyperlink(None) is None
    assert sanitize_external_hyperlink("") is None
    assert sanitize_external_hyperlink("   ") is None


def test_cell_hyperlink_target_blocks_external_scheme():
    """End-to-end at the untrusted boundary: a =HYPERLINK cell in an input
    workbook pointing at an external URL must NOT propagate into the report."""
    import openpyxl
    from core.infra.reconciliation._collect import _cell_hyperlink_target

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.cell(1, 1, '=HYPERLINK("http://evil.example/steal","Источник")')
    assert _cell_hyperlink_target(ws, 1, 1) is None

    # A legitimate local source link still passes through.
    ws.cell(2, 1, '=HYPERLINK("Q:\\Отчет\\src.xlsx","Источник")')
    tgt = _cell_hyperlink_target(ws, 2, 1)
    assert tgt is not None and tgt.endswith("src.xlsx")
    wb.close()
