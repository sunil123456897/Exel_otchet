"""Reconciliation report service.

Extracted from AppController. ``run_reconciliation_report`` builds a
discrepancy report from already-generated master and RSЧ files — it does
not depend on the consolidation pipeline, so it is safe to isolate here.

``run_auto_reconciliation_day`` stays in AppController because it calls
``_run_auto_master_report`` → ``_run_consolidation_blocking``, which
couples it to the consolidation core.
"""

import logging
import threading
from pathlib import Path
from typing import Callable, Dict, Optional

from core.infra.reconciliation import build_combined_reconciliation_report


class ReconciliationService:
    """Builds discrepancy reports comparing master reports against RSЧ."""

    def __init__(
        self,
        start_thread_fn: Callable[[Callable], None],
        get_drive_letters_fn: Callable[[], tuple[str, ...]],
        alias_repo=None,
    ) -> None:
        self._start_thread = start_thread_fn
        self._get_drive_letters = get_drive_letters_fn
        self._alias_repo = alias_repo

    def run_reconciliation_report(
        self,
        master_paths: Dict[str, Path],
        rsch_path: Path,
        output_path: Path,
        selected_date,
        on_complete: Callable[[bool, str, Optional[Path]], None],
        cancel_event: Optional[threading.Event] = None,
    ) -> None:
        """Build a reconciliation report from already selected report and RSC files."""

        def task() -> None:
            try:
                from core.app_controller import _is_cancelled, _cancel_message

                if _is_cancelled(cancel_event):
                    _cancel_message(on_complete, output_path)
                    return
                target_date = (
                    selected_date.date() if hasattr(selected_date, "date") else selected_date
                )
                counts = build_combined_reconciliation_report(
                    {label: Path(path) for label, path in master_paths.items()},
                    Path(rsch_path),
                    Path(output_path),
                    target_date=target_date,
                    drive_letters=self._get_drive_letters(),
                    alias_repo=self._alias_repo,
                )
                msg = (
                    "Отчет расхождений собран: "
                    f"Общий {counts.get('Общий', 0)}, "
                    f"Борис {counts.get('Борис', 0)}, "
                    f"Иван {counts.get('Иван', 0)} строк."
                )
                on_complete(True, msg, Path(output_path))
            except Exception as e:
                logging.exception("Reconciliation report error: %s", e)
                on_complete(False, f"Ошибка сверки отчетов: {e}", None)

        self._start_thread(task)
