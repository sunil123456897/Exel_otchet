"""Unit tests for the exe-distribution updater (tools/update_exe.py).

These exercise the update LOGIC (backup / in-place swap / data preservation /
rollback / L0-L1 verification) through the offline LOCAL channel, so they need
no network and no compiled updater.exe — the Python module is imported
directly. The GitHub channel is covered separately (it adds only the fetch +
SHA256SUMS step on top of the same pipeline).
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

# Make tools/ (update_exe) and APP/ (core.*) importable regardless of cwd.
_REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (_REPO_ROOT / "tools", _REPO_ROOT / "APP"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import update_exe  # noqa: E402
from core.shared.github_fetcher import manifest_from_local_zip  # noqa: E402


# ── helpers ───────────────────────────────────────────────────────────


def _make_install(root: Path, *, main_bytes: bytes = b"OLD-EXE") -> Path:
    """Create a fake installed exe dist with program + user data."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "main.exe").write_bytes(main_bytes)
    (root / "assets" / "icons" / "dark").mkdir(parents=True)
    (root / "assets" / "icons" / "dark" / "refresh.png").write_bytes(b"png")
    # user data that MUST survive an update
    (root / "config.yaml").write_text("marker: KEEP-ME\n", encoding="utf-8")
    (root / "employees.yaml").write_text("Амалия: []\n", encoding="utf-8")
    (root / "cache.db").write_bytes(b"sqlite-data")
    (root / "runtime_state.json").write_text("[]", encoding="utf-8")
    return root


def _make_update_zip(path: Path, *, main_bytes: bytes = b"NEW-EXE",
                     wrap: str | None = "Master-Report") -> Path:
    """Build a program-only update zip (no user data inside)."""
    staging = path.parent / "_zipsrc"
    base = staging / wrap if wrap else staging
    (base / "assets" / "icons" / "dark").mkdir(parents=True)
    (base / "main.exe").write_bytes(main_bytes)
    (base / "assets" / "icons" / "dark" / "refresh.png").write_bytes(b"png2")
    (base / "db_schema.sql").write_text("CREATE TABLE t(x);", encoding="utf-8")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(staging.rglob("*")):
            if f.is_file():
                zf.write(f, f.relative_to(staging))
    import shutil
    shutil.rmtree(staging, ignore_errors=True)
    return path


def _ok_startup(_install: Path, _timeout: int) -> tuple[bool, str]:
    return True, "fake-ok"


def _fail_startup(_install: Path, _timeout: int) -> tuple[bool, str]:
    return False, "fake-fail"


# ── unit: data-file classifier ────────────────────────────────────────


def test_is_data_file_classification():
    assert update_exe._is_data_file("config.yaml")
    assert update_exe._is_data_file("employees.yaml")
    assert update_exe._is_data_file("cache.db")
    assert update_exe._is_data_file("cache.db-wal")
    assert update_exe._is_data_file("cache.db.backup_20260101")
    assert update_exe._is_data_file(".license")
    assert update_exe._is_data_file("first_run.json")
    # program files are NOT data
    assert not update_exe._is_data_file("main.exe")
    assert not update_exe._is_data_file("python312.dll")
    assert not update_exe._is_data_file("db_schema.sql")
    assert not update_exe._is_data_file("config.example.yaml")


# ── unit: dist-root discovery ─────────────────────────────────────────


def test_find_dist_root_with_and_without_wrapper(tmp_path):
    wrapped = tmp_path / "w"
    (wrapped / "Master-Report").mkdir(parents=True)
    (wrapped / "Master-Report" / "main.exe").write_bytes(b"x")
    assert update_exe.find_dist_root(wrapped) == wrapped / "Master-Report"

    flat = tmp_path / "f"
    flat.mkdir()
    (flat / "main.exe").write_bytes(b"x")
    assert update_exe.find_dist_root(flat) == flat

    empty = tmp_path / "e"
    empty.mkdir()
    with pytest.raises(RuntimeError):
        update_exe.find_dist_root(empty)


# ── happy path: local update preserves data + updates program ─────────


def test_local_update_preserves_data_and_updates_program(tmp_path):
    install = _make_install(tmp_path / "install")
    archive = _make_update_zip(tmp_path / "update.zip", main_bytes=b"NEW-EXE")
    manifest = manifest_from_local_zip(archive)

    res = update_exe.run_update(
        install, manifest, archive, channel="local",
        startup_ok_fn=_ok_startup, launch_after=True,
    )

    assert res.ok, res.message
    assert res.stage == "complete"
    # program updated
    assert (install / "main.exe").read_bytes() == b"NEW-EXE"
    assert (install / "db_schema.sql").exists()  # new program file appeared
    # data preserved verbatim
    assert (install / "config.yaml").read_text(encoding="utf-8") == "marker: KEEP-ME\n"
    assert (install / "employees.yaml").read_text(encoding="utf-8") == "Амалия: []\n"
    assert (install / "cache.db").read_bytes() == b"sqlite-data"
    # version metadata written
    assert update_exe.read_installed_version(install) == manifest.version
    # staging cleaned up
    assert not (install / ".update_staging").exists()


# ── rollback: failed startup restores the old program ─────────────────


def test_local_update_rolls_back_on_startup_failure(tmp_path):
    install = _make_install(tmp_path / "install", main_bytes=b"OLD-EXE")
    archive = _make_update_zip(tmp_path / "update.zip", main_bytes=b"NEW-EXE")
    manifest = manifest_from_local_zip(archive)

    res = update_exe.run_update(
        install, manifest, archive, channel="local",
        startup_ok_fn=_fail_startup, launch_after=True,
    )

    assert not res.ok
    assert res.rolled_back
    # old program restored
    assert (install / "main.exe").read_bytes() == b"OLD-EXE"
    # data still intact
    assert (install / "config.yaml").read_text(encoding="utf-8") == "marker: KEEP-ME\n"
    assert (install / "cache.db").read_bytes() == b"sqlite-data"


# ── L0 verification ───────────────────────────────────────────────────


def test_verify_archive_rejects_sha_mismatch(tmp_path):
    archive = _make_update_zip(tmp_path / "u.zip")
    manifest = manifest_from_local_zip(archive)
    manifest.sha256 = "0" * 64  # wrong on purpose
    from core.shared.updater_model import UpdateResult
    with pytest.raises(RuntimeError, match="sha256 mismatch"):
        update_exe.verify_archive(archive, manifest, UpdateResult())


def test_verify_archive_rejects_corrupt_zip(tmp_path):
    archive = tmp_path / "corrupt.zip"
    archive.write_bytes(b"this is not a zip at all")
    from core.shared.updater_model import UpdateResult, VersionManifest
    manifest = VersionManifest(version="x", sha256="", size=archive.stat().st_size)
    with pytest.raises(RuntimeError):
        update_exe.verify_archive(archive, manifest, UpdateResult())


# ── version metadata ──────────────────────────────────────────────────


def test_version_json_roundtrip(tmp_path):
    from core.shared.updater_model import VersionManifest
    install = tmp_path / "i"
    install.mkdir()
    manifest = VersionManifest(version="v9.9", sha256="", size=1, asset="a.zip")
    update_exe.write_version_json(install, manifest, "local")
    assert update_exe.read_installed_version(install) == "v9.9"
    assert update_exe.read_installed_version(tmp_path / "nope") is None
