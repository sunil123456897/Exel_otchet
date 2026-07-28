"""Exe-distribution updater for Master-Report.

Updates a flat Nuitka exe install (the ``build_exe/main.dist`` folder, or any
folder containing ``main.exe``) **in place**, preserving the user's data
(config / employees / cache.db / runtime state / licence) and rolling back on
failure. Two channels:

* **GitHub release asset** (default) — fetches the latest published
  ``Master-Report_<ver>_win64.zip`` release asset and verifies it against the
  published ``SHA256SUMS`` (real integrity — not the self-referential branch
  SHA the source updater relies on).
* **Local zip** (``--from-file <zip>``) — offline update from a downloaded /
  USB-carried archive.

The program archive contains ONLY program files (no user data), so extracting
it over the install dir naturally leaves data untouched; we still back data up
first so a failed swap can be rolled back.

This script is compiled to ``updater.exe`` by ``tools/build_exe.py`` so it runs
on PCs that have no Python installed. It reuses the proven pieces of the
source-layout updater rather than reimplementing them:

    core.infra.updater_model   UpdateLock, UpdateResult, VersionManifest,
                               Updater.sha256_of / check_archive_path_safety /
                               _free_space_mb, the preserved-data set
    core.infra.github_fetcher  download / auth / retry + release-asset fetch

Exit codes mirror ``tools/run_updater.py``:
    0 success · 2 network/not-found · 3 auth · 4 check failed (L0/L1/pin)
    5 rolled back · 1 generic.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

# ── make ``core`` importable when run from source (no-op when frozen) ──
_FROZEN = bool(getattr(sys, "frozen", False)) or "__compiled__" in globals()
if not _FROZEN:
    _APP_DIR = Path(__file__).resolve().parents[1] / "APP"
    if str(_APP_DIR) not in sys.path:
        sys.path.insert(0, str(_APP_DIR))

from core.infra.updater_model import (  # noqa: E402
    UpdateLock,
    UpdateResult,
    Updater,
    VersionManifest,
)

# Data files that must survive an update, relative to the install dir.
# Mirrors Updater._PRESERVED_DATA_FILES plus the onboarding/licence state.
_DATA_EXACT = set(Updater._PRESERVED_DATA_FILES) | {
    "first_run.json",
    ".license",
    ".last_run",
}
# cache.db sidecars + timestamped backups the app creates next to the DB.
_DATA_GLOBS = ("cache.db*", "*.unclean")

# Files/dirs that are part of the update machinery, never program or data.
_UPDATE_DIRS = (".update_state", ".update_staging", ".update_backups")

MIN_FREE_SPACE_MB = 500
STARTUP_TIMEOUT_SEC = 30


def _is_data_file(name: str) -> bool:
    """True if *name* (a file name relative to the install dir) is user data
    that must be preserved across a program update."""
    if name in _DATA_EXACT:
        return True
    return any(fnmatch.fnmatch(name, g) for g in _DATA_GLOBS)


def _log(result: UpdateResult, stage: str, msg: str) -> None:
    result.mark(stage, msg)
    print(f"[update_exe] {stage}: {msg}")


def install_dir_default() -> Path:
    """The folder that holds ``main.exe``.

    Frozen (``updater.exe``): the executable's own folder. Source run:
    ``<repo>/build_exe/main.dist`` (overridable via ``--install-dir``).
    """
    if _FROZEN:
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1] / "build_exe" / "main.dist"


# ── verification (L0 / L1) ────────────────────────────────────────────


def verify_archive(archive: Path, manifest: VersionManifest, result: UpdateResult) -> None:
    """L0 checks: size, SHA-256 (when the manifest carries an independent
    one), path-safety, and zip CRC integrity. Raises on failure."""
    if manifest.size and archive.stat().st_size != manifest.size:
        raise RuntimeError(
            f"size mismatch: {archive.stat().st_size} != {manifest.size}"
        )
    if manifest.sha256:
        actual = Updater.sha256_of(archive)
        if actual != manifest.sha256:
            raise RuntimeError(
                f"sha256 mismatch: {actual[:12]}… != {manifest.sha256[:12]}…"
            )
    bad = Updater.check_archive_path_safety(archive)
    if bad:
        raise RuntimeError(f"unsafe archive members: {bad[:3]}")
    with zipfile.ZipFile(archive) as zf:
        corrupt = zf.testzip()
    if corrupt is not None:
        raise RuntimeError(
            f"corrupt archive (bad CRC in {corrupt}) — download likely "
            "interrupted; re-run the update"
        )
    _log(result, "L0", "size+sha+path+zip-integrity OK")


def find_dist_root(staging: Path) -> Path:
    """Locate the folder inside *staging* that directly contains main.exe.

    The release zip wraps everything in a top-level ``Master-Report/`` folder
    (see tools/build_exe.py _make_zip); a raw main.dist zip may not. Return
    whichever dir holds main.exe, or raise."""
    if (staging / "main.exe").is_file():
        return staging
    for cand in staging.iterdir():
        if cand.is_dir() and (cand / "main.exe").is_file():
            return cand
    raise RuntimeError("L1: staging has no main.exe (wrong archive layout)")


def verify_exe_layout(dist_root: Path, result: UpdateResult) -> None:
    """L1 check for an exe dist: main.exe + the icon set must be present."""
    if not (dist_root / "main.exe").is_file():
        raise RuntimeError("L1: main.exe missing from staged update")
    if not (dist_root / "assets" / "icons").is_dir():
        raise RuntimeError("L1: assets/icons missing from staged update")
    _log(result, "L1", "main.exe + assets/icons present")


# ── backup / restore / swap ───────────────────────────────────────────


def _backup_dir(install: Path) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return install / ".update_backups" / ts


def backup_state(install: Path, result: UpdateResult) -> Path:
    """Back up data files AND current program files for rollback.

    Returns the backup directory. Data is small; the program copy (~120 MB)
    is the rollback source if the new version fails its startup check.
    """
    bk = _backup_dir(install)
    (bk / "data").mkdir(parents=True, exist_ok=True)
    (bk / "program").mkdir(parents=True, exist_ok=True)
    data_carried: list[str] = []
    for entry in install.iterdir():
        name = entry.name
        if name in _UPDATE_DIRS:
            continue
        if entry.is_file() and _is_data_file(name):
            try:
                shutil.copy2(entry, bk / "data" / name)
                data_carried.append(name)
            except OSError as e:
                _log(result, "backup", f"WARN: could not back up data {name}: {e}")
        elif entry.is_file():
            try:
                shutil.copy2(entry, bk / "program" / name)
            except OSError as e:
                _log(result, "backup", f"WARN: could not back up program {name}: {e}")
        elif entry.is_dir():
            try:
                shutil.copytree(entry, bk / "program" / name, dirs_exist_ok=True)
            except OSError as e:
                _log(result, "backup", f"WARN: could not back up dir {name}: {e}")
    _log(result, "backup", f"{bk.name} (data: {', '.join(data_carried) or 'none'})")
    return bk


def restore_state(install: Path, bk: Path, result: UpdateResult) -> None:
    """Roll back: restore program files (and re-assert data files) from *bk*."""
    prog = bk / "program"
    if prog.is_dir():
        for entry in prog.iterdir():
            try:
                if entry.is_file():
                    shutil.copy2(entry, install / entry.name)
                elif entry.is_dir():
                    shutil.copytree(entry, install / entry.name, dirs_exist_ok=True)
            except OSError as e:
                _log(result, "rollback", f"WARN: could not restore {entry.name}: {e}")
    data = bk / "data"
    if data.is_dir():
        for entry in data.iterdir():
            try:
                shutil.copy2(entry, install / entry.name)
            except OSError as e:
                _log(result, "rollback", f"WARN: could not restore data {entry.name}: {e}")
    result.rolled_back = True
    _log(result, "rollback", f"restored program+data from {bk.name}")


def apply_program(install: Path, dist_root: Path, result: UpdateResult) -> None:
    """Copy the staged program files over the install dir, in place.

    Data files are NEVER in the release archive (program-only build), so they
    are left untouched; we additionally skip anything that matches the data
    set defensively. Update-machinery dirs are skipped too."""
    for entry in dist_root.iterdir():
        name = entry.name
        if name in _UPDATE_DIRS:
            continue
        if _is_data_file(name):
            continue  # never overwrite user data from an archive
        dest = install / name
        if entry.is_dir():
            shutil.copytree(entry, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(entry, dest)
    _log(result, "swap", "program files replaced in place (data preserved)")


# ── startup-ok (injectable for tests) ─────────────────────────────────


def _read_from(path: Path, offset: int) -> str:
    if not path.exists():
        return ""
    try:
        with path.open("rb") as f:
            f.seek(offset)
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def default_startup_ok(install: Path, timeout_sec: int) -> tuple[bool, str]:
    """Launch main.exe and confirm it starts healthily.

    Healthy = the process stays alive AND a fresh ``STARTING`` line appears in
    startup_log.txt without an immediate Traceback/CRITICAL. Uses the app's
    own log signal — no application change required. The launched app is left
    running (this is the user's post-update session)."""
    exe = install / "main.exe"
    log = install / "startup_log.txt"
    offset = log.stat().st_size if log.exists() else 0
    try:
        proc = subprocess.Popen([str(exe)], cwd=str(install))
    except OSError as e:
        return False, f"could not launch main.exe: {e}"
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False, f"main.exe exited early (rc={proc.returncode})"
        fresh = _read_from(log, offset)
        if "STARTING" in fresh:
            time.sleep(2)  # let any immediate traceback surface
            fresh = _read_from(log, offset)
            if "Traceback" in fresh or "CRITICAL" in fresh:
                return False, "startup traceback/CRITICAL in log"
            return True, "main.exe started OK"
        time.sleep(0.5)
    return False, "no STARTING logged within timeout"


# ── version metadata ──────────────────────────────────────────────────


def write_version_json(install: Path, manifest: VersionManifest, channel: str) -> None:
    payload = {
        "version": manifest.version,
        "channel": channel,
        "asset": manifest.asset,
        "installed_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "updater": "update_exe/1.0",
    }
    tmp = install / "version.json.tmp"
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, install / "version.json")


