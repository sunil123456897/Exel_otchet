"""Cancellation primitives shared by core orchestration, services, and the UI.

Lives in ``core.app`` (UI-free) so that:

* ``core.app_controller`` can build/emit a cancellation marker WITHOUT
  importing ``core.ui``. Previously ``_cancel_message`` did a lazy
  ``from core.ui.gui_commands._base import CancelledByUser``, and since
  ``_base`` imports ``tkinter.messagebox``, the headless controller
  transitively depended on tkinter (silently degrading when the import
  failed).
* ``core.services.*`` can check for cancellation WITHOUT importing
  ``core.app_controller``. They used to do a lazy
  ``from core.app_controller import _cancel_message, _is_cancelled``, which
  created a hidden import cycle ``services -> app_controller`` masked only
  by the laziness. With this module the dependency graph is acyclic:
  ``ui -> {app, services, view_models, infra}``, ``services -> {app, infra}``,
  ``app -> infra``.

The marker subclasses ``str`` so it flows unchanged through every callback
that expects a string message; detection is type-based (``isinstance``) with
a substring fallback for legacy plain-string sites.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, List, Optional

from core.app.partial import format_partial_note, mark_partial
from core.infra.utils import cleanup_local_copy_cache


class CancelledByUser(str):
    """Marker signalling a user-initiated cancellation.

    Subclasses ``str`` (rather than ``Exception``) so it flows unchanged
    through every existing callback that expects a string message —
    ``logging.info("%s", msg)``, ``messagebox.showerror(..., msg)``,
    the toast manager, and the duplicate substring check in
    ``gui_master._on_*_complete``. Detection uses
    ``isinstance(msg, CancelledByUser)`` rather than substring matching
    on the Russian phrase, so a reworded message or a localized UI no
    longer breaks the cancelled-vs-error branch.

    The cancellation site (:func:`cancel_message`) constructs this marker
    instead of a bare ``str``; both paths produce identical string output,
    but only the marker is reliably detectable.
    """

    __slots__ = ()


def is_cancelled_message(msg: object) -> bool:
    """True if ``msg`` signals a 'cancelled by user' completion.

    Detection is type-based (``isinstance``) instead of Russian substring
    matching so the cancelled-vs-error branch survives a reworded message or
    a localized UI. The legacy substring fallback covers any cancellation
    site that still passes a plain ``str`` (e.g. ``gui_master`` re-routes
    completions through its own path).
    """
    if isinstance(msg, CancelledByUser):
        return True
    return "отменена пользователем" in str(msg or "").lower()


def is_cancelled(cancel_event: Optional[threading.Event]) -> bool:
    """Return True when the user requested cancellation.

    Helper for the threaded run_* entry points. The cancel_event is set by
    the GUI when the user clicks the Cancel button on the OperationStatusBar;
    the helper exists so call sites stay short and the check stays cheap (no
    allocation per iteration).
    """
    return cancel_event is not None and cancel_event.is_set()


def cancel_message(
    on_complete: Callable[[bool, str, Optional[Path]], None],
    *output_paths: Optional[Path],
) -> None:
    """Wrap the standard cancel completion in a partial-files note.

    All run_* methods funnel their cancel branch through this helper so the
    user gets a consistent message and the on-disk partial files are renamed
    (not deleted) before the GUI shows the toast. Network cache files are
    scrubbed in the same call.

    Pass each candidate output path (file or directory) that the operation
    may have started writing; the helper marks every existing ``*.xlsx``
    under those paths as ``.partial`` and appends a short note to the
    user-facing message. Completes via a :class:`CancelledByUser` marker so
    downstream handlers can detect cancellation by type.
    """
    cleanup_local_copy_cache(max_age_days=0, min_delete_age_seconds=0)
    partials: List[Path] = []
    for path in output_paths:
        partials.extend(mark_partial(path))
    note = format_partial_note(partials)
    message = "Операция отменена пользователем." + note
    on_complete(False, CancelledByUser(message), None)


__all__ = [
    "CancelledByUser",
    "is_cancelled_message",
    "is_cancelled",
    "cancel_message",
]
