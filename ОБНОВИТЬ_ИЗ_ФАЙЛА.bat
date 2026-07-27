@echo off
setlocal EnableExtensions
chcp 65001 >nul

title Master Report Offline Updater

set "ROOT=%~dp0"
set "VENV_PY=%ROOT%.venv\Scripts\python.exe"
set "SYS_PY=python"
set "RUN_UPDATER=%ROOT%tools\run_updater.py"

echo ============================================================
echo  Master-Report Offline Updater (from ZIP file)
echo ============================================================
echo.

:: ── 1. Locate a Python interpreter ───────────────────────────
set "PY_CMD="
if exist "%VENV_PY%" set "PY_CMD=%VENV_PY%"
if not defined PY_CMD (
    where %SYS_PY% >nul 2>&1
    if not errorlevel 1 set "PY_CMD=%SYS_PY%"
)
if not defined PY_CMD (
    echo [ERROR] Python not found.
    echo         Install Python 3.12+ and re-run ЗАПУСК.bat first to create .venv
    pause
    exit /b 1
)

:: ── 2. Locate the ZIP ────────────────────────────────────────
:: Accept the ZIP path as the first argument. If not given, prompt.
set "ZIP_PATH=%~1"
if "%ZIP_PATH%"=="" (
    echo Drag a release ZIP file onto this window and press Enter,
    echo or paste its full path:
    set /p "ZIP_PATH=> "
)
if "%ZIP_PATH%"=="" (
    echo [ERROR] No ZIP file specified.
    pause
    exit /b 1
)
:: Strip surrounding quotes if the user pasted them.
set "ZIP_PATH=%ZIP_PATH:"=%"
if not exist "%ZIP_PATH%" (
    echo [ERROR] File not found: %ZIP_PATH%
    pause
    exit /b 1
)

:: ── 3. Run the offline update ────────────────────────────────
if not exist "%RUN_UPDATER%" (
    echo [ERROR] Updater script not found: %RUN_UPDATER%
    pause
    exit /b 1
)

echo [updater] verifying ZIP, staging, self-checking, switching...
"%PY_CMD%" "%RUN_UPDATER%" --zip "%ZIP_PATH%" --launch
set "RC=%ERRORLEVEL%"

if "%RC%"=="0" (
    echo.
    echo ============================================================
    echo  Offline update complete. ЗАПУСК.bat has been launched.
    echo ============================================================
    exit /b 0
)

echo.
echo [ERROR] Offline update failed ^(exit code %RC%^).
echo         See update_log.txt for details.
echo.
echo Exit code reference:
echo   2 = ZIP not found / unreadable
echo   4 = self-check failed ^(L0/L1/L2^) — ZIP is corrupt or incompatible
echo   5 = update applied but rolled back after failure
echo   6 = updater internal error
pause
exit /b %RC%
