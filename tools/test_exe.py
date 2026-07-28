"""End-to-end smoke test for the packaged Master-Report exe.

Validates the Nuitka build in ``build_exe/main.dist`` (or ``--dist``) on two
levels:

1. **Structural** — the package is complete and protected:
   - ``main.exe`` exists;
   - NO loose ``.py`` source leaked (the whole point of Nuitka over
     PyInstaller — code is native, not extractable ``.pyc``);
   - the icon set shipped (``assets/icons/{dark,light}``), without which
     icon-only buttons render invisible;
   - key runtime modules present (calamine, pydantic_core, sqlite3, tcl/tk);
   - no dev/heavy bloat bundled (pandas, numpy, pytest, mypy, ...);
   - total size stays sane (< 250 MB).

2. **Runtime** (unless ``--skip-launch``) — the app actually starts:
   - launches without import/GUI/icon errors;
   - the licence is accepted (NOT view-only) when a valid ``.license`` is
     present;
   - connects to the database and loads the employee list (> 0 employees).

The runtime phase launches the real ``main.exe``, lets it run long enough to
finish startup + the first employee refresh, then terminates it and inspects
the ``startup_log.txt`` the app writes. It is deliberately headless-friendly:
no GUI clicking is attempted (that needs a human or a UI-automation tool).

Exit code = number of failed checks (0 == everything passed), so this can gate
a release build.

Usage:
    python tools/test_exe.py                  # structural + runtime
    python tools/test_exe.py --skip-launch    # structural only
    python tools/test_exe.py --dist <dir>     # test a different build
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_DIST = _ROOT / "build_exe" / "main.dist"

# Modules that MUST be present for the app to function.
_REQUIRED = (
    "python_calamine",
    "pydantic_core",
    "sqlite3.dll",
    "tcl86t.dll",
    "tk86t.dll",
)

# Packages that must NOT be bundled (dev tooling / unused heavy deps).
_FORBIDDEN = (
    "pandas", "numpy", "scipy", "pytest", "mypy",
    "hypothesis", "ruff", "fpdf", "pypdf", "fonttools", "vulture",
)

_MAX_SIZE_MB = 250
_LAUNCH_WAIT_S = 35


class Report:
    """Collects PASS/FAIL results and prints a summary."""

    def __init__(self) -> None:
        self.failures: list[str] = []
        self.passes = 0

    def check(self, ok: bool, label: str, detail: str = "") -> None:
        mark = "PASS" if ok else "FAIL"
        suffix = f"  ({detail})" if detail else ""
        print(f"  [{mark}] {label}{suffix}")
        if ok:
            self.passes += 1
        else:
            self.failures.append(label)

    def summary(self) -> int:
        total = self.passes + len(self.failures)
        print()
        print("=" * 60)
        if self.failures:
            print(f"RESULT: {len(self.failures)}/{total} checks FAILED")
            for f in self.failures:
                print(f"  - {f}")
            return len(self.failures)
        print(f"RESULT: all {total} checks passed ✓")
        return 0


def _dir_size_mb(path: Path) -> float:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) / (1024 * 1024)


def structural(dist: Path, r: Report) -> None:
    print("Structural checks")
    exe = dist / "main.exe"
    r.check(exe.exists(), "main.exe exists")

    py_files = list(dist.rglob("*.py"))
    r.check(len(py_files) == 0, "no loose .py source (native build / protected)",
            f"{len(py_files)} found")

    icons = dist / "assets" / "icons"
    dark = list((icons / "dark").glob("*.png")) if (icons / "dark").exists() else []
    light = list((icons / "light").glob("*.png")) if (icons / "light").exists() else []
    r.check(len(dark) > 0 and len(light) > 0, "icon set bundled (dark + light)",
            f"dark={len(dark)} light={len(light)}")

    for mod in _REQUIRED:
        present = any(p.name == mod or p.name.startswith(mod) for p in dist.iterdir())
        r.check(present, f"runtime module present: {mod}")

    leaked = [b for b in _FORBIDDEN if (dist / b).exists()]
    r.check(len(leaked) == 0, "no dev/heavy bloat bundled",
            ", ".join(leaked) if leaked else "clean")

    size = _dir_size_mb(dist)
    r.check(size < _MAX_SIZE_MB, f"dist size < {_MAX_SIZE_MB} MB", f"{size:.1f} MB")


def runtime(dist: Path, r: Report) -> None:
    print("Runtime checks")
    exe = dist / "main.exe"
    log = dist / "startup_log.txt"
    if log.exists():
        log.unlink()

    proc = subprocess.Popen([str(exe)], cwd=str(dist))
    try:
        time.sleep(_LAUNCH_WAIT_S)
    finally:
        # GUI apps don't always die on terminate(); taskkill is reliable.
        try:
            subprocess.run(
                ["taskkill", "/F", "/PID", str(proc.pid)],
                capture_output=True, timeout=10,
            )
        except Exception:
            proc.kill()
        # Belt and braces: kill any lingering main.exe from this test.
        subprocess.run(["taskkill", "/F", "/IM", "main.exe"],
                       capture_output=True)

    if not log.exists():
        r.check(False, "app wrote startup_log.txt (it started)")
        return

    text = log.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    r.check(any("STARTING" in ln for ln in lines), "app started (STARTING logged)")

    view_only = any("License expired" in ln for ln in lines)
    has_license = (dist / ".license").exists()
    if has_license:
        r.check(not view_only, "licence accepted (not view-only)")
    else:
        print("  [INFO] no .license present — view-only is expected, skipping that check")

    db_ok = any("Cache cleanup" in ln or "db_connection" in ln for ln in lines)
    r.check(db_ok, "database connected")

    emp = [ln for ln in lines if "employees" in ln and "Refresh status" in ln]
    r.check(len(emp) > 0, "employee list refreshed",
            emp[-1].split(" - ")[-1] if emp else "no refresh line")

    # Icon / image load failures surface as TclError around image=... ; a
    # healthy build has none during startup.
    icon_err = [ln for ln in lines if "TclError" in ln and "image" in ln.lower()]
    r.check(len(icon_err) == 0, "no icon/image load errors",
            f"{len(icon_err)} found")

    # Hard failures: tracebacks or ERROR records. The known-benign startup
    # warnings (unclean-shutdown integrity check after a forced kill) are
    # allowed — they are a consequence of the test killing the process.
    benign = ("Unclean shutdown", "quick_check", "is already running")
    tracebacks = [ln for ln in lines if "Traceback" in ln]
    errors = [ln for ln in lines if " - ERROR - " in ln
              and not any(b in ln for b in benign)]
    r.check(len(tracebacks) == 0, "no tracebacks during startup",
            f"{len(tracebacks)} found")
    r.check(len(errors) == 0, "no ERROR log records", f"{len(errors)} found")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dist", default=str(_DEFAULT_DIST), help="dist folder to test")
    ap.add_argument("--skip-launch", action="store_true", help="structural checks only")
    args = ap.parse_args()

    dist = Path(args.dist).resolve()
    if not dist.exists():
        print(f"dist folder not found: {dist}\nBuild it first: tools\\build_exe.bat")
        return 2

    r = Report()
    print(f"Testing exe build: {dist}")
    print()
    structural(dist, r)
    print()
    if args.skip_launch:
        print("Runtime checks skipped (--skip-launch)")
    else:
        runtime(dist, r)
    return r.summary()


if __name__ == "__main__":
    sys.exit(main())
