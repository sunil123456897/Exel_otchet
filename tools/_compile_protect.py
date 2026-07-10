"""Production build helper — compiles .py to .pyc and deletes .py source.

Called by ``tools/update_from_github.ps1`` → ``Compile-And-Protect`` via
``python tools/_compile_protect.py``. Doing the work in a separate .py
file (rather than an inline ``python -c "..."``) avoids PowerShell's
quote-eating that silently strips double-quotes from ``-c`` arguments.

Exit codes:
  0 — success: .pyc created for every .py, .py deleted, license written.
  1 — failure: .pyc missing for some .py; .py PRESERVED (fail-safe).
"""
from __future__ import annotations

import compileall
import datetime
import py_compile
import shutil
import sys
from pathlib import Path


def main() -> int:
    # Resolve the APP directory (parent of tools/).
    app_dir = Path(__file__).resolve().parents[1] / "APP"
    core_dir = app_dir / "core"
    main_py = app_dir / "main.py"
    main_pyc = app_dir / "main.pyc"

    print(f"[compile-protect] APP dir: {app_dir}")

    # 1. Compile core/ to flat .pyc (legacy layout).
    print("[compile-protect] Compiling core/ ...")
    ok = compileall.compile_dir(str(core_dir), quiet=1, force=True, legacy=True)
    if not ok:
        print("[compile-protect] ERROR: compileall failed for core/")
        return 1

    # 2. Compile main.py → main.pyc
    if main_py.exists():
        print("[compile-protect] Compiling main.py ...")
        try:
            py_compile.compile(str(main_py), str(main_pyc), doraise=True)
        except py_compile.PyCompileError as e:
            print(f"[compile-protect] ERROR: main.py compile failed: {e}")
            return 1

    # 3. Clean __pycache__ dirs (keep only flat .pyc).
    for d in core_dir.rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)

    # 4. FAIL-SAFE: verify EVERY .py has a matching .pyc.
    py_files = list(core_dir.rglob("*.py"))
    missing = []
    for py in py_files:
        pyc = py.with_suffix(".pyc")
        if not pyc.exists():
            missing.append(py.name)
    if main_py.exists() and not main_pyc.exists():
        missing.append("main.pyc")

    if missing:
        print(f"[compile-protect] ABORT: {len(missing)} .pyc missing: {missing}")
        print("[compile-protect] .py source PRESERVED — app runs unprotected.")
        return 1

    print(f"[compile-protect] All {len(py_files)} .py verified ✓")

    # 5. Generate trial license (30 days).
    sys.path.insert(0, str(app_dir))
    from core.license import write_license  # noqa: E402

    expiry = datetime.datetime.now() + datetime.timedelta(days=30)
    write_license(expiry)
    print(f"[compile-protect] License written, expires {expiry:%Y-%m-%d}")

    # 6. Delete .py source (all checks passed).
    for py in py_files:
        py.unlink()
    if main_py.exists():
        main_py.unlink()
    print(f"[compile-protect] Deleted {len(py_files) + 1} .py files.")
    print("[compile-protect] Production build complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
