import logging
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def backup_existing_excel_output(
    output_path: Path | str,
    backup_root: Path | str | None = None,
    *,
    keep: int = 10,
) -> Path | None:
    """Copy an existing Excel output before it is overwritten.

    Backups are best-effort: a backup failure must not silently overwrite the
    output, so the caller should abort saving when this function raises.
    """

    source = Path(output_path)
    if not source.exists() or not source.is_file():
        return None
    if source.name.startswith("~$"):
        return None

    root = Path(backup_root) if backup_root else source.parent / "backups"
    target_dir = root / "excel_outputs" / source.stem
    target_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    target = target_dir / f"{stamp}_{source.name}"
    shutil.copy2(source, target)
    _prune_backups(target_dir, source.suffix, keep)
    logger.info("Excel output backup created: %s", target)
    return target


def _prune_backups(target_dir: Path, suffix: str, keep: int) -> None:
    if keep <= 0:
        return
    backups = sorted(
        (
            path
            for path in target_dir.iterdir()
            if path.is_file() and path.suffix.lower() == suffix.lower()
        ),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for old_path in backups[keep:]:
        try:
            old_path.unlink()
        except OSError as exc:
            logger.warning("Could not prune old Excel backup %s: %s", old_path, exc)
