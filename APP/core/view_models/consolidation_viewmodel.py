"""Consolidation ViewModel — состояние и логика консолидации."""
from typing import Callable, Optional
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class ConsolidationViewModel:
    """ViewModel для процесса консолидации.
    
    Отделяет логику:
    - Проверка готовности перед запуском
    - Прогресс-бар
    - Обработка результатов (успех/ошибка)
    - Состояние кнопок (enabled/disabled)
    """

    def __init__(self) -> None:
        self._is_running = False
        self._progress = 0.0
        self._on_progress: Optional[Callable[[float], None]] = None
        self._on_complete: Optional[Callable[[bool, str, Optional[Path]], None]] = None

    def set_callbacks(self, on_progress: Callable[[float], None], on_complete: Callable[[bool, str, Optional[Path]], None]) -> None:
        """Установить callback для обновления UI."""
        self._on_progress = on_progress
        self._on_complete = on_complete

    # === Commands ===

    def can_run_single_date(self, missing_count: int) -> bool:
        """Проверить можно ли запускать консолидацию за одну дату."""
        return missing_count == 0  # Можно если все готовы

    def run_consolidation(
        self,
        app_controller,
        selected_date: datetime,
    ) -> None:
        """Запустить консолидацию за выбранную дату."""
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

        app_controller.run_consolidation(selected_date, on_progress, on_complete)

    def run_consolidation_all_dates(
        self,
        app_controller,
    ) -> None:
        """Запустить консолидацию за все даты."""
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

        app_controller.run_consolidation_all_dates(on_progress, on_complete)

    # === Queries ===

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def progress(self) -> float:
        return self._progress

    def get_button_state(self) -> str:
        """Состояние кнопок: 'normal' или 'disabled'."""
        return 'disabled' if self._is_running else 'normal'
