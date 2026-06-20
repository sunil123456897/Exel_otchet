"""Tests for core.app.partial — mark interrupted outputs as .partial."""

import os
from pathlib import Path

from core.app.partial import format_partial_note, mark_partial


class TestMarkPartial:
    def test_none_path(self):
        assert mark_partial(None) == []

    def test_nonexistent_path(self, tmp_path):
        assert mark_partial(tmp_path / "nonexistent.xlsx") == []

    def test_single_file(self, tmp_path):
        src = tmp_path / "report.xlsx"
        src.write_text("data")
        result = mark_partial(src)
        assert len(result) == 1
        assert ".partial" in result[0].name
        assert not src.exists()
        assert result[0].exists()

    def test_directory_renames_xlsx(self, tmp_path):
        d = tmp_path / "output"
        d.mkdir()
        (d / "a.xlsx").write_text("1")
        (d / "b.xlsx").write_text("2")
        (d / "c.txt").write_text("3")
        result = mark_partial(d)
        assert len(result) == 2
        assert (d / "c.txt").exists()

    def test_no_clobber_existing_partial(self, tmp_path):
        src = tmp_path / "report.xlsx"
        src.write_text("data")
        existing_partial = tmp_path / "report.partial.xlsx"
        existing_partial.write_text("old")
        result = mark_partial(src)
        assert len(result) == 1
        assert result[0].name != "report.partial.xlsx"
        assert existing_partial.exists()

    def test_empty_directory(self, tmp_path):
        d = tmp_path / "empty"
        d.mkdir()
        assert mark_partial(d) == []


class TestFormatPartialNote:
    def test_empty(self):
        assert format_partial_note([]) == ""

    def test_single_file(self):
        note = format_partial_note([Path("report.partial.xlsx")])
        assert "report.partial.xlsx" in note
        assert ".partial" in note

    def test_multiple_files(self):
        paths = [Path(f"f{i}.partial.xlsx") for i in range(5)]
        note = format_partial_note(paths)
        assert "5" in note
        assert "и ещё 2" in note

    def test_three_files_no_suffix(self):
        paths = [Path(f"f{i}.partial.xlsx") for i in range(3)]
        note = format_partial_note(paths)
        assert "и ещё" not in note
