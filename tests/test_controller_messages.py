from datetime import datetime

from core.app.controller_messages import (
    build_empty_data_message,
    build_issue_preview,
    build_success_message,
    format_file_error_note,
    normalize_consolidation_dates,
)


def test_format_file_error_note_summarizes_first_three_files() -> None:
    note = format_file_error_note(
        [
            {"path": r"C:\reports\a.xlsx"},
            {"path": r"C:\reports\b.xlsx"},
            {"path": r"C:\reports\c.xlsx"},
            {"path": r"C:\reports\d.xlsx"},
        ]
    )

    assert note == "Не удалось обработать 4 файл(ов): a.xlsx, b.xlsx, c.xlsx ...."


def test_build_empty_data_message_appends_runtime_notes() -> None:
    message = build_empty_data_message(
        None,
        "01.04.2026",
        "30.04.2026",
        "Даты после 24.04.2026 исключены.",
        "Не удалось обработать 1 файл(ов).",
    )

    assert message == (
        "Нет данных за период 01.04.2026 — 30.04.2026. "
        "Даты после 24.04.2026 исключены. Не удалось обработать 1 файл(ов)."
    )


def test_build_success_message_for_all_dates_uses_plain_done() -> None:
    message = build_success_message("all_dates", None, None, None, None)

    assert message == "Готово!"


def test_normalize_consolidation_dates_rejects_future_target_date() -> None:
    future = datetime.now().date().replace(year=datetime.now().year + 1)
    target = future.strftime("%d.%m.%Y")

    normalized = normalize_consolidation_dates(target, None, None)

    assert normalized == (
        None,
        None,
        None,
        f"Дата {target} в будущем. Будущие даты исключаются из сборки.",
        None,
    )


def test_build_issue_preview_deduplicates_and_limits() -> None:
    preview = build_issue_preview(["a", "b", "a", "c", "d"])

    assert preview == "a; b; c; и еще 1"
