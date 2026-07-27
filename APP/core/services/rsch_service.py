"""RSЧ (bank account control) report service.

Extracted from AppController to reduce its size. All four run_rsch_*
variants live here; AppController delegates, keeping its public API
unchanged so the GUI layer needs no changes.
"""

import logging
import threading
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence

# Прогресс-колбэчи для статус-бара (как в Consolidation). Optional, чтобы
# не ломать существующих вызовов; GUI пробрасывает set_progress/set_current_file.
ProgressCb = Optional[Callable[[float], None]]
CurrentFileCb = Optional[Callable[[str, int, int], None]]

from core.app.cancellation import cancel_message as _cancel_message
from core.app.cancellation import is_cancelled as _is_cancelled
from core.app.message_formatting import build_issue_preview
from core.infra.rsch import build_rsch_report


class RschService:
    """Builds RSЧ control workbooks from source Excel files.

    Each method starts a background thread (via the injected
    ``start_thread_fn``) so the GUI stays responsive. Cancellation is
    cooperative: pass a ``threading.Event`` and the worker checks it
    at every checkpoint.
    """

    def __init__(
        self,
        start_thread_fn: Callable[[Callable[[], None]], None],
        get_drive_letters_fn: Callable[[], tuple[str, ...]],
    ) -> None:
        self._start_thread = start_thread_fn
        self._get_drive_letters = get_drive_letters_fn

    def run_rsch_report(
        self,
        source_paths: Path | Sequence[Path],
        output_path: Path,
        selected_date: Any,
        on_complete: Callable[[bool, str, Optional[Path]], None],
        cancel_event: Optional[threading.Event] = None,
        on_progress: Optional[ProgressCb] = None,
        on_current_file: Optional[CurrentFileCb] = None,
    ) -> None:
        """Build an RSC control report from selected workbooks."""

        def task() -> None:
            try:
                target_date = selected_date
                if hasattr(selected_date, "date"):
                    target_date = selected_date.date()

                if _is_cancelled(cancel_event):
                    _cancel_message(on_complete, output_path)
                    return

                if isinstance(source_paths, (str, Path)):
                    normalized_sources = [Path(source_paths)]
                else:
                    normalized_sources = [Path(p) for p in source_paths]

                issues: List[str] = []

                written_rows = build_rsch_report(
                    normalized_sources,
                    output_path,
                    target_date=target_date,
                    issues_sink=issues,
                    drive_letters=self._get_drive_letters(),
                    on_progress=on_progress,
                    on_current_file=on_current_file,
                )
                if written_rows == 0:
                    raise ValueError("РСЧ: нет строк за выбранную дату")

                if issues:
                    msg = (
                        f"РСЧ отчет собран: {written_rows} строк из {len(normalized_sources)} файлов. "
                        f"Есть проблемы с листами: {build_issue_preview(issues)}"
                    )
                else:
                    msg = (
                        f"РСЧ отчет собран: {written_rows} строк из {len(normalized_sources)} файлов"
                    )

                on_complete(
                    True,
                    msg,
                    output_path,
                )
            except Exception as e:
                logging.exception("RSC build error: %s", e)
                on_complete(False, f"Ошибка сборки РСЧ: {e}", None)

        self._start_thread(task)

    def run_rsch_report_period(
        self,
        source_paths: Path | Sequence[Path],
        output_path: Path,
        start_date: Any,
        end_date: Any,
        on_complete: Callable[[bool, str, Optional[Path]], None],
        cancel_event: Optional[threading.Event] = None,
        on_progress: Optional[ProgressCb] = None,
        on_current_file: Optional[CurrentFileCb] = None,
    ) -> None:
        """Build one RSC control workbook with one sheet per row date in range."""

        def task() -> None:
            try:
                start = start_date.date() if hasattr(start_date, "date") else start_date
                end = end_date.date() if hasattr(end_date, "date") else end_date

                if _is_cancelled(cancel_event):
                    _cancel_message(on_complete, output_path)
                    return

                if isinstance(source_paths, (str, Path)):
                    normalized_sources = [Path(source_paths)]
                else:
                    normalized_sources = [Path(p) for p in source_paths]

                issues: List[str] = []
                written_rows = build_rsch_report(
                    normalized_sources,
                    output_path,
                    start_date=start,
                    end_date=end,
                    issues_sink=issues,
                    drive_letters=self._get_drive_letters(),
                    on_progress=on_progress,
                    on_current_file=on_current_file,
                )
                if written_rows == 0:
                    raise ValueError("РСЧ: нет строк за выбранный период")

                if issues:
                    msg = (
                        f"РСЧ отчет за период собран: {written_rows} строк из {len(normalized_sources)} файлов. "
                        f"Есть проблемы с листами: {build_issue_preview(issues)}"
                    )
                else:
                    msg = (
                        f"РСЧ отчет за период собран: {written_rows} строк из "
                        f"{len(normalized_sources)} файлов"
                    )

                on_complete(True, msg, output_path)
            except Exception as e:
                logging.exception("RSC period build error: %s", e)
                on_complete(False, f"Ошибка сборки РСЧ за период: {e}", None)

        self._start_thread(task)

    def run_rsch_report_period_batch(
        self,
        source_paths: Path | Sequence[Path],
        output_dir: Path,
        start_date: Any,
        end_date: Any,
        on_complete: Callable[[bool, str, Optional[Path]], None],
        cancel_event: Optional[threading.Event] = None,
    ) -> None:
        """Build separate RSC workbooks for each date in the selected range."""

        def task() -> None:
            try:
                start = start_date.date() if hasattr(start_date, "date") else start_date
                end = end_date.date() if hasattr(end_date, "date") else end_date

                if _is_cancelled(cancel_event):
                    _cancel_message(on_complete, output_dir)
                    return

                if isinstance(source_paths, (str, Path)):
                    normalized_sources = [Path(source_paths)]
                else:
                    normalized_sources = [Path(p) for p in source_paths]

                output_dir_path = Path(output_dir)
                output_dir_path.mkdir(parents=True, exist_ok=True)

                current = start
                total_rows = 0
                files_written = 0
                issues: List[str] = []
                while current <= end:
                    if _is_cancelled(cancel_event):
                        _cancel_message(on_complete, output_dir_path)
                        return
                    output_path = output_dir_path / f"РСЧ_отчет_{current.strftime('%d.%m.%Y')}.xlsx"
                    written_rows = build_rsch_report(
                        normalized_sources,
                        output_path,
                        target_date=current,
                        issues_sink=issues,
                        drive_letters=self._get_drive_letters(),
                    )
                    if written_rows:
                        total_rows += written_rows
                        files_written += 1
                    current += timedelta(days=1)

                if files_written == 0:
                    raise ValueError("РСЧ: нет строк за выбранный период")

                if issues:
                    msg = (
                        f"РСЧ отчеты за период собраны: {files_written} файлов, {total_rows} строк. "
                        f"Есть проблемы с листами: {build_issue_preview(issues)}"
                    )
                else:
                    msg = (
                        f"РСЧ отчеты за период собраны: {files_written} файлов, "
                        f"{total_rows} строк"
                    )

                on_complete(True, msg, output_dir_path)
            except Exception as e:
                logging.exception("RSC period batch build error: %s", e)
                on_complete(False, f"Ошибка пакетной сборки РСЧ за период: {e}", None)

        self._start_thread(task)

    def run_rsch_report_batch(
        self,
        source_paths: Sequence[Path],
        output_paths: Sequence[Path],
        selected_date: Any,
        on_complete: Callable[[bool, str, Optional[Path]], None],
        cancel_event: Optional[threading.Event] = None,
    ) -> None:
        """Build separate RSC reports per source workbook."""

        def task() -> None:
            try:
                target_date = selected_date
                if hasattr(selected_date, "date"):
                    target_date = selected_date.date()

                if _is_cancelled(cancel_event):
                    _cancel_message(on_complete, *output_paths)
                    return

                normalized_sources = [Path(p) for p in source_paths]
                normalized_outputs = [Path(p) for p in output_paths]
                if len(normalized_sources) != len(normalized_outputs):
                    raise ValueError("Sources and outputs count mismatch")
                if len({str(path) for path in normalized_outputs}) != len(
                    normalized_outputs
                ):
                    raise ValueError("Duplicate output paths")

                total_rows = 0
                issues: List[str] = []
                for src, out in zip(normalized_sources, normalized_outputs, strict=True):
                    if _is_cancelled(cancel_event):
                        _cancel_message(on_complete, *normalized_outputs)
                        return
                    written_rows = build_rsch_report(
                        src,
                        out,
                        target_date=target_date,
                        issues_sink=issues,
                        drive_letters=self._get_drive_letters(),
                    )
                    if written_rows:
                        total_rows += written_rows
                    elif out.exists():
                        out.unlink()

                output_dir = (
                    normalized_outputs[0].parent if normalized_outputs else None
                )
                if total_rows == 0:
                    raise ValueError("РСЧ: нет строк за выбранную дату")

                if issues:
                    msg = (
                        f"РСЧ отчеты собраны: {len(normalized_outputs)} файлов, {total_rows} строк. "
                        f"Есть проблемы с листами: {build_issue_preview(issues)}"
                    )
                else:
                    msg = (
                        f"РСЧ отчеты собраны: {len(normalized_outputs)} файлов, "
                        f"{total_rows} строк"
                    )

                on_complete(
                    True,
                    msg,
                    output_dir,
                )
            except Exception as e:
                logging.exception("RSC batch build error: %s", e)
                on_complete(False, f"Ошибка пакетной сборки РСЧ: {e}", None)

        self._start_thread(task)
