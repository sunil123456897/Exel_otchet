"""Tests for the system theme detector.

The detector never imports GUI code, so we can drive every platform
branch through ``patch``.
"""
import platform

from core.ui.system_theme import (
    detect_system_theme,
    is_windows_8_or_earlier,
)


def test_detect_windows_light_when_registry_value_1(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr("core.ui.system_theme._windows_apps_use_light", lambda: True)
    assert detect_system_theme() == "light"


def test_detect_windows_dark_when_registry_value_0(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr("core.ui.system_theme._windows_apps_use_light", lambda: False)
    assert detect_system_theme() == "dark"


def test_detect_windows_8_falls_back_to_none(monkeypatch):
    """On Windows 8 the registry key is absent, so detection fails.

    The caller (ThemeManager) treats ``None`` as 'ask the user'.
    """
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr("core.ui.system_theme._windows_apps_use_light", lambda: None)
    assert detect_system_theme() is None


def test_detect_macos_light(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr("core.ui.system_theme._macos_appearance", lambda: True)
    assert detect_system_theme() == "light"


def test_detect_macos_dark(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr("core.ui.system_theme._macos_appearance", lambda: False)
    assert detect_system_theme() == "dark"


def test_detect_linux_dark(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr("core.ui.system_theme._linux_gnome_dark", lambda: False)
    assert detect_system_theme() == "dark"


def test_detect_unknown_os_returns_none(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Plan9")
    assert detect_system_theme() is None


def test_is_windows_8_or_earlier_on_windows_8(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    # Win 8 surfaces through ``platform.release`` as the user-visible
    # version "8" (the kernel 6.2 is hidden from Python 3.13+).
    monkeypatch.setattr(platform, "release", lambda: "8", raising=False)
    assert is_windows_8_or_earlier() is True


def test_is_windows_8_or_earlier_on_windows_7(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(platform, "release", lambda: "7", raising=False)
    assert is_windows_8_or_earlier() is True


def test_is_windows_8_or_earlier_on_windows_10(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Windows")
    monkeypatch.setattr(platform, "release", lambda: "10", raising=False)
    assert is_windows_8_or_earlier() is False


def test_is_windows_8_or_earlier_on_linux(monkeypatch):
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    assert is_windows_8_or_earlier() is False


def test_windows_apps_use_light_handles_missing_winreg(monkeypatch):
    """The detector must not raise on a non-Windows runtime."""
    import builtins

    from core.ui.system_theme import _windows_apps_use_light

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "winreg":
            raise ImportError("no winreg")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert _windows_apps_use_light() is None
