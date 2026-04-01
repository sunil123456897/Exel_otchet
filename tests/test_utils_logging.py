import logging
import tkinter as tk
from unittest.mock import MagicMock, patch
from core.infra.utils_logging import TextHandler, setup_gui_logging

def test_text_handler_emit():
    mock_text_widget = MagicMock()
    handler = TextHandler(mock_text_widget)
    record = logging.LogRecord('test', logging.INFO, 'pathname', 10, 'test message', None, None)
    
    # We need to set a formatter or use the default one
    handler.setFormatter(logging.Formatter('%(message)s'))
    
    handler.emit(record)
    
    assert not handler.msg_queue.empty()
    assert handler._is_scheduled is True
    mock_text_widget.after_idle.assert_called_once_with(handler._process_queue)

def test_text_handler_process_queue():
    mock_text_widget = MagicMock()
    handler = TextHandler(mock_text_widget)
    handler.msg_queue.put("message 1")
    handler.msg_queue.put("message 2")
    handler._is_scheduled = True
    
    handler._process_queue()
    
    assert handler.msg_queue.empty()
    assert handler._is_scheduled is False
    # Check that configure was called with 'normal' then 'disabled'
    # The order matters, but assert_any_call is easier
    mock_text_widget.configure.assert_any_call(state='normal')
    mock_text_widget.configure.assert_any_call(state='disabled')
    mock_text_widget.insert.assert_any_call(tk.END, "message 1\n")
    mock_text_widget.insert.assert_any_call(tk.END, "message 2\n")
    mock_text_widget.yview.assert_called_once_with(tk.END)

def test_setup_gui_logging():
    mock_text_widget = MagicMock()
    with patch('logging.getLogger') as mock_get_logger:
        mock_root_logger = MagicMock()
        mock_get_logger.return_value = mock_root_logger
        
        handler = setup_gui_logging(mock_text_widget)
        
        assert isinstance(handler, TextHandler)
        mock_root_logger.addHandler.assert_called_once_with(handler)
        mock_root_logger.setLevel.assert_called_once_with(logging.INFO)
        
        # Cleanup: remove handler to not affect other tests
        mock_root_logger.removeHandler(handler)
