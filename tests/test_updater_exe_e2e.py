"""End-to-end test of the compiled ``updater.exe`` (offline/local channel).

Requires a built ``updater.exe`` (``tools/build_exe.py``); skipped if absent so
this doesn't block environments without a Nuitka build. Runs the REAL binary
against a throwaway install to prove the no-Python update flow:

* a valid program-only zip updates the program while user data
  (config/employees/cache) is preserved and ``version.json`` is written;
* an archive lacking ``main.exe`` is rejected (L1) and leaves the install
  untouched.
"""
from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_UPDATER = _REPO_ROOT / "build_exe" / "main.dist" / "updater.exe"

pytestmark = pytest.mark.skipif(
    not _UPDATER.is_file(),
    reason="updater.exe not built (run tools/build_exe.py)",
)


def _make_install(root: Path) -> None:
    (root / "assets" / "icons" / "dark").mkdir(parents=True)
    (root / "main.exe").write_bytes(b"OLD-PROGRAM")
    (root / "assets" / "icons" / "dark" / "x.png").write_bytes(b"png")
    (root / "config.yaml").write_text("marker: KEEP-ME\n", encoding="utf-8")
    (root / "employees.yaml").write_text("Амалия: []\n", encoding="utf-8")
    (root / "cache.db").write_bytes(b"sqlite-data")


def _make_zip(zip_path: Path, main_bytes: bytes, with_main: bool = True) -> None:
    staging = zip_path.parent / "_src"
    base = staging / "Master-Report"  # wrapper folder, like build_exe --zip
    (base / "assets" / "icons" / "dark").mkdir(parents=True)
    if with_main:
        (base / "main.exe").write_bytes(main_bytes)
    (base / "assets" / "icons" / "dark" / "x.png").write_bytes(b"png2")
    (base / "db_schema.sql").write_text("CREATE TABLE t(x);", encoding="utf-8")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(staging.rglob("*")):
            if f.is_file():
                zf.write(f, f.relative_to(staging))
    shutil.rmtree(staging, ignore_errors=True)


def _run_updater(install: Path, zip_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(_UPDATER), "--install-dir", str(install),
         "--from-file", str(zip_path), "--no-launch"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120,
    )


def test_updater_exe_local_update_preserves_data(tmp_path):
    install = tmp_path / "install"
    install.mkdir()
    _make_install(install)
    zip_path = tmp_path / "v2.zip"
    _make_zip(zip_path, b"NEW-PROGRAM")

    proc = _run_updater(install, zip_path)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    # program updated
    assert (install / "main.exe").read_bytes() == b"NEW-PROGRAM"
    assert (install / "db_schema.sql").is_file()
    # user data preserved verbatim
    assert (install / "config.yaml").read_text(encoding="utf-8") == "marker: KEEP-ME\n"
    assert (install / "employees.yaml").read_text(encoding="utf-8") == "Амалия: []\n"
    assert (install / "cache.db").read_bytes() == b"sqlite-data"
    # version metadata recorded
    assert (install / "version.json").is_file()


def test_updater_exe_rejects_bad_archive_and_preserves_install(tmp_path):
    install = tmp_path / "install"
    install.mkdir()
    _make_install(install)
    zip_path = tmp_path / "bad.zip"
    _make_zip(zip_path, b"X", with_main=False)  # no main.exe -> L1 fails

    proc = _run_updater(install, zip_path)
    assert proc.returncode != 0

    # install untouched
    assert (install / "main.exe").read_bytes() == b"OLD-PROGRAM"
    assert (install / "config.yaml").read_text(encoding="utf-8") == "marker: KEEP-ME\n"
    assert (install / "cache.db").read_bytes() == b"sqlite-data"
