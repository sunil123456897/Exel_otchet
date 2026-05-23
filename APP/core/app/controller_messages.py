from __future__ import annotations

import ntpath
import os
from datetime import datetime
from typing import Dict, List, Optional


def _basename(path: str) -> str:
    return os.path.basename(path) or ntpath.basename(path)


def format_file_error_note(file_errors: List[Dict[str, str]]) -> Optional[str]:
    if not file_errors:
        return None

    def format_item(err: Dict[str, str]) -> str:
        name = _basename(err.get("path", ""))
        error = str(err.get("error") or "").strip()
        if not name:
            return ""
        if not error:
            return name
        if len(error) > 80:
            error = error[:77].rstrip() + "..."
        return f"{name} ({error})"

    sample = ", ".join(
        format_item(err)
        for err in file_errors[:3]
        if err.get("path")
    )
    suffix = "" if len(file_errors) <= 3 else " ..."
    if sample:
        end = "." if not suffix else ""
        return f"Не удалось обработать {len(file_errors)} файл(ов): {sample}{suffix}{end}"
    return f"Не удалось обработать {len(file_errors)} файл(ов)."


def build_empty_data_message(
    target_date_str: Optional[str],
    start_date_str: Optional[str],
    end_date_str: Optional[str],
    range_note: Optional[str],
    file_error_note: Optional[str],
) -> str:
    if start_date_str and end_date_str:
        msg = f"Нет данных за период {start_date_str} — {end_date_str}"
    elif target_date_str:
        msg = "Нет данных за дату"
    else:
        msg = "Нет данных"

    notes = [note for note in (range_note, file_error_note) if note]
    if notes:
        return f"{msg}. {' '.join(notes)}"
    return msg


def build_success_message(
    session_type: str,
    start_date_str: Optional[str],
    end_date_str: Optional[str],
    range_note: Optional[str],
    file_error_note: Optional[str],
) -> str:
    if start_date_str and end_date_str:
        msg = f"Готово! ({start_date_str} — {end_date_str})"
    elif session_type == "all_dates":
        msg = "Готово!"
    else:
        msg = "Успешно!"

    notes = [note for note in (range_note, file_error_note) if note]
    if notes:
        return f"{msg} {' '.join(notes)}"
    return msg


def normalize_consolidation_dates(
    target_date_str: Optional[str],
    start_date_str: Optional[str],
    end_date_str: Optional[str],
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    today = datetime.now().date()
    range_note: Optional[str] = None
    effective_target_date = target_date_str
    effective_start_date = start_date_str
    effective_end_date = end_date_str

    if target_date_str:
        td = datetime.strptime(target_date_str, "%d.%m.%Y").date()
        if td > today:
            msg = (
                f"Дата {target_date_str} в будущем. "
                "Будущие даты исключаются из сборки."
            )
            return None, None, None, msg, None

    if start_date_str and end_date_str:
        sd = datetime.strptime(start_date_str, "%d.%m.%Y").date()
        ed = datetime.strptime(end_date_str, "%d.%m.%Y").date()
        if sd > today:
            msg = (
                f"Период {start_date_str} — {end_date_str} полностью в будущем. "
                "Будущие даты исключаются из сборки."
            )
            return None, None, None, msg, None
        if ed > today:
            effective_end_date = today.strftime("%d.%m.%Y")
            range_note = (
                f"Даты после {effective_end_date} исключены "
                "(будущие даты не учитываются)."
            )

    return effective_target_date, effective_start_date, effective_end_date, None, range_note


def build_issue_preview(issues: List[str], limit: int = 3) -> str:
    unique_issues: list[str] = []
    seen: set[str] = set()
    for issue in issues:
        if issue in seen:
            continue
        seen.add(issue)
        unique_issues.append(issue)

    preview = "; ".join(unique_issues[:limit])
    if len(unique_issues) > limit:
        preview += f"; и еще {len(unique_issues) - limit}"
    return preview
