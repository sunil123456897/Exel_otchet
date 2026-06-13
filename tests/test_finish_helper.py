"""Tests for ``CommandContext`` and the ``finish()`` completion helper.

These cover the Phase 5.3 split: the original 734-line ``gui_commands``
monolith had four near-identical 20-line completion handlers. They
collapsed to one helper plus per-command callers; this file pins the
behaviour so the four callers can stay short and obvious.
"""
import logging
from pathlib import Path
from unittest.mock import MagicMock


from core.ui.gui_commands._base import (
    CommandContext,
    _is_cancelled_message,
    finish,
)
from core.ui.operation_state import OperationState
from core.ui.toast import ToastLevel, ToastManager


def _make_ctx(toasts=None, root=None):
    """Build a CommandContext with all collaborators stubbed."""
    if root is None:
        root = MagicMock()
    return CommandContext(
        root=root,
        config_controller=MagicMock(),
        app_controller=MagicMock(),
        employee_vm=MagicMock(),
        consolidation_vm=MagicMock(),
        sidebar=MagicMock(),
        employee_table=MagicMock(),
        stats_panel=MagicMock(),
        dashboard_tabs=MagicMock(),
        operation_state=OperationState(),
        toasts=toasts,
    )


def test_is_cancelled_message_matches_phrase():
    assert _is_cancelled_message("Операция отменена пользователем")
    assert _is_cancelled_message("ОПЕРАЦИЯ ОТМЕНЕНА ПОЛЬЗОВАТЕЛЕМ")
    # The substring check is intentionally strict: an empty haystack
    # does not match, so an empty message is treated as "not cancelled".


def test_is_cancelled_message_rejects_unrelated():
    assert not _is_cancelled_message("файл не найден")
    assert not _is_cancelled_message(None)
    assert not _is_cancelled_message("")


def test_finish_ok_emits_success_toast_and_records():
    toasts = MagicMock(spec=ToastManager)
    record = MagicMock()
    ctx = _make_ctx(toasts=toasts)
    finish(ctx, ok=True, msg="Готово", path=None, label="Сборка", record_result=record)
    toasts.show.assert_called_once()
    level, title, body, _duration = toasts.show.call_args[0]
    assert level == ToastLevel.SUCCESS
    assert title == "Сборка"
    assert body == "Готово"
    record.assert_called_once_with("Сборка", True, "Готово", None)


def test_finish_ok_asks_to_open_when_path_provided(monkeypatch):
    """When the user accepts the dialog, the file should be opened."""
    from core.ui.gui_commands import _base as base_mod

    open_calls: list[str] = []
    monkeypatch.setattr(base_mod, "open_path", lambda p: open_calls.append(p))
    monkeypatch.setattr(
        "tkinter.messagebox.askyesno", lambda *a, **k: True
    )
    toasts = MagicMock(spec=ToastManager)
    ctx = _make_ctx(toasts=toasts)
    out = Path("C:/tmp/x.xlsx")
    finish(
        ctx,
        ok=True,
        msg="Готово",
        path=out,
        label="РСЧ",
        ask_open_text="Открыть?",
    )
    assert open_calls == [str(out)]


def test_finish_ok_no_open_dialog_when_declined(monkeypatch):
    from core.ui.gui_commands import _base as base_mod

    open_calls: list[str] = []
    monkeypatch.setattr(base_mod, "open_path", lambda p: open_calls.append(p))
    monkeypatch.setattr(
        "tkinter.messagebox.askyesno", lambda *a, **k: False
    )
    toasts = MagicMock(spec=ToastManager)
    ctx = _make_ctx(toasts=toasts)
    finish(
        ctx,
        ok=True,
        msg="Готово",
        path=Path("C:/tmp/x.xlsx"),
        label="РСЧ",
        ask_open_text="Открыть?",
    )
    assert open_calls == []


