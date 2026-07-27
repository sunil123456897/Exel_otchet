"""Stage 2 / MR-0202 — sequential, idempotent config migrations.

This package turns "config_version bump" into an explicit, testable
operation. The contract:

* A migration takes a config dict at version *N* and returns a config
  dict at version *N+1*.
* Migrations are **idempotent**: applying the same migration twice
  produces the same output as applying it once.
* Migrations **never delete** unknown keys. If the operator added
  ``custom_widget.color = red``, a migration leaves it alone.
* The runner applies migrations in order up to ``CURRENT_CONFIG_VERSION``.
* If the input has no version, it is treated as v0 and walked forward.
* Any exception rolls back: the on-disk file is NOT modified.

Migrations are registered in ``MIGRATIONS`` below. To add one:

1. Bump ``CURRENT_CONFIG_VERSION`` in ``config_schema.py``.
2. Create ``vN_to_vN+1.py`` here with a ``migrate(data: dict) -> dict``
   function.
3. Register it in ``MIGRATIONS``.

Example: when ``config_version`` goes from 1 → 2 because we rename
``database.path`` to ``database.sqlite_path``, the migration copies the
old value to the new key and leaves the old key in place with a comment
for the operator to review.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from core.infra.config_schema import CURRENT_CONFIG_VERSION

log = logging.getLogger(__name__)

# A migration takes a v{N} dict and returns a v{N+1} dict.
Migration = Callable[[dict[str, Any]], dict[str, Any]]

# Ordered chain: index 0 migrates v0→v1, index 1 migrates v1→v2, ...
# Currently empty because v1 is the first versioned schema. Add entries
# here as the schema evolves.
MIGRATIONS: list[Migration] = [
    # v0_to_v1: implicitly handled by ensure_config_version — the very
    # first migration is "stamp the config_version field". No structural
    # change beyond that, so we register it as a no-op that the runner
    # uses to mark the version.
]


def _stamp_version(data: dict[str, Any], version: int) -> dict[str, Any]:
    """Return a shallow copy of *data* with ``config_version`` set."""
    out = dict(data)
    out["config_version"] = version
    return out


def migrate_to_current(data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Walk *data* forward to ``CURRENT_CONFIG_VERSION``.

    Returns ``(migrated_data, log_lines)``. ``log_lines`` describe each
    applied migration for the audit trail; they contain no PII.

    Idempotency: if the data is already at the current version, no
    migrations run and the data is returned unchanged.
    """
    if not isinstance(data, dict):
        raise TypeError(f"config must be a dict, got {type(data).__name__}")

    log_lines: list[str] = []
    current = data.get("config_version")
    if current is None or current == 0:
        # Pre-versioning config (field absent) or explicit v0. Stamp v1;
        # v0→v1 is the implicit "introduce config_version" migration.
        log_lines.append("v0 → v1: no config_version present (or =0); stamping v1 (no structural change).")
        data = _stamp_version(data, 1)
        current = 1
    else:
        try:
            current = int(current)
        except (TypeError, ValueError) as e:
            raise ValueError(
                f"config_version={current!r} is not an integer; refusing to migrate."
            ) from e

    if current > CURRENT_CONFIG_VERSION:
        # Future version. Do not silently downgrade.
        raise ValueError(
            f"config_version={current} is newer than the schema's "
            f"CURRENT_CONFIG_VERSION={CURRENT_CONFIG_VERSION}. "
            f"Refusing to migrate backwards; upgrade the application."
        )

    # Apply each registered migration in order. The chain starts at v1→v2
    # (index 0). v0→v1 was the implicit "stamp version" step handled above.
    while current < CURRENT_CONFIG_VERSION:
        idx = current - 1  # MIGRATIONS[0] is v1→v2
        if idx < 0 or idx >= len(MIGRATIONS):
            # No registered migration for this step. We are at a version
            # below CURRENT but no migration is defined — this is a bug.
            raise RuntimeError(
                f"no migration registered to bring config from v{current} to "
                f"v{current + 1}. Expected MIGRATIONS[{idx}]."
            )
        step = MIGRATIONS[idx]
        before = dict(data)
        try:
            data = step(data)
        except Exception as e:
            # Never partially apply; the caller restores the backup.
            log.error("migration v%d→v%d failed: %s", current, current + 1, e)
            raise
        # Idempotency / safety: the migration MUST bump the version.
        if data.get("config_version") != current + 1:
            data = _stamp_version(data, current + 1)
        log_lines.append(f"v{current} → v{current + 1}: {step.__doc__ or '(no description)'}")
        current = int(data["config_version"])

        # Sanity: migration must not have dropped user keys.
        dropped = set(before.keys()) - set(data.keys())
        if dropped:
            log_lines.append(
                f"  WARNING: migration dropped keys {sorted(dropped)}; restoring them."
            )
            for k in dropped:
                data[k] = before[k]

    return data, log_lines
