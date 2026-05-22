from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = REPO_ROOT / "ЗАПУСК.bat"


def test_launcher_requires_root_requirements_file():
    launcher = LAUNCHER.read_text(encoding="utf-8")

    assert "requirements.txt" in launcher
    assert 'if not exist "%~dp0requirements.txt"' in launcher
    assert 'set "FAIL_MESSAGE=' in launcher
    assert "goto fail" in launcher


def test_launcher_writes_separate_gui_error_log_and_preflight():
    launcher = LAUNCHER.read_text(encoding="utf-8")

    assert "gui_error_log.txt" in launcher
    assert "GUI import preflight" in launcher
    assert "main.preflight_gui_imports()" in launcher


def test_launcher_avoids_redirection_inside_if_blocks_for_spaced_paths():
    launcher = LAUNCHER.read_text(encoding="utf-8")

    assert '>> "%LOGFILE%"' in launcher
    assert "if errorlevel 1 (" not in launcher


def test_launcher_uses_simple_failure_flow_safe_for_spaced_paths():
    launcher = LAUNCHER.read_text(encoding="utf-8")

    assert "setlocal EnableExtensions" in launcher
    assert "EnableDelayedExpansion" not in launcher
    assert "call :fail" not in launcher
    assert "|| call :fail" not in launcher


def test_launcher_avoids_multiline_if_blocks_that_break_cmd_parsing():
    launcher = LAUNCHER.read_text(encoding="utf-8")

    assert 'if not exist "%MAINFILE%" (' not in launcher
    assert 'if not exist "%~dp0requirements.txt" (' not in launcher
    assert "if errorlevel 1 (" not in launcher
    assert "if defined PYTHONW_CMD (" not in launcher


def test_launcher_avoids_chained_failure_commands_in_conditionals():
    launcher = LAUNCHER.read_text(encoding="utf-8")

    assert "& goto fail" not in launcher
    assert ":missing_main" in launcher
    assert ":missing_requirements" in launcher
    assert ":pip_repair_failed" in launcher
