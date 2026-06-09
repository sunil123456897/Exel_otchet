"""Regression: OperationStatusBar must live at the bottom of the root window.

Prior to commit feat-ui-bottom-status-bar, the OperationStatusBar was
packed into the sidebar. The sidebar's scrollable canvas consumed all
visible vertical space with ``fill=tk.BOTH, expand=True``, so the
progress bar got squeezed below the visible area and the user could
not see it during operations.

The fix: pack the status bar into the root window with
``side=tk.BOTTOM``. This pins it to the bottom of the main window,
always visible regardless of the active tab or the window height.

This test pins the new parent by re-parsing gui_master.setup_ui to
make sure no future refactor accidentally moves the bar back into the
sidebar (the regression that hid the progress indicator in the first
place).
"""
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "APP"
sys.path.insert(0, str(APP_DIR))


def _read_gui_master() -> str:
    return (APP_DIR / "core" / "ui" / "gui_master.py").read_text(
        encoding="utf-8"
    )


def test_status_bar_pack_uses_root_and_bottom():
    """The status bar must be packed into the root window from the side=BOTTOM,
    not into the sidebar."""
    src = _read_gui_master()

    # 1. OperationStatusBar must be constructed with self.root, not self.sidebar.
    match = re.search(
        r"self\.status_bar\s*=\s*OperationStatusBar\(\s*([^,)]+)",
        src,
    )
    assert match is not None, (
        "OperationStatusBar instantiation in gui_master.py not found."
    )
    parent = match.group(1).strip()
    assert parent == "self.root", (
        f"OperationStatusBar parent is {parent!r}; expected 'self.root' "
        "so the bar sits at the bottom of the main window and is always "
        "visible during operations. Packing it into the sidebar hides it "
        "behind the scrollable canvas."
    )


def test_status_bar_packs_to_bottom():
    """The status bar must be packed with side=tk.BOTTOM so it stays anchored
    at the bottom edge of the window."""
    src = _read_gui_master()

    # 2. The pack call for status_bar must include side=tk.BOTTOM.
    match = re.search(
        r"self\.status_bar\.pack\(([^)]+)\)", src, re.DOTALL
    )
    assert match is not None, "status_bar.pack() call not found."
    pack_args = match.group(1)
    assert "side=tk.BOTTOM" in pack_args, (
        f"status_bar.pack() must include 'side=tk.BOTTOM' to anchor the "
        f"progress indicator at the window edge. Got: {pack_args!r}"
    )


def test_status_bar_uses_status_bar_style():
    """The status bar widget must use the StatusBar style so it picks up the
    bg_panel color (visual separation from the main area)."""
    from core.ui.operation_status_bar import OperationStatusBar
    from core.ui.operation_state import OperationState

    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    try:
        op_state = OperationState()
        bar = OperationStatusBar(root, op_state, on_cancel=lambda: None)
        try:
            assert str(bar["style"]) == "StatusBar.TFrame", (
                f"OperationStatusBar must be configured with style "
                f"'StatusBar.TFrame', got {bar['style']!r}. The old "
                "'Sidebar.TFrame' style blends into the sidebar and is "
                "invisible when the bar is moved into the root window."
            )
        finally:
            bar.destroy()
    finally:
        root.destroy()
