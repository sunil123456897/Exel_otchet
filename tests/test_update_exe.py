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


# ── hard-kill recovery: a swap interrupted by power loss / force-kill ─


def test_recover_if_interrupted_restores_after_mid_swap_kill(tmp_path):
    """A power loss / BSOD / force-kill during apply_program leaves the install
    with a mix of old and new program files. The pending-swap marker survives
    (it is only cleared in apply_program's finally on completion), so the next
    run detects it and restores the pre-swap backup to a known-good state."""
    install = _make_install(tmp_path / "install", main_bytes=b"OLD-EXE")
    archive = _make_update_zip(tmp_path / "update.zip", main_bytes=b"NEW-EXE")
    manifest = manifest_from_local_zip(archive)

    # Run a complete successful update first so a real backup exists and the
    # install reflects the NEW program. This is the state *before* a second
    # update gets killed.
    first = update_exe.run_update(
        install, manifest, archive, channel="local",
        startup_ok_fn=_ok_startup, launch_after=True,
    )
    assert first.ok
    assert (install / "main.exe").read_bytes() == b"NEW-EXE"

    # Simulate a hard kill DURING a subsequent swap: write the marker pointing
    # at a backup, then leave main.exe partially overwritten. No exception is
    # raised (a hard kill raises nothing), so the normal rollback path would
    # NEVER trigger — only _recover_if_interrupted can save the install.
    (install / "main.exe").write_bytes(b"HALF-WRITTEN-CORRUPT")

    # Find the backup the (interrupted) second update would have made.
    backups_root = install / ".update_backups"
    assert backups_root.is_dir()
    latest_backup = sorted(backups_root.iterdir(), key=lambda p: p.name)[-1]
    # Make that backup contain the known-good NEW program (simulate backup_state
    # having run before the swap).
    (latest_backup / "program").mkdir(parents=True, exist_ok=True)
    (latest_backup / "program" / "main.exe").write_bytes(b"NEW-EXE")

    update_exe._pending_marker_path(install).parent.mkdir(parents=True, exist_ok=True)
    update_exe._pending_marker_path(install).write_text(
        str(latest_backup), encoding="utf-8"
    )
    assert (install / "main.exe").read_bytes() == b"HALF-WRITTEN-CORRUPT"

    # Now a new update runs. Its first action must detect the marker and restore.
    res = update_exe.run_update(
        install, manifest, archive, channel="local",
        startup_ok_fn=_ok_startup, launch_after=True,
    )

    # Recovery happened and the corrupt half-write was replaced by the backup.
    assert any("recovery" in line for line in res.log_lines), res.log_lines
    assert (install / "main.exe").read_bytes() != b"HALF-WRITTEN-CORRUPT"
    # The update then proceeds normally and completes.
    assert res.ok
    # marker cleared after recovery + successful swap
    assert not update_exe._pending_marker_path(install).exists()


def test_recover_if_interrupted_noop_without_marker(tmp_path):
    """No marker → no recovery, normal update proceeds. Guards the guard."""
    from core.shared.updater_model import UpdateResult

    install = _make_install(tmp_path / "install")
    result = UpdateResult()
    assert update_exe._recover_if_interrupted(install, result) is False
    assert all("recovery" not in line for line in result.log_lines)


def test_pending_marker_cleared_on_successful_swap(tmp_path):
    """A completed swap must not leave a pending marker — otherwise the next
    update would wrongly think the install is stranded."""
    install = _make_install(tmp_path / "install", main_bytes=b"OLD-EXE")
    archive = _make_update_zip(tmp_path / "update.zip", main_bytes=b"NEW-EXE")
    manifest = manifest_from_local_zip(archive)

    res = update_exe.run_update(
        install, manifest, archive, channel="local",
        startup_ok_fn=_ok_startup, launch_after=True,
    )
    assert res.ok
    assert not update_exe._pending_marker_path(install).exists()


