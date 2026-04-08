import os
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional


logger = logging.getLogger(__name__)


def resolve_employee_path(
    path_str: str,
    file_id=None,
    file_hash=None,
    discovered_files: List[Dict[str, Any]] = None,
    config_controller=None,
) -> tuple:
    """Резолвит путь к файлу сотрудника с обнаружением переименований.

    Returns:
        (resolved_path_str, updated_meta, rename_detected)
    """
    discovered_files = discovered_files or []
    rename_detected = False
    p_abs = Path(path_str)

    if p_abs.is_absolute() and p_abs.exists():
        meta = {"path": str(p_abs)}
        if file_id is not None:
            meta["id"] = file_id
        if file_hash is not None:
            meta["fp"] = file_hash
        return str(p_abs), meta, False

    found_meta = None
    norm_path = path_str.replace("\\", "/").lower()
    for df in discovered_files:
        df_norm = df["path"].replace("\\", "/").lower()
        if df_norm.endswith(norm_path):
            found_meta = df
            break

    if not found_meta and (file_id or file_hash):
        for df in discovered_files:
            if (file_id and df.get("id") == file_id) or (
                file_hash and df.get("fp") and df.get("fp") == file_hash
            ):
                found_meta = df
                break

    if found_meta:
        rename_detected = True
        return found_meta["path"], found_meta, rename_detected

    if (
        not p_abs.is_absolute()
        and config_controller
        and hasattr(config_controller, "config_path")
    ):
        alt_p = (Path(config_controller.config_path).parent / p_abs).resolve()
        if alt_p.exists():
            p_abs = alt_p

    if p_abs.exists():
        meta = {"path": str(p_abs)}
        if file_id is not None:
            meta["id"] = file_id
        if file_hash is not None:
            meta["fp"] = file_hash
        return str(p_abs), meta, False

    return path_str, None, False
