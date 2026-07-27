"""Stage 7 / MR-0701 + MR-0702 — first-run smoke and error-presenter invariants.

These tests do NOT require a real Tk display (the welcome dialog's
``_display_available`` short-circuits to False in CI). They pin the
*contract* of first-run detection and error presentation:

* first-run flag is read/written atomically and survives a corrupt file;
* error messages never contain ``str(exc)`` — only ``repr(exc)`` in
  the optional detail, plus a stable, human-readable Russian message;
* the four exception classes that have explicit mappings (Permission,
  FileNotFound, JSONDecode, default) all surface the right message;
* a present_error call never raises — even if both toast and messagebox
  fail, the original error is logged and the caller can continue.

These are the invariants that make the UI safe to ship: the user always
sees a meaningful message, never a Python traceback.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from core.ui.error_presenter import (
    _human_message,
    present_error,
    present_validation_error,
)
from core.ui import welcome_dialog


# ── MR-0701: first-run flag ────────────────────────────────────────────


def test_first_run_flag_round_trips(tmp_path: Path, monkeypatch) -> None:
    """Writing first_run_done=True then reading must report not-first-run."""
    flag_file = tmp_path / "first_run.json"
    monkeypatch.setattr(welcome_dialog, "_FLAG_PATH", flag_file)

    assert welcome_dialog.is_first_run() is True  # no file yet
    welcome_dialog.mark_first_run_done()
    assert welcome_dialog.is_first_run() is False


def test_corrupt_first_run_file_treated_as_first_run(
    tmp_path: Path, monkeypatch,
) -> None:
    """A corrupt JSON file must NOT crash the app or block first-run."""
    flag_file = tmp_path / "first_run.json"
    flag_file.write_text("not-json", encoding="utf-8")
    monkeypatch.setattr(welcome_dialog, "_FLAG_PATH", flag_file)

    # Must return True (treat as first run), not raise.
    assert welcome_dialog.is_first_run() is True


def test_first_run_flag_with_extra_keys_preserves_them(
    tmp_path: Path, monkeypatch,
) -> None:
    """mark_first_run_done must not clobber unrelated keys."""
    flag_file = tmp_path / "first_run.json"
    flag_file.write_text(
        json.dumps({"unrelated_key": "keep_me"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(welcome_dialog, "_FLAG_PATH", flag_file)

    welcome_dialog.mark_first_run_done()

    data = json.loads(flag_file.read_text(encoding="utf-8"))
    assert data["first_run_done"] is True
    assert data["unrelated_key"] == "keep_me"


def test_first_run_flag_missing_file_is_first_run(
    tmp_path: Path, monkeypatch,
) -> None:
    """No flag file at all ⇒ first run."""
    monkeypatch.setattr(welcome_dialog, "_FLAG_PATH", tmp_path / "missing.json")
    assert welcome_dialog.is_first_run() is True


def test_mark_first_run_done_handles_unwritable_file(
    tmp_path: Path, monkeypatch,
) -> None:
    """If the flag file cannot be written, the app must not crash.

    The user will see the welcome dialog again next launch — that's a
    minor annoyance, far better than crashing on startup.
    """
    flag_file = tmp_path / "first_run.json"
    monkeypatch.setattr(welcome_dialog, "_FLAG_PATH", flag_file)
    # Make write fail.
    monkeypatch.setattr(Path, "write_text", lambda *a, **kw: (_ for _ in ()).throw(OSError("disk full")))
    # Must not raise.
    welcome_dialog.mark_first_run_done()


# ── MR-0702: error presenter invariants ────────────────────────────────


def test_permission_error_yields_human_message() -> None:
    """PermissionError maps to a stable Russian message, not str(exc)."""
    exc = PermissionError("/path/with/secrets.xlsx")
    msg = _human_message(exc)
    assert msg == "Нет доступа к файлу"
    # The original path must NOT leak through.
    assert "/path/with/secrets" not in msg


def test_file_not_found_yields_human_message() -> None:
    exc = FileNotFoundError("/some/secret/file.xlsx")
    msg = _human_message(exc)
    assert msg == "Файл не найден"
    assert "/some/secret" not in msg


def test_json_decode_error_yields_human_message() -> None:
    exc = json.JSONDecodeError("msg", "doc", 0)
    msg = _human_message(exc)
    assert msg == "Файл настроек повреждён"


def test_unknown_exception_yields_default_message() -> None:
    """Anything unmapped falls back to a generic message — never str(exc)."""
    exc = RuntimeError("database password is 'hunter2'")
    msg = _human_message(exc)
    assert msg == "Внутренняя ошибка"
    # Critical: the message must not leak the raw exception text.
    assert "hunter2" not in msg


def test_human_message_handles_exception_with_empty_str() -> None:
    """Some exceptions have empty ``str()`` — matching must use repr."""
    exc = PermissionError()  # no args, str(exc) == ''
    msg = _human_message(exc)
    assert msg == "Нет доступа к файлу"


def test_present_error_never_leaks_str_exception() -> None:
    """End-to-end: the user-facing message never contains str(exc).

    The detail section uses repr(exc), which is safer (class name +
    sanitised args). But the primary message must be the human-readable
    Russian text plus "Подробнее в логе." — never the raw exception.
    """
    captured_toast_calls: list[dict] = []
    fake_toasts = MagicMock()
    fake_toasts.error = lambda title, msg, *, detail=None, duration_ms=0: (
        captured_toast_calls.append({"title": title, "msg": msg, "detail": detail})
    )

    secret = "super-secret-token-12345"
    exc = ValueError(secret)
    present_error(
        parent=MagicMock(),
        context="Не удалось загрузить данные",
        exc=exc,
        toasts=fake_toasts,
    )

    assert len(captured_toast_calls) == 1
    call = captured_toast_calls[0]
    # Primary message: no secret leaks.
    assert secret not in call["msg"]
    assert "Не удалось загрузить данные" in call["msg"]
    # Detail uses repr, which is also safer than str.
    assert secret not in call["detail"]
    assert "ValueError" in call["detail"]


def test_present_error_falls_back_to_messagebox_when_no_toasts(
    monkeypatch,
) -> None:
    """Without a ToastManager, present_error uses messagebox.showerror."""
    shown: list[dict] = []
    monkeypatch.setattr(
        "core.ui.error_presenter.messagebox.showerror",
        lambda title, msg, **kw: shown.append({"title": title, "msg": msg}),
    )

    present_error(
        parent=MagicMock(),
        context="Ошибка",
        exc=FileNotFoundError("/some/file"),
        toasts=None,
    )

    assert len(shown) == 1
    assert shown[0]["title"] == "Ошибка"
    # str(exc) must NOT be in the user-facing message.
    assert "/some/file" not in shown[0]["msg"]


def test_present_error_does_not_raise_when_toast_fails(monkeypatch) -> None:
    """If the toast pipeline throws, present_error must fall back gracefully."""
    failing_toasts = MagicMock()
    failing_toasts.error = MagicMock(side_effect=RuntimeError("toast broken"))

    shown: list[dict] = []
    monkeypatch.setattr(
        "core.ui.error_presenter.messagebox.showerror",
        lambda title, msg, **kw: shown.append({"title": title, "msg": msg}),
    )

    # Must not raise.
    present_error(
        parent=MagicMock(),
        context="x",
        exc=ValueError("anything"),
        toasts=failing_toasts,
    )
    # Fell back to messagebox.
    assert len(shown) == 1


def test_present_error_does_not_raise_when_everything_fails(monkeypatch) -> None:
    """If both toast and messagebox fail, present_error still returns.

    The original error must not be masked by a second exception from
    the error-presentation layer.
    """
    failing_toasts = MagicMock()
    failing_toasts.error = MagicMock(side_effect=RuntimeError("toast broken"))
    monkeypatch.setattr(
        "core.ui.error_presenter.messagebox.showerror",
        MagicMock(side_effect=RuntimeError("messagebox broken")),
    )

    # Must not raise.
    present_error(
        parent=MagicMock(),
        context="x",
        exc=ValueError("original error"),
        toasts=failing_toasts,
    )


def test_present_error_message_does_not_use_only_color() -> None:
    """The error message must contain text, not be empty.

    This is a weak check for TZ MR-0702 ("не использовать только цвет для
    статуса"). A toast that only changed color (no text) would fail
    accessibility for screen-reader users.
    """
    captured: list[dict] = []
    fake_toasts = MagicMock()
    fake_toasts.error = lambda title, msg, *, detail=None, duration_ms=0: (
        captured.append({"title": title, "msg": msg})
    )

    present_error(
        parent=MagicMock(),
        context="Контекст",
        exc=ValueError("x"),
        toasts=fake_toasts,
    )

    assert captured
    assert captured[0]["msg"]  # non-empty
    assert len(captured[0]["msg"]) > 10  # not just whitespace


def test_human_message_is_stable_across_calls() -> None:
    """The same exception class must always yield the same message.

    A non-deterministic mapping would make the UI flaky and break
    screenshot-based regression tests.
    """
    exc = PermissionError("/x")
    m1 = _human_message(exc)
    m2 = _human_message(exc)
    m3 = _human_message(PermissionError("/different/path"))
    assert m1 == m2 == m3 == "Нет доступа к файлу"


# ── MR-0702 followup: present_validation_error ────────────────────────


def test_present_validation_error_shows_message_verbatim(monkeypatch) -> None:
    """The validation presenter shows the message as-is.

    Unlike present_error (which masks the message), validation errors
    are user-safe by contract — the caller has audited the source.
    """
    shown: list[str] = []
    monkeypatch.setattr(
        "core.ui.error_presenter.messagebox.showerror",
        lambda title, msg, **kw: shown.append(msg),
    )
    present_validation_error(MagicMock(), "Заказчики идентичны — алиас не нужен")
    assert shown == ["Заказчики идентичны — алиас не нужен"]


def test_present_validation_error_uses_toast_when_available() -> None:
    """When a ToastManager is available, validation goes to a warning toast."""
    captured: list[dict] = []
    fake_toasts = MagicMock()
    fake_toasts.warning = lambda title, msg, **kw: captured.append(
        {"title": title, "msg": msg}
    )
    present_validation_error(MagicMock(), "x", toasts=fake_toasts)
    assert captured and captured[0]["title"] == "Проверьте ввод"


def test_present_validation_error_does_not_raise_when_messagebox_fails(
    monkeypatch,
) -> None:
    """Defensive depth: even a broken messagebox must not propagate."""
    monkeypatch.setattr(
        "core.ui.error_presenter.messagebox.showerror",
        MagicMock(side_effect=RuntimeError("broken")),
    )
    present_validation_error(MagicMock(), "x")  # must not raise
