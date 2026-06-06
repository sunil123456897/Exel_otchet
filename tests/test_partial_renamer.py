"""Tests for the ``.partial.xlsx`` renamer used by cancel flow."""
import shutil
import tempfile
import unittest
from pathlib import Path

from core.app.partial import mark_partial, format_partial_note


class MarkPartialFileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_mark_partial_file(self):
        f = self.tmp / "Master_2025-01-15.xlsx"
        f.write_text("x")
        result = mark_partial(f)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "Master_2025-01-15.partial.xlsx")
        self.assertFalse(f.exists())
        self.assertTrue(result[0].exists())

    def test_mark_partial_file_with_collision_uses_counter(self):
        base = self.tmp / "Master_2025-01-15.xlsx"
        partial = self.tmp / "Master_2025-01-15.partial.xlsx"
        base.write_text("orig")
        partial.write_text("pre-existing")
        result = mark_partial(base)
        self.assertEqual(len(result), 1)
        # The first .partial slot is taken by the pre-existing file, so
        # the renamer falls back to .partial.1.
        self.assertEqual(result[0].name, "Master_2025-01-15.partial.1.xlsx")
        self.assertTrue(result[0].exists())
        self.assertEqual(result[0].read_text(), "orig")
        # Pre-existing partial must be preserved.
        self.assertTrue(partial.exists())

    def test_mark_partial_missing_file_returns_empty(self):
        f = self.tmp / "does_not_exist.xlsx"
        self.assertEqual(mark_partial(f), [])

    def test_mark_partial_directory_marks_all_xlsx(self):
        d = self.tmp / "out"
        d.mkdir()
        (d / "a.xlsx").write_text("a")
        (d / "b.xlsx").write_text("b")
        (d / "c.txt").write_text("c")
        result = mark_partial(d)
        self.assertEqual(len(result), 2)
        names = {p.name for p in result}
        self.assertIn("a.partial.xlsx", names)
        self.assertIn("b.partial.xlsx", names)
        # Non-xlsx files are left alone.
        self.assertTrue((d / "c.txt").exists())
        self.assertFalse((d / "a.xlsx").exists())


class FormatPartialNoteTests(unittest.TestCase):
    def test_no_partials(self):
        self.assertEqual(format_partial_note([]), "")
        self.assertEqual(format_partial_note(None), "")

    def test_single_partial(self):
        text = format_partial_note([Path("/tmp/foo.partial.xlsx")])
        self.assertIn("Неполный файл", text)
        self.assertIn("foo.partial.xlsx", text)

    def test_multiple_partials(self):
        paths = [
            Path("/tmp/a.partial.xlsx"),
            Path("/tmp/b.partial.xlsx"),
        ]
        text = format_partial_note(paths)
        self.assertIn("a.partial.xlsx", text)
        self.assertIn("b.partial.xlsx", text)

    def test_truncates_long_lists(self):
        paths = [Path(f"/tmp/file_{i}.partial.xlsx") for i in range(20)]
        text = format_partial_note(paths)
        # Should not blow up; should mention the first few and an ellipsis.
        self.assertIn("file_0.partial.xlsx", text)
        # Avoid listing every single file — keep the message short.
        self.assertLess(len(text), 800)


if __name__ == "__main__":
    unittest.main()
