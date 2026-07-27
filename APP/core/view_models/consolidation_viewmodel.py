"""Consolidation ViewModel — состояние и логика консолидации."""

import threading
from typing import Any, Callable
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Signature of the worker passed to ``_execute``: it receives an
# ``(on_progress, on_complete)`` pair. Giving the lambdas in ``run_*`` a
# concrete expected type keeps mypy from failing to infer their parameter
# types (a bare ``Any`` target would trigger "Cannot infer type of lambda").
_ActionFn = Callable[
    [Callable[[float], None], Callable[[bool, str, Path | None], None]], None
]


class ConsolidationViewModel:
    def __init__(self, app_controller: Any = None, operation_state: Any = None) -> None:
        self._app_controller = app_controller
        self._operation_state = operation_state
        self._lock = threading.Lock()
        self._is_running = False
        self._progress = 0.0
        self._on_progress: Callable[[float], None] | None = None
        self._on_complete: Callable[[bool, str, Path | None], None] | None = None
        self._on_current_file: Callable[[str, int, int], None] | None = None  # FIX-009

    def set_callbacks(
        self,
        on_progress: Callable[[float], None],
        on_complete: Callable[[bool, str, Path | None], None],
        on_current_file: Callable[[str, int, int], None] | None = None,
    ) -> None:
        self._on_progress = on_progress
        self._on_complete = on_complete
        self._on_current_file = on_current_file

    def _execute(self, action_fn: _ActionFn) -> None:
        with self._lock:
            if self._is_running:
                return
            self._is_running = True
            self._progress = 0.0

        try:
            def on_progress(p: float) -> None:
                with self._lock:
                    self._progress = p
                if self._on_progress:
                    self._on_progress(p)

            def on_complete(ok: bool, msg: str, path: Path | None) -> None:
                with self._lock:
                    self._is_running = False
                    self._progress = 100.0 if ok else self._progress
                if self._on_complete:
                    self._on_complete(ok, msg, path)

            action_fn(on_progress, on_complete)
        except Exception:
            with self._lock:
                self._is_running = False
            if self._operation_state is not None:
                try:
                    self._operation_state.end()
                except Exception:
                    logger.exception("operation_state.end() failed in VM _execute")
            raise

    def can_run_single_date(self, missing_count: int) -> bool:
        return missing_count == 0

    def run_consolidation(
        self, app_controller: Any = None, selected_date: datetime | None = None, curator: Any = None,
    ) -> None:
        ctl = app_controller or self._app_controller
        cancel_event = (
            self._operation_state.cancel_event if self._operation_state else None
        )
        ocf = self._on_current_file
        self._execute(
            lambda p, c: ctl.run_consolidation(
                selected_date, p, c, curator=curator, cancel_event=cancel_event,
                on_current_file=ocf,
            )
        )

    def run_consolidation_all_dates(
        self, app_controller: Any = None, curator: Any = None,
    ) -> None:
        ctl = app_controller or self._app_controller
        cancel_event = (
            self._operation_state.cancel_event if self._operation_state else None
        )
        ocf = self._on_current_file
        self._execute(
            lambda p, c: ctl.run_consolidation_all_dates(
                p, c, curator=curator, cancel_event=cancel_event,
                on_current_file=ocf,
            )
        )

    def run_consolidation_month(
        self,
        app_controller: Any = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        curator: Any = None,
    ) -> None:
        ctl = app_controller or self._app_controller
        cancel_event = (
            self._operation_state.cancel_event if self._operation_state else None
        )
        ocf = self._on_current_file
        self._execute(
            lambda p, c: ctl.run_consolidation_month(
                start_date, end_date, p, c, curator=curator, cancel_event=cancel_event,
                on_current_file=ocf,
            )
        )

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._is_running

    @property
    def progress(self) -> float:
        with self._lock:
            return self._progress

    def get_button_state(self) -> str:
        return "disabled" if self._is_running else "normal"
