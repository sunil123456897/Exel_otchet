@echo off
setlocal EnableExtensions
chcp 65001 >nul

:: Master-Report — build the standalone exe distribution (Nuitka).
:: Thin wrapper: locates the project Python and delegates to
:: tools\build_exe.py, which holds all the real build logic and flags.
::
:: Usage:
::   build_exe.bat              release build (no console window)
::   build_exe.bat --console    keep a console window (debugging launches)
::   build_exe.bat --zip        also produce a distributable .zip
::   build_exe.bat --clean      wipe build_exe\ before building
::
:: Output: <repo>\build_exe\main.dist\main.exe  (+ .zip if requested).

for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "ARGS=%*"

if exist "%PY%" goto :use_venv
where py >nul 2>&1
if not errorlevel 1 goto :use_py
where python >nul 2>&1
if not errorlevel 1 goto :use_python

echo [build_exe] Python not found. Install Python 3.12 or create the project .venv first.
pause
exit /b 1

:use_venv
echo [build_exe] Using: %PY%
"%PY%" "%ROOT%\tools\build_exe.py" %ARGS%
goto :done

:use_py
echo [build_exe] Using: py -3.12
py -3.12 "%ROOT%\tools\build_exe.py" %ARGS%
goto :done

:use_python
echo [build_exe] Using: python
python "%ROOT%\tools\build_exe.py" %ARGS%
goto :done

:done
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo.
    echo [build_exe] FAILED with exit code %RC%
    pause
    exit /b %RC%
)
echo.
echo [build_exe] Done.
pause
exit /b 0
