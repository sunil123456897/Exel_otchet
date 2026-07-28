@echo off
setlocal EnableExtensions
chcp 65001 >nul

:: Master-Report — launcher for the compiled EXE distribution.
::
:: The exe bundles its own runtime (no Python needed). This launcher just
:: runs main.exe and, if the process dies right away, shows the tail of
:: startup_log.txt so a non-technical user has something concrete to send
:: to support (mirrors the error-surfacing behaviour of the source-layout
:: launcher). Double-clicking main.exe directly works just the same.

set "HERE=%~dp0"
set "EXE=%HERE%main.exe"

if not exist "%EXE%" (
    echo [ERROR] main.exe not found next to this launcher.
    echo Copy the WHOLE program folder, not just this file.
    pause
    exit /b 1
)

:: Launch the app; it lives on as its own GUI process after we exit.
start "" "%EXE%"

:: Wait a few seconds. If the process is gone that quickly it crashed on
:: startup — surface the last log lines instead of a silent nothing.
timeout /t 3 /nobreak >nul
tasklist /FI "IMAGENAME eq main.exe" 2>nul | find /I "main.exe" >nul
if not errorlevel 1 exit /b 0

echo.
echo The program closed right after starting. Last log lines:
echo --------------------------------------------------------
if exist "%HERE%startup_log.txt" (
    powershell -NoProfile -Command "Get-Content -LiteralPath '%HERE%startup_log.txt' -Tail 15"
) else (
    echo startup_log.txt was not created.
)
echo --------------------------------------------------------
echo Send the text above (or the whole startup_log.txt) to support.
pause
exit /b 1
