"""Consolidation ViewModel — состояние и логика консолидации."""

from typing import Callable, Optional
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class ConsolidationViewModel:
    def __init__(self, app_controller=None) -> None:
        self._app_controller = app_controller
        self._is_running = False
        self._progress = 0.0
        self._on_progress: Optional[Callable[[float], None]] = None
        self._on_complete: Optional[Callable[[bool, str, Optional[Path]], None]] = None

    def set_callbacks(
        self,
        on_progress: Callable[[float], None],
        on_complete: Callable[[bool, str, Optional[Path]], None],
    ) -> None:
        self._on_progress = on_progress
        self._on_complete = on_complete

    def _execute(self, action_fn) -> None:
        if self._is_running:
            return
        self._is_running = True
        self._progress = 0.0

        def on_progress(p: float) -> None:
            self._progress = p
            if self._on_progress:
                self._on_progress(p)

        def on_complete(ok: bool, msg: str, path: Optional[Path]) -> None:
            self._is_running = False
            self._progress = 100.0 if ok else self._progress
            if self._on_complete:
                self._on_complete(ok, msg, path)

        action_fn(on_progress, on_complete)

    def can_run_single_date(self, missing_count: int) -> bool:
        return missing_count == 0

    def run_consolidation(
        self, app_controller=None, selected_date: datetime = None
    ) -> None:
        ctl = app_controller or self._app_controller
        self._execute(lambda p, c: ctl.run_consolidation(selected_date, p, c))

    def run_consolidation_all_dates(self, app_controller=None) -> None:
        ctl = app_controller or self._app_controller
        self._execute(lambda p, c: ctl.run_consolidation_all_dates(p, c))

    def run_consolidation_month(
        self,
        app_controller=None,
        start_date: datetime = None,
        end_date: datetime = None,
    ) -> None:
        ctl = app_controller or self._app_controller
        self._execute(
            lambda p, c: ctl.run_consolidation_month(start_date, end_date, p, c)
        )

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def progress(self) -> float:
        return self._progress

    def get_button_state(self) -> str:
        return "disabled" if self._is_running else "normal"
