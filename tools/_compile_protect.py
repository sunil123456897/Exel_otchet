"""Production build helper — compiles .py to .pyc and deletes .py source.

Called by ``tools/update_from_github.ps1`` → ``Compile-And-Protect`` via
``python tools/_compile_protect.py``. Doing the work in a separate .py
file (rather than an inline ``python -c "..."``) avoids PowerShell's
quote-eating that silently strips double-quotes from ``-c`` arguments.

The caller (``Compile-And-Protect``) guarantees this script runs under
the SAME Python that ``ЗАПУСК.bat`` will later use to launch the app —
bytecode is version-specific and a mismatch (e.g. 3.11 .pyc under 3.12)
raises ``bad magic number`` and bricks the installation.

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


def _cleanup_partial_pyc(core_dir: Path, main_pyc: Path) -> None:
    """Remove flat .pyc + __pycache__ left by a partial compile.

    Called on every failure path so the source tree stays clean when we
    bail out: if we keep .py (fail-safe) but leave 80 stale .pyc behind,
    Python may load a mix of stale bytecode and fresh source on the next
    run, which is a debugging nightmare. Wiping the partial artifacts
    guarantees the next launch runs purely from .py source.
    """
    for d in core_dir.rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)
    for pyc in core_dir.rglob("*.pyc"):
        try:
            pyc.unlink()
        except OSError:
            pass
    if main_pyc.exists():
        try:
            main_pyc.unlink()
        except OSError:
            pass


def main() -> int:
    # Resolve the APP directory (parent of tools/).
    app_dir = Path(__file__).resolve().parents[1] / "APP"
    core_dir = app_dir / "core"
    main_py = app_dir / "main.py"
    main_pyc = app_dir / "main.pyc"

    print(f"[compile-protect] APP dir: {app_dir}")
    print(f"[compile-protect] Python:  {sys.version.split()[0]}")

    # 0. Import write_license BEFORE compiling — it is a pure-stdlib
    #    module (base64/datetime/hashlib/pathlib) so no heavy deps are
    #    pulled in. Importing it up-front means the __pycache__ entry it
    #    would create gets cleaned in step 3 instead of appearing AFTER
    #    the cleanup (which previously left 2 stray .pyc behind).
    sys.path.insert(0, str(app_dir))
    from core.license import write_license  # noqa: E402

    # 1. Compile core/ to flat .pyc (legacy layout — .pyc next to where
    #    .py was). The CLI ``-b`` flag is unreliable across Python
    #    builds; the Python API ``legacy=True`` is guaranteed.
    print("[compile-protect] Compiling core/ ...")
    ok = compileall.compile_dir(str(core_dir), quiet=1, force=True, legacy=True)
    if not ok:
        print("[compile-protect] ERROR: compileall failed for core/")
        _cleanup_partial_pyc(core_dir, main_pyc)
        print("[compile-protect] Partial .pyc removed, .py source preserved.")
        return 1

    # 2. Compile main.py → main.pyc (flat, directly executable).
    if main_py.exists():
        print("[compile-protect] Compiling main.py ...")
        try:
            py_compile.compile(str(main_py), str(main_pyc), doraise=True)
        except py_compile.PyCompileError as e:
            print(f"[compile-protect] ERROR: main.py compile failed: {e}")
            _cleanup_partial_pyc(core_dir, main_pyc)
            print("[compile-protect] Partial .pyc removed, .py source preserved.")
            return 1

    # 3. Clean __pycache__ dirs created by compileall (PEP-3147 layout).
    #    We only ship the flat .pyc files alongside their former .py.
    for d in core_dir.rglob("__pycache__"):
        shutil.rmtree(d, ignore_errors=True)

    # 4. FAIL-SAFE: verify EVERY .py has a matching flat .pyc. If any
    #    is missing, abort and PRESERVE all .py — the app keeps running
    #    from source (unprotected but functional).
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
        _cleanup_partial_pyc(core_dir, main_pyc)
        print("[compile-protect] .py source PRESERVED — app runs unprotected.")
        return 1

    print(f"[compile-protect] All {len(py_files)} .py verified ✓")

    # 5. Generate the 30-day trial license.
    expiry = datetime.datetime.now() + datetime.timedelta(days=30)
    write_license(expiry)
    print(f"[compile-protect] License written, expires {expiry:%Y-%m-%d}")

    # 6. Delete .py source (all checks passed).
    for py in py_files:
        py.unlink()
    if main_py.exists():
        main_py.unlink()
    deleted = len(py_files) + (1 if not main_py.exists() else 0)
    print(f"[compile-protect] Deleted {deleted} .py files.")
    print("[compile-protect] Production build complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
