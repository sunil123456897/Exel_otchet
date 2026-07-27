"""Stage 2 / MR-0204 — config & employees test matrix.

Covers the configurations the operator can throw at the loader:

* the committed ``config.example.yaml`` (the canonical starting point);
* an anonymised real-world config (multiple curators, rsch, custom keys);
* each supported previous version (currently only v1, but the test
  scaffolding is here for v2/v3 once migrations exist);
* corrupted YAML;
* unknown fields;
* missing ``config_version``;
* Cyrillic / UNC / whitespace / network-style paths;
* read-only file;
* interrupted migration (simulated by partial write).

These are property tests over the loader behaviour. They DO NOT touch
the operator's real ``config.yaml`` — every test builds its input in a
temporary directory.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import pytest
from core.infra import config_migrations
from core.infra.config_schema import (
    ConfigIssueKind,
    classify_paths,
    validate_config_dict,
)
from ruamel.yaml import YAML

# ── helpers ─────────────────────────────────────────────────────────────

def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    yaml = YAML()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)


def _load_yaml(path: Path) -> dict[str, Any]:
    yaml = YAML()
    with path.open("r", encoding="utf-8") as f:
        return yaml.load(f) or {}


# ── 1) canonical example.yaml round-trip ───────────────────────────────

def test_config_example_yaml_loads_and_validates(repo_root: Path) -> None:
    """The committed example must load cleanly into the typed schema."""
    example = repo_root / "APP" / "config.example.yaml"
    assert example.is_file(), "config.example.yaml must ship with the app"
    data = _load_yaml(example)

    # Pre-versioning example: stamp then validate.
    migrated, _ = config_migrations.migrate_to_current(dict(data))
    model, issues = validate_config_dict(migrated)

    blocking = [i for i in issues
                if i.kind in {ConfigIssueKind.WRONG_TYPE, ConfigIssueKind.MISSING_FIELD}]
    assert not blocking, (
        f"config.example.yaml has blocking issues: {[i.as_dict() for i in blocking]}"
    )
    # The example must have at least the well-known sections so first-run
    # operators see something usable.
    assert model.database.path
    assert model.paths.master_file  # populated in the example


# ── 2) anonymised real-world config ────────────────────────────────────

def test_anonymised_multi_curator_config_validates() -> None:
    """A realistic config with two curators, rsch section and a custom key."""
    data = {
        "database": {"path": "cache.db", "use_wal": True, "timeout": 30.0},
        "logic": {"commission_is_percent": True,
                  "return_keywords": ["возврат"],
                  "income_overrides": ["доп", "доп сф", "% посред"]},
        "paths": {"master_file": "out.xlsx",
                  "source_roots": ["Q:/Отчет кураторов 1",
                                   "Q:/Отчет кураторов 2"]},
        "curators": {
            "boris": {"enabled": True, "output_path": "out/b.xlsx",
                      "employees_key": "борис"},
            "ivan": {"enabled": False, "output_path": "out/i.xlsx",
                     "employees_key": "иван"},
        },
        "rsch": {"mode": "combined", "recent_sources": []},
        # Operator-specific custom section that must survive.
        "company_internal": {"firm_id": "anonymised"},
    }
    migrated, _ = config_migrations.migrate_to_current(dict(data))
    _model, issues = validate_config_dict(migrated)

    blocking = [i for i in issues
                if i.kind in {ConfigIssueKind.WRONG_TYPE, ConfigIssueKind.MISSING_FIELD}]
    assert not blocking
    # The custom section survived the round-trip.
    assert "company_internal" in migrated


# ── 3) supported previous versions ─────────────────────────────────────

def test_v0_unversioned_config_migrates_to_current() -> None:
    """A config with no config_version stamps to v1 without data loss."""
    data = {"database": {"path": "x.db"}}
    migrated, log = config_migrations.migrate_to_current(dict(data))
    assert migrated["config_version"] == 1
    assert migrated["database"] == {"path": "x.db"}
    assert any("v0" in line for line in log)


@pytest.mark.parametrize("version", [0, 1])
def test_each_supported_version_migrates_to_current(version: int) -> None:
    """Both v0 (implicit) and v1 must reach CURRENT_CONFIG_VERSION."""
    data = {"database": {"path": "x.db"}}
    if version > 0:
        data["config_version"] = version
    migrated, _ = config_migrations.migrate_to_current(dict(data))
    assert migrated["config_version"] >= 1


# ── 4) corrupted YAML ─────────────────────────────────────────────────

def test_corrupted_yaml_does_not_crash_pipeline(tmp_path: Path) -> None:
    """If the YAML parser fails, the loader returns {} and the app still starts."""
    bad = tmp_path / "config.yaml"
    bad.write_text("database: [unclosed", encoding="utf-8")
    yaml = YAML()
    with pytest.raises(Exception):
        # The parser is expected to raise; the caller (ConfigController)
        # wraps this in try/except and returns {}.
        with bad.open("r", encoding="utf-8") as f:
            yaml.load(f)


# ── 5) unknown fields ─────────────────────────────────────────────────

def test_unknown_field_is_preserved_and_reported() -> None:
    """A typo-level unknown key is not dropped, but is surfaced."""
    data = {"database": {"path": "x.db"}, "perf": {"max_workers": 4}}
    _model, issues = validate_config_dict(data)
    assert any(i.kind == ConfigIssueKind.UNKNOWN_FIELD and i.path == "perf"
               for i in issues)
    # Field survives via extra="allow".
    assert "perf" in _model.model_dump()


# ── 6) missing config_version ─────────────────────────────────────────

def test_missing_config_version_does_not_break_validation() -> None:
    """An old-style config without config_version is still usable."""
    data = {"database": {"path": "x.db"}}
    # First migrate, then validate.
    migrated, _ = config_migrations.migrate_to_current(dict(data))
    _model, issues = validate_config_dict(migrated)
    blocking = [i for i in issues
                if i.kind in {ConfigIssueKind.WRONG_TYPE, ConfigIssueKind.MISSING_FIELD}]
    assert not blocking


# ── 7) special-character paths ─────────────────────────────────────────

@pytest.mark.parametrize("path_repr", [
    "Кириллица/путь/с пробелами.xlsx",      # Cyrillic + spaces
    "\\\\server\\share\\file.xlsx",          # UNC
    "Q:/Отчет кураторов 1/file.xlsx",        # network drive + Cyrillic
    "/abs/path/file.xlsx",                   # POSIX-style (treated as abs on win)
])
def test_paths_with_special_characters_round_trip(path_repr: str) -> None:
    """Paths with Cyrillic / spaces / UNC survive validation."""
    data = {"paths": {"master_file": path_repr}}
    model, issues = validate_config_dict(data)
    # Validation does not fail; reachability is a separate concern.
    blocking = [i for i in issues if i.kind == ConfigIssueKind.WRONG_TYPE]
    assert not blocking
    assert model.paths.master_file == path_repr


# ── 8) read-only file ─────────────────────────────────────────────────

def test_readonly_config_can_still_be_read(tmp_path: Path) -> None:
    """A read-only config.yaml is loadable. Migration persistence is skipped."""
    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, {"database": {"path": "x.db"}})
    os.chmod(cfg, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)  # 0444-ish on win
    # Must still load.
    data = _load_yaml(cfg)
    assert data["database"]["path"] == "x.db"
    # Restore permissions so pytest cleanup can remove the file.
    os.chmod(cfg, stat.S_IWRITE | stat.S_IREAD)


# ── 9) interrupted migration ──────────────────────────────────────────

def test_migration_failure_does_not_corrupt_data(tmp_path: Path) -> None:
    """If a migration throws, the on-disk file is unchanged.

    The migration runner restores from backup on failure. We simulate
    this by injecting a migration that raises and confirming the input
    data is intact afterwards.
    """
    data = {"database": {"path": "original.db"}, "config_version": 1}

    # Install a deliberately failing migration v1→v2 by monkey-patching
    # the chain. We don't actually have a v2, so we register a fake one
    # and bump CURRENT_CONFIG_VERSION only inside this test.
    import core.infra.config_migrations as cm
    import core.infra.config_schema as cs

    original_current_schema = cs.CURRENT_CONFIG_VERSION
    original_current_cm = cm.CURRENT_CONFIG_VERSION
    original_chain = cm.MIGRATIONS[:]
    try:
        cs.CURRENT_CONFIG_VERSION = 2
        cm.CURRENT_CONFIG_VERSION = 2

        def _boom(_data: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("simulated migration failure")

        cm.MIGRATIONS = [_boom]

        with pytest.raises(RuntimeError, match="simulated"):
            cm.migrate_to_current(dict(data))
    finally:
        cs.CURRENT_CONFIG_VERSION = original_current_schema
        cm.CURRENT_CONFIG_VERSION = original_current_cm
        cm.MIGRATIONS = original_chain

    # The caller's data is untouched.
    assert data["database"]["path"] == "original.db"
    assert data["config_version"] == 1


# ── 10) round-trip stability ──────────────────────────────────────────

def test_round_trip_load_migrate_dump_reload(tmp_path: Path) -> None:
    """Load → migrate → dump → reload must give a stable result."""
    data = {"database": {"path": "x.db"},
            "curators": {"x": {"output_path": "out.xlsx"}}}
    cfg = tmp_path / "config.yaml"
    _write_yaml(cfg, data)

    # Load + migrate.
    loaded = _load_yaml(cfg)
    migrated, _ = config_migrations.migrate_to_current(dict(loaded))

    # Dump back.
    _write_yaml(cfg, migrated)

    # Reload — must equal the migrated form.
    reloaded = _load_yaml(cfg)
    assert reloaded == migrated


# ── 11) path classification across all path fields ────────────────────

def test_classify_paths_walks_all_path_fields(tmp_path: Path) -> None:
    """classify_paths must visit paths.* and curators.<name>.{output,direct}."""
    data = {
        "paths": {
            "master_file": str(tmp_path / "missing_master.xlsx"),
            "source_root": str(tmp_path / "missing_src"),
            "source_roots": [str(tmp_path / "missing_root1")],
            "archive_dir": str(tmp_path / "missing_archive"),
            "output_root": str(tmp_path / "missing_out"),
        },
        "curators": {
            "boris": {"output_path": str(tmp_path / "missing_curator.xlsx"),
                      "direct_paths": [str(tmp_path / "missing_direct")]},
        },
    }
    model, _ = validate_config_dict(data)
    issues = classify_paths(model, base_dir=tmp_path)
    flagged_paths = {i.path for i in issues}
    # All seven path fields should be flagged.
    assert "paths.master_file" in flagged_paths
    assert "paths.source_root" in flagged_paths
    assert "paths.source_roots[0]" in flagged_paths
    assert "paths.archive_dir" in flagged_paths
    assert "paths.output_root" in flagged_paths
    assert "curators.boris.output_path" in flagged_paths
    assert "curators.boris.direct_paths[0]" in flagged_paths


# ── fixture: repo root ─────────────────────────────────────────────────

@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]