def test_finish_cancelled_emits_warning_not_error():
    toasts = MagicMock(spec=ToastManager)
    record = MagicMock()
    ctx = _make_ctx(toasts=toasts)
    finish(
        ctx,
        ok=False,
        msg="Операция отменена пользователем",
        path=None,
        label="Сверка",
        record_result=record,
    )
    level, title, _body, _duration = toasts.show.call_args[0]
    assert level == ToastLevel.WARNING
    assert "отменено" in title.lower()
    record.assert_called_once()
    # The dashboard must see the cancellation as a "False" result, not
    # a hard error. The label argument to record_result is what the
    # dashboard tab uses to colour the row.
    assert record.call_args[0][1] is False


def test_finish_error_emits_error_toast():
    toasts = MagicMock(spec=ToastManager)
    record = MagicMock()
    ctx = _make_ctx(toasts=toasts)
    finish(
        ctx,
        ok=False,
        msg="Не удалось открыть файл",
        path=None,
        label="Сверка",
        record_result=record,
    )
    level, title, _body, _duration = toasts.show.call_args[0]
    assert level == ToastLevel.ERROR
    assert "ошибка" in title.lower()


def test_finish_error_falls_back_to_messagebox_when_no_toasts(monkeypatch):
    """If ToastManager is not injected, fall back to messagebox."""
    from core.ui.gui_commands import _base as base_mod

    boxes: list[tuple[str, str]] = []
    monkeypatch.setattr(
        base_mod.messagebox,
        "showerror",
        lambda title, body, **kw: boxes.append((title, body)),
    )
    ctx = _make_ctx(toasts=None)
    finish(ctx, ok=False, msg="файл не найден", path=None, label="X")
    assert boxes == [("Ошибка", "файл не найден")]


def test_finish_does_not_call_askyesno_without_ask_text(monkeypatch):
    """When ``ask_open_text`` is None we must skip the dialog entirely."""
    from core.ui.gui_commands import _base as base_mod

    open_calls: list[str] = []
    monkeypatch.setattr(base_mod, "open_path", lambda p: open_calls.append(p))
    asked: list[bool] = []
    monkeypatch.setattr(
        "tkinter.messagebox.askyesno",
        lambda *a, **k: asked.append(True) or True,
    )
    toasts = MagicMock(spec=ToastManager)
    ctx = _make_ctx(toasts=toasts)
    finish(
        ctx,
        ok=True,
        msg="Готово",
        path=Path("C:/tmp/x.xlsx"),
        label="X",
        ask_open_text=None,
    )
    assert open_calls == []
    assert asked == []


def test_command_context_post_uses_root_after():
    root = MagicMock()
    ctx = _make_ctx(root=root)
    fn = MagicMock()
    ctx.post(fn)
    root.after.assert_called_once()
    assert root.after.call_args[0][0] == 0
    assert root.after.call_args[0][1] is fn


def test_command_context_default_toasts_is_none():
    ctx = CommandContext(
        root=MagicMock(),
        config_controller=MagicMock(),
        app_controller=MagicMock(),
        employee_vm=MagicMock(),
        consolidation_vm=MagicMock(),
        sidebar=MagicMock(),
        employee_table=MagicMock(),
        stats_panel=MagicMock(),
        dashboard_tabs=MagicMock(),
        operation_state=OperationState(),
    )
    assert ctx.toasts is None


def test_finish_ok_logs_info(caplog):
    caplog.set_level(logging.INFO)
    ctx = _make_ctx(toasts=MagicMock(spec=ToastManager))
    finish(ctx, ok=True, msg="Готово", path=None, label="X")
    assert any("X" in rec.message and "Готово" in rec.message for rec in caplog.records)


def test_finish_error_logs_error(caplog):
    caplog.set_level(logging.ERROR)
    ctx = _make_ctx(toasts=MagicMock(spec=ToastManager))
    finish(ctx, ok=False, msg="фейл", path=None, label="X")
    assert any("X" in rec.message and "фейл" in rec.message for rec in caplog.records)
