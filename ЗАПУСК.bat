@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "ARG1=%~1"
set "ARG2=%~2"

title Master Report Launcher v5.5

set "APPDIR=%~dp0APP"
set "MAINFILE=%APPDIR%\main.py"
set "LOGFILE=%~dp0startup_log.txt"
set "GUIERRLOG=%~dp0gui_error_log.txt"
set "TARGET_PY=3.12"
set "VENV_DIR=%~dp0.venv"
set "FAIL_MESSAGE="

set "PYTHON_CMD="
set "PYTHONW_CMD="
set "PYTHON_IS_VENV="

:: Clean up inherited environment variables if they contain empty quotes or invalid placeholders
if "%PYTHON_CMD%"=="""" set "PYTHON_CMD="
if "%PYTHON_CMD%"=="""""" set "PYTHON_CMD="
if "%PYTHONW_CMD%"=="""" set "PYTHONW_CMD="
if "%PYTHONW_CMD%"=="""""" set "PYTHONW_CMD="

break > "%LOGFILE%"
break > "%GUIERRLOG%"

call :log "========================================================"
call :log "MASTER REPORT CONSOLIDATOR v5.5"
call :log "========================================================"
call :log "Start time: %date% %time%"

echo ========================================================
echo MASTER REPORT CONSOLIDATOR v5.5
echo ========================================================
echo.
echo Checking environment...

if not exist "%MAINFILE%" goto missing_main

if not exist "%~dp0requirements.txt" goto missing_requirements

cd /d "%APPDIR%"
if errorlevel 1 goto appdir_unavailable

call :step "Step 1/5. Finding Python"
call :refresh_paths
call :find_python

