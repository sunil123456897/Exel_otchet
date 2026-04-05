"""Расширенные тесты для utils_logging.py."""
import pytest
import logging
import queue
from unittest.mock import MagicMock, patch, call
from core.infra.utils_logging import TextHandler, setup_gui_logging


class TestTextHandler:
    """Тесты TextHandler — логирование в Tkinter Text widget."""

    def test_emit_puts_to_queue(self):
        mock_widget = MagicMock()
        handler = TextHandler(mock_widget)

        record = logging.LogRecord(
            name='test', level=logging.INFO, pathname='', lineno=0,
            msg='Test message', args=(), exc_info=None
        )
        handler.emit(record)

        assert not handler.msg_queue.empty()
        assert handler.msg_queue.get_nowait().endswith('Test message')

    def test_emit_schedules_processing(self):
        mock_widget = MagicMock()
        handler = TextHandler(mock_widget)

        record = logging.LogRecord(
            name='test', level=logging.INFO, pathname='', lineno=0,
            msg='Hello', args=(), exc_info=None
        )
        handler.emit(record)

        mock_widget.after_idle.assert_called_once()
        assert handler._is_scheduled is True

    def test_emit_does_not_double_schedule(self):
        mock_widget = MagicMock()
        handler = TextHandler(mock_widget)

        # Первый emit
        handler.emit(logging.LogRecord('test', logging.INFO, '', 0, '1', (), None))
        first_call_count = mock_widget.after_idle.call_count

        # Второй emit пока первый не обработан
        handler.emit(logging.LogRecord('test', logging.INFO, '', 0, '2', (), None))
        assert mock_widget.after_idle.call_count == first_call_count

    def test_process_queue_inserts_messages(self):
        mock_widget = MagicMock()
        handler = TextHandler(mock_widget)

        handler.msg_queue.put("Message 1")
        handler.msg_queue.put("Message 2")
        handler._is_scheduled = True

        handler._process_queue()

        mock_widget.configure.assert_any_call(state='normal')
        mock_widget.insert.assert_any_call(pytest.importorskip('tkinter').END, "Message 1\n")
        mock_widget.insert.assert_any_call(pytest.importorskip('tkinter').END, "Message 2\n")
        mock_widget.configure.assert_any_call(state='disabled')
        mock_widget.yview.assert_called_once_with(pytest.importorskip('tkinter').END)

    def test_process_queue_clears_flag(self):
        mock_widget = MagicMock()
        handler = TextHandler(mock_widget)
        handler._is_scheduled = True

        handler._process_queue()
        assert handler._is_scheduled is False

    def test_process_queue_handles_empty_queue(self):
        mock_widget = MagicMock()
        handler = TextHandler(mock_widget)
        handler._is_scheduled = True

        # Не должно выбрасывать при пустой очереди
        handler._process_queue()
        mock_widget.insert.assert_not_called()

    def test_process_queue_scrolls_to_end(self):
        import tkinter as tk
        mock_widget = MagicMock()
        handler = TextHandler(mock_widget)
        handler.msg_queue.put("msg")
        handler._is_scheduled = True

        handler._process_queue()
        mock_widget.yview.assert_called_once_with(tk.END)


class TestSetupGuiLogging:
    """Тесты setup_gui_logging."""

    def test_adds_handler_to_root_logger(self):
        mock_widget = MagicMock()
        handler = setup_gui_logging(mock_widget)

        root = logging.getLogger()
        assert handler in root.handlers
        assert root.level == logging.INFO

    def test_sets_formatter(self):
        mock_widget = MagicMock()
        handler = setup_gui_logging(mock_widget)

        assert handler.formatter is not None
        # Проверить формат
        record = logging.LogRecord('test', logging.INFO, '', 0, 'Test', (), None)
        formatted = handler.format(record)
        assert 'Test' in formatted

    def test_returns_handler(self):
        mock_widget = MagicMock()
        handler = setup_gui_logging(mock_widget)
        assert isinstance(handler, TextHandler)

    def test_multiple_calls_add_multiple_handlers(self):
        """Несколько вызовов — несколько хендлеров (не перезаписывает)."""
        import tkinter as tk
        mock_widget1 = MagicMock()
        mock_widget2 = MagicMock()

        h1 = setup_gui_logging(mock_widget1)
        h2 = setup_gui_logging(mock_widget2)

        root = logging.getLogger()
        assert h1 in root.handlers
        assert h2 in root.handlers
