import os
import logging
import uuid
import concurrent.futures
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Callable, Optional

from core.infra import is_file_writable


logger = logging.getLogger(__name__)


def check_master_lock(config_controller) -> bool:
    master_str = config_controller.config.get("paths", {}).get(
        "master_file", "Master_Report.xlsx"
    )
    master_path = config_controller.resolve_path(master_str)
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
) -> int:
    path_str = meta["path"] if isinstance(meta, dict) else meta
    if not os.path.exists(path_str):
        return 0

    logging.info(f"Processing file {path_str}")
    file_ids = persistence.save_file_metadata(session_id, [meta])
    file_id = file_ids[0]
    try:
        rows = ingestion.read_file(Path(path_str))
        valid_rows = []
        for row in rows:
            row_date = row.get("date")
            if not row_date:
                continue
            if target_date_str:
                date_match = row_date == target_date_str
            elif start_date_str and end_date_str:
                try:
                    rd = datetime.strptime(row_date, "%d.%m.%Y")
                    sd = datetime.strptime(start_date_str, "%d.%m.%Y")
                    ed = datetime.strptime(end_date_str, "%d.%m.%Y")
                    date_match = sd <= rd <= ed
                except ValueError:
                    date_match = False
            else:
                date_match = True

            if date_match and validator.validate_row(row):
                row["employee_name"] = emp_name
                valid_rows.append(row)

        if valid_rows:
            persistence.save_staging_data(file_id, valid_rows)
            persistence.wait_for_writes()
        persistence.update_file_status(file_id, "processed")
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
) -> bool:
    total_files = sum(len(paths) for paths in employees_map.values())
    if total_files == 0:
        return False

    processed_files = 0
    total_rows_processed = 0

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
                )
                future_to_file[future] = meta

        for future in concurrent.futures.as_completed(future_to_file):
            try:
                total_rows_processed += future.result()
            except Exception as e:
                logging.error(f"Failed to process file: {e}")

            processed_files += 1
            on_progress((processed_files / total_files) * 50)

    logging.info(
        f"Ingestion complete. Total valid rows processed: {total_rows_processed}"
    )
    return True


def get_master_path(config_controller) -> Path:
    master_str = config_controller.config.get("paths", {}).get(
        "master_file", "Master_Report.xlsx"
    )
    return config_controller.resolve_path(master_str)