if not defined PYTHON_CMD goto python_not_found
if "%PYTHON_CMD%"=="""" goto python_not_found
if "%PYTHON_CMD%"=="""""" goto python_not_found
goto python_ok

:python_not_found
call :log "Python not found. Install it from python.org"
set "FAIL_MESSAGE=Python not found. Please install Python 3.10 or newer and make sure it is in PATH."
goto fail

:python_ok

call :step "Step 2/5. Checking pip"
"%PYTHON_CMD%" -m pip --version >> "%LOGFILE%" 2>&1
if not errorlevel 1 goto pip_ok
call :log "pip missing. Repairing..."
"%PYTHON_CMD%" -m ensurepip --upgrade >> "%LOGFILE%" 2>&1
if errorlevel 1 goto pip_repair_failed

:pip_ok

call :step "Step 3/5. Checking packaging tools"
"%PYTHON_CMD%" -m pip --version >> "%LOGFILE%" 2>&1
if errorlevel 1 goto tool_upgrade_failed

call :step "Step 4/5. Checking libraries"
"%PYTHON_CMD%" -c "import tkinter, openpyxl, yaml, ruamel.yaml, tkcalendar, pyxlsb, pydantic, python_calamine" >> "%LOGFILE%" 2>&1
if errorlevel 1 goto install_requirements
goto after_requirements

:install_requirements
call :log "Installing missing libraries..."
if defined PYTHON_IS_VENV (
    "%PYTHON_CMD%" -m pip install -r "%~dp0requirements.txt" >> "%LOGFILE%" 2>&1
) else (
    call :log "WARNING: local .venv is unavailable; installing into user site-packages."
    "%PYTHON_CMD%" -m pip install --user -r "%~dp0requirements.txt" >> "%LOGFILE%" 2>&1
)
if errorlevel 1 goto requirements_install_failed

:after_requirements

call :step "Step 4.5/5. GUI import preflight"
"%PYTHON_CMD%" -c "import main; main.preflight_gui_imports()" >> "%GUIERRLOG%" 2>&1
if not errorlevel 1 goto gui_ok
call :log "GUI preflight failed. See gui_error_log.txt"
goto gui_preflight_failed

:gui_ok

call :step "Step 5/5. Launching application"
if not defined PYTHONW_CMD goto start_python
call :log "Launching via pythonw (no console)"
start "" "%PYTHONW_CMD%" "%MAINFILE%"
goto launch_done

:start_python
call :log "Launching via python (with console)"
start "" "%PYTHON_CMD%" "%MAINFILE%"

:launch_done

echo.
echo -------------------------------------------------------
echo DONE. The application is starting...
echo This window will close automatically in 3 seconds.
echo -------------------------------------------------------
timeout /t 3 >nul
exit /b 0


:step
echo %~1
call :log "%~1"
exit /b 0

:log
>> "%LOGFILE%" echo [%date% %time%] %~1
exit /b 0

:fail
echo.
echo [ERROR] %FAIL_MESSAGE%
call :log "[ERROR] %FAIL_MESSAGE%"
if not "%ARG1%"=="/nopause" if not "%ARG2%"=="/nopause" pause
exit /b 1

:missing_main
set "FAIL_MESSAGE=main.py was not found inside APP."
goto fail

:missing_requirements
set "FAIL_MESSAGE=requirements.txt was not found next to the launcher. Copy the whole project, not just APP."
goto fail

:appdir_unavailable
set "FAIL_MESSAGE=Could not switch into the APP directory."
goto fail

:pip_repair_failed
set "FAIL_MESSAGE=Could not repair pip. See startup_log.txt for details."
goto fail

:tool_upgrade_failed
set "FAIL_MESSAGE=Could not update pip/setuptools/wheel. See startup_log.txt for details."
goto fail

:requirements_install_failed
set "FAIL_MESSAGE=Could not install dependencies from requirements.txt. See startup_log.txt for details."
goto fail

:gui_preflight_failed
set "FAIL_MESSAGE=GUI startup failed. See gui_error_log.txt for details."
goto fail

:refresh_paths
set "PATH=%PATH%;%USERPROFILE%\AppData\Local\Microsoft\WindowsApps;%LocalAppData%\Programs\Python\Launcher"
exit /b 0

:find_python
rem 1. Prefer an isolated local virtual environment next to the launcher.
if exist "%VENV_DIR%\Scripts\python.exe" (
    call :check_venv_valid
    if not errorlevel 1 (
        set "PYTHON_CMD=%VENV_DIR%\Scripts\python.exe"
        set "PYTHON_IS_VENV=1"
        if exist "%VENV_DIR%\Scripts\pythonw.exe" set "PYTHONW_CMD=%VENV_DIR%\Scripts\pythonw.exe"
        goto python_launcher_done
    )
    call :log "WARNING: Local .venv is broken (likely copied from another PC). Re-creating..."
    call :cleanup_broken_venv
)

rem 2. Try to create the local virtual environment using different Python handles.
rem Try py -3.12 first
py -%TARGET_PY% --version >nul 2>&1
if not errorlevel 1 (
    call :log "Creating local virtual environment using py -%TARGET_PY%: %VENV_DIR%"
    py -%TARGET_PY% -m venv "%VENV_DIR%" >> "%LOGFILE%" 2>&1
    goto check_created_venv
)

rem Try py launcher generally
py --version >nul 2>&1
if not errorlevel 1 (
    call :log "Creating local virtual environment using py: %VENV_DIR%"
    py -m venv "%VENV_DIR%" >> "%LOGFILE%" 2>&1
    goto check_created_venv
)

rem Try python in PATH
python --version >nul 2>&1
if not errorlevel 1 (
    call :log "Creating local virtual environment using python: %VENV_DIR%"
    python -m venv "%VENV_DIR%" >> "%LOGFILE%" 2>&1
    goto check_created_venv
)

:check_created_venv
if exist "%VENV_DIR%\Scripts\python.exe" (
    call :check_venv_valid
    if not errorlevel 1 (
        set "PYTHON_CMD=%VENV_DIR%\Scripts\python.exe"
        set "PYTHON_IS_VENV=1"
        if exist "%VENV_DIR%\Scripts\pythonw.exe" set "PYTHONW_CMD=%VENV_DIR%\Scripts\pythonw.exe"
        goto python_launcher_done
    )
)
call :log "WARNING: could not create local .venv; falling back to PATH Python."

rem 3. Fallback to regular python in PATH
for /f "delims=" %%I in ('where python 2^>nul') do (
    if not defined PYTHON_CMD set "PYTHON_CMD=%%~fI"
)
for /f "delims=" %%I in ('where pythonw 2^>nul') do (
    if not defined PYTHONW_CMD set "PYTHONW_CMD=%%~fI"
)

rem 4. Last fallback to py launcher directly
if defined PYTHON_CMD goto python_launcher_done
py --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py"
    set "PYTHONW_CMD=pyw"
)

:python_launcher_done
exit /b 0

:cleanup_broken_venv
set "TEMP_VENV=%VENV_DIR%_broken_%RANDOM%"
move "%VENV_DIR%" "%TEMP_VENV%" >nul 2>&1
if exist "%VENV_DIR%" rd /s /q "%VENV_DIR%" >nul 2>&1
if exist "%TEMP_VENV%" rd /s /q "%TEMP_VENV%" >nul 2>&1
exit /b 0

:check_venv_valid
for %%I in ("%VENV_DIR%\Scripts\python.exe") do (
    if %%~zI LSS 10000 exit /b 1
)
"%VENV_DIR%\Scripts\python.exe" --version >nul 2>&1
exit /b %errorlevel%