def read_installed_version(install: Path) -> Optional[str]:
    vf = install / "version.json"
    if not vf.exists():
        return None
    try:
        return str(json.loads(vf.read_text(encoding="utf-8")).get("version"))
    except (json.JSONDecodeError, OSError):
        return None


# ── the update pipeline ───────────────────────────────────────────────


def run_update(
    install: Path,
    manifest: VersionManifest,
    archive: Path,
    *,
    channel: str,
    min_free_space_mb: int = MIN_FREE_SPACE_MB,
    startup_timeout_sec: int = STARTUP_TIMEOUT_SEC,
    startup_ok_fn: Callable[[Path, int], tuple[bool, str]] = default_startup_ok,
    launch_after: bool = True,
) -> UpdateResult:
    """Full in-place update with backup + rollback. Never raises."""
    result = UpdateResult(version=manifest.version)
    lock = UpdateLock(install)
    if not lock.acquire():
        result.stage = "lock"
        result.message = "another updater is already running"
        return result
    try:
        free = Updater._free_space_mb(install)
        if free < min_free_space_mb:
            raise RuntimeError(f"insufficient free space: {free}MB < {min_free_space_mb}MB")
        _log(result, "preflight", f"free_space={free}MB")

        staging = install / ".update_staging"
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(staging)
        dist_root = find_dist_root(staging)
        _log(result, "staging", str(dist_root))

        verify_archive(archive, manifest, result)
        verify_exe_layout(dist_root, result)

        prev_version = read_installed_version(install)
        bk = backup_state(install, result)

        try:
            apply_program(install, dist_root, result)
        except Exception as e:
            result.message = f"swap failed: {type(e).__name__}: {e}"
            _log(result, "error", result.message)
            restore_state(install, bk, result)
            return result

        if launch_after:
            ok, detail = startup_ok_fn(install, startup_timeout_sec)
            _log(result, "startup-ok", detail)
            if not ok:
                result.message = f"startup check failed: {detail}"
                restore_state(install, bk, result)
                return result

        write_version_json(install, manifest, channel)
        _log(result, "version.json",
             f"{prev_version or '(none)'} -> {manifest.version}")
        shutil.rmtree(staging, ignore_errors=True)
        result.ok = True
        result.stage = "complete"
        result.message = f"updated to {manifest.version}"
        return result
    except Exception as e:
        result.ok = False
        result.stage = result.stage or "unknown"
        result.message = f"{type(e).__name__}: {e}"
        _log(result, "error", result.message)
        return result
    finally:
        lock.release()


