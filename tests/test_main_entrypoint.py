from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import main as app_main

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_main_uses_lazy_gui_imports_and_preflight_hook():
    source = (REPO_ROOT / "APP" / "main.py").read_text(encoding="utf-8")

    assert "def preflight_gui_imports():" in source
    assert "from core.ui.gui_master import GuiMaster" in source
    assert source.index("from core.ui.gui_master import GuiMaster") > source.index(
        "def preflight_gui_imports():"
    )


def test_preflight_gui_imports_returns_gui_master():
    assert app_main.preflight_gui_imports().__name__ == "GuiMaster"


def test_main_starts_gui_and_shutdowns_on_window_close():
    root = MagicMock()
    app_ctl = MagicMock()
    gui_master = MagicMock()

    with (
        patch("main.preflight_gui_imports", return_value=gui_master),
        patch("main.Bootstrap.setup", return_value=(MagicMock(), app_ctl, MagicMock())),
        patch("main.tk.Tk", return_value=root),
    ):
        app_main.main()

    gui_master.assert_called_once()
    root.protocol.assert_called_once()
    root.mainloop.assert_called_once()

    _event_name, on_close = root.protocol.call_args[0]
    on_close()
    app_ctl.shutdown.assert_called_once()
    root.destroy.assert_called_once()


def test_main_window_close_still_destroys_root_when_shutdown_fails():
    root = MagicMock()
    app_ctl = MagicMock()
    app_ctl.shutdown.side_effect = RuntimeError("shutdown failed")

    with (
        patch("main.preflight_gui_imports", return_value=MagicMock()),
        patch("main.Bootstrap.setup", return_value=(MagicMock(), app_ctl, MagicMock())),
        patch("main.tk.Tk", return_value=root),
    ):
        app_main.main()

    _event_name, on_close = root.protocol.call_args[0]
    on_close()
    app_ctl.shutdown.assert_called_once()
    root.destroy.assert_called_once()


def test_main_shutdowns_controller_on_startup_failure():
    app_ctl = MagicMock()

    with (
        patch("main.preflight_gui_imports", return_value=MagicMock()),
        patch("main.Bootstrap.setup", return_value=(MagicMock(), app_ctl, MagicMock())),
        patch("main.tk.Tk", side_effect=RuntimeError("tk failed")),
        pytest.raises(SystemExit),
    ):
        app_main.main()

    app_ctl.shutdown.assert_called_once()
