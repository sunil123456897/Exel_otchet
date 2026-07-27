"""Behavioural tests for the license / trial checker (core.license).

Previously untested (0 coverage). The checker's date logic — expiry plus
clock-rollback detection — is fragile: it depends on ``date.today()`` and
on-disk state. These tests pin its behaviour using dates relative to the
real today (no time mocking, so no false coupling to a frozen clock) and
redirect the license / last-run files to a temp dir.
"""
from __future__ import annotations

import datetime as dt

import pytest

from core import license as lic


@pytest.fixture
def prod(tmp_path, monkeypatch):
    """Force PRODUCTION mode with license/last-run files in a temp dir.

    ``is_development_mode`` is patched to False (in a source checkout the
    dev marker file exists and every check is skipped); the two state files
    are redirected so tests never touch the real ``APP/.license``.
    """
    monkeypatch.setattr(lic, "is_development_mode", lambda: False)
    monkeypatch.setattr(lic, "_LICENSE_FILE", tmp_path / ".license")
    monkeypatch.setattr(lic, "_LASTRUN_FILE", tmp_path / ".last_run")
    return tmp_path


def _write_valid_license(days: int) -> None:
    lic.write_license(dt.datetime.now() + dt.timedelta(days=days))


# ── obfuscation round-trip ─────────────────────────────────────────────


def test_encrypt_decrypt_roundtrip():
    assert lic._decrypt(lic._encrypt("2026-07-26")) == "2026-07-26"


# ── development mode ───────────────────────────────────────────────────


def test_dev_mode_never_blocks(monkeypatch):
    monkeypatch.setattr(lic, "is_development_mode", lambda: True)
    # No license files at all — dev mode must still not block.
    assert lic.check_license() is False


# ── production: expiry ─────────────────────────────────────────────────


def test_valid_license_not_expired(prod):
    _write_valid_license(days=10)
    assert lic.check_license() is False


def test_expired_license_blocks(prod):
    _write_valid_license(days=-1)
    assert lic.check_license() is True


def test_expiry_boundary_today_is_not_expired(prod):
    # Expiring exactly today is still valid (block only AFTER expiry).
    _write_valid_license(days=0)
    assert lic.check_license() is False


# ── production: tamper / missing / corrupt ─────────────────────────────


def test_missing_license_blocks(prod):
    # No .license in production = treated as tampered/deleted → block.
    assert lic.check_license() is True


def test_corrupt_license_blocks(prod):
    (prod / ".license").write_text("!!!not-base64!!!", encoding="utf-8")
    assert lic.check_license() is True


# ── production: clock rollback ─────────────────────────────────────────


def test_clock_rollback_blocks(prod):
    _write_valid_license(days=10)  # license itself is valid…
    # …but the recorded last run is in the future → clock was rolled back.
    lic._write_last_run(dt.date.today() + dt.timedelta(days=5))
    assert lic.check_license() is True


def test_no_rollback_when_today_after_last_run(prod):
    _write_valid_license(days=10)
    lic._write_last_run(dt.date.today() - dt.timedelta(days=1))
    assert lic.check_license() is False


# ── trail bookkeeping ──────────────────────────────────────────────────


def test_last_run_recorded_after_check(prod):
    _write_valid_license(days=10)
    assert lic._read_last_run() is None
    lic.check_license()
    assert lic._read_last_run() == dt.date.today()
    # A same-day re-check stays valid (no spurious rollback).
    assert lic.check_license() is False
