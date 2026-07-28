"""Reproducible single-file-distribution build for Master-Report (Nuitka).

Compiles ``APP/main.py`` (and the whole ``core`` package) to **native
machine code** via Nuitka and emits a self-contained ``main.dist/`` folder
(~120 MB) that runs on a clean Windows PC with no Python installed.

Why Nuitka (and not PyInstaller):
    PyInstaller only *bundles* your code as ``.pyc`` inside the archive —
    trivially extractable (``pyinstxtractor``) and decompilable. Nuitka
    compiles Python to C and then to native code, so there is **no .pyc to
    recover** — the actual protection upgrade this project wants. The build
    was validated on Python 3.12 with python-calamine and pydantic_core
    (both Rust extensions); Nuitka links their ``.pyd`` files in cleanly.

Why a *folder* (``--standalone``) and not ``--onefile``:
    The app writes its runtime state (``cache.db``, ``config.yaml``,
    ``startup_log.txt``, logs) next to ``Path(__file__).parent``. A onefile
    build extracts to a throw-away temp dir on every launch, so that state
    would be lost / read-only. A standalone folder keeps state beside the
    exe, which matches how the source tree behaves. Ship the folder as-is or
    zip it (``--zip``).

Bloat control:
    The build traces real imports from ``main.py`` and additionally EXCLUDES
    packages that are installed in the dev venv but never imported at
    runtime (pandas/numpy) or are pure dev tooling (mypy/pytest/ruff/...).
    This is what keeps the output at ~120 MB instead of the multi-gigabyte
    result you get from naively bundling the whole venv + the ``cache.db``.

Usage:
    python tools/build_exe.py            # build main.dist (release, no console)
    python tools/build_exe.py --console  # keep a console window (debugging)
    python tools/build_exe.py --zip      # also produce Master-Report_<ver>_win64.zip
    python tools/build_exe.py --clean    # wipe build_exe/ first

First run downloads the MinGW64 gcc Nuitka needs (~150 MB, cached in
``%LocalAppData%\\Nuitka``); subsequent builds reuse it and the ccache.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_APP_DIR = _ROOT / "APP"
_VERSION_FILE = _APP_DIR / "__init__.py"

# Packages present in the dev venv that must NOT be bundled: either unused
# at runtime (0 imports in APP/) or pure development tooling.
_EXCLUDES = (
    "pandas",
    "numpy",
    "pytest",
    "mypy",
    "hypothesis",
    "ruff",
    "fpdf",
    "pypdf",
    "fonttools",
    "vulture",
)


def _read_version() -> str:
    """Pull ``__version__`` from APP/__init__.py (the single source of truth)."""
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', _VERSION_FILE.read_text(encoding="utf-8"))
    return match.group(1) if match else "0.0"


def _check_nuitka() -> None:
    import importlib.util

    if importlib.util.find_spec("nuitka") is None:
        sys.exit(
            "Nuitka is not installed in this interpreter.\n"
            "Install it first:\n"
            "    python -m pip install nuitka ordered-set zstandard"
        )


def _build_argv(output_dir: Path, keep_console: bool) -> list[str]:
    argv = [
        sys.executable,
        "-m", "nuitka",
        "--standalone",
        "--include-package=core",
        "--enable-plugin=tk-inter",
        f"--output-dir={output_dir}",
        # Auto-download MinGW64 gcc on first build instead of prompting.
        "--assume-yes-for-downloads",
        # Drop the generated C sources after a successful compile.
        "--remove-output",
        # Ship the PNG/ICO icon set next to the exe. Nuitka does NOT
        # bundle this automatically (assets/ is data, not a package).
        # Without it every icon-only toolbar button — e.g. the sidebar
        # "refresh" button (text="") — renders invisible in the exe.
        # cwd is APP/, so this maps APP/assets -> <dist>/assets.
        "--include-data-dir=assets=assets",
        # First-run seed files so a BRAND-NEW PC (no prior data) is
        # self-sufficient: ConfigController auto-creates config.yaml from
        # the sibling example (Q:\ defaults, curators, column markers), and
        # cache.db is built from the full db_schema.sql. Without these the
        # exe produced a schema-less cache.db on a fresh PC.
        "--include-data-files=config.example.yaml=config.example.yaml",
        "--include-data-files=db_schema.sql=db_schema.sql",
        # Incremental migrations, needed to upgrade an EXISTING cache.db
        # carried forward to a newer version (fresh DBs are complete from
        # db_schema.sql). db_connection locates them via a frozen-aware path.
        "--include-data-dir=migrations=migrations",
    ]
    # Release builds hide the console (the app logs to startup_log.txt);
    # --console keeps it for debugging launch issues.
    if keep_console:
        argv.append("--windows-console-mode=force")
    else:
        argv.append("--windows-console-mode=disable")
    for pkg in _EXCLUDES:
        argv.append(f"--nofollow-import-to={pkg}")
    argv.append("main.py")  # entry point, resolved relative to cwd=APP
    return argv


def _dist_size_mb(dist: Path) -> float:
    total = sum(p.stat().st_size for p in dist.rglob("*") if p.is_file())
    return total / (1024 * 1024)


def _make_zip(output_dir: Path, version: str) -> Path:
    """Zip main.dist/ into a single distributable archive."""
    dist = output_dir / "main.dist"
    archive = output_dir / f"Master-Report_{version}_win64.zip"
    if archive.exists():
        archive.unlink()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(dist.rglob("*")):
            if path.is_file():
                # Top folder inside the zip: Master-Report/
                zf.write(path, Path("Master-Report") / path.relative_to(dist))
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--console", action="store_true",
                        help="keep a console window (for debugging launch issues)")
    parser.add_argument("--zip", action="store_true",
                        help="also produce a distributable .zip of the build")
    parser.add_argument("--clean", action="store_true",
                        help="remove the output directory before building")
    parser.add_argument("--output", default=str(_ROOT / "build_exe"),
                        help="output directory (default: <repo>/build_exe)")
    args = parser.parse_args()

    output_dir = Path(args.output).resolve()
    if args.clean and output_dir.exists():
        print(f"[build_exe] cleaning {output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not (_APP_DIR / "main.py").exists():
        sys.exit(f"[build_exe] entry point not found: {_APP_DIR / 'main.py'}")

    _check_nuitka()
    version = _read_version()
    print(f"[build_exe] Master-Report v{version}")
    print(f"[build_exe] Python:   {sys.version.split()[0]}")
    print(f"[build_exe] Output:   {output_dir}")
    print("[build_exe] Compiling with Nuitka (first run downloads MinGW64 gcc)...")

    argv = _build_argv(output_dir, args.console)
    # cwd=APP so the top-level `core` package resolves naturally.
    result = subprocess.run(argv, cwd=str(_APP_DIR))
    if result.returncode != 0:
        print(f"[build_exe] Nuitka failed with exit code {result.returncode}")
        return result.returncode

    dist = output_dir / "main.dist"
    exe = dist / "main.exe"
    if not exe.exists():
        print(f"[build_exe] build reported success but {exe} is missing")
        return 1

    print()
    print("=" * 60)
    print(f"[build_exe] SUCCESS — {exe}")
    print(f"[build_exe] dist size: {_dist_size_mb(dist):.1f} MB  "
          f"({sum(1 for _ in dist.rglob('*') if _.is_file())} files)")
    print("=" * 60)

    # Drop the friendly launcher into the dist so the portable folder has a
    # familiar double-click entry (ЗАПУСК.bat) that also surfaces
    # startup_log.txt if the app crashes on startup.
    launcher_src = _ROOT / "tools" / "exe_launcher.bat"
    if launcher_src.exists():
        shutil.copyfile(launcher_src, dist / "ЗАПУСК.bat")
        print(f"[build_exe] launcher copied -> {dist / 'ЗАПУСК.bat'}")

    if args.zip:
        archive = _make_zip(output_dir, version)
        print(f"[build_exe] zip: {archive} "
              f"({archive.stat().st_size / (1024 * 1024):.1f} MB)")

    print()
    print("The dist folder is the PROGRAM ONLY. It has no data by design.")
    print("To make it usable, copy next to main.exe:")
    print("    config.yaml      (paths.source_roots -> where the real reports live)")
    print("    employees.yaml   (curator list)")
    print("cache.db and logs are created automatically on first run.")
    print("Easiest: copy config.yaml + employees.yaml from a working install (e.g. Vika's PC).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
