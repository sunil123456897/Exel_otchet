"""U12-B: Error presentation layer.

A thin mapping layer that turns raw exceptions into user-facing messages
without leaking internals. Every call site that previously did
``messagebox.showerror("Ошибка", str(e))`` should instead call
:func:`present_error`, which:

1. **Always logs the full traceback** via ``logging.exception(context)``
   so nothing is lost for debugging.
2. **Never shows ``str(exc)`` to the user** — exception ``__str__``
   frequently embeds absolute paths, hostnames, tokens or SQL fragments
   (an information-disclosure risk, and useless to a non-developer).
3. Maps a handful of well-known exception types to **human-readable**
   Russian messages and exposes only ``repr(exc)`` in the optional
   expandable detail section of a toast (``repr`` is far less likely to
   contain secrets than ``str``).
4. Falls back to ``messagebox.showerror`` when no ``ToastManager`` is
   available (e.g. very early startup), with the same sanitised message.

Scope note
----------
This module is deliberately a **utility function**, not a new exception
hierarchy. The remaining ``messagebox.showerror(..., str(e))`` call sites
(~16) are out of scope for this cycle and tracked as TODO below; they
will be migrated incrementally because bulk-replacing them in one shot
would balloon the diff and the regression surface.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from tkinter import messagebox
import tkinter as tk

if TYPE_CHECKING:  # pragma: no cover - typing only, no runtime import
    from core.ui.toast import ToastManager

logger = logging.getLogger(__name__)

# All known ``messagebox.showerror("Ошибка", str(e))`` call sites have
# been migrated. The remaining direct ``messagebox.showerror`` uses are:
#   - in gui_commands/_base.py, _consolidation.py, _rsch.py, _employee.py:
#     they pass a static Russian string literal (no exception leak);
#   - in present_error / present_validation_error themselves: that's the
#     final fallback when no ToastManager is wired.
# New code MUST use present_error / present_validation_error and never
# ``messagebox.showerror(..., str(e))`` directly.

# Mapping from a substring found in ``repr(exc)`` to a human-readable
# Russian message. ``repr`` is used for the match because ``str(exc)``
# may be empty for some exceptions (e.g. a bare ``PermissionError()``)
# while ``repr`` always includes the class name.
#
# Order matters: the first matching substring wins, so list more
# specific / higher-signal classes first.
_EXCEPTION_MESSAGES: tuple[tuple[str, str], ...] = (
    ("PermissionError", "Нет доступа к файлу"),
    ("FileNotFoundError", "Файл не найден"),
    ("JSONDecodeError", "Файл настроек повреждён"),
)

_DEFAULT_MESSAGE = "Внутренняя ошибка"


def _human_message(exc: Exception) -> str:
    """Return a human-readable message for a known exception class.

    Matches against ``repr(exc)`` (which always carries the class name)
    rather than ``str(exc)`` (which can be empty). Falls back to a
    generic message for anything unmapped.
    """
    text = repr(exc)
    for needle, message in _EXCEPTION_MESSAGES:
        if needle in text:
            return message
    return _DEFAULT_MESSAGE


def present_error(
    parent: tk.Misc,
    context: str,
    exc: Exception,
    *,
    toasts: Optional["ToastManager"] = None,
) -> None:
    """Present an exception to the user with sanitised messaging.

    Parameters
    ----------
    parent:
        The Tk widget to parent any fallback messagebox on. Ignored when
        ``toasts`` is provided (toasts anchor to their own root).
    context:
        Short human-readable description of *what* failed, e.g.
        ``"Не удалось загрузить алиасы"``. Shown verbatim to the user.
    exc:
        The exception that was raised. Its full traceback is logged; its
        ``str()`` is NEVER shown to the user. Only ``repr(exc)`` appears,
        and only inside the expandable detail section of a toast.
    toasts:
        Optional :class:`~core.ui.toast.ToastManager`. When provided the
        error is shown as an error-toast (with an expandable "Подробнее"
        section holding ``repr(exc)``). When ``None`` a
        ``messagebox.showerror`` is used instead — with the same
        sanitised message and no traceback exposed.
    """
    # 1. Always log the full traceback for debugging. ``logging.exception``
    #    captures the active exception via ``sys.exc_info()`` so this must
    #    be called while ``exc`` is still the current exception (i.e.
    #    inside the ``except`` block at the call site).
    logging.exception(context)

    # 2. Build the user-facing message. ``context`` + a pointer to the
    # log; never the raw exception text.
    user_message = f"{context}. Подробнее в логе."

    # 3. Detail section: class name only, NOT ``repr(exc)``.
    # ``repr`` was previously used because it is "safer than ``str``",
    # but that is a gradient, not a guarantee: ``repr(ValueError('token'))``
    # literally contains the token. The class name is the maximum we can
    # show without re-auditing every exception type for secret leakage.
    # The full repr is in the log for developers.
    detail = type(exc).__name__

    # 4. Surface via toast (preferred) or messagebox (fallback).
    if toasts is not None:
        try:
            toasts.error(
                "Ошибка",
                user_message,
                detail=detail,
                duration_ms=6000,
            )
            return
        except Exception:
            # If the toast pipeline itself is broken, fall through to the
            # messagebox so the user is never left without feedback.
            logger.warning("Toast presentation failed; falling back to messagebox", exc_info=True)

    try:
        messagebox.showerror("Ошибка", user_message, parent=parent)
    except Exception:
        # Last-resort: if even the messagebox is unreachable (e.g. parent
        # already destroyed), the error is already in the log — do not
        # mask the original problem with a second exception.
        logger.warning("messagebox.showerror failed in present_error", exc_info=True)


def present_validation_error(
    parent: tk.Misc,
    message: str,
    *,
    toasts: Optional["ToastManager"] = None,
) -> None:
    """Present a **known, validation-derived** message verbatim.

    Unlike :func:`present_error`, this is for cases where the caller has
    already produced a user-safe message — typically the ``str()`` of a
    ``ValueError`` raised from a known validation point (e.g.
    ``"Заказчики идентичны — алиас не нужен"``). The message is shown
    as-is, with the full traceback still going to the log so developers
    can trace where the validation fired.

    Use this instead of ``messagebox.showerror("Ошибка", str(e))`` ONLY
    when the exception is from a known, audited call site that raises
    with a human-readable Russian message and no PII.
    """
    logging.getLogger(__name__).info("validation error shown: %s", message)
    if toasts is not None:
        try:
            toasts.warning("Проверьте ввод", message, duration_ms=5000)
            return
        except Exception:
            logger.warning("Toast presentation failed; falling back to messagebox",
                           exc_info=True)
    try:
        messagebox.showerror("Ошибка", message, parent=parent)
    except Exception:
        logger.warning("messagebox.showerror failed in present_validation_error",
                       exc_info=True)
