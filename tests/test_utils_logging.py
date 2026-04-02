import logging
import tkinter as tk
import queue
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

def test_gui_log_suppression():
    """
    Verify that DEBUG messages (like TEMPORAL WARNING) are suppressed in the GUI log
    when the log level is set to INFO.
    """
    mock_text_widget = MagicMock()
    # Reset root logger handlers to avoid interference
    root_logger = logging.getLogger()
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
        
    handler = setup_gui_logging(mock_text_widget)
    handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    
    # Emit messages
    logging.debug("TEMPORAL WARNING: Invalid date 31.04")
    logging.info("Processing started")
    
    # Check the queue
    messages = []
    while not handler.msg_queue.empty():
        messages.append(handler.msg_queue.get_nowait())
        
    assert "INFO: Processing started" in messages
    assert any("TEMPORAL WARNING" in m for m in messages) is False
    
    # Cleanup
    root_logger.removeHandler(handler)

def test_temporal_warning_suppression_real_call():
    """
    Verify that the actual extract_date_from_sheet call with an invalid date
    doesn't produce an INFO log that would reach the GUI.
    """
    from core.infra.ingestion_utils import extract_date_from_sheet
    
    mock_text_widget = MagicMock()
    root_logger = logging.getLogger()
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
        
    handler = setup_gui_logging(mock_text_widget)
    
    # Call the function that used to produce a warning
    extract_date_from_sheet("31.04")
    
    # Check the queue
    messages = []
    while not handler.msg_queue.empty():
        messages.append(handler.msg_queue.get_nowait())
        
    assert len(messages) == 0
    
    # Cleanup
    root_logger.removeHandler(handler)
