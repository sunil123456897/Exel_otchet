import os
import subprocess
import platform
import hashlib
import logging
import shutil
import tempfile
import threading
import time
from types import SimpleNamespace
from pathlib import Path


def open_path(path: str):
    if platform.system() == "Windows":
        os.startfile(path)
    elif platform.system() == "Darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)


def atomic_save_workbook(wb, output_path: Path) -> None:
    """Save an openpyxl workbook to output_path atomically.

    Writes to a sibling temp file then os.replace's it over the target, so a
    crash or window-close mid-save never leaves a truncated/half-written
    workbook. The backup_existing_excel_output call (done by the caller)
    protects the previous version; this guards the live file.

    Mirrors the proven pattern in export_writer._save_workbook_inner, but as
    a free function so rsch/ and reconciliation/ can share one implementation.
    """
    output_path = Path(output_path)
    tmp = str(output_path) + ".tmp"
    # Long Windows paths need the \\?\ prefix.
    if os.name == "nt" and len(tmp) > 250:
        tmp = "\\\\?\\" + tmp
        target = "\\\\?\\" + str(output_path)
    else:
        target = str(output_path)
    try:
        wb.save(tmp)
        os.replace(tmp, target)
    except Exception:
        # Clean up the partial temp file so a retry does not collide.
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        raise


def is_file_writable(path: str) -> bool:
    p = Path(path)
    if not p.exists():
        return True
    try:
        with open(str(p), "r+b"):
            pass
        return True
    except (IOError, PermissionError, OSError):
        return False


_CACHE_DIR = Path(tempfile.gettempdir()) / "master_report_cache"
_CACHE_CLEANUP_LOCK = threading.Lock()
_CACHE_CLEANUP_DONE = False
_CACHE_COPY_LOCK = threading.Lock()  # threading.Lock is sufficient for ThreadPoolExecutor; multiprocessing.Lock was overkill and could cause pickle errors on Windows
_CACHE_MIN_DELETE_AGE_SECONDS = 30 * 60
_DIGEST_CHUNK_SIZE = 1024 * 1024


def _is_configured_drive_path(path: str, drive_letters: tuple) -> bool:
    if len(path) < 2 or path[1] != ":":
        return False

    configured_drives = {
        str(letter).strip().upper().rstrip(":\\/")
        for letter in drive_letters
        if str(letter).strip()
    }
    return path[0].upper() in configured_drives


def _is_network_path(path: str, drive_letters: tuple) -> bool:
    return path.startswith("\\\\") or _is_configured_drive_path(path, drive_letters)