# ── channel: fetch + manifest ─────────────────────────────────────────


def _local_channel(from_file: Path, result: UpdateResult) -> tuple[Path, VersionManifest]:
    from core.infra.github_fetcher import manifest_from_local_zip
    if not from_file.is_file():
        raise RuntimeError(f"local archive not found: {from_file}")
    manifest = manifest_from_local_zip(from_file)
    _log(result, "fetch", f"local: {from_file} (version {manifest.version})")
    return from_file, manifest


def _github_channel(
    install: Path, *, tag: Optional[str], pin_tag: Optional[str], result: UpdateResult,
) -> tuple[Path, VersionManifest]:
    from core.infra.github_fetcher import fetch_release_asset
    archive, manifest = fetch_release_asset(
        install, tag=tag, dest_dir=install / ".update_state",
    )
    _log(result, "fetch", f"github release: {manifest.asset} (tag {manifest.version})")
    if pin_tag and manifest.version != pin_tag:
        raise RuntimeError(
            f"release tag {manifest.version} != pinned tag {pin_tag} — refusing "
            "(possible compromised release; update the pin to accept it)"
        )
    return archive, manifest


def _resolve_pin_tag(explicit: Optional[str], install: Path) -> Optional[str]:
    if explicit:
        return explicit.strip().lower() or None
    pin_file = install / "updater_exe_pin.txt"
    if pin_file.is_file():
        for line in pin_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line.lower()
    return None


