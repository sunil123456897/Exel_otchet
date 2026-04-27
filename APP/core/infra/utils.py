import os
import subprocess
import platform
import hashlib
import shutil
import tempfile
from types import SimpleNamespace
from pathlib import Path


def open_path(path: str):
    if platform.system() == "Windows":
        os.startfile(path)
    elif platform.system() == "Darwin":
        subprocess.run(["open", path])
    else:
        subprocess.run(["xdg-open", path])


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
    is_network = (
        network_path.startswith("\\\\") or network_path[0].upper() in drive_letters
    )
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
                return network_path, None
    else:
        try:
            stat = os.stat(network_path)
        except OSError:
            return network_path, None

    key = hashlib.md5(
        f"{network_path}_{stat.st_mtime}_{stat.st_size}".encode()
    ).hexdigest()
    suffix = Path(network_path).suffix
    local_path = _CACHE_DIR / f"{key}{suffix}"

    if local_path.exists():
        # Validate cached copy against current remote metadata
        try:
            cached_stat = os.stat(local_path)
            if cached_stat.st_size != stat.st_size or cached_stat.st_mtime < stat.st_mtime:
                # Size or mtime mismatch — stale cache, remove it
                os.remove(local_path)
            else:
                return str(local_path), None
        except OSError:
            pass

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
        except Exception:
            return network_path, None
