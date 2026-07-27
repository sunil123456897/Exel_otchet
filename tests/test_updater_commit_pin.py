"""Tests for the updater's commit-pinning (supply-chain integrity).

The branch-zipball SHA-256 is self-referential (computed from the bytes just
downloaded) and cannot detect a malicious push to a compromised repo/account.
Commit pinning closes that gap: resolve the branch HEAD commit SHA from the
GitHub API and refuse to apply any commit that does not match the operator's
pin. These tests cover the SHA resolver (mocked HTTP) and the pin resolution
+ comparison helpers — no network, no real update.
"""
from __future__ import annotations

import json

import pytest

import run_updater
from core.infra import github_fetcher


# ── resolve_branch_commit_sha ──────────────────────────────────────────


def test_resolve_branch_commit_sha_parses_api_response(tmp_path, monkeypatch):
    captured = {}

    def fake_urlopen(url, headers, *, timeout):
        captured["url"] = url
        return json.dumps({"sha": "ABC123def456"}).encode("utf-8")

    monkeypatch.setattr(github_fetcher, "_urlopen_with_retry", fake_urlopen)
    monkeypatch.setattr(github_fetcher, "_read_token", lambda _root: None)

    sha = github_fetcher.resolve_branch_commit_sha(
        tmp_path, owner="octo", repo="repo", branch="main"
    )
    assert sha == "abc123def456"  # normalised lowercase
    assert "/repos/octo/repo/commits/main" in captured["url"]


def test_resolve_branch_commit_sha_raises_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        github_fetcher, "_urlopen_with_retry",
        lambda url, headers, *, timeout: json.dumps({"nope": 1}).encode("utf-8"),
    )
    monkeypatch.setattr(github_fetcher, "_read_token", lambda _root: None)
    with pytest.raises(RuntimeError):
        github_fetcher.resolve_branch_commit_sha(tmp_path)


def test_resolve_branch_commit_sha_raises_on_bad_json(tmp_path, monkeypatch):
    monkeypatch.setattr(
        github_fetcher, "_urlopen_with_retry",
        lambda url, headers, *, timeout: b"<html>not json</html>",
    )
    monkeypatch.setattr(github_fetcher, "_read_token", lambda _root: None)
    with pytest.raises(RuntimeError):
        github_fetcher.resolve_branch_commit_sha(tmp_path)


# ── resolve_pin ────────────────────────────────────────────────────────


def test_resolve_pin_cli_wins_over_file(tmp_path, monkeypatch):
    pin_file = tmp_path / "updater_pin.txt"
    pin_file.write_text("filesha000\n", encoding="utf-8")
    monkeypatch.setattr(run_updater, "PIN_FILE", pin_file)
    assert run_updater.resolve_pin("  CLISHA999  ") == "clisha999"


def test_resolve_pin_reads_file_skips_comments(tmp_path, monkeypatch):
    pin_file = tmp_path / "updater_pin.txt"
    pin_file.write_text("# comment\n\n  deadbeef  \nignored\n", encoding="utf-8")
    monkeypatch.setattr(run_updater, "PIN_FILE", pin_file)
    assert run_updater.resolve_pin(None) == "deadbeef"


def test_resolve_pin_none_when_no_pin(tmp_path, monkeypatch):
    monkeypatch.setattr(run_updater, "PIN_FILE", tmp_path / "absent.txt")
    assert run_updater.resolve_pin(None) is None
    assert run_updater.resolve_pin("   ") is None


# ── verify_commit_pin ──────────────────────────────────────────────────


def test_verify_commit_pin_match_is_case_insensitive():
    assert run_updater.verify_commit_pin("AbC123", "abc123") is True


def test_verify_commit_pin_mismatch():
    assert run_updater.verify_commit_pin("abc123", "fff999") is False


def test_verify_commit_pin_rejects_empty():
    assert run_updater.verify_commit_pin("", "abc123") is False
    assert run_updater.verify_commit_pin("abc123", "") is False