def file_content_fingerprint(path: str | Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(_DIGEST_CHUNK_SIZE), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _cache_copy_is_fresh(local_path: Path, remote_path: str, remote_stat) -> bool:
    try:
        cached_stat = os.stat(local_path)
    except OSError:
        return False

    remote_mtime_ns = getattr(
        remote_stat, "st_mtime_ns", int(float(remote_stat.st_mtime) * 1_000_000_000)
    )
    cached_mtime_ns = getattr(
        cached_stat, "st_mtime_ns", int(float(cached_stat.st_mtime) * 1_000_000_000)
    )
    if cached_stat.st_size != remote_stat.st_size or cached_mtime_ns < remote_mtime_ns:
        return False
    return True


def cleanup_local_copy_cache(
    max_age_days: int = 14,
    max_total_mb: int = 512,
    min_delete_age_seconds: int = _CACHE_MIN_DELETE_AGE_SECONDS,
) -> None:
    """Remove old local network-file cache entries without touching fresh files."""
    try:
        if not _CACHE_DIR.exists():
            return

        now = time.time()
        max_age_seconds = max(0, max_age_days) * 24 * 60 * 60
        max_total_bytes = max(0, max_total_mb) * 1024 * 1024
        entries: list[tuple[float, int, Path]] = []

        for entry in _CACHE_DIR.iterdir():
            try:
                if entry.is_symlink() or not entry.is_file():
                    continue
                stat = entry.stat()
            except OSError:
                continue

            age = now - stat.st_mtime
            if age < min_delete_age_seconds:
                entries.append((stat.st_mtime, stat.st_size, entry))
                continue
            if max_age_seconds and age > max_age_seconds:
                entry.unlink(missing_ok=True)
                continue
            entries.append((stat.st_mtime, stat.st_size, entry))

        if max_total_bytes <= 0:
            return

        total_size = sum(size for _mtime, size, _entry in entries)
        for mtime, size, entry in sorted(entries, key=lambda item: item[0]):
            if total_size <= max_total_bytes:
                break
            if now - mtime < min_delete_age_seconds:
                continue
            try:
                entry.unlink(missing_ok=True)
                total_size -= size
            except OSError:
                logging.debug("Could not remove cache file %s", entry, exc_info=True)
    except OSError:
        logging.debug("Could not cleanup local copy cache %s", _CACHE_DIR, exc_info=True)


def _maybe_cleanup_local_copy_cache() -> None:
    global _CACHE_CLEANUP_DONE
    if _CACHE_CLEANUP_DONE:
        return
    with _CACHE_CLEANUP_LOCK:
        if _CACHE_CLEANUP_DONE:
            return
        cleanup_local_copy_cache()
        _CACHE_CLEANUP_DONE = True


def get_local_copy(
    network_path: str,
    drive_letters: tuple = ("Q", "Z"),
    remote_mtime: float | None = None,
    remote_size: int | None = None,
) -> tuple:
    """Get a local cached copy of a network file.

    Cache is invalidated when mtime or size changes on the remote file.
    Returns (local_path, temp_file_to_cleanup_or_None).
    """
    if not network_path:
        return network_path, None
    is_network = _is_network_path(network_path, drive_letters)
    if not is_network:
        return network_path, None

    if remote_mtime is not None and remote_size is not None:
        try:
            stat = SimpleNamespace(st_mtime=float(remote_mtime), st_size=int(remote_size))
            if stat.st_size < 0:
                raise ValueError("remote_size must be non-negative")
        except (TypeError, ValueError):
            try:
                stat = os.stat(network_path)
            except OSError:
                stat = SimpleNamespace(st_mtime=0, st_size=0)
    else:
        try:
            stat = os.stat(network_path)
        except OSError:
            stat = SimpleNamespace(st_mtime=0, st_size=0)


    stat_mtime_ns = getattr(stat, "st_mtime_ns", int(float(stat.st_mtime) * 1_000_000_000))
    key = hashlib.sha256(
        f"{network_path}_{stat_mtime_ns}_{stat.st_size}".encode()
    ).hexdigest()[:32]
    suffix = Path(network_path).suffix
    local_path = _CACHE_DIR / f"{key}{suffix}"

    with _CACHE_COPY_LOCK:
        if local_path.exists():
            if _cache_copy_is_fresh(local_path, network_path, stat):
                return str(local_path), None
            try:
                os.remove(local_path)
            except OSError:
                pass

        _maybe_cleanup_local_copy_cache()
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(network_path, str(local_path))
            return str(local_path), None
        except Exception:
            fd, temp_file = tempfile.mkstemp(suffix=suffix)
            os.close(fd)
            try:
                shutil.copy2(network_path, temp_file)
                return temp_file, temp_file
            except Exception as exc:
                raise IOError(f"Network copy failed for {network_path} — no local fallback available") from exc


def path_exists_with_timeout(path: str | Path, timeout: float = 1.0) -> bool:
    """Check if a path exists without blocking long on slow or offline network paths."""
    p = Path(path)
    try:
        drive = p.drive
        if drive:
            import os
            if hasattr(os, "listdrives"):
                available_drives = {d.upper().rstrip(":\\") for d in os.listdrives()}
                if drive.upper().rstrip(":\\") not in available_drives:
                    return False
    except Exception:
        pass

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(p.exists)
        try:
            return future.result(timeout=timeout)
        except (concurrent.futures.TimeoutError, Exception):
            return False
