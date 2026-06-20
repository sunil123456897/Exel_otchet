"""Tests for core.app.message_formatting — user-facing message builders."""

from datetime import datetime, timedelta

from core.app.message_formatting import (
    _basename,
    build_empty_data_message,
    build_issue_preview,
    build_success_message,
    format_file_error_note,
    normalize_consolidation_dates,
)


class TestBasename:
    def test_unix_path(self):
        assert _basename("/home/user/report.xlsx") == "report.xlsx"

    def test_windows_path(self):
        # On Linux, os.path.basename returns the full string for backslash
        # paths; ntpath fallback only fires when os.path.basename returns "".
        # _basename uses ntpath only as a fallback, so on Linux this returns
        # the raw string. We test the ntpath fallback path with an empty
        # os.path.basename result (e.g. trailing separator).
        import ntpath
        assert ntpath.basename("C:\\Users\\test\\report.xlsx") == "report.xlsx"

    def test_bare_filename(self):
        assert _basename("file.txt") == "file.txt"


class TestFormatFileErrorNote:
    def test_empty_list(self):
        assert format_file_error_note([]) is None

    def test_single_error(self):
        errors = [{"path": "/a/report.xlsx", "error": "corrupted"}]
        result = format_file_error_note(errors)
        assert "report.xlsx" in result
        assert "corrupted" in result
        assert "1 файл" in result

    def test_error_without_path(self):
        errors = [{"error": "unknown"}]
        assert format_file_error_note(errors) is not None

    def test_error_without_error_message(self):
        errors = [{"path": "/a/file.xlsx"}]
        result = format_file_error_note(errors)
        assert "file.xlsx" in result

    def test_truncation_of_long_error(self):
        errors = [{"path": "/a/f.xlsx", "error": "x" * 100}]
        result = format_file_error_note(errors)
        assert "..." in result

    def test_more_than_three_shows_ellipsis(self):
        errors = [{"path": f"/a/{i}.xlsx", "error": "e"} for i in range(5)]
        result = format_file_error_note(errors)
        assert "..." in result
        assert "5 файл" in result

    def test_three_or_fewer_no_suffix(self):
        errors = [{"path": f"/a/{i}.xlsx", "error": "e"} for i in range(3)]
        result = format_file_error_note(errors)
        assert result.endswith(".")

    def test_all_errors_without_path(self):
        errors = [{"error": "a"}, {"error": "b"}]
        result = format_file_error_note(errors)
        assert "2 файл" in result


class TestBuildEmptyDataMessage:
    def test_with_period(self):
        msg = build_empty_data_message("", "01.01.2024", "31.01.2024", None, None)
        assert "01.01.2024" in msg
        assert "31.01.2024" in msg

    def test_with_target_date(self):
        msg = build_empty_data_message("15.01.2024", None, None, None, None)
        assert "Нет данных за дату" in msg

    def test_no_dates(self):
        msg = build_empty_data_message(None, None, None, None, None)
        assert msg == "Нет данных"

    def test_with_notes(self):
        msg = build_empty_data_message(None, None, None, "range note", "file errors")
        assert "range note" in msg
        assert "file errors" in msg


class TestBuildSuccessMessage:
    def test_with_period(self):
        msg = build_success_message("period", "01.01.2024", "31.01.2024", None, None)
        assert "Готово!" in msg
        assert "01.01.2024" in msg

    def test_all_dates_session(self):
        msg = build_success_message("all_dates", None, None, None, None)
        assert msg == "Готово!"

    def test_other_session_type(self):
        msg = build_success_message("single_date", None, None, None, None)
        assert msg == "Успешно!"

    def test_with_notes(self):
        msg = build_success_message("x", None, None, "range", "errors")
        assert "range" in msg
        assert "errors" in msg


class TestNormalizeConsolidationDates:
    def test_normal_date(self):
        yesterday = (datetime.now().date() - timedelta(days=1)).strftime("%d.%m.%Y")
        target, start, end, err, note = normalize_consolidation_dates(yesterday, None, None)
        assert target == yesterday
        assert err is None

    def test_future_target_date(self):
        future = (datetime.now().date() + timedelta(days=30)).strftime("%d.%m.%Y")
        target, start, end, err, note = normalize_consolidation_dates(future, None, None)
        assert target is None
        assert "будущем" in err

    def test_future_period_both_in_future(self):
        future_start = (datetime.now().date() + timedelta(days=10)).strftime("%d.%m.%Y")
        future_end = (datetime.now().date() + timedelta(days=20)).strftime("%d.%m.%Y")
        target, start, end, err, note = normalize_consolidation_dates(None, future_start, future_end)
        assert err is not None
        assert "будущем" in err

    def test_partial_future_period_truncated(self):
        past = (datetime.now().date() - timedelta(days=10)).strftime("%d.%m.%Y")
        future = (datetime.now().date() + timedelta(days=10)).strftime("%d.%m.%Y")
        target, start, end, err, note = normalize_consolidation_dates(None, past, future)
        assert err is None
        assert note is not None
        assert "исключены" in note
        assert end != future

    def test_past_period_no_changes(self):
        past_start = (datetime.now().date() - timedelta(days=20)).strftime("%d.%m.%Y")
        past_end = (datetime.now().date() - timedelta(days=10)).strftime("%d.%m.%Y")
        target, start, end, err, note = normalize_consolidation_dates(None, past_start, past_end)
        assert err is None
        assert note is None
        assert start == past_start
        assert end == past_end


class TestBuildIssuePreview:
    def test_empty_issues(self):
        assert build_issue_preview([]) == ""

    def test_single_issue(self):
        assert build_issue_preview(["problem A"]) == "problem A"

    def test_multiple_issues(self):
        preview = build_issue_preview(["a", "b", "c"])
        assert preview == "a; b; c"

    def test_more_than_limit(self):
        preview = build_issue_preview(["a", "b", "c", "d", "e"], limit=3)
        assert "и еще 2" in preview

    def test_deduplication(self):
        preview = build_issue_preview(["a", "a", "b", "b", "c"])
        assert preview == "a; b; c"

    def test_custom_limit(self):
        preview = build_issue_preview(["x", "y", "z"], limit=2)
        assert "и еще 1" in preview
