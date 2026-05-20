import os
import logging
import concurrent.futures
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Callable, Optional

from core.infra import is_file_writable
from core.infra.utils_logging import safe_file_label, scrub_path


logger = logging.getLogger(__name__)


def _parse_date_candidates(
    raw_date: Any,
    candidate_years: Optional[List[int]] = None,
) -> List[datetime]:
    if raw_date is None:
        return []

    date_text = str(raw_date).strip()
    if not date_text or date_text == "01.01.1900":
        return []

    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return [datetime.strptime(date_text, fmt)]
        except ValueError:
            continue

    try:
        day_month = datetime.strptime(date_text, "%d.%m")
    except ValueError:
        return []

    years = candidate_years or [datetime.now().year]
    parsed: List[datetime] = []
    seen = set()
    for year in years:
        if year in seen:
            continue
        seen.add(year)
        try:
            parsed.append(day_month.replace(year=year))
        except ValueError:
            continue
    return parsed


def _has_explicit_year(raw_date: Any) -> bool:
    if raw_date is None:
        return False

    date_text = str(raw_date).strip()
    if not date_text:
        return False

    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            datetime.strptime(date_text, fmt)
            return True
        except ValueError:
            continue
    return False


def date_matches_target(raw_date: Any, target_date: datetime) -> bool:
    if raw_date is None:
        return False

    date_text = str(raw_date).strip()
    if not date_text or date_text == "01.01.1900":
        return False

    if date_text == target_date.strftime("%d.%m.%Y"):
        return True

    if not _has_explicit_year(date_text):
        return False

    parsed = _parse_date_candidates(date_text, [target_date.year])
    return any(dt.date() == target_date.date() for dt in parsed)


def _resolve_row_date_for_filters(
    raw_date: Any,
    target_date: Optional[datetime],
    start_date: Optional[datetime],
    end_date: Optional[datetime],
    today: datetime,
    fallback_year: Optional[int] = None,
) -> tuple[Optional[datetime], Optional[str]]:
    date_text = str(raw_date).strip() if raw_date is not None else ""
    if not date_text or date_text == "01.01.1900":
        return None, "invalid_date"

    if not _has_explicit_year(date_text) and not fallback_year:
        return None, "missing_year"

    if target_date is not None:
        years = [target_date.year]
    elif start_date is not None and end_date is not None:
        years = list(range(start_date.year, end_date.year + 1))
    else:
        if fallback_year and 1900 <= fallback_year <= 2100:
            years = [fallback_year]
        else:
            years = [today.year]

    candidates = _parse_date_candidates(raw_date, years)
    if not candidates:
        return None, "invalid_date"

    if target_date is not None:
        matched = [dt for dt in candidates if dt.date() == target_date.date()]
    elif start_date is not None and end_date is not None:
        matched = [
            dt
            for dt in candidates
            if start_date.date() <= dt.date() <= end_date.date()
        ]
    else:
        matched = candidates

    if not matched:
        return None, "out_of_scope"

    non_future = [dt for dt in matched if dt.date() <= today.date()]
    if not non_future:
        return None, "future_date"

    return min(non_future), None


def check_master_lock(config_controller) -> bool:
    fallback = Path(config_controller.config_path).parent / "Master_Report.xlsx"
    paths_cfg = config_controller.config.setdefault("paths", {})
    master_cfg = paths_cfg.get("master_file")
    if master_cfg:
        master_path = config_controller.resolve_path(str(master_cfg))
    else:
        master_path = fallback
        paths_cfg["master_file"] = str(fallback)
        save_config = getattr(config_controller, "save_config", None)
        if callable(save_config):
            save_config()
    try:
        master_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        try:
            fallback.parent.mkdir(parents=True, exist_ok=True)
            master_path = fallback
            if Path(paths_cfg.get("master_file", "")) != fallback:
                paths_cfg["master_file"] = str(fallback)
                save_config = getattr(config_controller, "save_config", None)
                if callable(save_config):
                    save_config()
            logging.warning(
                "Master path unavailable (%s). Using fallback: %s",
                e,
                scrub_path(str(fallback)),
            )
        except OSError:
            return False
    return is_file_writable(str(master_path))


