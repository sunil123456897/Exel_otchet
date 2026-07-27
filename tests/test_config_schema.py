"""Stage 2 / MR-0201 + MR-0202 — config schema, versioning, migrations.

Two layers are tested:

1. ``config_schema.py`` — typed Pydantic model + four-way error taxonomy
   (missing field, wrong type, unknown field, unreachable path).
2. ``config_migrations/`` — sequential, idempotent migration chain that
   walks old configs forward and never drops operator-added keys.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from core.infra import config_migrations
from core.infra.config_schema import (
    CURRENT_CONFIG_VERSION,
    AppConfig,
    ConfigIssue,
    ConfigIssueKind,
    classify_paths,
    ensure_config_version,
    validate_config_dict,
)

# ── MR-0201: schema & error taxonomy ───────────────────────────────────

def test_minimal_config_validates_with_defaults() -> None:
    """An empty dict should still produce a usable AppConfig with defaults."""
    model, issues = validate_config_dict({})
    assert isinstance(model, AppConfig)
    assert model.config_version == CURRENT_CONFIG_VERSION
    # An empty dict has no validation issues.
    assert issues == []


def test_config_version_field_is_required_in_output() -> None:
    """The validated model always reports config_version."""
    model, _ = validate_config_dict({})
    assert model.config_version == CURRENT_CONFIG_VERSION


def test_wrong_type_is_classified() -> None:
    """A field with the wrong type surfaces as WRONG_TYPE, not silently coerced."""
    data = {"database": {"timeout": "not-a-number"}}
    model, issues = validate_config_dict(data)
    kinds = {i.kind for i in issues}
    assert ConfigIssueKind.WRONG_TYPE in kinds
    # Despite the error, the model is usable (default filled in).
    assert model.database.timeout == 30.0


def test_unknown_top_level_field_is_reported_not_dropped() -> None:
    """A typo or unknown key is preserved AND reported."""
    data = {"performnace": {"isolate_calamine": True}, "database": {"path": "x.db"}}
    model, issues = validate_config_dict(data)
    # The model retained the unknown section via extra="allow".
    dumped = model.model_dump()
    assert "performnace" in dumped
    # And we surfaced it as an issue.
    unknown = [i for i in issues if i.kind == ConfigIssueKind.UNKNOWN_FIELD]
    assert any("performnace" in i.path for i in unknown)


def test_missing_required_field_for_strict_mode_classified() -> None:
    """If a field had no default and was missing, we'd flag it.

    Currently every field has a default (the schema is permissive), so we
    simulate the path by injecting a None where a typed value is expected.
    """
    data = {"database": None}  # section expected to be a dict, got None
    model, issues = validate_config_dict(data)
    # Pydantic will fall back to defaults, but the issue is recorded.
    assert any(i.kind == ConfigIssueKind.WRONG_TYPE for i in issues)


def test_config_version_accepts_numeric_string() -> None:
    """config_version may arrive as "1" from YAML; should still parse."""
    data = {"config_version": "1"}
    model, _ = validate_config_dict(data)
    assert model.config_version == 1


def test_config_version_rejects_bool() -> None:
    """bool is an int subclass; the schema must reject it explicitly."""
    data = {"config_version": True}
    model, issues = validate_config_dict(data)
    # Either rejected with a WRONG_TYPE issue, or set to default. Either
    # way, never silently accepted as version 1.
    if model.config_version == 1:
        # Pydantic fell back to default because True was rejected.
        assert any(i.kind == ConfigIssueKind.WRONG_TYPE for i in issues)


# ── path classification (UNREACHABLE_PATH vs WRONG_TYPE) ───────────────

def test_unreachable_path_is_not_a_type_error(tmp_path: Path) -> None:
    """A path that does not resolve is NOT the same as a malformed field."""
    data = {"paths": {"master_file": str(tmp_path / "does_not_exist.xlsx")}}
    model, issues = validate_config_dict(data)
    # Schema-level: valid (it's a string).
    assert not any(i.kind == ConfigIssueKind.WRONG_TYPE for i in issues)
    # Environment-level: unreachable.
    path_issues = classify_paths(model, base_dir=tmp_path)
    assert any(i.kind == ConfigIssueKind.UNREACHABLE_PATH for i in path_issues)


def test_reachable_path_is_not_flagged(tmp_path: Path) -> None:
    """A path that resolves produces no UNREACHABLE_PATH issue."""
    real_file = tmp_path / "real.xlsx"
    real_file.write_text("ok")
    data = {"paths": {"master_file": str(real_file)}}
    model, _ = validate_config_dict(data)
    path_issues = classify_paths(model, base_dir=tmp_path)
    assert not any(i.kind == ConfigIssueKind.UNREACHABLE_PATH for i in path_issues)


# ── MR-0202: migration chain ───────────────────────────────────────────

def test_migration_idempotent_on_current_version() -> None:
    """A config already at CURRENT_CONFIG_VERSION is returned unchanged."""
    data = {"config_version": CURRENT_CONFIG_VERSION, "database": {"path": "x.db"}}
    out, log_lines = config_migrations.migrate_to_current(dict(data))
    assert out == data
    assert log_lines == []


def test_migration_stamps_v1_for_pre_version_config() -> None:
    """A config with no config_version is stamped to v1."""
    data = {"database": {"path": "x.db"}}
    out, log_lines = config_migrations.migrate_to_current(dict(data))
    assert out["config_version"] == 1
    assert any("v0" in line and "v1" in line for line in log_lines)


def test_migration_preserves_operator_keys() -> None:
    """Operator-added custom keys must survive every migration."""
    data = {
        "config_version": 0,  # forces the v0→v1 stamp
        "database": {"path": "x.db"},
        "custom_widget": {"color": "red", "size": 42},
    }
    out, _ = config_migrations.migrate_to_current(dict(data))
    assert out["custom_widget"] == {"color": "red", "size": 42}


def test_migration_refuses_downgrade() -> None:
    """A config claiming a future version must not be silently downgraded."""
    future = CURRENT_CONFIG_VERSION + 5
    data = {"config_version": future}
    with pytest.raises(ValueError, match="newer than"):
        config_migrations.migrate_to_current(dict(data))


def test_migration_rejects_non_integer_version() -> None:
    """A garbage config_version is a hard error, not a silent fix."""
    data = {"config_version": "abc"}
    with pytest.raises(ValueError, match="not an integer"):
        config_migrations.migrate_to_current(dict(data))


def test_migration_chain_is_idempotent() -> None:
    """Running migrate_to_current on its own output is a no-op."""
    data = {"database": {"path": "x.db"}, "custom": {"x": 1}}
    once, _ = config_migrations.migrate_to_current(dict(data))
    twice, _ = config_migrations.migrate_to_current(dict(once))
    assert once == twice


def test_ensure_config_version_only_stamps_for_known_shapes() -> None:
    """``ensure_config_version`` only stamps if data looks like a real config."""
    # Looks like a config: should stamp.
    real = {"database": {"path": "x.db"}}
    stamped = ensure_config_version(dict(real))
    assert "config_version" in stamped
    # Random dict: should NOT stamp.
    random_data = {"unrelated": {"key": "value"}}
    not_stamped = ensure_config_version(dict(random_data))
    assert "config_version" not in not_stamped


# ── round-trip: yaml → validate → migrate → validate ───────────────────

def test_full_round_trip_via_dict() -> None:
    """A realistic config dict round-trips through validate/migrate cleanly."""
    data = {
        "database": {"path": "cache.db", "timeout": 30.0, "use_wal": True},
        "logic": {"return_keywords": ["возврат"], "commission_is_percent": True},
        "paths": {"master_file": "out.xlsx"},
        "rsch": {"mode": "combined"},
        "config_version": 1,
    }
    migrated, _ = config_migrations.migrate_to_current(dict(data))
    model, issues = validate_config_dict(migrated)
    # No type errors, no missing fields.
    blocking = [i for i in issues if i.kind in {ConfigIssueKind.WRONG_TYPE,
                                                ConfigIssueKind.MISSING_FIELD}]
    assert not blocking, f"unexpected blocking issues: {blocking}"
    assert model.database.path == "cache.db"
    assert model.logic.return_keywords == ["возврат"]


# ── MR-0201: ConfigIssue serialization ─────────────────────────────────

def test_config_issue_serializes() -> None:
    """Issues must be JSON-serializable for UI display."""
    issue = ConfigIssue(ConfigIssueKind.WRONG_TYPE, "database.timeout",
                        "expected float, got str")
    d = issue.as_dict()
    assert d == {"kind": "wrong_type", "path": "database.timeout",
                 "detail": "expected float, got str"}
    # Round-trips through JSON.
    import json
    assert json.loads(json.dumps(d)) == d
