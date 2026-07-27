"""Stage 9 / MR-0902 — diagnostic package privacy test.

Builds a diagnostic ZIP from a fixture that deliberately contains
forbidden content (real-looking tokens, paths, amounts, employee
names) and verifies NONE of it survives into the output. If any
forbidden pattern appears, the collector has a privacy bug.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

import pytest

from tools.diagnostic_package import (
    _scan_for_forbidden,
    build_diagnostic_package,
)


# ── fixture: a fake repo root with forbidden content everywhere ────────


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """A repo root containing every kind of secret the collector must drop."""
    root = tmp_path / "fake_repo"
    app = root / "APP"
    app.mkdir(parents=True)

    # config.yaml with secrets in values (paths, custom endpoints).
    (app / "config.yaml").write_text(
        "database:\n"
        "  path: C:\\Users\\operator\\cache.db\n"  # username in path
        "paths:\n"
        "  master_file: \\\\firmsrv\\finance$\\out.xlsx\n"  # UNC + server name
        "operator:\n"
        "  token: ghp_abcdefghijklmnopqrstuvwxyz0123456789ABCD\n"  # GitHub PAT
        "custom:\n"
        "  commission_amount: 12345.67\n"  # monetary amount
        "  customer_name: 'ООО Ромашка'\n"  # real firm name
        , encoding="utf-8",
    )

    # A fake DB with a row containing real-looking data.
    import sqlite3
    conn = sqlite3.connect(app / "cache.db")
    conn.execute("CREATE TABLE sessions (id TEXT, customer TEXT, amount REAL)")
    conn.execute(
        "INSERT INTO sessions VALUES ('s1', 'ООО Ромашка', 99999.99)"
    )
    conn.commit()
    conn.close()

    # Log with forbidden content.
    log_dir = root / "logs"
    log_dir.mkdir()
    (log_dir / "data_loss.log").write_text(
        "2026-01-01 customer ООО Ромашка amount 12345.67 token ghp_aaa\n"
        "C:\\Users\\operator\\file.xlsx\n",
        encoding="utf-8",
    )

    # Real Excel-like file that must NOT be bundled.
    (app / "real_report.xlsx").write_bytes(b"PK\x03\x04 real data")

    return root


# ── helpers ────────────────────────────────────────────────────────────


def _read_zip(path: Path) -> dict[str, str]:
    """Return ``{name: content}`` for every text-decodable file in the ZIP."""
    out: dict[str, str] = {}
    with zipfile.ZipFile(path, "r") as zf:
        for name in zf.namelist():
            try:
                out[name] = zf.read(name).decode("utf-8", errors="replace")
            except Exception:
                out[name] = ""
    return out


# ── 1) scan_for_forbidden helper is correct ────────────────────────────


def test_scan_finds_github_token() -> None:
    hits = _scan_for_forbidden("leaked: ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789ABCD")
    # ``hits`` contains the regex patterns that matched, not literal
    # substrings. The ghp pattern starts with ``gh[pousr]_``.
    assert any(h.startswith("gh[pousr]") or "ghp_" in h for h in hits), (
        f"scanner did not flag a github token; hits={hits}"
    )


def test_scan_finds_amount() -> None:
    hits = _scan_for_forbidden("amount: 12345.67")
    assert any(hits)


def test_scan_finds_unc_path() -> None:
    hits = _scan_for_forbidden(r"\\firmsvr\share\file.xlsx")
    assert any("server" in h or "\\\\" in h for h in hits)


def test_scan_finds_windows_user_path() -> None:
    hits = _scan_for_forbidden(r"C:\Users\vanya\file.xlsx")
    assert hits


def test_scan_does_not_flag_small_numbers() -> None:
    """Small integers (row counts, version numbers) are NOT forbidden."""
    hits = _scan_for_forbidden("row_count: 42, version: 5.6")
    # 42 is fine; 5.6 only has 1 digit before the decimal.
    assert not hits


def test_scan_does_not_flag_anonymised_placeholders() -> None:
    """After scrubbing, the placeholders [AMOUNT] and <user> must not match."""
    hits = _scan_for_forbidden("amount: [AMOUNT], user: C:\\Users\\<user>")
    assert not hits


# ── 2) the collector itself respects privacy ───────────────────────────


def test_collector_does_not_include_xlsx_files(fake_repo: Path, tmp_path: Path) -> None:
    """No .xlsx file from the repo may be bundled into the diagnostic ZIP."""
    out = tmp_path / "diag.zip"
    build_diagnostic_package(out, repo_root=fake_repo)

    files = _read_zip(out)
    assert not any(name.endswith(".xlsx") for name in files), (
        f"diagnostic ZIP contains xlsx files: {[n for n in files if n.endswith('.xlsx')]}"
    )


def test_collector_does_not_leak_github_token(fake_repo: Path, tmp_path: Path) -> None:
    out = tmp_path / "diag.zip"
    build_diagnostic_package(out, repo_root=fake_repo)

    content = "\n".join(_read_zip(out).values())
    assert "ghp_" not in content
    assert "abcdefghijklmnopqrstuvwxyz0123456789ABCD" not in content


def test_collector_does_not_leak_real_amounts(fake_repo: Path, tmp_path: Path) -> None:
    """Monetary amounts must not appear in the ZIP (anonymised or dropped)."""
    out = tmp_path / "diag.zip"
    build_diagnostic_package(out, repo_root=fake_repo)

    content = "\n".join(_read_zip(out).values())
    assert "12345.67" not in content
    assert "99999.99" not in content


def test_collector_does_not_leak_user_paths(fake_repo: Path, tmp_path: Path) -> None:
    """Windows usernames and UNC server names must not appear."""
    out = tmp_path / "diag.zip"
    build_diagnostic_package(out, repo_root=fake_repo)

    content = "\n".join(_read_zip(out).values())
    # The username "operator" may appear as a YAML *key* (operator: {...})
    # which is harmless. It must NOT appear as a path component.
    assert r"C:\Users\operator" not in content, "Windows username leaked as path"
    # UNC server name must not appear at all.
    assert "firmsrv" not in content, "UNC server name leaked"
    assert "finance$" not in content, "UNC share name leaked"


def test_collector_does_not_leak_customer_names(fake_repo: Path, tmp_path: Path) -> None:
    """Real customer / firm names must not appear in any field."""
    out = tmp_path / "diag.zip"
    build_diagnostic_package(out, repo_root=fake_repo)

    content = "\n".join(_read_zip(out).values())
    assert "Ромашка" not in content


def test_collector_does_not_leak_db_row_data(fake_repo: Path, tmp_path: Path) -> None:
    """DB schema is allowed; row data (customer, amount) is not."""
    out = tmp_path / "diag.zip"
    build_diagnostic_package(out, repo_root=fake_repo)

    files = _read_zip(out)
    manifest = json.loads(files["manifest.json"])
    # Schema is present (table + column names).
    schema = manifest["db_schema"]
    assert schema["present"] is True
    assert "sessions" in schema["tables"]
    assert "customer" in schema["tables"]["sessions"]
    # Row count is allowed (it's a count, not data).
    assert schema["row_counts"]["sessions"] == 1
    # But the actual row value (ООО Ромашка / 99999.99) is NOT anywhere.
    content = "\n".join(files.values())
    assert "Ромашка" not in content
    assert "99999" not in content


# ── 3) collector is robust to missing files ────────────────────────────


def test_collector_handles_missing_config(tmp_path: Path) -> None:
    """If config.yaml is missing, the ZIP must still build successfully."""
    empty_repo = tmp_path / "empty"
    (empty_repo / "APP").mkdir(parents=True)
    out = tmp_path / "diag.zip"
    # Must not raise.
    build_diagnostic_package(out, repo_root=empty_repo)
    assert out.exists()


def test_collector_handles_corrupt_config(tmp_path: Path) -> None:
    """A corrupt config.yaml must not crash the collector."""
    bad_repo = tmp_path / "bad"
    app = bad_repo / "APP"
    app.mkdir(parents=True)
    (app / "config.yaml").write_text("not: valid: yaml: [", encoding="utf-8")
    out = tmp_path / "diag.zip"
    build_diagnostic_package(out, repo_root=bad_repo)
    assert out.exists()


def test_collector_installation_id_is_stable(tmp_path: Path) -> None:
    """The installation_id must be the same across two runs on the same repo."""
    fake_repo = tmp_path / "repo"
    (fake_repo / "APP").mkdir(parents=True)
    out1 = tmp_path / "diag1.zip"
    out2 = tmp_path / "diag2.zip"
    m1 = build_diagnostic_package(out1, repo_root=fake_repo)
    m2 = build_diagnostic_package(out2, repo_root=fake_repo)
    assert m1["installation_id"] == m2["installation_id"]


def test_collector_installation_id_does_not_leak_path(tmp_path: Path) -> None:
    """The installation_id is a hash; it must not reveal the install path."""
    fake_repo = tmp_path / "secret_install_path_do_not_leak"
    (fake_repo / "APP").mkdir(parents=True)
    out = tmp_path / "diag.zip"
    manifest = build_diagnostic_package(out, repo_root=fake_repo)

    content = json.dumps(manifest)
    assert "secret_install_path_do_not_leak" not in content
    # The id is a 12-char hex prefix of a sha256.
    assert re.fullmatch(r"[0-9a-f]{12}", manifest["installation_id"])


# ── 4) config_shape exposes types, not values ─────────────────────────


def test_config_shape_contains_types_not_values(fake_repo: Path, tmp_path: Path) -> None:
    """The shape report must contain ``"str"``, not the string itself."""
    out = tmp_path / "diag.zip"
    manifest = build_diagnostic_package(out, repo_root=fake_repo)
    shape = manifest["config_shape"]

    # The database.path value is the literal "C:\\Users\\operator\\cache.db"
    # in the source config. In the shape, it must be the string "str".
    db_path_shape = shape.get("database", {}).get("path")
    assert db_path_shape == "str", (
        f"config_shape leaked a value: {db_path_shape!r} (expected 'str')"
    )

    # operator.token must be "str", not the actual token.
    token_shape = shape.get("operator", {}).get("token")
    assert token_shape == "str"