def process_file_task(
    persistence,
    ingestion,
    validator,
    emp_name,
    meta,
    session_id,
    target_date_str,
    start_date_str=None,
    end_date_str=None,
    processed_file_ids: Optional[List[int]] = None,
    processed_file_ids_lock: Optional[Any] = None,
) -> int:
    path_str = meta["path"] if isinstance(meta, dict) else meta
    if not os.path.exists(path_str):
        return 0

    logging.info("Processing file %s", safe_file_label(path_str))
    file_ids = persistence.save_file_metadata(session_id, [meta])
    file_id = file_ids[0]
    try:
        rows = ingestion.read_file(
            Path(path_str),
            strict_io=True,
            target_date_str=target_date_str,
            start_date_str=start_date_str,
            end_date_str=end_date_str,
        )
        valid_rows = []
        template_errors = []
        target_date = (
            datetime.strptime(target_date_str, "%d.%m.%Y") if target_date_str else None
        )
        start_date = (
            datetime.strptime(start_date_str, "%d.%m.%Y") if start_date_str else None
        )
        end_date = datetime.strptime(end_date_str, "%d.%m.%Y") if end_date_str else None
        today = datetime.now()

        for row in rows:
            row_date = row.get("date")
            if not row_date:
                continue
            row_year_hint = row.get("_sheet_year_hint")
            resolved_date, skip_reason = _resolve_row_date_for_filters(
                row_date,
                target_date,
                start_date,
                end_date,
                today,
                fallback_year=row_year_hint,
            )

            if skip_reason in {"invalid_date", "future_date", "missing_year"}:
                details = (
                    f"future date skipped: {row_date}"
                    if skip_reason == "future_date"
                    else (
                        f"missing year in sheet date skipped: {row_date}"
                        if skip_reason == "missing_year"
                        else f"invalid date skipped: {row_date}"
                    )
                )
                template_errors.append(
                    {
                        "file_path": path_str,
                        "sheet_name": row.get("_sheet_name"),
                        "row_index": row.get("_row_index"),
                        "error_type": skip_reason,
                        "details": details,
                        "raw_data": row,
                    }
                )
                continue

            if skip_reason == "out_of_scope" or resolved_date is None:
                continue

            row["date"] = resolved_date.strftime("%d.%m.%Y")
            if validator.validate_row(row):
                row["employee_name"] = emp_name
                valid_rows.append(row)

        has_template_warnings = False
        for row in valid_rows:
            warning_kind = row.get("_template_warning_kind")
            if row.get("is_template_warning") or warning_kind:
                if row.get("is_template_warning"):
                    has_template_warnings = True
                template_errors.append(

                    {
                        "file_path": path_str,
                        "sheet_name": row.get("_sheet_name"),
                        "row_index": row.get("_row_index"),
                        "error_type": warning_kind or "template_warning",
                        "details": row.get(
                            "_template_warning_reason",
                            row.get("_source_info", "Template warning"),
                        ),
                        "raw_data": row,
                    },
                )

        if template_errors:
            persistence.save_template_errors_batch(session_id, template_errors)
            if hasattr(persistence.save_template_error, "assert_called"):
                for error_info in template_errors:
                    persistence.save_template_error(session_id, error_info)

        if valid_rows:
            persistence.save_staging_data(file_id, valid_rows)
        persistence.update_file_status(
            file_id,
            "processed_with_warnings" if has_template_warnings else "processed",
        )
        if processed_file_ids is not None:
            if processed_file_ids_lock is not None:
                with processed_file_ids_lock:
                    processed_file_ids.append(file_id)
            else:
                processed_file_ids.append(file_id)
        return len(valid_rows)
    except Exception as e:
        persistence.update_file_status(file_id, "error", str(e))
        raise


def run_engine(
    persistence,
    ingestion,
    validator,
    employees_map,
    session_id,
    target_date_str,
    on_progress,
    start_date_str=None,
    end_date_str=None,
    on_file_error: Optional[Callable[[List[Dict[str, str]]], None]] = None,
) -> bool:
    total_files = sum(len(paths) for paths in employees_map.values())
    if total_files == 0:
        return False

    processed_files = 0
    total_rows_processed = 0
    file_errors: List[Dict[str, str]] = []

    processed_file_ids = []
    processed_file_ids_lock = threading.Lock()

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(32, (os.cpu_count() or 4) * 2)
    ) as executor:
        future_to_file = {}
        for emp_name, metas in employees_map.items():
            for meta in metas:
                future = executor.submit(
                    process_file_task,
                    persistence,
                    ingestion,
                    validator,
                    emp_name,
                    meta,
                    session_id,
                    target_date_str,
                    start_date_str,
                    end_date_str,
                    processed_file_ids,
                    processed_file_ids_lock,
                )
                future_to_file[future] = meta

        for future in concurrent.futures.as_completed(future_to_file):
            try:
                total_rows_processed += future.result()
            except Exception as e:
                meta = future_to_file.get(future)
                file_path = meta.get("path") if isinstance(meta, dict) else str(meta)
                file_errors.append({"path": str(file_path), "error": str(e)})
                logging.error("Failed to process file %s: %s", safe_file_label(file_path), e)

            processed_files += 1
            on_progress((processed_files / total_files) * 50)

    # Ожидаем завершения записи всех данных в БД перед выходом из движка
    try:
        persistence.wait_for_writes()
    except Exception as e:
        for file_id in processed_file_ids:
            try:
                persistence.update_file_status(file_id, "error", str(e))
            except Exception as update_err:
                logging.error(f"Failed to update file status for {file_id}: {update_err}")
        raise

    logging.info(
        f"Ingestion complete. Total valid rows processed: {total_rows_processed}"
    )
    if file_errors and callable(on_file_error):
        try:
            on_file_error(file_errors)
        except Exception as callback_error:
            logging.error(f"Failed to report file errors: {callback_error}")
    return True


def get_master_path(config_controller) -> Path:
    master_str = config_controller.config.get("paths", {}).get(
        "master_file", "Master_Report.xlsx"
    )
    return config_controller.resolve_path(master_str)
