@echo off
setlocal EnableExtensions
chcp 65001 >nul

title Master Report Updater

set "ROOT=%~dp0"
set "VENV_PY=%ROOT%.venv\Scripts\python.exe"
set "SYS_PY=python"
set "RUN_UPDATER=%ROOT%tools\run_updater.py"
set "PS1_FALLBACK=%ROOT%tools\update_from_github.ps1"

echo ============================================================
echo  Master-Report Updater
echo ============================================================
echo.

:: ── 1. Locate a Python interpreter ───────────────────────────
:: Prefer the project's venv (has all deps); fall back to system python.
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

:: ── 2. Run the new Python updater ────────────────────────────
if not exist "%RUN_UPDATER%" (
    echo [ERROR] Updater script not found: %RUN_UPDATER%
    pause
    exit /b 1
)

echo [updater] contacting GitHub, downloading, verifying, switching...
"%PY_CMD%" "%RUN_UPDATER%" --branch main --launch
set "RC=%ERRORLEVEL%"

if "%RC%"=="0" goto done

:: ── 3. Fallback to legacy PowerShell updater ─────────────────
:: If the new Python updater failed for a reason that looks like a
:: Python-side problem (module import, syntax, etc.), try the old
:: PowerShell path — it has been the production updater for months
:: and handles a different class of failures.
echo.
echo [updater] Python updater exited with code %RC%.
echo [updater] Falling back to legacy PowerShell updater...
echo.

if not exist "%PS1_FALLBACK%" (
    echo [ERROR] Fallback not found: %PS1_FALLBACK%
    echo         See update_log.txt for details.
    pause
    exit /b %RC%
)

set "POWERSHELL_CMD=powershell"
where pwsh >nul 2>&1
if not errorlevel 1 set "POWERSHELL_CMD=pwsh"

"%POWERSHELL_CMD%" -NoProfile -ExecutionPolicy Bypass -File "%PS1_FALLBACK%" -Launch
set "RC2=%ERRORLEVEL%"
if not "%RC2%"=="0" (
    echo.
    echo [ERROR] Both updaters failed.
    echo         Python updater exit code: %RC%
    echo         PowerShell updater exit code: %RC2%
    echo         See update_log.txt for details.
    pause
    exit /b %RC2%
)

:done
echo.
echo ============================================================
echo  Update complete. ЗАПУСК.bat has been launched.
echo ============================================================
exit /b 0
