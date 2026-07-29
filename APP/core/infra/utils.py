import os
import subprocess
import platform
import hashlib
import logging
import shutil
import tempfile
import threading
import time
import concurrent.futures
from types import SimpleNamespace
from pathlib import Path
from typing import Any, Callable


# Таймауты на блокирующие сетевые операции внутри get_local_copy.
# Симптом бага «РСЧ за период грузит грузит и не выгружается»: зависший
# SMB-сервер держит os.stat / shutil.copy2 минутами. Эти значения дают
# потоку разблокироваться и сообщить понятную ошибку вместо бесконечного
# ожидания. Зависший диск обычно не отвечает вовсе, поэтому даже 3 c
# хватает, чтобы отличить «медленно» от «умерло».
NETWORK_STAT_TIMEOUT_SECONDS = 3.0
NETWORK_COPY_TIMEOUT_SECONDS = 30.0

# Per-process counter + lock for unique atomic-save temp names (anti-TOCTOU:
# two concurrent saves of the same target must not share a .tmp name).
_TEMP_LOCK = threading.Lock()
_TEMP_COUNTER = 0


def _run_io_with_timeout(fn: Callable[..., Any], *args: Any, timeout: float) -> Any:
    """Run a blocking I/O callable with a wall-clock timeout.

    Uses a throwaway thread. On timeout the worker thread is NOT killed
    (Python cannot safely kill threads) and is left to die with the
    process; the *caller* is unblocked — which is what matters so the UI
    thread does not freeze on a hung network drive ("грузит грузит и не
    выгружается").

    NB: deliberately NOT using ``with ThreadPoolExecutor(...)`` because
    its ``__exit__`` calls ``shutdown(wait=True)`` and would re-block on
    the very hung worker we are trying to escape. ``shutdown(wait=False)``
    returns immediately and abandons the worker.
    """
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(fn, *args)
    try:
        return future.result(timeout=timeout)
    finally:
        executor.shutdown(wait=False)


def open_path(path: str) -> None:
    if platform.system() == "Windows":
        os.startfile(path)
    elif platform.system() == "Darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)


def _unique_temp_path(output_path: Path) -> tuple[str, str]:
    """Build a sibling temp path unique per process+thread for *output_path*.

    Returns ``(tmp, target)`` with the Windows ``\\\\?\\`` long-path prefix
    applied when the resolved path exceeds 250 chars. The temp name embeds
    pid + thread id + a per-process counter so two concurrent atomic saves of
    the SAME target (e.g. a background discovery autosave racing a manual
    config edit) cannot collide on a shared ``.tmp`` name and tear each
    other's write — the TOCTOU that a fixed ``path + ".tmp"`` introduced.
    """
    global _TEMP_COUNTER
    with _TEMP_LOCK:
        _TEMP_COUNTER += 1
        seq = _TEMP_COUNTER
    suffix = f".{os.getpid()}.{threading.get_ident()}.{seq}.tmp"
    tmp = str(output_path) + suffix
    if os.name == "nt" and len(tmp) > 250:
        tmp = "\\\\?\\" + tmp
        target = "\\\\?\\" + str(output_path)
    else:
        target = str(output_path)
    return tmp, target


def atomic_save_workbook(wb: Any, output_path: Path) -> None:
    """Save an openpyxl workbook to output_path atomically.

    Writes to a sibling temp file then os.replace's it over the target, so a
    crash or window-close mid-save never leaves a truncated/half-written
    workbook. The backup_existing_excel_output call (done by the caller)
    protects the previous version; this guards the live file.

    Mirrors the proven pattern in export_writer._save_workbook_inner, but as
    a free function so rsch/ and reconciliation/ can share one implementation.
    """
    output_path = Path(output_path)
    tmp, target = _unique_temp_path(output_path)
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


def atomic_save_yaml(
    path: str | Path, data: Any, yaml_dumper: Any, *, encoding: str = "utf-8"
) -> None:
    """Write YAML data to ``path`` atomically (temp + ``os.replace``).

    ``save_config`` / ``_save_employees`` previously did ``open("w")`` directly
    on the live file, which truncates *before* the new content is written. A
    crash, power loss, or disk-full between truncate and the completed
    ``yaml.dump`` left ``config.yaml`` / ``employees.yaml`` empty or
    half-written — destroying the operator's employee→file mapping and forcing
    a manual re-map of every network Excel file. ``os.replace`` is atomic on
    Windows (same volume), so the target file is only ever the old version or
    the complete new version, never an intermediate state.

    Mirrors ``atomic_save_workbook`` / the ``current.json`` writer in
    ``updater_model``. ``yaml_dumper`` is a ``ruamel.yaml.YAML`` instance;
    ``utils`` stays free of a hard ruamel import.
    """
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp, target = _unique_temp_path(output_path)
    try:
        with open(tmp, "w", encoding=encoding) as f:
            yaml_dumper.dump(data, f)
        os.replace(tmp, target)
    except Exception:
        # Remove the partial temp so a retry does not collide; the previous
        # good file is left untouched because we never touched it.
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        raise


