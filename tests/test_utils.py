from pathlib import Path
from unittest.mock import patch
import os

from core.infra.utils import (
    _cache_copy_is_fresh,
    cleanup_local_copy_cache,
    get_local_copy,
    is_file_writable,
)


def test_is_file_writable_returns_true_for_missing_file(tmp_path):
    missing = tmp_path / "missing.xlsx"
    assert is_file_writable(str(missing)) is True


def test_is_file_writable_returns_true_for_existing_file(tmp_path):
    existing = tmp_path / "existing.xlsx"
    existing.write_text("x", encoding="utf-8")
    assert is_file_writable(str(existing)) is True


def test_get_local_copy_returns_input_for_empty_path():
    assert get_local_copy("") == ("", None)


def test_get_local_copy_returns_input_for_non_network_path(tmp_path):
    local = tmp_path / "report.xlsx"
    local.write_text("x", encoding="utf-8")
    path = str(local)
    assert get_local_copy(path) == (path, None)


def test_get_local_copy_uses_custom_drive_letters(tmp_path):
    network_path = r"R:\share\report.xlsx"
    cache_file = tmp_path / "cached.xlsx"

    with (
        patch("core.infra.utils._CACHE_DIR", tmp_path),
        patch("core.infra.utils.hashlib.md5") as mock_md5,
        patch("core.infra.utils.shutil.copy2") as mock_copy,
    ):
        mock_md5.return_value.hexdigest.return_value = "cached"
        local_path, temp_file = get_local_copy(
            network_path,
            drive_letters=("R",),
            remote_mtime=1000.0,
            remote_size=10,
        )

    assert local_path == str(cache_file)
    assert temp_file is None
    mock_copy.assert_called_once_with(network_path, str(cache_file))


