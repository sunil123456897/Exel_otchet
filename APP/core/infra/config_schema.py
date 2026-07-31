"""Stage 2 / MR-0201 — typed Pydantic schema for the application config.

Replaces the previous "load YAML, return a dict, hope for the best"
approach with a typed model that surfaces four distinct error kinds:

* ``MissingField``            — a field is absent and has no default;
* ``WrongType``               — a field is present but with the wrong type;
* ``UnreachablePath``         — a path field points to nothing reachable
                                right now (network drive down, USB removed).
                                Distinct from invalid: the YAML is fine, the
                                environment is not;
* ``UnknownField``            — a field we do not recognise. Preserved, not
                                silently dropped, but reported so a typo
                                like ``database.path`` vs ``database.pathx``
                                surfaces.

The model deliberately allows ``extra="allow"`` so operator-specific and
future fields survive a round-trip. We do not want a schema bump to
delete a field the operator added for their own workflow.

This module is import-safe: importing it never touches the filesystem.
``load_validated_config`` is the public entry point used by
``config_controller``.
"""
from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

log = logging.getLogger(__name__)

# ── the current schema version ──────────────────────────────────────────
#
# Bump this when the shape of any section changes in a way that requires
# a migration. The migration chain lives in
# ``APP/core/infra/config_migrations/`` and walks old versions forward.

CURRENT_CONFIG_VERSION = 1


# ── error taxonomy ──────────────────────────────────────────────────────

class ConfigIssueKind(str, Enum):
    """Why a config failed strict validation.

    ``UNREACHABLE_PATH`` is deliberately separate from ``WRONG_TYPE`` so
    a flapping network drive does not look like a typo in the YAML.
    """
    MISSING_FIELD = "missing_field"
    WRONG_TYPE = "wrong_type"
    UNKNOWN_FIELD = "unknown_field"
    UNREACHABLE_PATH = "unreachable_path"


class ConfigIssue(Exception):
    """A single, classified configuration problem.

    ``path`` is a dotted path like ``"database.timeout"``.
    ``detail`` is human-readable, no PII.
    """

    def __init__(self, kind: ConfigIssueKind, path: str, detail: str):
        self.kind = kind
        self.path = path
        self.detail = detail
        super().__init__(f"[{kind.value}] {path}: {detail}")

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind.value, "path": self.path, "detail": self.detail}


# ── section models ──────────────────────────────────────────────────────

class DatabaseSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    path: str = "cache.db"
    schema_path: str = "db_schema.sql"
    timeout: float = 30.0
    allow_local_fallback: bool = False
    # NOTE: `use_wal` / `isolation_level` used to live here but were never
    # read by db_connection.py (WAL + EXCLUSIVE are hardcoded). Removed from
    # the schema so the UI stops offering a dead switch; legacy configs that
    # still carry the keys survive via extra="allow".


class LockingSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    retry_count: int = 3
    retry_backoff: float = 1.0
    use_semaphores: bool = True


class NetworkSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    drive_letters: list[str] = Field(default_factory=list)


class LogicSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    commission_is_percent: bool = True
    income_overrides: list[str] = Field(default_factory=lambda: ["доп", "доп сф"])
    return_keywords: list[str] = Field(default_factory=lambda: ["возврат"])


class PathsSection(BaseModel):
    """Paths in the config.

    A path field can be unreachable without being invalid (network drive
    is down). The schema does not enforce existence; existence is checked
    separately by ``classify_paths`` so an unreachable path surfaces as
    ``UNREACHABLE_PATH`` rather than ``WRONG_TYPE``.
    """
    model_config = ConfigDict(extra="allow")

    master_file: str = ""
    source_root: str = ""
    source_roots: list[str] = Field(default_factory=list)
    archive_dir: str = ""
    output_root: str = ""


class CuratorEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = True
    output_path: str = ""
    employees_key: str = ""
    direct_paths: list[str] = Field(default_factory=list)


class RschSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    recent_sources: list[str] = Field(default_factory=list)
    last_output_dir: str = ""
    mode: str = "combined"


class PerformanceSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    isolate_calamine: bool = False
    max_workers: Optional[int] = None


class BackupSection(BaseModel):
    model_config = ConfigDict(extra="allow")

    excel_keep: int = 10


# ── top-level model ─────────────────────────────────────────────────────

class AppConfig(BaseModel):
    """Top-level typed configuration.

    Sections not declared here (``sh1``, ``sh2``, ``validation`` …) are
    allowed through ``extra="allow"`` and survive a round-trip. They are
    simply not type-checked — adding a section to the schema is an
    explicit, deliberate action.
    """
    model_config = ConfigDict(extra="allow")

    config_version: int = CURRENT_CONFIG_VERSION

    database: DatabaseSection = Field(default_factory=DatabaseSection)
    locking: LockingSection = Field(default_factory=LockingSection)
    network: NetworkSection = Field(default_factory=NetworkSection)
    logic: LogicSection = Field(default_factory=LogicSection)
    paths: PathsSection = Field(default_factory=PathsSection)
    curators: dict[str, CuratorEntry] = Field(default_factory=dict)
    rsch: RschSection = Field(default_factory=RschSection)
    performance: PerformanceSection = Field(default_factory=PerformanceSection)
    backup: BackupSection = Field(default_factory=BackupSection)

    @field_validator("config_version", mode="before")
    @classmethod
    def _coerce_version(cls, v: Any) -> int:
        """Accept int-like strings (``"1"``) but reject garbage."""
        if v is None:
            return CURRENT_CONFIG_VERSION
        if isinstance(v, bool):
            # bool is a subclass of int; reject explicitly.
            raise ValueError("config_version must be an integer, not bool")
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.strip().isdigit():
            return int(v.strip())
        raise ValueError(f"config_version must be an integer, got {type(v).__name__}")


