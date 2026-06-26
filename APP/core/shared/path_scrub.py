"""Path-scrubbing and file-label helpers.

Pure text utilities with no Tk, DB, or filesystem dependencies. Lives
in ``core.shared`` so that both the domain layer (e.g.
``core.domain.data_loss_log``) and the infra layer (e.g.
``core.infra.utils_logging``) can import it without creating a
cross-layer dependency (TD-007).

``scrub_path`` redacts Windows user names and SMB server/share names
from a string so that log lines do not leak PII.

``safe_file_label`` produces a short, hash-suffixed label for a file
path — used in logs and progress callbacks to identify a file without
exposing the full path.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path, PureWindowsPath

WINDOWS_USER_RE = re.compile(r"C:\\Users\\[^\\]+", re.IGNORECASE)
SMB_RE = re.compile(r"\\\\[^\\]+\\[^\\]+")


def scrub_path(value: str) -> str:
    """Redact Windows user paths and SMB shares in ``value``."""
    value = WINDOWS_USER_RE.sub(r"C:\\Users\\<user>", str(value))
    return SMB_RE.sub(r"\\\\<server>\<share>", value)


def safe_file_label(path: str | Path) -> str:
    """Return ``"filename#hashprefix"`` for a path — short and PII-free."""
    raw = str(path)
    name = PureWindowsPath(raw).name or Path(raw).name or "<file>"
    digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:10]
    return f"{name}#{digest}"


__all__ = ["scrub_path", "safe_file_label"]
