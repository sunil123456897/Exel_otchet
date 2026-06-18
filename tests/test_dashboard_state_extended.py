from core.ui.dashboard_state import read_recent_log_errors, read_recent_logs

def test_read_recent_log_errors_filters_only_errors(tmp_path):
    log_file = tmp_path / "test_error.log"
    log_file.write_text(
        "INFO - App started\n"
        "ERROR - Database connection failed\n"
        "WARNING - Low memory\n"
        "CRITICAL - Out of disk space\n"
        "INFO - Retry success\n",
        encoding="utf-8"
    )
    
    errors = read_recent_log_errors([log_file], limit=5)
    assert len(errors) == 2
    assert "Database connection failed" in errors[0]
    assert "Out of disk space" in errors[1]

def test_read_recent_logs_reads_all_lines(tmp_path):
    log_file = tmp_path / "test_full.log"
    log_file.write_text(
        "INFO - Starting step 1\n"
        "DEBUG - Loading resources\n"
        "INFO - Finished step 1\n"
        "WARNING - Connection slow\n",
        encoding="utf-8"
    )
    
    logs = read_recent_logs([log_file], limit=3)
    assert len(logs) == 3
    assert "DEBUG - Loading resources" in logs[0]
    assert "INFO - Finished step 1" in logs[1]
    assert "WARNING - Connection slow" in logs[2]
