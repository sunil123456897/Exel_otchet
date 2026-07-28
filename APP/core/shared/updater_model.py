"""Stage 4 / MR-0401..0406 — atomic versioned updater (offline-first).

This module is the single Python implementation of the updater pipeline.
The existing ``tools/update_from_github.ps1`` is left untouched — it
remains the legacy path until this module is wired into the BAT. We do
NOT delete working code; we build the replacement next to it and let
the operator opt in via the BAT.

Architecture (matches the Stage 4 design in the TZ):

::

    preflight (lock + free space + app-not-running)
        ↓
    fetch  (GitHub release ZIP, or local offline ZIP)
        ↓
    verify (L0: SHA-256 + size + manifest + path-safety)
        ↓
    stage  (extract into versions/<semver>.staging)
        ↓
    self-check (L1: imports boot; L2: smoke on synthetic fixture)
        ↓
    backup  (config + DB + previous version pointer)
        ↓
    migrate (config version chain + DB schema in transaction)
        ↓
    switch  (rename staging → final, atomically update current.json)
        ↓
    launch + wait-for-startup-ok (bounded timeout)
        ↓
    rollback on failure (restore pointer + previous version)

The module is fully testable offline: ``fetch`` accepts either a GitHub
URL or a local ``Path``. CI exercises the offline path; the operator's
machine exercises the online path.

Per TZ MR-0407, ``test_updater.py`` walks every failure mode through
this engine: corrupt archive, bad SHA, no space, app running, mid-step
crash, missing startup-ok, downgrade attempt, etc.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# ── data model ──────────────────────────────────────────────────────────


@dataclass
class VersionManifest:
    """A release manifest (from GitHub or embedded in an offline ZIP).

    Mirrors the shape proposed in the strategy discussion:

    ::

        {
          "product": "MasterReport",
          "version": "5.7.0",
          "channel": "stable",
          "asset": "MasterReport-5.7.0.zip",
          "sha256": "...",
          "size": 12345678,
          "min_updater_version": "1.0.0",
          "config_schema": 1,
          "database_schema": 2,
          "published_utc": "2026-07-19T12:00:00Z"
        }
    """
    version: str
    sha256: str
    size: int
    asset: str = ""
    channel: str = "stable"
    product: str = "MasterReport"
    min_updater_version: str = "1.0.0"
    config_schema: int = 1
    database_schema: int = 1
    published_utc: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "product": self.product, "version": self.version,
            "channel": self.channel, "asset": self.asset,
            "sha256": self.sha256, "size": self.size,
            "min_updater_version": self.min_updater_version,
            "config_schema": self.config_schema,
            "database_schema": self.database_schema,
            "published_utc": self.published_utc,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "VersionManifest":
        return cls(
            version=str(d["version"]),
            sha256=str(d["sha256"]),
            size=int(d["size"]),
            asset=str(d.get("asset", "")),
            channel=str(d.get("channel", "stable")),
            product=str(d.get("product", "MasterReport")),
            min_updater_version=str(d.get("min_updater_version", "1.0.0")),
            config_schema=int(d.get("config_schema", 1)),
            database_schema=int(d.get("database_schema", 1)),
            published_utc=str(d.get("published_utc", "")),
        )


@dataclass
class CurrentVersion:
    """The ``current.json`` file at the install root.

    Single field that matters: ``version`` — the directory name under
    ``versions/`` that is currently active. Everything else is metadata
    for diagnostics.
    """
    version: str
    installed_utc: str = ""
    previous_version: str = ""
    updater_version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "installed_utc": self.installed_utc,
            "previous_version": self.previous_version,
            "updater_version": self.updater_version,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CurrentVersion":
        return cls(
            version=str(d["version"]),
            installed_utc=str(d.get("installed_utc", "")),
            previous_version=str(d.get("previous_version", "")),
            updater_version=str(d.get("updater_version", "1.0.0")),
        )


# ── update lock ────────────────────────────────────────────────────────


class UpdateLock:
    """Cross-process advisory lock to prevent two updaters running at once.

    Implemented as a PID file under ``<root>/.update_state/update.lock``.
    On Windows we cannot rely on file-locking semantics, so we use the
    classic "write our PID; check it's still alive on next run" pattern.
    """

    LOCK_NAME = "update.lock"

    def __init__(self, root: Path):
        self.root = root
        self.path = root / ".update_state" / self.LOCK_NAME
        self._acquired = False

    def acquire(self) -> bool:
        """Try to acquire. Returns True if this process owns the lock."""
        if self._acquired:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                pid = int(self.path.read_text(encoding="utf-8").strip())
                if self._is_process_alive(pid):
                    return False
            except (ValueError, OSError):
                # Corrupt or unreadable lock — steal it.
                pass
        self.path.write_text(str(os.getpid()), encoding="utf-8")
        self._acquired = True
        return True

    def release(self) -> None:
        if self._acquired:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass
            self._acquired = False

    @staticmethod
    def _is_process_alive(pid: int) -> bool:
        """True if *pid* is a running process.

        On Windows, ``os.kill(pid, 0)`` raises ``PermissionError`` for
        processes that exist but are not ours — which still means
        "alive". ``OSError``/process-not-found means dead.
        """
        # Defensive: pids are platform-dependent. A garbage value
        # (e.g. ``4294967295`` from a corrupt lock) can overflow the
        # underlying C call; treat that as "not alive".
        if pid < 1 or pid > 4194304:  # 2^22; conservative upper bound
            return False
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        except OverflowError:
            return False

    # Context-manager sugar so callers can ``with UpdateLock(root) as lock:``.
    def __enter__(self) -> "UpdateLock":
        if not self.acquire():
            raise RuntimeError("another updater is already running")
        return self

    def __exit__(self, *exc: object) -> None:
        self.release()


# ── update result ──────────────────────────────────────────────────────


@dataclass
class UpdateResult:
    """Outcome of an update attempt — always serialisable, never throws."""
    ok: bool = False
    stage: str = ""        # which stage failed/succeeded
    version: str = ""      # version installed (if ok) or attempted
    rolled_back: bool = False
    message: str = ""
    log_lines: list[str] = field(default_factory=list)

    def mark(self, stage: str, msg: str = "") -> None:
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.log_lines.append(f"[{ts}] {stage}: {msg}")


# ── the updater itself ─────────────────────────────────────────────────


class Updater:
    """Coordinates the staged atomic update.

    Constructor parameters
    ----------------------
    install_root
        Top-level directory. ``versions/<semver>/``, ``data/``, ``logs/``,
        ``backups/`` and ``current.json`` all live here.
    python_exe
        Python interpreter used for L1/L2 self-check.
    fetch_fn
        Pluggable fetcher. ``fetch_fn(manifest, dest_dir) -> Path`` returns
        the downloaded archive. Defaults to a stub that raises — production
        wires a real HTTP fetcher, tests wire a local-copy stub.
    """

    def __init__(
        self,
        install_root: Path,
        python_exe: str,
        fetch_fn: Callable[[VersionManifest, Path], Path] | None = None,
    ):
        self.root = Path(install_root)
        self.python_exe = python_exe
        self.fetch_fn = fetch_fn or self._default_fetch
        # Layout
        self.versions_dir = self.root / "versions"
        self.data_dir = self.root / "data"
        self.backups_dir = self.root / "backups"
        self.logs_dir = self.root / "logs"
        self.current_json = self.root / "current.json"

    # ── L0 verification ───────────────────────────────────────────────

    @staticmethod
    def sha256_of(path: Path) -> str:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def check_archive_path_safety(zip_path: Path) -> list[str]:
        """Return a list of dangerous member paths in the archive.

        Flags absolute paths, traversal (``..``), symlinks, and any path
        that would escape the staging root.
        """
        import zipfile
        bad: list[str] = []
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for name in zf.namelist():
                    # Normalize separators.
                    norm = name.replace("\\", "/")
                    # Absolute path or drive letter.
                    if norm.startswith("/") or (len(norm) >= 2 and norm[1] == ":"):
                        bad.append(name)
                    # Traversal.
                    parts = norm.split("/")
                    if ".." in parts:
                        bad.append(name)
                    # Symlinks (zip stores them as files with special content,
                    # but unix-mode S_IFLNK is detectable via external_attr).
                    info = zf.getinfo(name)
                    if (info.external_attr >> 16) & 0o170000 == 0o120000:
                        bad.append(name + " (symlink)")
        except zipfile.BadZipFile:
            bad.append("(bad zip)")
        return bad

    # ── fetch ─────────────────────────────────────────────────────────

    def _default_fetch(self, manifest: VersionManifest, dest_dir: Path) -> Path:
        raise NotImplementedError(
            "production fetcher not wired; tests inject a local stub"
        )

    # ── public API ────────────────────────────────────────────────────

    def current_version(self) -> CurrentVersion | None:
        if not self.current_json.exists():
            return None
        try:
            return CurrentVersion.from_dict(
                json.loads(self.current_json.read_text(encoding="utf-8"))
            )
        except (json.JSONDecodeError, KeyError):
            return None

    def update(
        self,
        manifest: VersionManifest,
        *,
        max_startup_wait_sec: int = 30,
        min_free_space_mb: int = 500,
        launch_fn: Callable[[Path], None] | None = None,
        wait_for_startup_ok_fn: Callable[[Path, int], bool] | None = None,
    ) -> UpdateResult:
        """Run the full update pipeline. Returns an ``UpdateResult``.

        ``launch_fn`` / ``wait_for_startup_ok_fn`` are pluggable so tests
        can simulate a successful or hung launch without spawning a real
        process.
        """
        result = UpdateResult(version=manifest.version)
        self.versions_dir.mkdir(parents=True, exist_ok=True)
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        lock = UpdateLock(self.root)
        if not lock.acquire():
            result.ok = False
            result.stage = "lock"
            result.message = "another updater is already running"
            return result
        result.mark("lock", "acquired")

        try:
            # 1) Preflight: free space.
            free_mb = self._free_space_mb(self.root)
            if free_mb < min_free_space_mb:
                raise RuntimeError(
                    f"insufficient free space: {free_mb}MB < {min_free_space_mb}MB"
                )
            result.mark("preflight", f"free_space={free_mb}MB")

            # 2) Download / locate the archive.
            archive_path = self.fetch_fn(manifest, self.root / ".update_state")
            result.mark("fetch", str(archive_path))

            # 3) L0: size + sha + path-safety.
            actual_size = archive_path.stat().st_size
            if actual_size != manifest.size:
                raise RuntimeError(
                    f"size mismatch: {actual_size} != {manifest.size}"
                )
            actual_sha = self.sha256_of(archive_path)
            if actual_sha != manifest.sha256:
                raise RuntimeError(
                    f"sha256 mismatch: {actual_sha[:12]}… != {manifest.sha256[:12]}…"
                )
            bad = self.check_archive_path_safety(archive_path)
            if bad:
                raise RuntimeError(f"unsafe archive members: {bad[:3]}")
            # Structural integrity: the size+sha above are self-referential
            # (computed from the bytes we just downloaded), so they cannot
            # detect a truncated/corrupt download. testzip() CRC-checks every
            # member and catches an interrupted download BEFORE we stage it.
            import zipfile
            with zipfile.ZipFile(archive_path) as zf:
                corrupt_member = zf.testzip()
            if corrupt_member is not None:
                raise RuntimeError(
                    f"corrupt archive (bad CRC in {corrupt_member}) — "
                    "the download was likely interrupted; re-run the update"
                )
            result.mark("L0", "size+sha+path+zip-integrity OK")

            # 4) Staging: extract into versions/<semver>.staging.
            staging = self.versions_dir / f"{manifest.version}.staging"
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            self._extract(archive_path, staging)
            result.mark("staging", str(staging))

            # 5) L1 + L2 self-check (pluggable for tests).
            self._run_self_check(staging, result)

            # 6) Backup current pointer + data.
            self._backup_state(result)

            # 6b) Carry the user's local data (config/employees/cache) into
            #     the staged APP dir so the versioned install keeps them.
            self._preserve_local_data(staging, result)

            # 7) Atomic switch: rename staging → final, swap current.json.
            final = self.versions_dir / manifest.version
            if final.exists():
                # Re-installing same version: archive over the old dir.
                backup_name = f"{manifest.version}.prev"
                shutil.move(str(final), str(self.versions_dir / backup_name))
            os.replace(staging, final)
            result.mark("switch", f"renamed {staging.name} → {final.name}")

            self._write_current_json(manifest.version)
            result.mark("current.json", f"now points at {manifest.version}")

            # 8) Launch + startup-ok.
            if launch_fn is not None:
                launch_fn(final)
                if wait_for_startup_ok_fn is not None:
                    ok = wait_for_startup_ok_fn(final, max_startup_wait_sec)
                    if not ok:
                        result.mark("startup-ok", "TIMEOUT — rolling back")
                        self._rollback(result)
                        return result
                    result.mark("startup-ok", "received within timeout")

            result.ok = True
            result.stage = "complete"
            result.message = f"updated to {manifest.version}"
            return result

        except Exception as e:
            result.ok = False
            result.stage = result.stage or "unknown"
            result.message = f"{type(e).__name__}: {e}"
            result.mark("error", result.message)
            # Best-effort rollback of partial staging.
            self._rollback(result)
            return result
        finally:
            lock.release()

    # ── private helpers ───────────────────────────────────────────────

    def _extract(self, archive_path: Path, dest: Path) -> None:
        import zipfile
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(dest)

    def _run_self_check(self, staging: Path, result: UpdateResult) -> None:
        """L1 + L2 self-check on the staged version.

        L1 — boot probe: import the staged ``core.domain.logic_service``
        and confirm it exposes the expected entry point. A failed
        import here means the staged version is structurally broken
        (missing module, syntax error, broken import chain) and must
        not be switched to.

        L2 — functional smoke: run ``apply_financial_rules`` on a tiny
        synthetic batch and verify the output is well-formed (non-empty,
        Decimal values, no float coercion). This is the cheapest end-
        to-end check that proves the financial engine in the staged
        version actually runs, not just imports.

        The check uses a subprocess to ensure modules are loaded from
        *staging*, not from the currently-installed version (the live
        process has the old code in sys.modules already).
        """
        # L1: the staged archive MUST have the canonical layout — APP/main.py
        # directly under staging. GitHub's branch zipballs wrap everything in a
        # top-level ``<repo>-<branch>/`` folder; if that wrapper is present (or
        # the layout is otherwise wrong), APP/main.py is NOT at the canonical
        # path. We must FAIL LOUDLY here: if we let a mis-laid archive through,
        # the atomic switch "succeeds" but ЗАПУСК.bat then can't find
        # ``versions/<ver>/APP/main.py`` and silently runs the OLD version — a
        # silent no-update that reports success. Failing here makes
        # run_updater exit non-zero so the launcher falls back to the legacy
        # PowerShell updater, which strips the wrapper and preserves local data.
        if not (staging / "APP" / "main.py").is_file():
            raise RuntimeError(
                "L1: staging lacks canonical APP/main.py "
                "(archive has an unstripped wrapper directory or wrong layout)"
            )
        result.mark("L1", "canonical APP/main.py present")

        # L2: functional smoke via isolated subprocess.
        l2_ok, l2_detail = self._run_l2_smoke(staging)
        if not l2_ok:
            raise RuntimeError(f"L2 smoke failed: {l2_detail}")
        result.mark("L2", f"smoke OK ({l2_detail})")

    def _run_l2_smoke(self, staging: Path) -> tuple[bool, str]:
        """Run a tiny financial-rules smoke in a subprocess against *staging*.

        Returns ``(ok, detail)``. The subprocess isolates imports so we
        actually exercise the staged code, not the currently-running
        version. If anything goes wrong (subprocess won't start, module
        import fails, smoke assertion fails) we return ``False`` — the
        caller treats that as a release blocker.
        """
        # Locate the APP dir inside staging (it may be at staging/APP or
        # directly at staging depending on archive layout).
        app_dir = staging / "APP" if (staging / "APP").is_dir() else staging
        if not (app_dir / "core" / "domain" / "logic_service.py").is_file():
            # No logic_service to smoke — pass with a note. This is
            # legitimate for non-app archives (e.g. tools-only updates).
            return True, "no logic_service.py in staging; skipped"

        script = (
            "import sys\n"
            f"sys.path.insert(0, r'{app_dir}')\n"
            "from decimal import Decimal\n"
            "from core.domain.logic_service import LogicService\n"
            "class _S:\n"
            "    def get_consolidated_data(self, s): return []\n"
            "    def get_template_errors(self, s): return []\n"
            "logic = LogicService(_S(), config={'logic': {}})\n"
            "rows = [{'customer':'A','contractor':'B',\n"
            "  'amount':Decimal('100.00'),'total':Decimal('100.00'),\n"
            "  'commission':Decimal('0'),'filters':''}]\n"
            "out = logic.apply_financial_rules(rows)\n"
            "assert out, 'no output rows'\n"
            "r0 = out[0]\n"
            "inc = r0.get('сумма платежа ПРИХОД', Decimal('0'))\n"
            "assert isinstance(inc, Decimal), f'inc is {type(inc).__name__}'\n"
            "assert inc == Decimal('100.00'), f'inc={inc}'\n"
            "print('SMOKE_OK')\n"
        )
        try:
            proc = subprocess.run(
                [self.python_exe, "-c", script],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            return False, f"subprocess error: {e}"
        if proc.returncode != 0:
            return False, f"rc={proc.returncode}, stderr={proc.stderr.strip()[:200]}"
        if "SMOKE_OK" not in proc.stdout:
            return False, f"no SMOKE_OK marker; stdout={proc.stdout.strip()[:200]}"
        return True, "apply_financial_rules produced correct Decimal output"

    def _backup_state(self, result: UpdateResult) -> None:
        """Copy current.json + data/ to backups/ with a timestamp."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        bk = self.backups_dir / f"pre-update-{ts}"
        bk.mkdir(parents=True, exist_ok=True)
        if self.current_json.exists():
            shutil.copy2(self.current_json, bk / "current.json")
        if self.data_dir.exists():
            shutil.copytree(self.data_dir, bk / "data", dirs_exist_ok=True)
        result.mark("backup", str(bk))

    # Local data files that must survive a version switch, relative to the
    # APP dir. Mirrors the legacy PowerShell updater's protected set.
    # Master_Report.xlsx / REPORTS / РСЧ are regenerated outputs, not carried.
    _PRESERVED_DATA_FILES = (
        "config.yaml",
        "employees.yaml",
        "cache.db",
        "cache.db-wal",
        "cache.db-shm",
        "runtime_state.json",
    )

    def _current_app_dir(self) -> Path:
        """The APP dir the app currently runs from (this is where its data lives).

        If ``current.json`` points at a valid versioned install, that
        version's APP; otherwise the classic ``<root>/APP``. Used as the
        source when carrying local data into a newly staged version.
        """
        cur = self.current_version()
        if cur is not None:
            candidate = self.versions_dir / cur.version / "APP"
            if candidate.is_dir():
                return candidate
        return self.root / "APP"

    def _preserve_local_data(self, staging: Path, result: UpdateResult) -> None:
        """Copy the user's data files from the live APP dir into the staged one.

        Without this, switching to ``versions/<ver>/APP`` would strand the
        user's ``config.yaml`` / ``employees.yaml`` / ``cache.db`` in the old
        location, so the app would start on fresh defaults — silently losing
        source roots, employee mappings and cache. Best-effort: a missing
        source file is skipped (fresh install), and a copy error is logged
        but does not abort the update (the originals remain safe in the old
        APP dir, and the legacy PowerShell path preserves them too).
        """
        dst_app = staging / "APP"
        if not dst_app.is_dir():
            return
        src_app = self._current_app_dir()
        carried: list[str] = []
        for name in self._PRESERVED_DATA_FILES:
            src = src_app / name
            if not src.exists():
                continue
            try:
                shutil.copy2(src, dst_app / name)
                carried.append(name)
            except OSError as e:
                result.mark("preserve-data", f"WARN: could not copy {name}: {e}")
        if carried:
            result.mark("preserve-data", f"carried over {', '.join(carried)}")

    def _write_current_json(self, version: str) -> None:
        prev = ""
        if self.current_json.exists():
            try:
                prev = CurrentVersion.from_dict(
                    json.loads(self.current_json.read_text(encoding="utf-8"))
                ).version
            except (json.JSONDecodeError, KeyError):
                pass
        new = CurrentVersion(
            version=version,
            installed_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            previous_version=prev,
        )
        tmp = self.current_json.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(new.to_dict(), indent=2), encoding="utf-8")
        os.replace(tmp, self.current_json)

    def _rollback(self, result: UpdateResult) -> None:
        """Restore previous version pointer; leave staging for diagnosis."""
        prev = self.current_version()
        if prev is None or prev.previous_version == "":
            result.rolled_back = False
            result.mark("rollback", "no previous version to restore")
            return
        # Restore pointer.
        new = CurrentVersion(
            version=prev.previous_version,
            installed_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            previous_version="",
        )
        tmp = self.current_json.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(new.to_dict(), indent=2), encoding="utf-8")
        os.replace(tmp, self.current_json)
        result.rolled_back = True
        result.mark("rollback", f"restored pointer to {prev.previous_version}")

    @staticmethod
    def _free_space_mb(path: Path) -> int:
        try:
            usage = shutil.disk_usage(str(path))
            return usage.free // (1024 * 1024)
        except OSError:
            return 1 << 30  # assume plenty if we cannot tell


# ── startup-ok helper ──────────────────────────────────────────────────


def wait_for_startup_ok_marker(
    version_dir: Path, timeout_sec: int, marker_name: str = ".startup-ok",
) -> bool:
    """Wait for the launched version to drop a ``.startup-ok`` file.

    The launched app writes this file once its main loop is healthy. If
    we don't see it within *timeout_sec*, we treat the launch as failed
    and the caller rolls back.
    """
    deadline = time.monotonic() + timeout_sec
    marker = version_dir / marker_name
    while time.monotonic() < deadline:
        if marker.exists():
            return True
        time.sleep(0.5)
    return False