# ── CLI ───────────────────────────────────────────────────────────────


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Update the Master-Report exe in place.")
    ap.add_argument("--install-dir", default=None,
                    help="folder containing main.exe (default: auto-detect)")
    ap.add_argument("--from-file", default=None,
                    help="update from a local zip instead of GitHub")
    ap.add_argument("--tag", default=None,
                    help="GitHub release tag to install (default: latest)")
    ap.add_argument("--pin-tag", default=None,
                    help="refuse any release tag other than this one")
    ap.add_argument("--no-launch", action="store_true",
                    help="do not launch/startup-check after updating")
    args = ap.parse_args(argv)

    install = Path(args.install_dir).resolve() if args.install_dir else install_dir_default()
    if not (install / "main.exe").is_file():
        print(f"[update_exe] no main.exe in {install} — not an exe install")
        return 1

    result = UpdateResult()
    try:
        if args.from_file:
            archive, manifest = _local_channel(Path(args.from_file).resolve(), result)
            channel = "local"
            pin = None
        else:
            pin = _resolve_pin_tag(args.pin_tag, install)
            archive, manifest = _github_channel(
                install, tag=args.tag, pin_tag=pin, result=result,
            )
            channel = "github"
    except RuntimeError as e:
        msg = str(e)
        print(f"[update_exe] fetch failed: {msg}")
        if "auth" in msg.lower():
            return 3
        return 2

    res = run_update(
        install, manifest, archive,
        channel=channel, launch_after=not args.no_launch,
    )
    for line in res.log_lines:
        print(line)
    if res.ok:
        print(f"[update_exe] SUCCESS: {res.message}")
        return 0
    if res.rolled_back:
        print(f"[update_exe] ROLLED BACK: {res.message}")
        return 5
    if "L0" in res.stage or "L1" in res.stage or "pin" in res.message.lower():
        return 4
    print(f"[update_exe] FAILED at {res.stage}: {res.message}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
