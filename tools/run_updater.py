#!/usr/bin/env python3
"""Stage 4 wiring — single CLI entrypoint for the new Python updater.

This script is what the BAT files call. It builds a ``Updater`` with
the right fetcher (GitHub branch zipball or local offline ZIP) and
runs the full atomic-update pipeline. Output goes to
``update_log.txt`` next to the install root — same convention as the
legacy ``update_from_github.ps1`` so operator tooling keeps working.

Modes
-----

* ``--branch <name>`` (default ``main``):
    Fetch the latest branch zipball from GitHub. Needs ``.github_token``
    only if the repo is private.
* ``--zip <path>``:
    Offline update from a local ZIP file (``ОБНОВИТЬ_ИЗ_ФАЙЛА.bat``).
    No network required.
* ``--launch``:
    After a successful update, start ``ЗАПУСК.bat``.

Failure modes are deliberate and visible:

* Network down → exit 2, message "GitHub unreachable".
* Auth failed → exit 3, message "auth failed".
* L0/L1/L2 check failed → exit 4, message identifying which check.
* Rollback happened → exit 5, message "rolled back to previous".
* Success → exit 0.

The script never raises an unhandled exception to the operator. Every
failure path is caught, logged, and turned into a numeric exit code.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / "APP"

# Make APP/ importable both as `core.*` and as `APP.*` (for the
# updater_model imports).
for p in (str(APP_DIR), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

LOG_FILE = REPO_ROOT / "update_log.txt"


def log(message: str) -> None:
    """Append a timestamped line to update_log.txt and stdout."""
    ts = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {message}"
    try:
        print(line)
    except UnicodeEncodeError:
        # A console whose encoding can't represent the (Russian) text must
        # not crash the updater — fall back to an ASCII-safe rendering.
        print(line.encode("ascii", "replace").decode("ascii"))
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


# ── commit pinning (supply-chain integrity) ────────────────────────────

PIN_FILE = REPO_ROOT / "tools" / "updater_pin.txt"


def resolve_pin(cli_pin: str | None) -> str | None:
    """Resolve the effective commit pin: CLI flag wins, else ``updater_pin.txt``.

    The pin file is optional and operator-managed; blank lines and ``#``
    comments are ignored. Returns a normalised lowercase SHA or ``None``.
    """
    if cli_pin and cli_pin.strip():
        return cli_pin.strip().lower()
    if PIN_FILE.is_file():
        try:
            for line in PIN_FILE.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    return line.lower()
        except OSError:
            return None
    return None


def verify_commit_pin(pin: str, resolved_sha: str) -> bool:
    """Pure comparison: True iff the resolved branch HEAD matches the pin."""
    return bool(pin) and bool(resolved_sha) and (
        pin.strip().lower() == resolved_sha.strip().lower()
    )


# ── main ───────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Atomic Python updater for Master-Report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--branch", default="main",
                     help="GitHub branch to fetch (default: main)")
    src.add_argument("--zip", metavar="PATH",
                     help="local ZIP file for offline update")
    parser.add_argument("--owner", default="sunil123456897",
                        help="GitHub repo owner (default: sunil123456897)")
    parser.add_argument("--repo", default="Exel_otchet",
                        help="GitHub repo name (default: Exel_otchet)")
    parser.add_argument("--install-root", default=str(REPO_ROOT),
                        help="install root directory (default: repo root; "
                             "tests override to a temp dir)")
    parser.add_argument("--launch", action="store_true",
                        help="after a successful update, run ЗАПУСК.bat")
    parser.add_argument("--pin-sha", default=None,
                        help="expected branch HEAD commit SHA; abort the "
                             "update if the fetched commit differs "
                             "(supply-chain integrity pin). If omitted, "
                             "tools/updater_pin.txt is used when present.")
    parser.add_argument("--python", default=sys.executable,
                        help="python interpreter for L1/L2 self-check "
                             "(default: this python)")
    args = parser.parse_args()

    log("=" * 60)
    log("Master-Report atomic updater — starting")
    log(f"  mode: {'offline ZIP' if args.zip else f'branch {args.branch!r}'}")

    # Build the fetcher + manifest.
    try:
        if args.zip:
            from core.infra.github_fetcher import (
                make_local_fetcher,
            )
            zip_path = Path(args.zip).resolve()
            if not zip_path.is_file():
                log(f"ERROR: ZIP not found: {zip_path}")
                return 2
            fetch_fn = make_local_fetcher(zip_path)
            # Manifest is derived from the actual ZIP bytes; we'll let
            # Updater.update recompute it on L0 to avoid path-leak.
            from core.infra.updater_model import VersionManifest
            import hashlib
            raw = zip_path.read_bytes()
            import re
            name_match = re.search(r"(\d+\.\d+\.\d+)", zip_path.name)
            version = name_match.group(1) if name_match else f"local-{hashlib.sha256(raw).hexdigest()[:8]}"
            manifest = VersionManifest(
                version=version,
                sha256=hashlib.sha256(raw).hexdigest(),
                size=len(raw),
                asset=zip_path.name,
                channel="offline",
            )
        else:
            from core.infra.github_fetcher import make_branch_fetcher
            fetch_fn = make_branch_fetcher(
                REPO_ROOT, owner=args.owner, repo=args.repo,
                branch=args.branch,
            )
            # For branch mode we don't know the manifest until we've
            # downloaded. We use a sentinel manifest; the fetcher
            # ignores it and Updater.update recomputes SHA/size on L0.
            # To make this work, we monkey-patch the L0 check to use
            # the actual downloaded bytes. Simpler: pre-fetch here, then
            # pass the local-fetcher closure + real manifest.
            log(f"  contacting GitHub: {args.owner}/{args.repo}@{args.branch}")
            try:
                from core.infra.github_fetcher import fetch_branch_zipball
                tmp_dir = REPO_ROOT / ".update_state"
                archive_path, manifest = fetch_branch_zipball(
                    REPO_ROOT, owner=args.owner, repo=args.repo,
                    branch=args.branch, dest_dir=tmp_dir,
                )
                fetch_fn = make_local_fetcher(archive_path)
                log(f"  fetched {manifest.size} bytes, sha {manifest.sha256[:12]}…")

                # Supply-chain integrity: if the operator pinned a commit SHA,
                # refuse to apply any other commit BEFORE anything is unpacked
                # or executed (Updater's L2 smoke runs code from the archive).
                pin = resolve_pin(args.pin_sha)
                if pin:
                    from core.infra.github_fetcher import resolve_branch_commit_sha
                    try:
                        commit_sha = resolve_branch_commit_sha(
                            REPO_ROOT, owner=args.owner, repo=args.repo,
                            branch=args.branch,
                        )
                    except RuntimeError as e:
                        log(f"ERROR: could not resolve commit SHA for pin check: {e}")
                        return 2
                    if not verify_commit_pin(pin, commit_sha):
                        log("SECURITY: commit pin MISMATCH — update ABORTED.")
                        log(f"  pinned : {pin}")
                        log(f"  fetched: {commit_sha}")
                        log(f"  Review the diff, then update the pin: "
                            f"https://github.com/{args.owner}/{args.repo}/"
                            f"compare/{pin}...{commit_sha}")
                        return 4
                    log(f"  commit pin verified ({commit_sha[:12]}…)")
                else:
                    log(f"WARNING: no commit pin set — updating from branch "
                        f"'{args.branch}' WITHOUT commit-integrity verification. "
                        f"Set --pin-sha or tools/updater_pin.txt to protect "
                        f"against repository/account compromise.")
            except RuntimeError as e:
                msg = str(e)
                log(f"ERROR: {msg}")
                if "auth" in msg.lower():
                    return 3
                if "network" in msg.lower() or "HTTP" in msg:
                    return 2
                return 6
    except Exception as e:
        log(f"ERROR: setup failed: {type(e).__name__}: {e}")
        log(traceback.format_exc())
        return 6

    # Build the Updater.
    try:
        from core.infra.updater_model import Updater
    except Exception as e:
        log(f"ERROR: updater module failed to import: {e}")
        return 6

    updater = Updater(
        install_root=Path(args.install_root).resolve(),
        python_exe=args.python,
        fetch_fn=fetch_fn,
    )

    # Launch + startup-ok handling.
    launched = {"path": None}

    def launch_fn(version_dir: Path) -> None:
        launched["path"] = version_dir
        # We don't actually start the app here — the BAT does that
        # after the script returns 0. We just record success.

    def wait_for_startup_ok(_version_dir: Path, _timeout: int) -> bool:
        # For BAT-driven launch we treat the script's own success as
        # the startup-ok signal. The actual GUI startup is verified by
        # the BAT launching ЗАПУСК.bat next, which will fail visibly
        # if the new version is broken.
        return True

    try:
        result = updater.update(
            manifest,
            launch_fn=launch_fn,
            wait_for_startup_ok_fn=wait_for_startup_ok,
        )
    except Exception as e:
        log(f"ERROR: update crashed: {type(e).__name__}: {e}")
        log(traceback.format_exc())
        return 6

    # Surface every log line.
    for line in result.log_lines:
        log(f"  {line}")

    if result.ok:
        log(f"OK: updated to {result.version}")
        if args.launch:
            log("launching ЗАПУСК.bat…")
            zap = REPO_ROOT / "ЗАПУСК.bat"
            if zap.is_file():
                # Detach so the updater script can exit cleanly.
                subprocess.Popen(
                    ["cmd.exe", "/c", str(zap)],
                    cwd=str(REPO_ROOT),
                    close_fds=True,
                )
        return 0
    else:
        log(f"FAILED at stage '{result.stage}': {result.message}")
        if result.rolled_back:
            log("  rolled back to previous version — operator may need "
                "to launch the old version manually.")
            return 5
        # Distinguish failure class.
        msg = result.message.lower()
        if "sha" in msg or "size" in msg or "l0" in msg:
            return 4
        if "l1" in msg or "l2" in msg or "smoke" in msg:
            return 4
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
