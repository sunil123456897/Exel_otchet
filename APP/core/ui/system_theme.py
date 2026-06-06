"""Detect whether the OS is currently in dark mode.

Supports Windows 10/11 (registry query), macOS (osascript heuristic),
and Linux (gsettings heuristic for GNOME/Unity). On Windows 8 the
AppsUseLightTheme registry key does not exist, so the function returns
None and the caller is expected to fall back to a manual user choice
rather than guessing.

This module deliberately does not import any GUI toolkit; it is safe
to call from headless tests.
"""
from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
from typing import Optional

_logger = logging.getLogger(__name__)


def _windows_apps_use_light() -> Optional[bool]:
    """Read the Windows 10/11 AppsUseLightTheme registry value.

    Returns True if the system is in light mode, False for dark mode,
    None if the value is missing (typical of Windows 8/8.1) or the
    registry is inaccessible.
    """
    try:
        import winreg  # type: ignore[import-not-found]
    except ImportError:
        return None

    registry_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    value_name = "AppsUseLightTheme"

    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, registry_path) as key:
                value, _ = winreg.QueryValueEx(key, value_name)
                return bool(value)
        except FileNotFoundError:
            # Path or value missing — try the next root, or fall through.
            continue
        except OSError as e:
            _logger.debug("Registry query failed for %s: %s", root, e)
            return None
    return None


def _macos_appearance() -> Optional[bool]:
    """Return True for light, False for dark, None if unknown.

    Uses AppleScript which is universally available on macOS. Errors
    (no AppleScript, headless build agent) are swallowed and reported
    as unknown.
    """
    if not shutil.which("osascript"):
        return None
    try:
        result = subprocess.run(
            ["osascript", "-e", "tell application \"System Events\" to tell appearance preferences to get dark mode"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0:
            return None
        out = result.stdout.strip().lower()
        if "true" in out:
            return False
        if "false" in out:
            return True
        return None
    except (subprocess.TimeoutExpired, OSError) as e:
        _logger.debug("macOS appearance query failed: %s", e)
        return None


def _linux_gnome_dark() -> Optional[bool]:
    """Return True for light, False for dark, None if unknown.

    Only handles gsettings / GNOME-style desktop environments.
    """
    if not shutil.which("gsettings"):
        return None
    try:
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode != 0:
            return None
        out = result.stdout.strip().lower()
        if "dark" in out:
            return False
        if "default" in out or "light" in out or out == "''":
            return True
        return None
    except (subprocess.TimeoutExpired, OSError) as e:
        _logger.debug("gsettings query failed: %s", e)
        return None


def detect_system_theme() -> Optional[str]:
    """Return "light", "dark", or None when undetectable.

    None means the OS either does not publish a theme preference
    (Windows 8/8.1) or this code could not read it. Callers should
    treat None as "ask the user".
    """
    system = platform.system().lower()

    if system == "windows":
        is_light = _windows_apps_use_light()
        if is_light is None:
            _logger.info(
                "Windows theme preference not available "
                "(likely Windows 8/8.1). User must choose."
            )
            return None
        return "light" if is_light else "dark"

    if system == "darwin":
        is_light = _macos_appearance()
        if is_light is None:
            return None
        return "light" if is_light else "dark"

    if system == "linux":
        is_light = _linux_gnome_dark()
        if is_light is None:
            return None
        return "light" if is_light else "dark"

    return None


def is_windows_8_or_earlier() -> bool:
    """Return True when running on Windows 8/8.1 or earlier.

    Used to decide whether to surface the "auto-follow system" option
    in the UI: on Win 8 the registry lookup will always return None,
    so the user must pick manually.
    """
    if platform.system().lower() != "windows":
        return False
    release, _, _ = platform.windows_version()
    try:
        return int(release) <= 6  # Win 8 = 6.2, Win 7 = 6.1
    except ValueError:
        return False


__all__ = [
    "detect_system_theme",
    "is_windows_8_or_earlier",
]
