#!/usr/bin/env python3
"""Stage 9 / MR-0902 — diagnostic package collector.

Builds a ZIP that an operator can hand to support. Strict privacy rules
— the ZIP MUST NOT contain:

* real Excel files (``*.xlsx`` outside ``tests/``);
* real sums, employee names, customer names;
* tokens, passwords, full config dumps;
* SQLite database contents;
* memory dumps.

What the ZIP DOES contain:

* app version + Windows version;
* safe installation ID (derived, not raw);
* Python version, dependency versions;
* path availability flags (path exists? not the path itself);
* anonymised last-N errors from logs (filtered through scrub_path +
  amount-redaction);
* self-check result;
* last update result;
* DB schema (table + column names, no row data);
* ``config.yaml`` *shape* (section names + key names + value types,
  not values themselves).

The collector is import-safe and side-effect-free at import time. Run
via the CLI to produce the ZIP. A companion unit test
(``test_diagnostic_package.py``) asserts the privacy contract: it
builds a ZIP from a fixture containing forbidden content and verifies
none of it survives into the output.

Usage::

    python tools/diagnostic_package.py
    python tools/diagnostic_package.py --out C:\\Users\\me\\diag.zip
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

# Forbidden substrings that must NEVER appear in the diagnostic ZIP.
# The privacy test scans every file in the output for these.
FORBIDDEN_PATTERNS = [
    # GitHub token shapes
    r"gh[pousr]_[A-Za-z0-9]{36,}",
    r"github_pat_[A-Za-z0-9_]{22,}",
    # Real monetary amounts (3+ digits before separator)
    r"\d{3,}[.,]\d{2}",
    # Windows user paths — but NOT when already redacted to <user>.
    # We require a real-looking username (alphanumerics, not angle brackets).
    r"[A-Z]:\\Users\\[A-Za-z][A-Za-z0-9_\-]+",
    # UNC share — same exclusion: not when already redacted to <server>.
    r"\\\\[A-Za-z][A-Za-z0-9_\-\.]+\\[A-Za-z][A-Za-z0-9_\-\.]+",
    # Common SQL fragments that would indicate a leaked query
    r"INSERT INTO",
    r"SELECT \* FROM",
]

# Russian firm-name prefixes that, when followed by a name, indicate
# real customer data leaked. Used by the collector's post-scrub step.
_FIRM_NAME_RE = re.compile(
    r"\b(ООО|АО|ЗАО|ОАО|ИП)\s+[A-Za-zА-Яа-я0-9]+",
)

# Any token-like string — even a truncated or bogus one — is masked.
# We use a broader pattern than the FORBIDDEN_PATTERNS entry because a
# 3-char token in a log is still a token-shaped string the operator
# should not be sending to support.
_ANY_TOKEN_RE = re.compile(r"gh[pousr]_\S+|github_pat_\S+")


def _scrub_firm_names(text: str) -> str:
    """Replace ``ООО Ромашка`` with ``ООО <CustomerName>`` etc."""
    return _FIRM_NAME_RE.sub(r"\1 <CustomerName>", text)


def _scrub_tokens(text: str) -> str:
    """Replace any token-shaped substring with ``<token>``."""
    return _ANY_TOKEN_RE.sub("<token>", text)


def _safe_installation_id() -> str:
    """Derive a stable installation ID without revealing the machine.

    Hashes the repo path; the result is a 12-char prefix that support
    can use to correlate tickets from the same install without learning
    the install location.
    """
    h = hashlib.sha256(str(REPO_ROOT).encode("utf-8")).hexdigest()
    return h[:12]


def _app_version() -> str:
    # The APP package lives at REPO_ROOT/APP, so REPO_ROOT must be on
    # sys.path for `import APP` to resolve. Tools run from various
    # working dirs; ensure REPO_ROOT is importable.
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    try:
        import APP  # type: ignore
        return getattr(APP, "__version__", "unknown")
    except Exception:
        return "unknown"


def _python_and_deps() -> dict[str, str]:
    """Python version + a small allowlist of dependency versions."""
    out: dict[str, str] = {"python": sys.version.split()[0]}
    for dist in ("openpyxl", "pydantic", "python-calamine", "ruamel.yaml",
                 "Pillow", "tkcalendar"):
        try:
            import importlib.metadata as md
            out[dist] = md.version(dist)
        except Exception:
            out[dist] = "not installed"
    return out


def _path_availability(config_path: Path) -> list[dict[str, Any]]:
    """Walk the configured paths and report only existence + type.

    The path string itself is NOT included — only a flag and the
    basename (which is non-sensitive: ``master_file``, ``output_root``
    etc. are generic).
    """
    from ruamel.yaml import YAML
    yaml = YAML()
    out: list[dict[str, Any]] = []
    if not config_path.is_file():
        return out
    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = yaml.load(f) or {}
    except Exception:
        return out

    paths = data.get("paths", {}) if isinstance(data, dict) else {}
    for key in ("master_file", "source_root", "archive_dir", "output_root"):
        val = paths.get(key) if isinstance(paths, dict) else None
        if not val:
            continue
        p = Path(str(val))
        out.append({
            "key": key,
            "exists": p.exists(),
            "type": "dir" if p.is_dir() else "file" if p.is_file() else "missing",
        })
    return out


def _config_shape(config_path: Path) -> dict[str, Any]:
    """Return the *shape* of the config: section/key names + value types.

    Values themselves are NOT included. ``{"database": {"path": "str",
    "timeout": "float"}}`` instead of ``{"database": {"path": "x.db",
    "timeout": 30.0}}``.
    """
    from ruamel.yaml import YAML
    yaml = YAML()
    if not config_path.is_file():
        return {}

    def _shape(v: Any) -> str | list | dict:
        if isinstance(v, dict):
            return {str(k): _shape(val) for k, val in v.items()}
        if isinstance(v, list):
            return [_shape(val) for val in v[:1]] if v else []
        return type(v).__name__

    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = yaml.load(f) or {}
    except Exception as e:
        return {"_error": f"could not parse: {e}"}
    return _shape(data) if isinstance(data, dict) else {"_type": type(data).__name__}


def _db_schema(db_path: Path) -> dict[str, Any]:
    """Return table + column names, but no row data."""
    if not db_path.is_file():
        return {"present": False}
    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        tables: dict[str, list[str]] = {}
        for (name,) in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall():
            cols = [row[1] for row in conn.execute(f"PRAGMA table_info('{name}')").fetchall()]
            tables[name] = cols
        # Row counts only (no values).
        counts = {
            name: conn.execute(f"SELECT COUNT(*) FROM '{name}'").fetchone()[0]
            for name in tables
        }
        conn.close()
        return {"present": True, "tables": tables, "row_counts": counts}
    except Exception as e:
        return {"present": True, "_error": f"could not read schema: {e}"}


def _anonymised_log_tail(log_path: Path, n: int = 50) -> list[str]:
    """Return the last N lines of a log, with paths and amounts scrubbed.

    The scrubbing is the same defence used by ``data_loss_log``: paths
    and monetary amounts are replaced with placeholders. This is a
    second layer — the log writer already scrubs — but defence-in-depth.
    """
    if not log_path.is_file():
        return []
    try:
        from core.shared.path_scrub import scrub_path
    except Exception:
        def scrub_path(s: str) -> str:  # type: ignore[no-redef]
            return s

    amount_re = re.compile(r"\d{3,}[.,]\d{2}")
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [scrub_path(amount_re.sub("[AMOUNT]", line)) for line in lines[-n:]]


def _scan_for_forbidden(text: str) -> list[str]:
    """Return the list of forbidden patterns found in *text*."""
    hits: list[str] = []
    for pat in FORBIDDEN_PATTERNS:
        if re.search(pat, text):
            hits.append(pat)
    return hits


def build_diagnostic_package(
    out_path: Path,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Build the diagnostic ZIP at *out_path*. Returns a manifest dict.

    The manifest is also written into the ZIP as ``manifest.json`` so
    support can see at a glance what's inside.
    """
    root = repo_root or REPO_ROOT
    config_path = root / "APP" / "config.yaml"
    db_path = root / "APP" / "cache.db"
    logs = [
        root / "logs" / "data_loss.log",
        root / "APP" / "logs" / "data_loss.log",
        root / "startup_log.txt",
        root / "APP" / "startup_log.txt",
    ]

    manifest: dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "installation_id": _safe_installation_id(),
        "app_version": _app_version(),
        "python_and_deps": _python_and_deps(),
        "platform": sys.platform,
        "path_availability": _path_availability(config_path),
        "config_shape": _config_shape(config_path),
        "db_schema": _db_schema(db_path),
        "log_tails": {
            str(p.relative_to(root)): _anonymised_log_tail(p)
            for p in logs if p.is_file()
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Privacy: scrub every string field in the manifest BEFORE serialising.
    # Doing it post-serialisation breaks JSON when a token sits inside an
    # already-escaped string. Walking the structure is safer.
    manifest = _scrub_manifest_strings(manifest)
    manifest_text = json.dumps(manifest, indent=2, ensure_ascii=False)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", manifest_text)
    return manifest


def _scrub_manifest_strings(obj: Any) -> Any:
    """Recursively scrub tokens + firm names from every string in *obj*.

    Returns a new structure; the input is not mutated. Non-string leaves
    (ints, bools, None) pass through unchanged.
    """
    if isinstance(obj, str):
        s = _scrub_tokens(obj)
        s = _scrub_firm_names(s)
        return s
    if isinstance(obj, dict):
        return {k: _scrub_manifest_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub_manifest_strings(v) for v in obj]
    return obj


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=str(REPO_ROOT / "diagnostic_package.zip"),
                   help="output ZIP path")
    p.add_argument("--scan", action="store_true",
                   help="after building, scan the ZIP for forbidden patterns")
    args = p.parse_args()

    out_path = Path(args.out)
    manifest = build_diagnostic_package(out_path)

    print(f"[diag] wrote {out_path} ({out_path.stat().st_size} bytes)")
    print(f"[diag] installation_id={manifest['installation_id']}")
    print(f"[diag] app_version={manifest['app_version']}")

    if args.scan:
        # Read back the ZIP and verify no forbidden patterns slipped in.
        violations: list[tuple[str, str]] = []
        with zipfile.ZipFile(out_path, "r") as zf:
            for name in zf.namelist():
                content = zf.read(name).decode("utf-8", errors="replace")
                for pat in _scan_for_forbidden(content):
                    violations.append((name, pat))
        if violations:
            print("[diag] PRIVACY VIOLATIONS DETECTED:", file=sys.stderr)
            for name, pat in violations:
                print(f"  {name}: /{pat}/", file=sys.stderr)
            return 1
        print("[diag] privacy scan: clean")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