def test_get_local_copy_treats_relative_q_prefixed_file_as_local(tmp_path, monkeypatch):
    local = tmp_path / "Q_local_report.xlsx"
    local.write_text("x", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    assert get_local_copy(local.name) == (local.name, None)


def test_get_local_copy_returns_original_when_remote_stat_fails():
    network_path = r"\\server\share\report.xlsx"
    with patch("core.infra.utils.os.stat", side_effect=OSError("offline")):
        assert get_local_copy(network_path) == (network_path, None)


def test_get_local_copy_uses_provided_remote_metadata_without_stat(tmp_path):
    network_path = r"\\server\share\report.xlsx"
    cache_file = tmp_path / "cached.xlsx"
    original_stat = os.stat

    def stat_side_effect(path, *args, **kwargs):
        if str(path) == network_path:
            raise AssertionError("remote stat must not be called")
        return original_stat(path, *args, **kwargs)

    with (
        patch("core.infra.utils._CACHE_DIR", tmp_path),
        patch("core.infra.utils.hashlib.md5") as mock_md5,
        patch("core.infra.utils.shutil.copy2") as mock_copy,
        patch("core.infra.utils.os.stat", side_effect=stat_side_effect),
    ):
        mock_md5.return_value.hexdigest.return_value = "cached"
        local_path, temp_file = get_local_copy(
            network_path,
            remote_mtime=1000.0,
            remote_size=10,
        )

    assert local_path == str(cache_file)
    assert temp_file is None
    mock_copy.assert_called_once_with(network_path, str(cache_file))


def test_get_local_copy_reuses_cache_when_fresh(tmp_path):
    network_path = r"\\server\share\report.xlsx"
    cache_file = tmp_path / "cached.xlsx"
    cache_file.write_text("cached", encoding="utf-8")

    class _Stat:
        def __init__(self, size, mtime):
            self.st_size = size
            self.st_mtime = mtime

    remote_stat = _Stat(10, 1000.0)
    cached_stat = _Stat(10, 1000.0)

    original_stat = os.stat

    def stat_side_effect(path, *args, **kwargs):
        p = str(path)
        if p == network_path:
            return remote_stat
        if Path(path) == cache_file:
            return cached_stat
        return original_stat(path, *args, **kwargs)

    with (
        patch("core.infra.utils._CACHE_DIR", tmp_path),
        patch("core.infra.utils.hashlib.md5") as mock_md5,
        patch("core.infra.utils.os.stat", side_effect=stat_side_effect),
    ):
        mock_md5.return_value.hexdigest.return_value = "cached"
        local_path, temp_file = get_local_copy(network_path)

    assert local_path == str(cache_file)
    assert temp_file is None


def test_get_local_copy_invalidates_stale_cache_and_copies(tmp_path):
    network_path = r"\\server\share\report.xlsx"
    cache_file = tmp_path / "cached.xlsx"
    cache_file.write_text("stale", encoding="utf-8")

    class _Stat:
        def __init__(self, size, mtime):
            self.st_size = size
            self.st_mtime = mtime

    remote_stat = _Stat(20, 2000.0)
    stale_cached_stat = _Stat(10, 1000.0)

    original_stat = os.stat

    def stat_side_effect(path, *args, **kwargs):
        p = str(path)
        if p == network_path:
            return remote_stat
        if Path(path) == cache_file:
            return stale_cached_stat
        return original_stat(path, *args, **kwargs)

    with (
        patch("core.infra.utils._CACHE_DIR", tmp_path),
        patch("core.infra.utils.hashlib.md5") as mock_md5,
        patch("core.infra.utils.os.stat", side_effect=stat_side_effect),
        patch("core.infra.utils.os.remove") as mock_remove,
        patch("core.infra.utils.shutil.copy2") as mock_copy,
    ):
        mock_md5.return_value.hexdigest.return_value = "cached"
        local_path, temp_file = get_local_copy(network_path)

    assert local_path == str(cache_file)
    assert temp_file is None
    mock_remove.assert_called_once_with(cache_file)
    mock_copy.assert_called_once_with(network_path, str(cache_file))


def test_cache_copy_is_stale_when_content_changes_with_same_size_and_mtime(tmp_path):
    remote_file = tmp_path / "remote.xlsx"
    cache_file = tmp_path / "cached.xlsx"
    remote_file.write_bytes(b"abcdef")
    cache_file.write_bytes(b"abcdeg")
    os.utime(remote_file, (1000, 1000))
    os.utime(cache_file, (1000, 1000))

    remote_stat = os.stat(remote_file)

    assert _cache_copy_is_fresh(cache_file, str(remote_file), remote_stat) is False


def test_get_local_copy_fallbacks_to_temp_copy_when_cache_copy_fails(tmp_path):
    network_path = r"\\server\share\report.xlsx"

    class _Stat:
        st_size = 10
        st_mtime = 1000.0

    original_stat = os.stat

    def stat_side_effect(path, *args, **kwargs):
        if str(path) == network_path:
            return _Stat()
        return original_stat(path, *args, **kwargs)

    with (
        patch("core.infra.utils._CACHE_DIR", tmp_path),
        patch("core.infra.utils.hashlib.md5") as mock_md5,
        patch("core.infra.utils.os.stat", side_effect=stat_side_effect),
        patch(
            "core.infra.utils.shutil.copy2", side_effect=[OSError("cache fail"), None]
        ),
        patch(
            "core.infra.utils.tempfile.mkstemp",
            return_value=(123, str(tmp_path / "tmp.xlsx")),
        ),
        patch("core.infra.utils.os.close"),
    ):
        mock_md5.return_value.hexdigest.return_value = "cached"
        local_path, temp_file = get_local_copy(network_path)

    assert local_path == str(tmp_path / "tmp.xlsx")
    assert temp_file == str(tmp_path / "tmp.xlsx")


def test_get_local_copy_returns_original_when_all_copy_strategies_fail(tmp_path):
    network_path = r"\\server\share\report.xlsx"

    class _Stat:
        st_size = 10
        st_mtime = 1000.0

    original_stat = os.stat

    def stat_side_effect(path, *args, **kwargs):
        if str(path) == network_path:
            return _Stat()
        return original_stat(path, *args, **kwargs)

    with (
        patch("core.infra.utils._CACHE_DIR", tmp_path),
        patch("core.infra.utils.hashlib.md5") as mock_md5,
        patch("core.infra.utils.os.stat", side_effect=stat_side_effect),
        patch(
            "core.infra.utils.shutil.copy2",
            side_effect=[OSError("copy fail"), OSError("copy fail")],
        ),
        patch(
            "core.infra.utils.tempfile.mkstemp",
            return_value=(123, str(tmp_path / "tmp.xlsx")),
        ),
        patch("core.infra.utils.os.close"),
    ):
        mock_md5.return_value.hexdigest.return_value = "cached"
        local_path, temp_file = get_local_copy(network_path)

    assert local_path == network_path
    assert temp_file is None


def test_cleanup_local_copy_cache_removes_old_files(tmp_path):
    old_file = tmp_path / "old.xlsx"
    fresh_file = tmp_path / "fresh.xlsx"
    old_file.write_text("old", encoding="utf-8")
    fresh_file.write_text("fresh", encoding="utf-8")
    os.utime(old_file, (1, 1))

    with patch("core.infra.utils._CACHE_DIR", tmp_path):
        cleanup_local_copy_cache(
            max_age_days=1,
            max_total_mb=512,
            min_delete_age_seconds=0,
        )

    assert not old_file.exists()
    assert fresh_file.exists()


def test_cleanup_local_copy_cache_skips_recent_files(tmp_path):
    recent_file = tmp_path / "recent.xlsx"
    recent_file.write_text("recent", encoding="utf-8")

    with patch("core.infra.utils._CACHE_DIR", tmp_path):
        cleanup_local_copy_cache(
            max_age_days=0,
            max_total_mb=512,
            min_delete_age_seconds=30 * 60,
        )

    assert recent_file.exists()
