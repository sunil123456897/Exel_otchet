@echo off
setlocal EnableExtensions
chcp 65001 >nul

:: Master-Report — update the compiled EXE distribution in place.
::
:: Runs updater.exe (a compiled tools/update_exe.py; no Python needed). By
:: default it pulls the latest GitHub release, verifies it against the
:: published SHA256SUMS, preserves your data (config/employees/cache.db),
:: and relaunches the app. Drag a release .zip onto this bat for an offline
:: update from a local file. On any failure the previous version is kept or
:: restored automatically.

set "HERE=%~dp0"
set "UPDATER=%HERE%updater.exe"

if not exist "%UPDATER%" (
    echo [ERROR] updater.exe not found next to this file.
    echo Copy the whole program folder, not just this file.
    pause
    exit /b 1
)

if not "%~1"=="" (
    echo [update] offline update from: %~1
    "%UPDATER%" --install-dir "%HERE%" --from-file "%~1"
) else (
    echo [update] checking GitHub for the latest release...
    "%UPDATER%" --install-dir "%HERE%"
)
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
    echo [update] FAILED with exit code %RC%.
    echo The previous version was kept or restored — your data is safe.
    pause
    exit /b %RC%
)
echo [update] Done.
timeout /t 3 >nul
exit /b 0
