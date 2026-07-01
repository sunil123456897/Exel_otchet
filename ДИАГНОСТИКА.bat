@echo off
setlocal EnableExtensions
chcp 65001 >nul

title Master-Report Full Diagnostics

set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"
set "SCRIPT=%ROOT%Диагностика.py"

if not exist "%PY%" goto no_python
if not exist "%SCRIPT%" goto no_script

cd /d "%ROOT%"
"%PY%" "%SCRIPT%" %*
if errorlevel 1 goto diag_failed

exit /b 0

:no_python
echo.
echo [ERROR] Python not found: %PY%
echo         Run ЗАПУСК.bat once first to create the environment.
echo.
pause
exit /b 1

:no_script
echo.
echo [ERROR] Diagnostic script not found: %SCRIPT%
echo.
pause
exit /b 1

:diag_failed
echo.
echo [ERROR] Diagnostic finished with errors.
echo         See ДИАГНОСТИКА_ОТЧЁТ.txt next to this file.
echo.
pause
exit /b 1
