"""Employee file-status refresh logic for the AppController.

UI-free module extracted from ``core/app_controller.py`` (TD: god-object
decomposition). ``run_refresh_status`` orchestrates the parallel status
probe: cache hits are served from SQLite, misses re-scan the workbook via
the ingestion layer, and a 30s ``as_completed`` deadline keeps a single
hung network drive from freezing the whole refresh.
"""

from __future__ import annotations

import concurrent.futures
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from core.app.file_processor import date_matches_target
from core.app.curator_paths import normalize_selected_datetime


def has_target_date(
    available_dates: List[Any], target_date_obj: datetime, today: datetime
) -> bool:
    if target_date_obj.date() > today.date():
        return False
    for available_date in available_dates or []:
        if date_matches_target(available_date, target_date_obj):
            return True
    return False


def check_employee_refresh_status(
    persistence: Any,
    ingestion: Any,
    name: str,
    employees_map: Dict[str, List[Dict[str, Any]]],
    target_date_obj: datetime,
    today: datetime,
) -> tuple[str, str, str, str]:
    """Status of one employee's files for *target_date_obj*.

    Returns ``(name, status_text, path_label, tag)`` with tags
    ``ready``/``partial``/``missing``.
    """
    metas = employees_map.get(name, [])
    paths = [m["path"] if isinstance(m, dict) else m for m in metas]
    paths = [p for p in paths if os.path.exists(p)]

    if not paths:
        return (name, "🔴 НЕТ ФАЙЛА", "---", "missing")

    path_str = (
        os.path.basename(paths[0]) if len(paths) == 1 else f"[{len(paths)} файлов]"
    )
    status, tag = "🟠 НЕТ ДАТЫ", "partial"

    try:
        forced_refresh_tokens = set()
        for p in paths:
            p_path = Path(p)
            stat = os.stat(p_path)
            stat_mtime = stat.st_mtime
            stat_size = stat.st_size
            cache = persistence.get_file_cache(str(p_path))

            cache_hit = (
                cache
                and cache["mtime"] == stat_mtime
                and cache["size"] == stat_size
            )

            if cache_hit:
                available = cache.get("dates", [])
                if has_target_date(available, target_date_obj, today):
                    status, tag = "🟢 ГОТОВО", "ready"
                    break

                force_token = (
                    str(p_path),
                    target_date_obj.strftime("%d.%m.%Y"),
                    stat_mtime,
                    stat_size,
                )
                if force_token not in forced_refresh_tokens:
                    forced_refresh_tokens.add(force_token)
                    available = ingestion.get_available_dates(
                        p_path,
                        remote_mtime=stat_mtime,
                        remote_size=stat_size,
                        strict_io=True,
                    )
                    persistence.save_file_cache(
                        str(p_path),
                        stat_mtime,
                        stat_size,
                        available,
                    )
            else:
                available = ingestion.get_available_dates(
                    p_path,
                    remote_mtime=stat_mtime,
                    remote_size=stat_size,
                    strict_io=True,
                )
                persistence.save_file_cache(
                    str(p_path),
                    stat_mtime,
                    stat_size,
                    available,
                )

            if has_target_date(available, target_date_obj, today):
                status, tag = "🟢 ГОТОВО", "ready"
                break
    except Exception as e:
        logging.exception("Error %s: %s", name, e)
        status, tag = "[ERR] ОШИБКА", "missing"

    return (name, status, path_str, tag)


def run_refresh_status(
    *,
    persistence: Any,
    ingestion: Any,
    executor: concurrent.futures.ThreadPoolExecutor,
    employees_map_provider: Callable[[], Dict[str, List[Dict[str, Any]]]],
    rename_detected: Callable[[], bool],
    on_employees_loaded: Callable[[Dict[str, List[Dict[str, Any]]]], None],
    selected_date: Any,
    on_progress: Callable[[float], None],
    on_complete: Callable[[List[tuple[Any, ...]], Dict[str, Any], bool], None],
    on_error: Optional[Callable[[str], None]] = None,
) -> None:
    """Refresh every employee's file status in parallel (worker pool)."""
    try:
        _t0 = time.monotonic()
        logging.info("[NET] Загружаю статусы файлов...")
        employees_map = employees_map_provider()
        unique_names = sorted(employees_map.keys())
        if not unique_names:
            on_complete([], {}, False)
            return

        target_date_obj = normalize_selected_datetime(selected_date)
        today = datetime.now()
        total_count = len(unique_names)
        local_data: List[tuple[Any, ...]] = []

        futures = {
            executor.submit(
                check_employee_refresh_status,
                persistence,
                ingestion,
                name,
                employees_map,
                target_date_obj,
                today,
            ): name
            for name in unique_names
        }
        try:
            for i, future in enumerate(
                concurrent.futures.as_completed(futures, timeout=30)
            ):
                local_data.append(future.result())
                on_progress(((i + 1) / total_count) * 100)
        except concurrent.futures.TimeoutError:
            # A single hung stat lookup (network drive stall, etc.)
            # used to block the whole refresh indefinitely because
            # as_completed had no per-future deadline. Cancel the
            # stragglers, surface which employees we skipped, and
            # keep going with whatever we collected so the user
            # sees a partial result instead of a frozen UI.
            timed_out = [n for fut, n in futures.items() if not fut.done()]
            logging.warning(
                "[NET] Refresh status timed out after 30s; "
                "%d/%d employees not finished: %s",
                len(timed_out),
                total_count,
                ", ".join(timed_out[:10]) + ("..." if len(timed_out) > 10 else ""),
            )
            for fut in futures:
                if not fut.done():
                    fut.cancel()
            on_progress((len(local_data) / total_count) * 100)

        local_data.sort(key=lambda x: x[0])
        on_employees_loaded(employees_map)
        _elapsed = time.monotonic() - _t0
        logging.info(f"[PERF] Refresh status: {_elapsed:.1f}s for {total_count} employees")
        on_complete(local_data, employees_map, rename_detected())
    except Exception as e:
        logging.exception("Refresh error: %s", e)
        on_complete([], {}, False)
        if callable(on_error):
            on_error(f"Ошибка обновления статусов: {e}")
