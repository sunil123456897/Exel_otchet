"""Data loss audit logger.

Records every place where user data is silently dropped or coerced so that
operators can spot patterns (broken template, wrong column name, network glitch).
"""
import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from core.infra.utils_logging import scrub_path

_LOCK = threading.Lock()
_LOGGER_NAME = "data_loss"

_initialised = False

# Redact obvious monetary amounts (e.g. "1234.56", "99,50") before writing
# to disk so the log file does not accumulate financial PII in plaintext.
# Require 3+ digits before the separator to avoid false positives on dates
# (e.g. "12.05.2026"), versions ("v5.50"), or file names ("file_12.05.xlsx").
_AMOUNT_RE = re.compile(r"\d{3,}[.,]\d{2}")


def _project_root() -> Path:
    # Use CWD during pytest runs so that monkeypatch.chdir in tests works correctly.
    # Otherwise, use the package root (APP/) derived from this file's location to prevent
    # log files from being created in system directories (e.g. C:\Windows\System32) when
    # launched via Windows shortcuts.
    if "PYTEST_CURRENT_TEST" in os.environ:
        return Path(os.getcwd())
    return Path(__file__).resolve().parents[2]


def _get_logger() -> logging.Logger:
    global _initialised
    log = logging.getLogger(_LOGGER_NAME)
    if _initialised:
        return log
    log.setLevel(logging.INFO)
    log.propagate = False
    log_dir = _project_root() / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "data_loss.log"
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(
            logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%dT%H:%M:%S")
        )
        log.addHandler(fh)
        # Restrict to owner-only — the log captures Excel-derived values
        # (paths, amounts) that must not be world-readable on shared PCs.
        try:
            os.chmod(log_path, 0o600)
        except OSError as chmod_err:
            logging.warning(
                "Could not restrict %s permissions: %s", log_path, chmod_err
            )
    except OSError as e:
        logging.warning("Could not create data-loss log directory/file: %s", e)
    _initialised = True
    return log


def record_loss(
    *,
    source: str,
    kind: str,
    reason: str,
    row_index: int | None = None,
    sheet: str | None = None,
    field: str | None = None,
    original_value=None,
) -> None:
    """Append a structured data-loss event to logs/data_loss.log.

    Args:
        source: file path or pipeline stage identifier.
        kind: short category (e.g. ``"trash_filter"``, ``"numeric_coercion"``).
        reason: human-readable explanation.
        row_index: 1-based row number in the source sheet, if known.
        sheet: sheet name, if known.
        field: field/key being dropped, if known.
        original_value: the value that was lost (will be coerced to str).
    """
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "source": source,
        "kind": kind,
        "reason": reason,
        "row": row_index,
        "sheet": sheet,
        "field": field,
        "value": str(original_value) if original_value is not None else None,
    }
    try:
        line = json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        line = json.dumps({k: str(v) for k, v in payload.items()}, ensure_ascii=False)
    # Defense-in-depth: redact Windows user paths / UNC shares and obvious
    # monetary amounts before the line hits disk. Does NOT change the JSON
    # structure or the kind/reason fields — only PII-bearing substrings.
    line = _AMOUNT_RE.sub("[AMOUNT]", scrub_path(line))
    log = _get_logger()
    with _LOCK:
        log.info(line)


def reset_for_testing() -> None:
    """Drop cached handler so the next call re-binds to the current CWD.

    Tests that change the working directory (e.g. via ``monkeypatch.chdir``)
    call this to make the logger pick up the new project root.
    """
    global _initialised
    log = logging.getLogger(_LOGGER_NAME)
    for handler in list(log.handlers):
        try:
            handler.close()
        except Exception:
            pass
        log.removeHandler(handler)
    _initialised = False
