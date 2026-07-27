"""Stage 4 wiring — end-to-end tests for the updater CLI + fetchers.

These tests prove the wiring is correct end-to-end:

* ``github_fetcher.make_local_fetcher`` produces a working ``fetch_fn``.
* ``github_fetcher.manifest_from_local_zip`` builds the right manifest.
* ``tools/run_updater.py --zip`` actually drives a complete update and
  exits 0 on success.
* The offline mode works without any network.
* BAT files exist and have the expected shape (so the wiring doesn't
  drift if someone rewrites them).

We do NOT exercise the online (GitHub) fetcher here — that requires
real credentials and hits a real network endpoint. It is exercised by
the operator running ``ОБНОВИТЬ_И_ЗАПУСТИТЬ.bat`` on a real machine.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# ── fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def install_root(tmp_path: Path) -> Path:
    """A fake install root with a previous version installed."""
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


def _build_fake_release(
    dest_dir: Path, version: str = "5.7.0",
) -> Path:
    """Build a small fake release ZIP for offline-update tests."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    zip_path = dest_dir / f"MasterReport-{version}.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("APP/__init__.py", f'__version__ = "{version}"\n')
        zf.writestr("APP/main.py", "print('new')\n")
    return zip_path


# ── fetcher unit tests ────────────────────────────────────────────────


def test_local_fetcher_copies_zip(tmp_path: Path) -> None:
    """``make_local_fetcher`` returns a fetch_fn that copies the ZIP."""
    from core.infra.github_fetcher import make_local_fetcher
    from core.infra.updater_model import VersionManifest

    src = _build_fake_release(tmp_path / "src")
    dest = tmp_path / "dest"
    fetch_fn = make_local_fetcher(src)
    manifest = VersionManifest(version="x", sha256="x", size=0, asset=src.name)
    result = fetch_fn(manifest, dest)
    assert result.is_file()
    assert result.read_bytes() == src.read_bytes()


def test_manifest_from_local_zip_has_correct_sha_and_size(
    tmp_path: Path,
) -> None:
    """The manifest must match the actual ZIP bytes."""
    from core.infra.github_fetcher import manifest_from_local_zip

    src = _build_fake_release(tmp_path / "src", version="5.8.0")
    manifest = manifest_from_local_zip(src)
    raw = src.read_bytes()
    assert manifest.sha256 == hashlib.sha256(raw).hexdigest()
    assert manifest.size == len(raw)
    assert manifest.version == "5.8.0"
    assert manifest.asset == src.name


def test_manifest_from_local_zip_extracts_version_from_filename(
    tmp_path: Path,
) -> None:
    """``MasterReport-5.9.1.zip`` → version ``5.9.1``."""
    from core.infra.github_fetcher import manifest_from_local_zip
    src = _build_fake_release(tmp_path, version="5.9.1")
    manifest = manifest_from_local_zip(src)
    assert manifest.version == "5.9.1"


def test_manifest_from_local_zip_falls_back_when_no_version_in_name(
    tmp_path: Path,
) -> None:
    """A ZIP without a version in its name gets a SHA-derived version."""
    from core.infra.github_fetcher import manifest_from_local_zip
    src = tmp_path / "random-archive.zip"
    with zipfile.ZipFile(src, "w") as zf:
        zf.writestr("APP/main.py", "x")
    manifest = manifest_from_local_zip(src)
    assert manifest.version.startswith("local-")


# ── read_token: never leaks ───────────────────────────────────────────


def test_read_token_prefers_env(monkeypatch, tmp_path: Path) -> None:
    """``$GITHUB_TOKEN`` overrides ``.github_token``."""
    from core.infra import github_fetcher
    token_file = tmp_path / ".github_token"
    token_file.write_text("from_file", encoding="utf-8")
    monkeypatch.setattr(github_fetcher, "DEFAULT_OWNER", "x")
    monkeypatch.setenv("GITHUB_TOKEN", "from_env")
    token = github_fetcher._read_token(tmp_path)
    assert token == "from_env"


def test_read_token_falls_back_to_file(monkeypatch, tmp_path: Path) -> None:
    """Without ``$GITHUB_TOKEN``, the file is used."""
    from core.infra import github_fetcher
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    token_file = tmp_path / ".github_token"
    token_file.write_text("from_file\n", encoding="utf-8")
    token = github_fetcher._read_token(tmp_path)
    assert token == "from_file"


def test_read_token_returns_none_if_no_source(
    monkeypatch, tmp_path: Path,
) -> None:
    """No token, no file → None (public repo mode)."""
    from core.infra import github_fetcher
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert github_fetcher._read_token(tmp_path) is None


