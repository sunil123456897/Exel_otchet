"""Curator/report path resolution helpers for the AppController.

UI-free module extracted from ``core/app_controller.py`` (TD: god-object
decomposition). All functions are pure with respect to their arguments —
the config is passed in explicitly so callers stay explicit about their
dependencies.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, cast

from core.app.file_processor import check_master_lock
from core.infra import is_file_writable
from core.shared.path_scrub import scrub_path


def get_curator_config(config: Dict[str, Any], curator: Optional[str]) -> Optional[Dict[str, Any]]:
    """Return the enabled curator section of ``config`` (or ``None``)."""
    if not curator:
        return None
    curators = config.get("curators", {})
    if not isinstance(curators, dict):
        return None
    cfg = curators.get(curator)
    if not isinstance(cfg, dict) or not cfg.get("enabled", True):
        return None
    return cfg


def get_enabled_curator_employee_keys(config: Dict[str, Any]) -> set[str]:
    """Collect ``employees_key`` values of every enabled curator."""
    curators = config.get("curators", {})
    if not isinstance(curators, dict):
        return set()

    keys = set()
    for cfg in curators.values():
        if not isinstance(cfg, dict) or not cfg.get("enabled", True):
            continue
        key = str(cfg.get("employees_key") or "").strip().lower()
        if key:
            keys.add(key)
    return keys


def employee_name_matches_any_key(name: str, keys: set[str]) -> bool:
    lowered_name = str(name).lower()
    return any(key in lowered_name for key in keys)


def filter_employees_for_curator(
    employees_map: Dict[str, List[Dict[str, Any]]],
    curator_config: Optional[Dict[str, Any]],
    general_excluded_keys: Optional[set[str]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Filter the employee map down to the curator's own employees.

    Without a curator config the map is returned as-is, minus any employees
    whose names contain one of *general_excluded_keys* (the enabled curators'
    employee keys — an employee already claimed by a curator is not shown in
    the general report).
    """
    if not curator_config:
        excluded_keys = general_excluded_keys or set()
        if not excluded_keys:
            return employees_map
        return {
            name: metas
            for name, metas in employees_map.items()
            if not employee_name_matches_any_key(name, excluded_keys)
        }

    key = str(curator_config.get("employees_key") or "").strip().lower()
    if not key:
        return employees_map

    included_keys = {key}

    return {
        name: metas
        for name, metas in employees_map.items()
        if employee_name_matches_any_key(name, included_keys)
    }


def normalize_selected_datetime(selected_date: Any) -> datetime:
    if isinstance(selected_date, datetime):
        return selected_date
    return datetime.combine(selected_date, datetime.min.time())


def get_network_drive_letters(config: Dict[str, Any]) -> tuple[str, ...]:
    """Drive letters to probe for network sources (default: Q and Z)."""
    cfg = config or {}
    network_cfg = cfg.get("network") if isinstance(cfg, dict) else {}
    raw_letters = (
        network_cfg.get("drive_letters", ("Q", "Z"))
        if isinstance(network_cfg, dict)
        else ("Q", "Z")
    )
    if isinstance(raw_letters, str):
        raw_letters = [raw_letters]
    letters = tuple(str(letter).strip() for letter in raw_letters if str(letter).strip())
    return letters or ("Q", "Z")


def resolve_master_path(config_controller: Any) -> Path:
    """Resolve the output master report path (writing the default back to config)."""
    fallback = Path(config_controller.config_path).parent / "Master_Report.xlsx"
    paths_cfg = config_controller.config.setdefault("paths", {})
    master_cfg = paths_cfg.get("master_file")
    if master_cfg:
        master_path = config_controller.resolve_path(str(master_cfg))
    else:
        master_path = fallback
        paths_cfg["master_file"] = str(fallback)
        save_config = getattr(config_controller, "save_config", None)
        if callable(save_config):
            save_config()
    try:
        master_path.parent.mkdir(parents=True, exist_ok=True)
        return cast(Path, master_path)
    except OSError as e:
        logging.warning(
            "Master path unavailable (%s). Using fallback: %s",
            e,
            scrub_path(str(fallback)),
        )
        if Path(paths_cfg.get("master_file", "")) != fallback:
            paths_cfg["master_file"] = str(fallback)
            save_config = getattr(config_controller, "save_config", None)
            if callable(save_config):
                save_config()
        return fallback


def resolve_report_path(
    config_controller: Any, curator_config: Optional[Dict[str, Any]]
) -> Path:
    if curator_config and curator_config.get("output_path"):
        return cast(
            Path,
            config_controller.resolve_path(str(curator_config["output_path"])),
        )
    return resolve_master_path(config_controller)


def is_report_writable(
    config_controller: Any, curator_config: Optional[Dict[str, Any]]
) -> bool:
    """Check that the target report file is not locked by Excel."""
    if not curator_config:
        return cast(bool, check_master_lock(config_controller))
    path = resolve_report_path(config_controller, curator_config)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return cast(bool, is_file_writable(str(path)))


def build_drive_letters_fn(config_controller: Any) -> Callable[[], tuple[str, ...]]:
    """Curry ``get_network_drive_letters`` against the controller's config."""
    return lambda: get_network_drive_letters(config_controller.config)