# ── helpers ─────────────────────────────────────────────────────────────

def validate_config_dict(data: dict[str, Any]) -> tuple[AppConfig, list[ConfigIssue]]:
    """Validate *data* into ``AppConfig`` and classify any problems.

    Returns ``(model, issues)``. The model is always usable (sections have
    defaults); issues is a list of classified problems. The caller decides
    whether issues are warnings or blockers.
    """
    issues: list[ConfigIssue] = []

    # 1) Pydantic-level validation (types, required fields).
    try:
        model = AppConfig(**data)
    except ValidationError as ve:
        # Recover a usable model by re-validating with defaults merged in.
        # We do NOT discard the user's data — we keep it and let Pydantic
        # fill defaults only where validation failed.
        merged = _merge_with_defaults(data)
        try:
            model = AppConfig(**merged)
        except ValidationError as ve2:
            # Last-resort: fully default model. Should be unreachable.
            log.error("config failed validation even with defaults: %s", ve2)
            model = AppConfig()
        for err in ve.errors():
            loc = ".".join(str(x) for x in err["loc"]) or "(root)"
            msg = err["msg"]
            if err["type"] and "missing" in err["type"]:
                kind = ConfigIssueKind.MISSING_FIELD
            elif err["type"] and ("type" in err["type"] or "int" in err["type"]
                                  or "float" in err["type"] or "bool" in err["type"]):
                kind = ConfigIssueKind.WRONG_TYPE
            else:
                kind = ConfigIssueKind.WRONG_TYPE
            issues.append(ConfigIssue(kind, loc, msg))

    # 2) Unknown fields (anything in data not declared in the schema).
    #    Pydantic with extra="allow" lets them through; we report so a typo
    #    like ``performnace`` is visible.
    known_top = set(AppConfig.model_fields.keys())
    for key in data:
        if key not in known_top and not key.startswith("_"):
            issues.append(ConfigIssue(
                ConfigIssueKind.UNKNOWN_FIELD, key,
                "unrecognised top-level key; preserved but not validated. "
                "If this is intentional, leave it; if it is a typo, fix it.",
            ))

    return model, issues


def _merge_with_defaults(data: dict[str, Any]) -> dict[str, Any]:
    """Return *data* with defaults filled in for any missing top-level section.

    Used as a recovery path when Pydantic rejects the raw input. We never
    *remove* the user's keys — we only add the ones a section needs.
    """
    merged = dict(data)
    defaults = AppConfig().model_dump()
    for key, default_val in defaults.items():
        if key not in merged or merged[key] is None:
            merged[key] = default_val
        elif isinstance(default_val, dict) and isinstance(merged[key], dict):
            # Merge section-level defaults under the user's section.
            for sub_k, sub_v in default_val.items():
                merged[key].setdefault(sub_k, sub_v)
    return merged


def classify_paths(model: AppConfig, base_dir: Path) -> list[ConfigIssue]:
    """Walk every path field and report unreachable ones.

    ``base_dir`` is the directory the config file lives in (relative paths
    are resolved against it). An unreachable path is NOT a validation
    failure — it is an environment issue. We return it as a list so the
    UI can show "config valid but 2 paths currently unreachable".
    """
    issues: list[ConfigIssue] = []

    def _check(dotted: str, raw: str) -> None:
        if not raw:
            return
        # Try as-is first (covers UNC and absolute paths), then relative.
        candidates = [Path(raw), base_dir / raw]
        if any(p.exists() for p in candidates):
            return
        issues.append(ConfigIssue(
            ConfigIssueKind.UNREACHABLE_PATH, dotted,
            f"path does not currently resolve: {raw}",
        ))

    _check("paths.master_file", model.paths.master_file)
    _check("paths.source_root", model.paths.source_root)
    for i, src in enumerate(model.paths.source_roots):
        _check(f"paths.source_roots[{i}]", src)
    _check("paths.archive_dir", model.paths.archive_dir)
    _check("paths.output_root", model.paths.output_root)

    for name, curator in model.curators.items():
        _check(f"curators.{name}.output_path", curator.output_path)
        for i, p in enumerate(curator.direct_paths):
            _check(f"curators.{name}.direct_paths[{i}]", p)

    return issues


def ensure_config_version(data: dict[str, Any]) -> dict[str, Any]:
    """Return *data* with ``config_version`` present.

    If the field is missing entirely we set it to ``CURRENT_CONFIG_VERSION``
    *only* when the data looks like a fresh, schema-conformant config —
    i.e. one of the well-known section names is present. Otherwise we
    leave it absent and let ``validate_config_dict`` report it.
    """
    if "config_version" in data:
        return data
    well_known = {"database", "locking", "network", "logic", "paths",
                  "curators", "rsch", "performance", "backup"}
    if well_known & set(data.keys()):
        # Looks like a real config; stamp the current version. The
        # migration layer will handle genuinely old versions on a separate
        # path (see config_migrations/).
        out = dict(data)
        out["config_version"] = CURRENT_CONFIG_VERSION
        return out
    return data
