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
    # 0 / None / "" трактуются как «default» — это соответствует комментарию
    # в config.yaml («Empty keeps the current default»). Раньше явный 0
    # возвращал 1 (max(1, min(64, 0))), что молча замедляло чтение/сборку
    # на многоядерных ПК заказчика (F-PERF-1).
    if raw_value in (None, "", 0):
        return default_max_workers()
    assert raw_value is not None  # the guard above already excluded None
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return default_max_workers()
    return max(1, min(64, value))
