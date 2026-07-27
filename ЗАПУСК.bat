@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "PIP_NO_KEYRING=1"
set "PIP_DISABLE_PIP_VERSION_CHECK=1"
set "PIP_NO_INPUT=1"

set "ARG1=%~1"
set "ARG2=%~2"

:: Determine APPDIR: prefer versioned layout (versions/<semver>/APP/)
:: selected by current.json — that's the directory the atomic updater
:: (ОБНОВИТЬ_И_ЗАПУСТИТЬ.bat → tools/run_updater.py) writes to. Fall
:: back to the classic %~dp0APP location if no versioned install exists
:: (pre-Stage-4 layout, or first run before any update).
::
:: We avoid nested for/if blocks (cmd's delayed-expansion makes them
:: fragile) and instead call out to PowerShell to read current.json
:: and echo back either the versioned APP path or empty. PowerShell
:: is always available on Windows 10/11.
set "INSTALL_ROOT=%~dp0"
set "APPDIR=%INSTALL_ROOT%APP"
set "CURRENT_JSON=%INSTALL_ROOT%current.json"
if exist "%CURRENT_JSON%" goto :resolve_appdir
goto :appdir_resolved

:resolve_appdir
for /f "delims=" %%V in ('powershell -NoProfile -Command "if (Test-Path '%CURRENT_JSON%') { $j = Get-Content -LiteralPath '%CURRENT_JSON%' -Raw -Encoding UTF8 | ConvertFrom-Json; if ($j.version) { $cand = '%INSTALL_ROOT%versions\' + $j.version + '\APP'; if (Test-Path (Join-Path $cand 'main.py')) { $cand } } }" 2^>nul') do set "APPDIR=%%V"
:appdir_resolved
set "MAINFILE=%APPDIR%\main.py"

:: Single source of truth for the version is APP/__init__.py and
:: APP/core/__init__.py. The launcher used to extract the literal at
:: boot via findstr/powershell, but CMD's quoting rules around repo
:: paths with spaces ("Dlia Dashi\...") made every variant fragile.
:: We now defer version display to the GUI itself (which reads it via
:: `from APP import __version__`); the launcher just shows a generic
:: title. The version-source tests in tests/test_single_version_source.py
:: enforce that APP/__init__.py is the only Python-side source of truth.
set "APP_VERSION=see GUI"

title Master Report Launcher
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
call :log "MASTER REPORT CONSOLIDATOR (version in GUI title)"
call :log "========================================================"
call :log "Start time: %date% %time%"

echo ========================================================
echo MASTER REPORT CONSOLIDATOR
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
set "FAIL_MESSAGE=Python not found. Please install Python 3.12 or newer and make sure it is in PATH."
goto fail

:python_too_old
set "PYVER=unknown"
for /f "delims=" %%V in ('"%PYTHON_CMD%" -c "import sys; print(sys.version.split()[0])" 2^>nul') do set "PYVER=%%V"
call :log "Python too old: %PYVER%"
set "FAIL_MESSAGE=Python %PYVER% is too old. Install Python 3.12 or newer from python.org and tick 'Add Python to PATH'."
goto fail

:tkinter_missing
call :log "tkinter is missing from this Python"
set "FAIL_MESSAGE=tkinter (the GUI toolkit) is missing from this Python. Reinstall Python from python.org with 'tcl/tk and IDLE' enabled, then re-run."
goto fail

:python_ok

:: Verify the interpreter is new enough. README/pyproject require Python 3.12+
:: (py312 target; some runtime helpers use 3.12 APIs with graceful
:: degradation). On a clean PC with an old Python, failing here with a clear
:: message is far better than a cryptic TypeError at the GUI preflight step.
"%PYTHON_CMD%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1
if errorlevel 1 goto python_too_old

:: tkinter ships WITH Python (it is not pip-installable). If it is missing the
:: interpreter was installed without tcl/tk — say so explicitly instead of
:: letting pip "succeed" and then failing cryptically at the GUI preflight.
"%PYTHON_CMD%" -c "import tkinter" >nul 2>&1
if errorlevel 1 goto tkinter_missing

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
if exist "%LOGFILE%" type "%LOGFILE%"
set "FAIL_MESSAGE=Could not repair pip."
goto fail

:tool_upgrade_failed
if exist "%LOGFILE%" type "%LOGFILE%"
set "FAIL_MESSAGE=Could not update pip/setuptools/wheel."
goto fail

:requirements_install_failed
if exist "%LOGFILE%" type "%LOGFILE%"
set "FAIL_MESSAGE=Could not install dependencies from requirements.txt. Check your internet connection (or proxy settings), then re-run ЗАПУСК.bat."
goto fail

:gui_preflight_failed
if exist "%GUIERRLOG%" type "%GUIERRLOG%"
set "FAIL_MESSAGE=GUI startup failed."
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
if errorlevel 1 exit /b 1
:: Reject a venv built by an older Python (e.g. created before 3.12 was
:: installed, or copied from another PC) so it gets RE-CREATED with the
:: right interpreter — otherwise the stale venv keeps failing the version
:: gate even after the user installs Python 3.12.
"%VENV_DIR%\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>&1
exit /b %errorlevel%