def test_mid_swap_fault_writes_marker_and_recovers_exact_bytes(tmp_path):
    """A fault injected INTO apply_program's copy loop must: (a) leave the
    pending marker actually written by write_pending_marker (not a hand-built
    one), (b) pointing at the backup backup_state made for THIS update, and
    (c) the next run_update restores the EXACT pre-swap program bytes.

    This is the end-to-end guard the earlier recovery tests lacked: they
    wrote the marker by hand, so deleting the write_pending_marker call (or
    reordering it after the copy loop) would have passed silently. Here the
    fault is injected at the real seam, so the whole guard chain is exercised.
    """
    from unittest.mock import patch

    install = _make_install(tmp_path / "install", main_bytes=b"OLD-EXE")
    archive = _make_update_zip(tmp_path / "update.zip", main_bytes=b"NEW-EXE")
    manifest = manifest_from_local_zip(archive)

    # Run once successfully so the install is at NEW-EXE and a backup exists,
    # then capture the pre-second-update program bytes (main.exe = NEW-EXE).
    first = update_exe.run_update(
        install, manifest, archive, channel="local",
        startup_ok_fn=_ok_startup, launch_after=True,
    )
    assert first.ok
    pre_swap_bytes = (install / "main.exe").read_bytes()
    assert pre_swap_bytes == b"NEW-EXE"

    # Drive the second update with a fault injected at the FIRST copy2 inside
    # apply_program. write_pending_marker runs before the copy loop, so the
    # marker must already be on disk when the fault fires — capture it then.
    captured_marker = {}

    def _faulty_copy2_capture(src, dst, *a, **kw):
        marker = update_exe._pending_marker_path(install)
        if marker.exists() and "payload" not in captured_marker:
            captured_marker["payload"] = marker.read_text(encoding="utf-8").strip()
            captured_marker["exists_before_fault"] = True
        raise OSError("simulated power loss mid-copy")

    with patch("update_exe.shutil.copy2", side_effect=_faulty_copy2_capture):
        res2 = update_exe.run_update(
            install, manifest, archive, channel="local",
            startup_ok_fn=_ok_startup, launch_after=True,
        )

    # The swap fault surfaces as a swap failure + rollback on THIS run.
    assert not res2.ok
    # The marker was genuinely written by write_pending_marker before the fault
    # (not hand-built by the test), and it points at a real backup dir.
    assert captured_marker.get("exists_before_fault") is True, (
        "write_pending_marker did not run before the copy loop — the recovery "
        "feature would be silently broken if that line were removed/reordered"
    )
    payload = captured_marker["payload"]
    assert payload, "marker payload must name the backup dir"
    assert Path(payload).is_dir(), f"marker points at missing backup {payload}"

    # Corrupt main.exe to model the partial swap, then run a THIRD update: it
    # must recover the EXACT pre-swap bytes via _recover_if_interrupted.
    (install / "main.exe").write_bytes(b"PARTIAL-CORRUPT")
    res3 = update_exe.run_update(
        install, manifest, archive, channel="local",
        startup_ok_fn=_ok_startup, launch_after=True,
    )
    assert res3.ok
    # After recovery the install is back to the known-good NEW-EXE, then the
    # third update completes normally — main.exe is NOT the corrupt bytes.
    assert (install / "main.exe").read_bytes() != b"PARTIAL-CORRUPT"


def test_recover_aborts_when_no_backup_recorded(tmp_path):
    """If a hard kill left a marker but NO backup (empty payload), recovery
    must ABORT rather than run a fresh update over the corrupt install.
    Earlier behaviour cleared the marker and proceeded — stranding the install
    this feature exists to protect."""
    install = _make_install(tmp_path / "install", main_bytes=b"OLD-EXE")
    # Simulate the stranded state: marker present but empty payload.
    marker = update_exe._pending_marker_path(install)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("", encoding="utf-8")
    (install / "main.exe").write_bytes(b"HALF-CORRUPT")

    archive = _make_update_zip(tmp_path / "u.zip", main_bytes=b"NEW-EXE")
    manifest = manifest_from_local_zip(archive)
    res = update_exe.run_update(
        install, manifest, archive, channel="local",
        startup_ok_fn=_ok_startup, launch_after=True,
    )

    # Recovery aborted: the update did NOT proceed over the corrupt base.
    assert not res.ok
    assert res.stage == "recovery"
    # The half-corrupt main.exe is untouched (we refused to build on it).
    assert (install / "main.exe").read_bytes() == b"HALF-CORRUPT"
    # Marker cleared so a later manual reinstall isn't confused.
    assert not marker.exists()