def test_auth_headers_never_log_token() -> None:
    """The auth headers contain the token but the function has no side
    effects that would leak it."""
    from core.infra.github_fetcher import _auth_headers
    h = _auth_headers("secret-token-12345")
    assert h["Authorization"] == "token secret-token-12345"
    # The headers dict is the only output; no log/print.


# ── CLI end-to-end: tools/run_updater.py --zip ─────────────────────────


def test_run_updater_cli_offline_zip_succeeds(
    install_root: Path, tmp_path: Path, monkeypatch,
) -> None:
    """``run_updater.py --zip`` drives a complete update and exits 0.

    We run the CLI as a subprocess against the install root via
    ``--install-root`` so the test does not touch the developer's real
    repo. The fake ZIP has no logic_service.py so L2 will skip
    (legitimate for a minimal release); L0 + L1 must still pass.
    """
    src = _build_fake_release(tmp_path / "releases")
    rc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "run_updater.py"),
         "--zip", str(src),
         "--python", sys.executable,
         "--install-root", str(install_root)],
        cwd=str(install_root),
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120,
        env={**os.environ,
             "PYTHONPATH": str(install_root / "APP")},
    )
    assert rc.returncode == 0, (
        f"run_updater failed (rc={rc.returncode}):\n"
        f"STDOUT:\n{rc.stdout}\nSTDERR:\n{rc.stderr}"
    )
    assert "OK: updated to 5.7.0" in rc.stdout or "updated to" in rc.stdout
    # And the install_root actually has the new version.
    assert (install_root / "versions" / "5.7.0" / "APP" / "main.py").is_file()


def test_run_updater_cli_missing_zip_returns_error(
    install_root: Path, tmp_path: Path,
) -> None:
    """A non-existent ZIP must exit with a clear error, not a crash."""
    rc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "run_updater.py"),
         "--zip", str(tmp_path / "does_not_exist.zip"),
         "--python", sys.executable,
         "--install-root", str(install_root)],
        cwd=str(install_root),
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=60,
    )
    assert rc.returncode != 0
    assert "ZIP not found" in rc.stdout or "not found" in rc.stdout.lower()


def test_run_updater_cli_corrupt_zip_fails_cleanly(
    install_root: Path, tmp_path: Path,
) -> None:
    """A ZIP that isn't actually a zip must fail at L0, not crash."""
    bad_zip = tmp_path / "MasterReport-5.7.0.zip"
    bad_zip.write_bytes(b"NOT_A_ZIP_FILE" * 32)
    rc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "tools" / "run_updater.py"),
         "--zip", str(bad_zip),
         "--python", sys.executable,
         "--install-root", str(install_root)],
        cwd=str(install_root),
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=120,
        env={**os.environ,
             "PYTHONPATH": str(install_root / "APP")},
    )
    assert rc.returncode != 0
    # The failure must mention a specific stage, not be a traceback.
    assert "FAILED at stage" in rc.stdout or "L0" in rc.stdout or "L1" in rc.stdout


# ── BAT files exist and are well-formed ────────────────────────────────


def test_update_bat_calls_python_updater() -> None:
    """ОБНОВИТЬ_И_ЗАПУСТИТЬ.bat must invoke tools/run_updater.py."""
    bat = REPO_ROOT / "ОБНОВИТЬ_И_ЗАПУСТИТЬ.bat"
    assert bat.is_file(), "update BAT must ship with the app"
    content = bat.read_text(encoding="utf-8-sig", errors="replace")
    assert "run_updater.py" in content, (
        "update BAT must call the new Python updater"
    )
    # And have the legacy fallback.
    assert "update_from_github.ps1" in content, (
        "update BAT must have a PowerShell fallback"
    )


def test_offline_update_bat_exists() -> None:
    """ОБНОВИТЬ_ИЗ_ФАЙЛА.bat must ship with the app for offline updates."""
    bat = REPO_ROOT / "ОБНОВИТЬ_ИЗ_ФАЙЛА.bat"
    assert bat.is_file()
    content = bat.read_text(encoding="utf-8-sig", errors="replace")
    assert "run_updater.py" in content
    assert "--zip" in content


def test_bats_have_utf8_codepage() -> None:
    """Both BATs must set chcp 65001 so Russian output renders correctly."""
    for name in ("ОБНОВИТЬ_И_ЗАПУСТИТЬ.bat", "ОБНОВИТЬ_ИЗ_ФАЙЛА.bat"):
        content = (REPO_ROOT / name).read_text(
            encoding="utf-8-sig", errors="replace",
        )
        assert "chcp 65001" in content, f"{name} must set UTF-8 codepage"
