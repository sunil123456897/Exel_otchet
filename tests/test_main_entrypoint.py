from pathlib import Path


def test_main_uses_lazy_gui_imports_and_preflight_hook():
    source = Path("E:/Dlia Dashi/Version5/APP/main.py").read_text(encoding="utf-8")

    assert "def preflight_gui_imports():" in source
    assert "from core.ui.gui_master import GuiMaster" in source
    assert source.index("from core.ui.gui_master import GuiMaster") > source.index(
        "def preflight_gui_imports():"
    )
