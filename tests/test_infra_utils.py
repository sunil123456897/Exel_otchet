"""Tests for core.infra.utils — file utilities and caching helpers."""

from pathlib import Path
from types import SimpleNamespace

from core.infra.utils import (
    _is_configured_drive_path,
    _is_network_path,
    file_content_fingerprint,
    is_file_writable,
    path_exists_with_timeout,
    _cache_copy_is_fresh,
)


class TestIsConfiguredDrivePath:
    def test_matching_drive(self):
        assert _is_configured_drive_path("Q:\\path", ("Q",)) is True

    def test_non_matching_drive(self):
        assert _is_configured_drive_path("C:\\path", ("Q",)) is False

    def test_short_path(self):
        assert _is_configured_drive_path("Q", ("Q",)) is False

    def test_case_insensitive(self):
        assert _is_configured_drive_path("q:\\path", ("Q",)) is True

    def test_drive_letter_cleanup(self):
        assert _is_configured_drive_path("Q:\\path", ("Q:\\",)) is True
        assert _is_configured_drive_path("Q:\\path", ("Q:",)) is True


class TestIsNetworkPath:
    def test_unc_path(self):
        assert _is_network_path("\\\\server\\share", ()) is True

    def test_configured_drive(self):
        assert _is_network_path("Q:\\data", ("Q",)) is True

    def test_local_path(self):
        assert _is_network_path("C:\\data", ("Q",)) is False

    def test_relative_path(self):
        assert _is_network_path("relative/path", ()) is False


class TestFileContentFingerprint:
    def test_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        fp = file_content_fingerprint(f)
        assert fp is not None
        assert len(fp) == 64

    def test_same_content_same_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("identical")
        f2.write_text("identical")
        assert file_content_fingerprint(f1) == file_content_fingerprint(f2)

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("aaa")
        f2.write_text("bbb")
        assert file_content_fingerprint(f1) != file_content_fingerprint(f2)

    def test_nonexistent_file(self):
        assert file_content_fingerprint("/nonexistent/file.txt") is None

    def test_string_path(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("data")
        assert file_content_fingerprint(str(f)) is not None


class TestIsFileWritable:
    def test_nonexistent_file(self, tmp_path):
        assert is_file_writable(str(tmp_path / "new.txt")) is True

    def test_writable_file(self, tmp_path):
        f = tmp_path / "w.txt"
        f.write_text("data")
        assert is_file_writable(str(f)) is True


class TestPathExistsWithTimeout:
    def test_existing_path(self, tmp_path):
        f = tmp_path / "exists.txt"
        f.write_text("hi")
        assert path_exists_with_timeout(str(f)) is True

    def test_nonexistent_path(self, tmp_path):
        assert path_exists_with_timeout(str(tmp_path / "nope.txt")) is False

    def test_directory(self, tmp_path):
        assert path_exists_with_timeout(str(tmp_path)) is True


class TestCacheCopyIsFresh:
    def test_fresh_copy(self, tmp_path):
        f = tmp_path / "cached.xlsx"
        f.write_text("data")
        import os
        stat = os.stat(f)
        assert _cache_copy_is_fresh(f, str(f), stat) is True

    def test_stale_by_size(self, tmp_path):
        f = tmp_path / "cached.xlsx"
        f.write_text("data")
        fake_stat = SimpleNamespace(st_mtime=0, st_size=99999)
        assert _cache_copy_is_fresh(f, "remote", fake_stat) is False

    def test_nonexistent_local(self, tmp_path):
        fake_stat = SimpleNamespace(st_mtime=0, st_size=0)
        assert _cache_copy_is_fresh(tmp_path / "nope", "remote", fake_stat) is False
