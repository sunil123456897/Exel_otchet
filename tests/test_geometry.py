"""Tests for the window-geometry persistence layer.

We exercise the roundtrip (save -> load -> is_visible) with a
temporary file and never touch a real Tk root.
"""
from pathlib import Path

import pytest

from core.ui.geometry import (
    is_geometry_visible,
    load_geometry,
    save_geometry,
    _parse_geometry,
)


def test_parse_geometry_valid():
    assert _parse_geometry("1100x840+100+50") == (1100, 840, 100, 50)
    assert _parse_geometry("800x600-10-20") == (800, 600, -10, -20)


def test_parse_geometry_invalid():
    assert _parse_geometry("not a geometry") is None
    assert _parse_geometry("") is None
    assert _parse_geometry("1100x840") is None
    assert _parse_geometry("axb+1+2") is None


def test_save_then_load_roundtrip(tmp_path: Path):
    path = tmp_path / "geom.txt"
    save_geometry("1200x900+50+50", file_path=path)
    assert load_geometry(file_path=path) == "1200x900+50+50"


def test_load_returns_none_when_file_missing(tmp_path: Path):
    assert load_geometry(file_path=tmp_path / "nope.txt") is None


def test_load_returns_none_on_malformed(tmp_path: Path):
    path = tmp_path / "geom.txt"
    path.write_text("garbage", encoding="utf-8")
    assert load_geometry(file_path=path) is None


def test_save_rejects_malformed(tmp_path: Path):
    path = tmp_path / "geom.txt"
    save_geometry("garbage", file_path=path)
    assert not path.exists()


def test_is_geometry_visible_inside_screen():
    assert is_geometry_visible("800x600+10+10", 1920, 1080) is True


def test_is_geometry_visible_fully_off_screen():
    assert is_geometry_visible("800x600+2000+2000", 1920, 1080) is False


def test_is_geometry_visible_partial_overlap_counts_as_visible():
    # Title-bar overlap is enough — the user can drag the window back.
    assert is_geometry_visible("800x600+1800+100", 1920, 1080) is True


def test_is_geometry_visible_too_small():
    assert is_geometry_visible("50x50+0+0", 1920, 1080) is False


def test_is_geometry_visible_garbage_returns_false():
    assert is_geometry_visible("not a geom", 1920, 1080) is False
