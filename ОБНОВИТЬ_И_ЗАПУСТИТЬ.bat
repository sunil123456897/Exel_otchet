@echo off
setlocal EnableExtensions
chcp 65001 >nul

title Master Report Updater

set "ROOT=%~dp0"
set "SCRIPT=%ROOT%tools\update_from_github.ps1"
set "POWERSHELL_CMD=powershell"

if not exist "%SCRIPT%" (
    echo [ERROR] Updater not found: %SCRIPT%
    pause
    exit /b 1
)

where pwsh >nul 2>&1
if not errorlevel 1 set "POWERSHELL_CMD=pwsh"

"%POWERSHELL_CMD%" -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -Launch
if errorlevel 1 (
    echo.
    echo [ERROR] Update failed. See details above and in update_log.txt.
    pause
    exit /b 1
)

exit /b 0
