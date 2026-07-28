"""Stage 4 / MR-0407 — updater test matrix.

Every TZ failure mode is exercised through the offline updater engine.
Each test builds a fake install root in ``tmp_path``, builds an archive
through the ``archive_builder`` helper, and drives the Updater with a
local-copy fetcher (no network, no GitHub).

The matrix covers:

* happy path with launch + startup-ok;
* corrupted archive (bad SHA, truncated zip, dangerous members);
* insufficient free space;
* second updater instance blocked by lock;
* missing startup-ok → automatic rollback;
* mid-step crash → staging cleaned up + previous version intact;
* re-install same version (overwrites cleanly);
* downgrade refused;
* offline ZIP via local file (no network needed);
* L0 path safety (no absolute / ``..`` / symlinks);
* archive without main.py fails L1;
* rollback restores previous version pointer.
"""
from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
import zipfile
from pathlib import Path

import pytest
from core.shared.updater_model import (
    CurrentVersion,
    UpdateLock,
    Updater,
    VersionManifest,
    wait_for_startup_ok_marker,
)

# ── archive builder helpers ────────────────────────────────────────────


def build_fake_release(
    dest_dir: Path,
    version: str = "5.7.0",
    *,
    main_py: str = 'print("hello")\n',
    extra_files: dict[str, str] | None = None,
    corrupt: str = "",  # "" / "truncate" / "garble-content" / "bad-zip"
) -> tuple[Path, VersionManifest]:
    """Build a fake release ZIP + matching manifest.

    Returns ``(zip_path, manifest)``. By default the manifest matches the
    archive exactly. ``corrupt`` triggers specific failure modes:

    * ``"truncate"``    — chop the archive at half length. Manifest's
                          size still claims the original full length,
                          so size-check fires first.
    * ``"garble-content"`` — replace the archive with bytes that differ
                          from what the manifest SHA expects. The bytes
                          are still a valid ZIP so we reach the SHA
                          check rather than crashing in BadZipFile.
    * ``"bad-zip"``     — random bytes, not a zip at all.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / f"MasterReport-{version}.zip"

    files = {"APP/__init__.py": f'__version__ = "{version}"\n',
             "APP/main.py": main_py}
    if extra_files:
        files.update(extra_files)

    def _build(files_dict: dict[str, str]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, content in files_dict.items():
                zf.writestr(name, content)
        return buf.getvalue()

    raw = _build(files)

    if corrupt == "truncate":
        # Keep the manifest's size/sha pointing at the FULL archive so
        # the size check fires.
        full_size = len(raw)
        full_sha = hashlib.sha256(raw).hexdigest()
        raw = raw[: len(raw) // 2]
        zip_path.write_bytes(raw)
        manifest = VersionManifest(
            version=version, sha256=full_sha, size=full_size,
            asset=zip_path.name, config_schema=1, database_schema=1,
        )
        return zip_path, manifest

    if corrupt == "garble-content":
        # Build a *different* archive with extra content so it's still a
        # valid zip but its SHA differs from the manifest's claim.
        full_sha = hashlib.sha256(raw).hexdigest()
        full_size = len(raw)
        raw = _build({**files, "EXTRA.txt": "tampered"})
        zip_path.write_bytes(raw)
        manifest = VersionManifest(
            version=version, sha256=full_sha, size=full_size,
            asset=zip_path.name, config_schema=1, database_schema=1,
        )
        return zip_path, manifest

    if corrupt == "bad-zip":
        raw = b"NOT_A_ZIP_FILE" * 32
        # Manifest still claims the original SHA/size so we exercise the
        # extract step rather than the size check.
        full_sha = hashlib.sha256(_build(files)).hexdigest()
        full_size = len(_build(files))
        zip_path.write_bytes(raw)
        manifest = VersionManifest(
            version=version, sha256=full_sha, size=full_size,
            asset=zip_path.name, config_schema=1, database_schema=1,
        )
        return zip_path, manifest

    zip_path.write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    manifest = VersionManifest(
        version=version, sha256=sha, size=len(raw),
        asset=zip_path.name, config_schema=1, database_schema=1,
    )
    return zip_path, manifest


def local_fetcher(zip_path: Path):
    """Return a fetch_fn that copies *zip_path* into the updater's work dir."""
    def _fetch(manifest: VersionManifest, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / manifest.asset
        shutil.copy2(zip_path, dest)
        return dest
    return _fetch


@pytest.fixture
def install_root(tmp_path: Path) -> Path:
    """Empty install root with an initial version already installed."""
    root = tmp_path / "MasterReport"
    versions = root / "versions" / "5.6.0"
    versions.mkdir(parents=True)
    (versions / "APP").mkdir()
    (versions / "APP" / "__init__.py").write_text('__version__ = "5.6.0"\n')
    (versions / "APP" / "main.py").write_text('print("old")\n')
    (root / "current.json").write_text(json.dumps({
        "version": "5.6.0",
        "installed_utc": "2026-07-01T00:00:00+00:00",
        "previous_version": "",
        "updater_version": "1.0.0",
    }), encoding="utf-8")
    return root


# ── happy path ─────────────────────────────────────────────────────────


def test_happy_path_update(install_root: Path, tmp_path: Path) -> None:
    """End-to-end: fetch → verify → stage → switch → launch → startup-ok."""
    work = tmp_path / "releases"
    zip_path, manifest = build_fake_release(work)
    updater = Updater(install_root, python_exe="python",
                      fetch_fn=local_fetcher(zip_path))

    launched: list[Path] = []

    def launch(v: Path) -> None:
        launched.append(v)
        # Drop the startup-ok marker immediately, simulating a healthy boot.
        (v / ".startup-ok").write_text("ok")

    result = updater.update(
        manifest,
        launch_fn=launch,
        wait_for_startup_ok_fn=wait_for_startup_ok_marker,
    )

    assert result.ok, f"update failed: {result.message}\nlog: {result.log_lines}"
    assert (install_root / "versions" / "5.7.0" / "APP" / "main.py").exists()
    current = updater.current_version()
    assert current is not None and current.version == "5.7.0"
    assert current.previous_version == "5.6.0"
    assert launched and launched[0].name == "5.7.0"


def test_update_preserves_local_data(install_root: Path, tmp_path: Path) -> None:
    """The user's config/employees/cache must be carried into the new version.

    Regression guard: without preservation, switching to ``versions/<ver>/APP``
    strands these files in the old location, so the app would start on fresh
    defaults — silently losing source roots, employee mappings and cache.
    """
    # Data lives in the currently-active APP dir (5.6.0, per current.json).
    live_app = install_root / "versions" / "5.6.0" / "APP"
    (live_app / "config.yaml").write_text("paths: {master_file: X}\n", encoding="utf-8")
    (live_app / "employees.yaml").write_text("employees: []\n", encoding="utf-8")
    (live_app / "cache.db").write_bytes(b"\x00\x01\x02sqlite")

    work = tmp_path / "releases"
    zip_path, manifest = build_fake_release(work)
    updater = Updater(install_root, python_exe="python",
                      fetch_fn=local_fetcher(zip_path))
    result = updater.update(manifest)
    assert result.ok, f"update failed: {result.message}\nlog: {result.log_lines}"

    new_app = install_root / "versions" / "5.7.0" / "APP"
    assert (new_app / "config.yaml").read_text(encoding="utf-8") == "paths: {master_file: X}\n"
    assert (new_app / "employees.yaml").read_text(encoding="utf-8") == "employees: []\n"
    assert (new_app / "cache.db").read_bytes() == b"\x00\x01\x02sqlite"


# ── L0: SHA, size, path safety ────────────────────────────────────────


def test_sha_mismatch_aborts(install_root: Path, tmp_path: Path) -> None:
    """If the archive's actual SHA differs from the manifest, abort."""
    work = tmp_path / "releases"
    zip_path, _ = build_fake_release(work, corrupt="garble-content")
    updater = Updater(install_root, python_exe="python",
                      fetch_fn=local_fetcher(zip_path))

    # Build a manifest whose SHA deliberately does NOT match: take the
    # tampered archive's actual size, but lie about the SHA. This isolates
    # the SHA check from the size check.
    actual_size = zip_path.stat().st_size
    fake_sha = "0" * 64  # impossible SHA
    bad_manifest = VersionManifest(
        version="5.7.0", sha256=fake_sha, size=actual_size,
        asset=zip_path.name,
    )
    result = updater.update(bad_manifest)
    assert not result.ok
    assert "sha256 mismatch" in result.message
    # Previous version pointer is intact.
    assert updater.current_version().version == "5.6.0"


def test_size_mismatch_aborts(install_root: Path, tmp_path: Path) -> None:
    work = tmp_path / "releases"
    zip_path, manifest = build_fake_release(work)
    # Lie about size in the manifest.
    bad_manifest = VersionManifest(
        version=manifest.version, sha256=manifest.sha256,
        size=manifest.size + 999,
    )
    updater = Updater(install_root, python_exe="python",
                      fetch_fn=local_fetcher(zip_path))
    result = updater.update(bad_manifest)
    assert not result.ok
    assert "size mismatch" in result.message


def test_truncated_archive_aborts(install_root: Path, tmp_path: Path) -> None:
    """A truncated zip cannot be opened; abort cleanly."""
    work = tmp_path / "releases"
    zip_path, manifest = build_fake_release(work, corrupt="truncate")
    updater = Updater(install_root, python_exe="python",
                      fetch_fn=local_fetcher(zip_path))
    result = updater.update(manifest)
    assert not result.ok


def test_bad_zip_signature_aborts(install_root: Path, tmp_path: Path) -> None:
    """Random bytes (not a zip) cannot be extracted; abort cleanly."""
    work = tmp_path / "releases"
    zip_path, manifest = build_fake_release(work, corrupt="bad-zip")
    updater = Updater(install_root, python_exe="python",
                      fetch_fn=local_fetcher(zip_path))
    result = updater.update(manifest)
    assert not result.ok


def test_dangerous_absolute_path_in_archive_aborts(
    install_root: Path, tmp_path: Path,
) -> None:
    """An archive member with an absolute path must be refused.

    Otherwise extraction could overwrite system files.
    """
    work = tmp_path / "releases"
    zip_path = work / "evil.zip"
    work.mkdir(parents=True)
    # Build a zip with an absolute-path member.
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("APP/__init__.py", '__version__ = "5.7.0"\n')
        zf.writestr("APP/main.py", "print(42)\n")
        # On Windows an absolute member is "C:/Windows/evil.txt". The path
        # safety check rejects anything starting with "/" or with ":".
        zf.writestr("/etc/passwd", "PWNED\n")
    raw = zip_path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    manifest = VersionManifest(version="5.7.0", sha256=sha, size=len(raw),
                               asset="evil.zip")
    updater = Updater(install_root, python_exe="python",
                      fetch_fn=local_fetcher(zip_path))
    result = updater.update(manifest)
    assert not result.ok
    assert "unsafe" in result.message.lower()


def test_traversal_path_in_archive_aborts(
    install_root: Path, tmp_path: Path,
) -> None:
    """``../../../etc/passwd`` must be refused."""
    work = tmp_path / "releases"
    work.mkdir(parents=True)
    zip_path = work / "traversal.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("APP/__init__.py", '__version__ = "5.7.0"\n')
        zf.writestr("APP/main.py", "print(42)\n")
        zf.writestr("../../escape.txt", "PWNED\n")
    raw = zip_path.read_bytes()
    manifest = VersionManifest(
        version="5.7.0",
        sha256=hashlib.sha256(raw).hexdigest(),
        size=len(raw),
        asset="traversal.zip",
    )
    updater = Updater(install_root, python_exe="python",
                      fetch_fn=local_fetcher(zip_path))
    result = updater.update(manifest)
    assert not result.ok
    assert "unsafe" in result.message.lower()


# ── preflight ──────────────────────────────────────────────────────────


def test_insufficient_free_space_aborts(
    install_root: Path, tmp_path: Path, monkeypatch,
) -> None:
    """Patch disk_usage to report no space; update must abort at preflight."""
    work = tmp_path / "releases"
    zip_path, manifest = build_fake_release(work)
    updater = Updater(install_root, python_exe="python",
                      fetch_fn=local_fetcher(zip_path))
    # Force free space to look like 1MB.
    monkeypatch.setattr(shutil, "disk_usage", lambda _p: type("U", (), {"free": 1 << 20})())
    result = updater.update(manifest, min_free_space_mb=500)
    assert not result.ok
    assert "free space" in result.message.lower()


# ── lock ───────────────────────────────────────────────────────────────


def test_second_updater_instance_is_blocked(
    install_root: Path, tmp_path: Path,
) -> None:
    """While one updater holds the lock, a second one must abort."""
    lock = UpdateLock(install_root)
    assert lock.acquire()

    work = tmp_path / "releases"
    zip_path, manifest = build_fake_release(work)
    updater = Updater(install_root, python_exe="python",
                      fetch_fn=local_fetcher(zip_path))
    result = updater.update(manifest)
    assert not result.ok
    assert result.stage == "lock"
    assert "another updater" in result.message.lower()

    lock.release()


def test_stale_lock_is_reclaimed(install_root: Path) -> None:
    """A lock file pointing at a dead PID is overwritten."""
    lock_file = install_root / ".update_state" / UpdateLock.LOCK_NAME
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    # PID 0xFFFFFFFF is almost certainly not running.
    lock_file.write_text("4294967295", encoding="utf-8")
    lock = UpdateLock(install_root)
    assert lock.acquire()
    lock.release()


# ── L1 self-check ──────────────────────────────────────────────────────


def test_archive_without_main_py_fails_L1(
    install_root: Path, tmp_path: Path,
) -> None:
    """An archive that lacks main.py / APP/__init__.py is not a valid release."""
    work = tmp_path / "releases"
    work.mkdir()
    zip_path = work / "empty.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("readme.txt", "no python here")
    raw = zip_path.read_bytes()
    manifest = VersionManifest(
        version="5.7.0",
        sha256=hashlib.sha256(raw).hexdigest(),
        size=len(raw),
        asset="empty.zip",
    )
    updater = Updater(install_root, python_exe="python",
                      fetch_fn=local_fetcher(zip_path))
    result = updater.update(manifest)
    assert not result.ok
    assert "L1" in result.message or "main.py" in result.message


def test_wrapped_archive_fails_L1_loudly(
    install_root: Path, tmp_path: Path,
) -> None:
    """A GitHub-style archive wraps everything in a top-level
    ``<repo>-<branch>/`` folder, so the canonical ``APP/main.py`` is NOT at
    the staging root. L1 must fail LOUDLY here — otherwise the switch would
    "succeed" while the launcher can't find ``versions/<ver>/APP/main.py``
    and silently runs the OLD version (a silent no-update). Failing routes
    the operator to the legacy PowerShell updater."""
    work = tmp_path / "releases"
    work.mkdir()
    zip_path = work / "wrapped.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("Exel_otchet-main/APP/__init__.py", '__version__ = "5.7.0"\n')
        zf.writestr("Exel_otchet-main/APP/main.py", "print(42)\n")
    raw = zip_path.read_bytes()
    manifest = VersionManifest(
        version="5.7.0",
        sha256=hashlib.sha256(raw).hexdigest(),
        size=len(raw),
        asset="wrapped.zip",
    )
    updater = Updater(install_root, python_exe="python",
                      fetch_fn=local_fetcher(zip_path))
    result = updater.update(manifest)
    assert not result.ok
    assert ("L1" in result.message or "wrapper" in result.message
            or "APP/main.py" in result.message)


# ── startup-ok + rollback ─────────────────────────────────────────────


def test_missing_startup_ok_triggers_rollback(
    install_root: Path, tmp_path: Path,
) -> None:
    """If the launched version never drops .startup-ok, roll back."""
    work = tmp_path / "releases"
    zip_path, manifest = build_fake_release(work)
    updater = Updater(install_root, python_exe="python",
                      fetch_fn=local_fetcher(zip_path))

    def launch(_v: Path) -> None:
        pass  # do nothing — never drop startup-ok

    result = updater.update(
        manifest,
        launch_fn=launch,
        wait_for_startup_ok_fn=lambda _v, _t: False,
    )
    assert not result.ok
    assert result.rolled_back
    # Pointer is restored.
    assert updater.current_version().version == "5.6.0"
    # New version dir exists (we don't delete it — for diagnosis).
    assert (install_root / "versions" / "5.7.0").exists()


def test_rollback_restores_previous_pointer(
    install_root: Path, tmp_path: Path,
) -> None:
    """After rollback, current.json points at the previous version."""
    work = tmp_path / "releases"
    zip_path, manifest = build_fake_release(work)
    updater = Updater(install_root, python_exe="python",
                      fetch_fn=local_fetcher(zip_path))

    # Force a failure after switch.
    def launch(_v: Path) -> None:
        raise RuntimeError("simulated launch crash")

    result = updater.update(manifest, launch_fn=launch,
                            wait_for_startup_ok_fn=lambda *_: False)
    assert not result.ok
    # Pointer either still says 5.6.0 (if launch crashed before switch)
    # or was rolled back to 5.6.0 (if switch happened then launch failed).
    assert updater.current_version().version == "5.6.0"


# ── same-version reinstall ────────────────────────────────────────────


def test_reinstall_same_version_overwrites_cleanly(
    install_root: Path, tmp_path: Path,
) -> None:
    """Re-installing the same version replaces the dir, doesn't fail."""
    work = tmp_path / "releases"
    # Build a release at the SAME version as currently installed.
    zip_path, manifest = build_fake_release(work, version="5.6.0")
    updater = Updater(install_root, python_exe="python",
                      fetch_fn=local_fetcher(zip_path))

    def launch(v: Path) -> None:
        (v / ".startup-ok").write_text("ok")

    result = updater.update(manifest, launch_fn=launch,
                            wait_for_startup_ok_fn=wait_for_startup_ok_marker)
    assert result.ok
    assert updater.current_version().version == "5.6.0"
    # Old version dir was moved aside.
    assert (install_root / "versions" / "5.6.0.prev").exists()


# ── offline ZIP via local file ────────────────────────────────────────


def test_offline_zip_works_without_network(
    install_root: Path, tmp_path: Path,
) -> None:
    """The same engine accepts a local ZIP — no GitHub, no HTTP."""
    work = tmp_path / "releases"
    zip_path, manifest = build_fake_release(work)
    updater = Updater(install_root, python_exe="python",
                      fetch_fn=local_fetcher(zip_path))
    # No launch / startup-ok wired — proves the bare pipeline works.
    result = updater.update(manifest)
    assert result.ok
    assert (install_root / "versions" / "5.7.0").exists()


# ── mid-step crash leaves previous version intact ────────────────────


def test_mid_step_crash_does_not_corrupt_state(
    install_root: Path, tmp_path: Path, monkeypatch,
) -> None:
    """If _extract raises mid-way, current.json must be untouched."""
    work = tmp_path / "releases"
    zip_path, manifest = build_fake_release(work)
    updater = Updater(install_root, python_exe="python",
                      fetch_fn=local_fetcher(zip_path))

    def boom(_archive: Path, _dest: Path) -> None:
        raise RuntimeError("simulated mid-extract crash")

    monkeypatch.setattr(updater, "_extract", boom)
    result = updater.update(manifest)
    assert not result.ok
    assert "mid-extract" in result.message
    assert updater.current_version().version == "5.6.0"
    # Staging was cleaned up.
    assert not (install_root / "versions" / "5.7.0.staging").exists()


# ── downgrade refusal (delegated to manifest author policy) ───────────


def test_downgrade_is_not_automatically_prevented(
    install_root: Path, tmp_path: Path,
) -> None:
    """The updater itself doesn't refuse downgrades — the policy layer does.

    Documented expectation: ``Update-WithZip`` callers check
    ``current_version().version`` against ``manifest.version`` and refuse
    to proceed if the new version is older. This test pins that the
    engine itself stays agnostic (some rollback flows legitimately need
    to "downgrade" to the previous version).
    """
    work = tmp_path / "releases"
    zip_path, manifest = build_fake_release(work, version="5.5.0")
    updater = Updater(install_root, python_exe="python",
                      fetch_fn=local_fetcher(zip_path))
    result = updater.update(manifest)
    assert result.ok
    assert updater.current_version().version == "5.5.0"


# ── CurrentVersion / lock unit tests ──────────────────────────────────


def test_current_version_round_trips() -> None:
    cv = CurrentVersion(version="5.7.0", previous_version="5.6.0")
    d = cv.to_dict()
    assert CurrentVersion.from_dict(d) == cv


def test_update_lock_is_reentrant_safe(install_root: Path) -> None:
    """Releasing an un-acquired lock is a no-op (no exception)."""
    lock = UpdateLock(install_root)
    lock.release()  # must not raise


def test_update_lock_context_manager(install_root: Path) -> None:
    """``with UpdateLock(root):`` acquires and releases cleanly."""
    with UpdateLock(install_root):
        # Trying again while held fails.
        second = UpdateLock(install_root)
        assert not second.acquire()
    # After release, a new lock acquires.
    third = UpdateLock(install_root)
    assert third.acquire()
    third.release()


# ── version manifest ───────────────────────────────────────────────────


def test_manifest_round_trips() -> None:
    m = VersionManifest(version="5.7.0", sha256="abc", size=42,
                        asset="x.zip", config_schema=2)
    d = m.to_dict()
    again = VersionManifest.from_dict(d)
    assert again.version == m.version
    assert again.sha256 == m.sha256
    assert again.size == m.size
    assert again.config_schema == m.config_schema


def test_manifest_rejects_missing_required_fields() -> None:
    with pytest.raises((KeyError, TypeError)):
        VersionManifest.from_dict({"version": "5.7.0"})  # no sha256 / size


# ── MR-0404 followup: L2 functional smoke ─────────────────────────────


def test_l2_smoke_runs_real_logic_service(install_root: Path, tmp_path: Path) -> None:
    """L2 should actually invoke LogicService.apply_financial_rules on
    the staged version and verify it produces correct Decimal output.

    We build a release archive containing a copy of the real APP/core/
    domain/logic_service.py — proving the L2 smoke works against the
    production code, not a stub.
    """
    work = tmp_path / "releases"
    work.mkdir()

    # Build an archive that includes the real logic_service.py.
    real_logic = Path("APP/core/domain/logic_service.py")
    assert real_logic.is_file(), "test setup needs the real logic_service.py"
    zip_path = work / "with-logic.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("APP/__init__.py", '__version__ = "5.7.0"\n')
        zf.writestr("APP/main.py", "print(0)\n")
        # Copy the real logic_service.py and its deps.
        for rel in ("core/__init__.py", "core/domain/__init__.py",
                    "core/domain/logic_service.py",
                    "core/domain/utils_helpers.py",
                    "core/domain/data_schemas.py",
                    "core/domain/interfaces.py"):
            src = Path("APP") / rel
            if src.is_file():
                zf.write(src, f"APP/{rel}")
    raw = zip_path.read_bytes()
    manifest = VersionManifest(
        version="5.7.0", sha256=hashlib.sha256(raw).hexdigest(),
        size=len(raw), asset="with-logic.zip",
    )

    updater = Updater(install_root, python_exe=sys.executable,
                      fetch_fn=local_fetcher(zip_path))
    result = updater.update(manifest)
    assert result.ok, f"L2 smoke failed: {result.message}\nlog: {result.log_lines}"
    # L2 ran (not skipped).
    assert any("L2" in line and "smoke OK" in line for line in result.log_lines), (
        f"L2 smoke did not run to completion: {result.log_lines}"
    )


def test_l2_smoke_fails_on_broken_logic_service(
    install_root: Path, tmp_path: Path,
) -> None:
    """If the staged logic_service has a runtime bug, L2 must abort the update.

    We need a complete ``APP/core/domain/__init__.py`` chain so the L2
    subprocess actually imports the *staged* (broken) module instead
    of falling back to the developer's installed copy.
    """
    work = tmp_path / "releases"
    work.mkdir()
    zip_path = work / "broken.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("APP/__init__.py", '__version__ = "5.7.0"\n')
        zf.writestr("APP/main.py", "print(0)\n")
        # Full package chain so the subprocess doesn't fall through to cwd.
        zf.writestr("APP/core/__init__.py", "")
        zf.writestr("APP/core/domain/__init__.py", "")
        # A logic_service that exists but raises on import.
        zf.writestr(
            "APP/core/domain/logic_service.py",
            "raise RuntimeError('intentional break')\n",
        )
    raw = zip_path.read_bytes()
    manifest = VersionManifest(
        version="5.7.0", sha256=hashlib.sha256(raw).hexdigest(),
        size=len(raw), asset="broken.zip",
    )
    updater = Updater(install_root, python_exe=sys.executable,
                      fetch_fn=local_fetcher(zip_path))
    result = updater.update(manifest)
    # L2 failure aborts the update.
    assert not result.ok
    assert "L2" in result.message or "smoke" in result.message.lower()
    # Pointer is intact.
    assert updater.current_version().version == "5.6.0"
