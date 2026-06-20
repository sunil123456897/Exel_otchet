import logging
from pathlib import Path
from typing import List, Dict, Any, Optional


logger = logging.getLogger(__name__)


def _normalize_path_parts(path_str: str) -> List[str]:
    return [part for part in path_str.replace("\\", "/").split("/") if part not in ("", ".", "..")]


def _resolve_reports_alias(path_str: str, config_controller) -> Optional[Path]:
    if not (config_controller and hasattr(config_controller, "get_paths")):
        return None

    parts = _normalize_path_parts(path_str)
    if not parts or parts[0].lower() != "reports" or len(parts) < 3:
        return None

    get_paths = config_controller.get_paths
    if not callable(get_paths):
        return None

    try:
        paths_cfg = get_paths() or {}
    except Exception:
        logger.debug("get_paths() failed during reports alias resolution", exc_info=True)
        return None

    roots_raw = paths_cfg.get("source_roots") or paths_cfg.get("source_root") or []
    if isinstance(roots_raw, (str, Path)):
        roots = [Path(str(roots_raw))]
    else:
        roots = [Path(str(root)) for root in roots_raw]

    curator_root_name = parts[1]
    suffix_parts = parts[2:]

    for root in roots:
        root_parts = _normalize_path_parts(str(root))
        if not root_parts:
            continue
        if root_parts[-1].lower() != curator_root_name.lower():
            continue
        candidate = Path(root, *suffix_parts)
        if candidate.exists():
            return candidate

    return None


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


def _resolve_with_config_controller(path_str: str, config_controller) -> Path:
    p_abs = Path(path_str)
    if not (config_controller and hasattr(config_controller, "resolve_path")):
        return p_abs

    reports_alias = _resolve_reports_alias(path_str, config_controller)
    if reports_alias is not None:
        return reports_alias

    resolver = config_controller.resolve_path
    if not callable(resolver):
        return p_abs

    try:
        candidate = resolver(path_str)
    except (TypeError, OSError) as e:
        # NOTE: ValueError is deliberately NOT caught here. resolve_path
        # raises ValueError to signal a path-traversal rejection; catching
        # it and falling back to the raw ``p_abs`` would silently re-open
        # the very bypass resolve_path is meant to close. Let it propagate.
        logger.debug("resolve_path failed, using original path value: %s", e)
        return p_abs

    if isinstance(candidate, (str, Path)):
        return Path(candidate)
    return p_abs


def _find_discovered_meta(
    path_str: str,
    discovered_files: List[Dict[str, Any]],
    file_id=None,
    file_hash=None,
):
    suffixes = _path_suffix_candidates(path_str)
    for df in discovered_files:
        df_norm = df["path"].replace("\\", "/").lower()
        if any(df_norm.endswith(suffix) for suffix in suffixes):
            return df

    if not (file_id or file_hash):
        return None

    for df in discovered_files:
        if file_id and df.get("id") == file_id:
            return df
        if file_hash and df.get("fp") and df.get("fp") == file_hash:
            return df
    return None


def _build_meta(path_value: str, file_id=None, file_hash=None) -> Dict[str, Any]:
    meta = {"path": path_value}
    if file_id is not None:
        meta["id"] = file_id
    if file_hash is not None:
        meta["fp"] = file_hash
    return meta


def _resolve_relative_from_config(p_abs: Path, config_controller) -> Path:
    if p_abs.is_absolute():
        return p_abs
    if not (config_controller and hasattr(config_controller, "config_path")):
        return p_abs
    return (Path(config_controller.config_path).parent / p_abs).resolve()


def resolve_employee_path(
    path_str: str,
    file_id=None,
    file_hash=None,
    discovered_files: Optional[List[Dict[str, Any]]] = None,
    config_controller=None,
) -> tuple:
    """Резолвит путь к файлу сотрудника с обнаружением переименований.

    Returns:
        (resolved_path_str, updated_meta, rename_detected)
    """
    discovered_files = discovered_files or []
    p_abs = _resolve_with_config_controller(path_str, config_controller)
    found_meta = _find_discovered_meta(path_str, discovered_files, file_id, file_hash)
    if found_meta:
        return found_meta["path"], found_meta, True

    if p_abs.is_absolute() and p_abs.exists():
        return str(p_abs), _build_meta(str(p_abs), file_id, file_hash), False

    alt_p = _resolve_relative_from_config(p_abs, config_controller)
    if alt_p.exists():
        p_abs = alt_p

    if p_abs.exists():
        return str(p_abs), _build_meta(str(p_abs), file_id, file_hash), False

    return path_str, None, False
