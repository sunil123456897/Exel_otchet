"""Global operation state machine.

Single source of truth for "is any long-running operation in flight?".
Widgets subscribe via ``add_listener``; the command layer calls
``begin()``/``end()``/``request_cancel()``.

This is the foundation that fixes two user-visible bugs:
- double-clicking two different action buttons causing state corruption
- not knowing what is currently running or how long it will take
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)


class OperationType(str, Enum):
    NONE = ""
    REFRESH = "refresh"
    CONSOLIDATION_DAY = "consolidation_day"
    CONSOLIDATION_ALL = "consolidation_all"
    CONSOLIDATION_MONTH = "consolidation_month"
    RSCH_DAY = "rsch_day"
    RSCH_MONTH = "rsch_month"
    RECONCILIATION = "reconciliation"
    AUTO_RECONCILIATION = "auto_reconciliation"


OPERATION_LABELS: dict[OperationType, str] = {
    OperationType.NONE: "",
    OperationType.REFRESH: "Обновление статусов",
    OperationType.CONSOLIDATION_DAY: "Сборка за день",
    OperationType.CONSOLIDATION_ALL: "Сборка за все даты",
    OperationType.CONSOLIDATION_MONTH: "Сборка за период",
    OperationType.RSCH_DAY: "Сборка РСЧ",
    OperationType.RSCH_MONTH: "Сборка РСЧ за период",
    OperationType.RECONCILIATION: "Сверка отчётов",
    OperationType.AUTO_RECONCILIATION: "Автоматическая сверка",
}


@dataclass
class OperationSnapshot:
    current: OperationType
    cancelling: bool
    progress: float
    started_at: Optional[float]
    label: str
    current_file: str = ""  # FIX-009: file being processed, for status bar display


class OperationState:
    """Thread-safe singleton-like state machine for long-running operations.

    Listeners are notified after every state transition so widgets can
    re-render (button enable/disable, status bar update, toast).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current: OperationType = OperationType.NONE
        self._cancelling: bool = False
        self._cancel_event: threading.Event = threading.Event()
        self._progress: float = 0.0
        self._started_at: Optional[float] = None
        self._listeners: List[Callable[[OperationSnapshot], None]] = []
        self._current_file: str = ""  # FIX-009

    # --- read API --------------------------------------------------------

    def snapshot(self) -> OperationSnapshot:
        with self._lock:
            return OperationSnapshot(
                current=self._current,
                cancelling=self._cancelling,
                progress=self._progress,
                started_at=self._started_at,
                label=OPERATION_LABELS.get(self._current, ""),
                current_file=self._current_file,
            )

    @property
    def is_busy(self) -> bool:
        with self._lock:
            return self._current != OperationType.NONE

    @property
    def is_cancelling(self) -> bool:
        with self._lock:
            return self._cancelling

    @property
    def current(self) -> OperationType:
        with self._lock:
            return self._current

    @property
    def progress(self) -> float:
        with self._lock:
            return self._progress

    @property
    def started_at(self) -> Optional[float]:
        with self._lock:
            return self._started_at

    @property
    def cancel_event(self) -> threading.Event:
        return self._cancel_event

    # --- write API -------------------------------------------------------

    def begin(self, op: OperationType) -> bool:
        """Try to start an operation.

        Returns True if started; False if another operation is already running
        (in which case the caller should silently abort the new request).
        """
        with self._lock:
            if self._current != OperationType.NONE:
                logger.warning(
                    "Cannot start %s: %s is already running",
                    op.value,
                    self._current.value,
                )
                return False
            self._current = op
            self._cancelling = False
            self._cancel_event.clear()
            self._progress = 0.0
            self._started_at = time.monotonic()
        self._notify()
        return True

    def end(self) -> None:
        with self._lock:
            if self._current == OperationType.NONE and not self._cancelling:
                return
            self._current = OperationType.NONE
            self._cancelling = False
            self._cancel_event.clear()
            self._progress = 0.0
            self._started_at = None
            self._current_file = ""  # FIX-009: clear on end
        self._notify()

    def request_cancel(self) -> bool:
        with self._lock:
            if self._current == OperationType.NONE:
                return False
            self._cancelling = True
            self._cancel_event.set()
        self._notify()
        return True

    def set_progress(self, value: float) -> None:
        with self._lock:
            if self._current == OperationType.NONE:
                return
            self._progress = max(0.0, min(100.0, value))
        self._notify()

    def set_current_file(self, name: str) -> None:
        """FIX-009: Set the file currently being processed.

        Called from the worker thread so the status bar can show
        ``"Обработка: ivan_petrov.xlsx (3/5)"`` instead of just a
        bare percentage. Thread-safe via the same lock as set_progress.
        """
        with self._lock:
            if self._current == OperationType.NONE:
                return
            self._current_file = name
        self._notify()

    # --- listener API ----------------------------------------------------

    def add_listener(self, fn: Callable[[OperationSnapshot], None]) -> None:
        with self._lock:
            self._listeners.append(fn)

    def remove_listener(self, fn: Callable[[OperationSnapshot], None]) -> None:
        with self._lock:
            try:
                self._listeners.remove(fn)
            except ValueError:
                pass

    def _notify(self) -> None:
        snap = self.snapshot()
        for fn in list(self._listeners):
            try:
                fn(snap)
            except Exception:
                logger.exception("operation_state listener raised")
