@echo off
setlocal EnableExtensions
chcp 65001 >nul

:: Build the Inno Setup installer (installer_output\Master-Report_<ver>_Setup.exe)
:: from the portable build in build_exe\main.dist. Requires Inno Setup 6.

for %%I in ("%~dp0..") do set "ROOT=%%~fI"
cd /d "%ROOT%"

:: Version from the single source of truth (APP\__init__.py).
set "PY=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set "VER="
for /f "delims=" %%V in ('"%PY%" -c "import APP; print(APP.__version__)" 2^>nul') do set "VER=%%V"
if "%VER%"=="" set "VER=0.0"
echo [installer] version: %VER%

:: The portable build must exist first.
if not exist "build_exe\main.dist\main.exe" (
    echo [installer] build_exe\main.dist not found.
    echo Run tools\build_exe.bat first, then re-run this.
    pause
    exit /b 1
)

:: Locate the Inno Setup 6 compiler (ISCC.exe).
set "ISCC="
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    where iscc >nul 2>&1
    if not errorlevel 1 set "ISCC=iscc"
)
if not defined ISCC (
    echo [installer] Inno Setup 6 (ISCC.exe) not found.
    echo Install it from https://jrsoftware.org/isdl.php and re-run this bat.
    pause
    exit /b 1
)

echo [installer] compiling with: %ISCC%
"%ISCC%" /DMyAppVersion=%VER% installer.iss
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
    echo [installer] FAILED with exit code %RC%
    pause
    exit /b %RC%
)
echo.
echo [installer] Done: installer_output\Master-Report_%VER%_Setup.exe
pause
exit /b 0
