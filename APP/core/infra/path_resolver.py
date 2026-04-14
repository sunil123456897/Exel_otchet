import os
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional


logger = logging.getLogger(__name__)


def _path_suffix_candidates(path_str: str) -> List[str]:
    norm = path_str.replace("\\", "/").lower().strip()
    if not norm:
        return []

    candidates = [norm]
    reports_marker = "/reports/"
    idx = norm.find(reports_marker)
    if idx != -1:
        candidates.append(norm[idx + len(reports_marker) :])

    parts = [part for part in norm.split("/") if part not in ("", ".", "..")]
    if parts:
        candidates.append("/".join(parts))
    if len(parts) >= 2:
        candidates.append("/".join(parts[-2:]))
    if parts:
        candidates.append(parts[-1])

    deduped = []
    seen = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            deduped.append(candidate)
            seen.add(candidate)
    return deduped


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
    if config_controller and hasattr(config_controller, "resolve_path"):
        resolver = getattr(config_controller, "resolve_path")
        if callable(resolver):
            try:
                candidate = resolver(path_str)
                if isinstance(candidate, (str, Path)):
                    p_abs = Path(candidate)
            except (TypeError, ValueError, OSError) as e:
                logger.debug("resolve_path failed, using original path value: %s", e)

    found_meta = None
    suffixes = _path_suffix_candidates(path_str)
    for df in discovered_files:
        df_norm = df["path"].replace("\\", "/").lower()
        if any(df_norm.endswith(suffix) for suffix in suffixes):
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

    if p_abs.is_absolute() and p_abs.exists():
        meta = {"path": str(p_abs)}
        if file_id is not None:
            meta["id"] = file_id
        if file_hash is not None:
            meta["fp"] = file_hash
        return str(p_abs), meta, False

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
