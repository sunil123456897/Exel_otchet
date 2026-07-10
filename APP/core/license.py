"""License checker — protects the app when deployed without source.

Distinguishes two deployment modes by the presence of source files:

- **Development** (``.py`` files exist): the checker is a no-op. The
  developer runs the app directly from source; no expiry is enforced.
  This is detected by checking for ``core/ui/ui_sidebar.py`` — a file
  that always exists in a source checkout but is removed by the
  production build (see ``tools/update_from_github.ps1`` →
  ``Compile-And-Protect``).

- **Production** (``.py`` files removed, only ``.pyc`` shipped): the
  checker reads an obfuscated expiry date from ``APP/.license`` and
  blocks the app once it passes. A rollback-detection trail is kept in
  ``APP/.last_run`` — if the system clock is moved backwards past the
  last-recorded run, the app blocks too.

The obfuscation is a simple XOR + base64. It is NOT cryptographic
security — the real protection is that ``.py`` files are deleted in
production, so the attacker only has ``.pyc`` bytecode. This just stops
a casual edit of ``.license`` in notepad.
"""
from __future__ import annotations

import base64
import datetime as _dt
import logging
from pathlib import Path
from typing import Optional

_log = logging.getLogger("license")

# Marker file whose presence signals "running from source" (development).
# In production this file is removed by the update script.
_DEV_MARKER = Path(__file__).resolve().parent / "ui" / "ui_sidebar.py"

_LICENSE_FILE = Path(__file__).resolve().parents[1] / ".license"
_LASTRUN_FILE = Path(__file__).resolve().parents[1] / ".last_run"

# Obfuscation key (not crypto — just prevents casual notepad editing).
_KEY = b"Master-Report-Consolidator-v5.6"


def _xor(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _encrypt(text: str) -> str:
    return base64.b64encode(_xor(text.encode("utf-8"), _KEY)).decode("ascii")


def _decrypt(text: str) -> str:
    return _xor(base64.b64decode(text), _KEY).decode("utf-8")


def write_license(expiry: _dt.datetime) -> None:
    """Create/overwrite the ``.license`` file with an expiry timestamp.

    Called by the update script after a production build. ``expiry`` is
    typically ``now + 30 days``.
    """
    payload = expiry.strftime("%Y-%m-%d")
    _LICENSE_FILE.write_text(_encrypt(payload), encoding="utf-8")
    _log.info("License written, expires %s", payload)


def _read_expiry() -> Optional[_dt.date]:
    if not _LICENSE_FILE.exists():
        return None
    try:
        payload = _decrypt(_LICENSE_FILE.read_text(encoding="utf-8").strip())
        return _dt.datetime.strptime(payload, "%Y-%m-%d").date()
    except Exception:
        _log.warning("License file corrupt or tampered")
        return None


def _read_last_run() -> Optional[_dt.date]:
    if not _LASTRUN_FILE.exists():
        return None
    try:
        payload = _decrypt(_LASTRUN_FILE.read_text(encoding="utf-8").strip())
        return _dt.datetime.strptime(payload, "%Y-%m-%d").date()
    except Exception:
        return None


def _write_last_run(today: _dt.date) -> None:
    _LASTRUN_FILE.write_text(_encrypt(today.strftime("%Y-%m-%d")), encoding="utf-8")


def is_development_mode() -> bool:
    """Return True if running from source (``.py`` files present).

    In this mode all license checks are skipped — the developer's own
    machine always has the marker file.
    """
    return _DEV_MARKER.exists()


def check_license() -> bool:
    """Return True if the app should be view-only (licence expired).

    In development mode this is always False. In production it checks:
    1. The ``.license`` expiry date — if today is past it, block.
    2. The ``.last_run`` trail — if today is BEFORE the last recorded
       run, the clock was rolled back → block.
    Then records today's date as the new last-run.
    """
    if is_development_mode():
        return False

    today = _dt.date.today()
    last_run = _read_last_run()
    expiry = _read_expiry()

    # Rollback detection: if the system clock moved backwards past our
    # last-recorded run, treat it as tampering.
    if last_run is not None and today < last_run:
        _log.warning("Clock rollback detected (today=%s < last_run=%s)", today, last_run)
        _write_last_run(today)
        return True

    # Normal expiry check.
    if expiry is None:
        # No .license file in production = treat as expired (someone
        # deleted it to bypass the check).
        _log.warning("No .license file in production mode")
        _write_last_run(today)
        return True
    expired = today > expiry
    if expired:
        _log.warning("License expired (today=%s, expiry=%s)", today, expiry)

    # Always update the trail so a rollback is caught next time.
    _write_last_run(today)
    return expired
