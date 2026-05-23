import os
from typing import Any, Mapping


def default_max_workers() -> int:
    return min(32, (os.cpu_count() or 4) * 2)


def resolve_max_workers(config: Mapping[str, Any] | None) -> int:
    if not isinstance(config, Mapping):
        return default_max_workers()
    performance = config.get("performance")
    if not isinstance(performance, Mapping):
        return default_max_workers()
    raw_value = performance.get("max_workers")
    if raw_value in (None, ""):
        return default_max_workers()
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default_max_workers()
    return max(1, min(64, value))
