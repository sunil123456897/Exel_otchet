"""Shared context and helpers for the GuiCommands modules.

The dispatching ``GuiCommands`` class is split by feature into
``_employee``, ``_consolidation``, ``_rsch`` and ``_reconciliation``;
every feature module needs the same handful of collaborators
(``root``, ``operation_state``, ``toasts``…). Those collaborators are
collected in a single ``CommandContext`` dataclass so each module can
ask for ``self.ctx`` instead of repeating the same constructor
signature.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox
from typing import Callable, Optional

from core.infra import open_path
from core.ui.operation_state import OperationState
from core.ui.toast import ToastLevel, ToastManager


@dataclass
class CommandContext:
    """Bag of shared collaborators for every GuiCommands feature module.

    Held as a single attribute (``self.ctx``) on the ``GuiCommands``
    class. The fields are exactly the ones the original monolith took
    in its constructor; adding a new one here is the only place that
    needs to change.
    """

    root: object
    config_controller: object
    app_controller: object
    employee_vm: object
    consolidation_vm: object
    sidebar: object
    employee_table: object
    stats_panel: object
    dashboard_tabs: object
    operation_state: OperationState
    toasts: Optional[ToastManager] = None

    def post(self, fn: Callable[[], None]) -> None:
        """Schedule ``fn`` to run on the Tk main loop.

        Every async completion handler in the project wraps its work
        in ``self.root.after(0, fin)``; the helper saves the
        boilerplate and reads better.
        """
        self.root.after(0, fn)


def _is_cancelled_message(msg: str) -> bool:
    """True if ``msg`` looks like a 'cancelled by user' message.

    The controller's task() functions return a fixed phrase when the
    user pressed Cancel. The completion handlers use that phrase as a
    heuristic to choose between a warning toast (cancelled) and an
    error toast (genuine failure).
    """
    return "отменена пользователем" in (msg or "").lower()


def finish(
    ctx: CommandContext,
    ok: bool,
    msg: str,
    path: Optional[Path],
    label: str,
    ask_open_text: Optional[str] = None,
    record_result: Optional[Callable[[str, bool, str, Optional[Path]], None]] = None,
    success_duration_ms: int = 4000,
    error_duration_ms: int = 6000,
) -> None:
    """Shared completion handler for the build/reconciliation commands.

    The original monolith had four near-identical 20-line
    ``_on_*_complete`` methods; they collapsed to one helper plus a
    one-line caller. The behaviour is:

    * ``ok``         → success toast + optional 'open file?' prompt
    * cancelled      → warning toast (NOT an error)
    * error          → error toast (or ``messagebox.showerror`` when
                       no toast manager is available)
    """
    cancelled = (not ok) and _is_cancelled_message(msg)
    if ok:
        logging.info("Успешно (%s): %s", label, msg)
        if record_result is not None:
            record_result(label, True, msg, path)
        if path and ask_open_text and messagebox.askyesno("Успех", ask_open_text):
            open_path(str(path))
        if ctx.toasts:
            ctx.toasts.show(ToastLevel.SUCCESS, label, msg, success_duration_ms)
        return

    if cancelled:
        logging.info("Отменено (%s): %s", label, msg)
        if record_result is not None:
            record_result(label, False, msg, path)
        if ctx.toasts:
            ctx.toasts.show(ToastLevel.WARNING, f"{label}: отменено", msg, success_duration_ms)
        return

    logging.error("Ошибка (%s): %s", label, msg)
    if record_result is not None:
        record_result(label, ok, msg, path)
    if ctx.toasts:
        ctx.toasts.show(ToastLevel.ERROR, f"{label}: ошибка", msg, error_duration_ms)
    else:
        messagebox.showerror("Ошибка", msg)


__all__ = ["CommandContext", "finish"]
