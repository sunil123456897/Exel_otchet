"""Stage 2 / MR-0203 — typed schema for ``APP/employees.yaml``.

The file maps an employee name to a list of source files. Two historical
formats coexist in the wild:

* **Legacy** — ``{name: ["/path/to/file.xlsx", ...]}`` (bare strings).
* **Current** — ``{name: [{path: ..., id: ..., fp: ...}, ...]}`` (dicts
  with file fingerprint metadata used by smart-tracking).

The legacy format must keep working — operators have working copies in
this shape, and a forced migration would break their setups. This module
normalises both into the current shape on load, surfaces validation
issues without crashing, and offers an explicit ``migrate_employees``
for operators who want to upgrade the on-disk file.

Validation rules (per TZ MR-0203):

* duplicate employee names — flagged, not silently merged;
* empty/whitespace names — flagged;
* missing file paths — flagged per-entry (a network drive being down is
  not a YAML error);
* ambiguous entries (mixing str and dict in the same list) — flagged;
  the normaliser upgrades strings to dicts, but reports the upgrade so
  the operator knows.
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

log = logging.getLogger(__name__)


class EmployeeFile(BaseModel):
    """A single source file attached to an employee.

    ``id`` is the inode (used to detect moves); ``fp`` is a content hash
    used to detect edits. Both are absent for legacy string entries and
    filled in lazily by the app when the file is next scanned.
    """
    model_config = ConfigDict(extra="allow")

    path: str
    id: Optional[int] = None
    fp: Optional[str] = None


class EmployeeIssue(BaseModel):
    """A classified problem with the employees file (no PII in detail)."""
    kind: str   # "duplicate_name", "empty_name", "missing_path", "mixed_format"
    name: str   # the employee name it concerns (already non-sensitive — names are public)
    detail: str


def _is_legacy_entry(v: Any) -> bool:
    return isinstance(v, str)


def _is_current_entry(v: Any) -> bool:
    return isinstance(v, dict) and "path" in v


def normalise_employee_entries(raw: Any) -> tuple[list[EmployeeFile], list[EmployeeIssue]]:
    """Normalise a single employee's value (str | list) into typed entries.

    Returns ``(entries, issues)``. ``entries`` is always a list (possibly
    empty); ``issues`` describes anything that needed intervention.
    """
    issues: list[EmployeeIssue] = []

    # Tolerate the case where an employee's value is a single string or
    # dict instead of a list.
    if isinstance(raw, str):
        raw = [raw]
    elif isinstance(raw, dict):
        raw = [raw]
    elif raw is None:
        return [], []
    elif not isinstance(raw, list):
        issues.append(EmployeeIssue(
            kind="wrong_type",
            name="",
            detail=f"expected list, got {type(raw).__name__}",
        ))
        return [], issues

    # Detect mixed format (some str, some dict) — we'll upgrade, but flag it.
    types = {type(x).__name__ for x in raw}
    if len(types) > 1:
        issues.append(EmployeeIssue(
            kind="mixed_format",
            name="",
            detail=f"list mixes {sorted(types)}; normalising to dict form",
        ))

    entries: list[EmployeeFile] = []
    for item in raw:
        if _is_legacy_entry(item):
            # Upgrade legacy string → dict with path only.
            entries.append(EmployeeFile(path=str(item)))
        elif _is_current_entry(item):
            try:
                entries.append(EmployeeFile(**item))
            except Exception as e:
                issues.append(EmployeeIssue(
                    kind="bad_entry",
                    name="",
                    detail=f"could not parse entry {item!r}: {e}",
                ))
        else:
            issues.append(EmployeeIssue(
                kind="bad_entry",
                name="",
                detail=f"unrecognised entry type {type(item).__name__}: {item!r}",
            ))
    return entries, issues


def validate_employees_dict(
    data: dict[str, Any],
    check_paths: bool = False,
    base_dir: Optional[Path] = None,
) -> tuple[dict[str, list[EmployeeFile]], list[EmployeeIssue]]:
    """Validate an employees dict and return typed form + issues.

    Parameters
    ----------
    data
        Raw dict as loaded from YAML.
    check_paths
        If True, walk every entry's ``path`` and flag unreachable ones
        as ``missing_path`` issues. Disabled by default to keep the
        pure-parse phase fast and offline-friendly.
    base_dir
        Directory to resolve relative paths against. Required when
        ``check_paths=True``.
    """
    if not isinstance(data, dict):
        return {}, [EmployeeIssue(
            kind="wrong_type", name="",
            detail=f"expected dict at top level, got {type(data).__name__}",
        )]

    seen_names: dict[str, int] = {}
    out: dict[str, list[EmployeeFile]] = {}
    issues: list[EmployeeIssue] = []

    for name, raw_entries in data.items():
        name_str = str(name).strip()
        if not name_str:
            issues.append(EmployeeIssue(
                kind="empty_name", name="<empty>",
                detail="employee with empty or whitespace-only name",
            ))
            continue

        seen_names[name_str] = seen_names.get(name_str, 0) + 1

        entries, entry_issues = normalise_employee_entries(raw_entries)
        # Attach the name to per-entry issues for actionable messages.
        for issue in entry_issues:
            issue.name = name_str
        issues.extend(entry_issues)
        out[name_str] = entries

    # Duplicate-name pass (after we've seen everything).
    for name, count in seen_names.items():
        if count > 1:
            issues.append(EmployeeIssue(
                kind="duplicate_name", name=name,
                detail=f"name appears {count} times; only the last wins on reload",
            ))

    # Optional path-existence pass.
    if check_paths:
        if base_dir is None:
            base_dir = Path.cwd()
        for name, entries in out.items():
            for entry in entries:
                if not entry.path:
                    issues.append(EmployeeIssue(
                        kind="missing_path", name=name,
                        detail="entry has empty path",
                    ))
                    continue
                candidates = [Path(entry.path), base_dir / entry.path]
                if not any(p.exists() for p in candidates):
                    issues.append(EmployeeIssue(
                        kind="missing_path", name=name,
                        detail=f"path does not resolve: {entry.path}",
                    ))

    return out, issues


def migrate_employees_dict(data: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Return *data* in the current (dict-entry) shape, ready to dump.

    Strips ``id``/``fp`` if either is None so the YAML stays clean.
    Idempotent: a dict already in current shape round-trips unchanged.
    """
    typed, _issues = validate_employees_dict(data, check_paths=False)
    out: dict[str, list[dict[str, Any]]] = {}
    for name, entries in typed.items():
        serialised: list[dict[str, Any]] = []
        for entry in entries:
            d: dict[str, Any] = {"path": entry.path}
            if entry.id is not None:
                d["id"] = entry.id
            if entry.fp is not None:
                d["fp"] = entry.fp
            serialised.append(d)
        out[name] = serialised
    return out


def recompute_fingerprints(
    data: dict[str, Any],
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    """Walk every file, refresh its inode + content hash. Returns
    ``(upgraded_data, files_scanned)``.

    Used by operators who want to upgrade a legacy file *and* populate
    the metadata in one pass. Missing files are skipped (their entry
    is preserved without metadata, not dropped).
    """
    typed, _ = validate_employees_dict(data, check_paths=False)
    out: dict[str, list[dict[str, Any]]] = {}
    scanned = 0
    for name, entries in typed.items():
        serialised: list[dict[str, Any]] = []
        for entry in entries:
            d: dict[str, Any] = {"path": entry.path}
            try:
                st = os.stat(entry.path)
                with open(entry.path, "rb") as f:
                    h = hashlib.md5()
                    for chunk in iter(lambda: f.read(8192), b""):
                        h.update(chunk)
                d["id"] = st.st_ino
                d["fp"] = h.hexdigest()
                scanned += 1
            except OSError as e:
                log.debug("could not fingerprint %s: %s", entry.path, e)
            serialised.append(d)
        out[name] = serialised
    return out, scanned
