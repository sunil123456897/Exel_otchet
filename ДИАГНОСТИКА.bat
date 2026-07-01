@echo off
chcp 65001 >nul
title Master-Report Full Diagnostics

REM Double-click launcher for the full diagnostic.
REM Uses the project .venv python; reports saved next to this file.
REM All console text is ASCII-only so it renders correctly on any
REM OEM code page (CP866 / CP1251) without depending on chcp timing.

set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"
set "SCRIPT=%ROOT%Диагностика.py"

if not exist "%PY%" (
    echo.
    echo [ERROR] Python not found: %PY%
    echo         Run ЗАПУСК.bat once first to create the environment.
    echo.
    pause
    exit /b 1
)

if not exist "%SCRIPT%" (
    echo.
    echo [ERROR] Diagnostic script not found: %SCRIPT%
    echo.
    pause
    exit /b 1
)

cd /d "%ROOT%"
"%PY%" "%SCRIPT%" %*
if errorlevel 1 (
    echo.
    echo [ERROR] Diagnostic finished with errors.
    echo         See ДИАГНОСТИКА_ОТЧЁТ.txt next to this file.
    echo.
    pause
    exit /b 1
)

exit /b 0