_CACHE_DIR = Path(tempfile.gettempdir()) / "master_report_cache"
_CACHE_CLEANUP_LOCK = threading.Lock()
_CACHE_CLEANUP_DONE = False
_CACHE_COPY_LOCK = threading.Lock()  # threading.Lock is sufficient for ThreadPoolExecutor; multiprocessing.Lock was overkill and could cause pickle errors on Windows
_CACHE_MIN_DELETE_AGE_SECONDS = 30 * 60


def _is_configured_drive_path(path: str, drive_letters: tuple[str, ...]) -> bool:
    if len(path) < 2 or path[1] != ":":
        return False

    configured_drives = {
        str(letter).strip().upper().rstrip(":\\/")
        for letter in drive_letters
        if str(letter).strip()
    }
    return path[0].upper() in configured_drives


def _is_network_path(path: str, drive_letters: tuple[str, ...]) -> bool:
    return path.startswith("\\\\") or _is_configured_drive_path(path, drive_letters)


def _cache_copy_is_fresh(local_path: Path, remote_path: str, remote_stat: Any) -> bool:
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
    drive_letters: tuple[str, ...] = ("Q", "Z"),
    remote_mtime: float | None = None,
    remote_size: int | None = None,
) -> tuple[str, str | None]:
    """Get a local cached copy of a network file.

    Cache is invalidated when mtime or size changes on the remote file.
    Returns (local_path, temp_file_to_cleanup_or_None).
    """
    if not network_path:
        return network_path, None
    is_network = _is_network_path(network_path, drive_letters)
    if not is_network:
        return network_path, None

    # stat с таймаутом. Если сетевой диск завис («грузит грузит»), os.stat
    # блокирует поток минутами; таймаут превращает это в понятную ошибку.
    # Важно: если stat не прошёл по таймауту — путь недоступен, и пытаться
    # делать copy2 на тот же путь бессмысленно (он тоже зависнет).
    stat_unreachable = False
    if remote_mtime is not None and remote_size is not None:
        try:
            stat = SimpleNamespace(st_mtime=float(remote_mtime), st_size=int(remote_size))
            if stat.st_size < 0:
                raise ValueError("remote_size must be non-negative")
        except (TypeError, ValueError):
            try:
                stat = _run_io_with_timeout(
                    os.stat, network_path, timeout=NETWORK_STAT_TIMEOUT_SECONDS
                )
            except concurrent.futures.TimeoutError:
                stat_unreachable = True
                stat = SimpleNamespace(st_mtime=0, st_size=0)
            except OSError:
                stat = SimpleNamespace(st_mtime=0, st_size=0)
    else:
        try:
            stat = _run_io_with_timeout(
                os.stat, network_path, timeout=NETWORK_STAT_TIMEOUT_SECONDS
            )
        except concurrent.futures.TimeoutError:
            stat_unreachable = True
            stat = SimpleNamespace(st_mtime=0, st_size=0)
        except OSError:
            stat = SimpleNamespace(st_mtime=0, st_size=0)

    if stat_unreachable:
        raise OSError(
            f"Сетевой путь не отвечает за {NETWORK_STAT_TIMEOUT_SECONDS} c: "
            f"{network_path}. Проверьте подключение диска."
        )


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
            _run_io_with_timeout(
                shutil.copy2,
                network_path,
                str(local_path),
                timeout=NETWORK_COPY_TIMEOUT_SECONDS,
            )
            return str(local_path), None
        except (Exception, concurrent.futures.TimeoutError):
            fd, temp_file = tempfile.mkstemp(suffix=suffix)
            os.close(fd)
            try:
                _run_io_with_timeout(
                    shutil.copy2,
                    network_path,
                    temp_file,
                    timeout=NETWORK_COPY_TIMEOUT_SECONDS,
                )
                return temp_file, temp_file
            except (Exception, concurrent.futures.TimeoutError) as exc:
                raise IOError(
                    f"Network copy failed for {network_path} — no local fallback available"
                ) from exc


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
