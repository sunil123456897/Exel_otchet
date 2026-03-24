@echo off
setlocal
echo ========================================================
echo         MASTER REPORT CONSOLIDATOR v5.5
echo ========================================================
echo.

:: Change to APP directory
cd /d "%~dp0APP"
if %errorlevel% neq 0 (
    echo [!] ERROR: Could not find APP directory.
    pause
    exit /b
)

:: 1. Check Python
echo [1/3] Checking Python installation...

set "PYTHON_CMD="
set "PYTHONW_CMD="

:: Try standard PATH commands first
py --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=py"
    set "PYTHONW_CMD=pyw"
    goto :PYTHON_FOUND
)

python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python"
    set "PYTHONW_CMD=pythonw"
    goto :PYTHON_FOUND
)

:: Try finding Python in local AppData (standard install location without admin rights)
set "LOCAL_PYTHON_DIR=%USERPROFILE%\AppData\Local\Programs\Python"
if exist "%LOCAL_PYTHON_DIR%" (
    for /d %%i in ("%LOCAL_PYTHON_DIR%\Python*") do (
        if exist "%%i\python.exe" (
            set "PYTHON_CMD=%%i\python.exe"
            set "PYTHONW_CMD=%%i\pythonw.exe"
            goto :PYTHON_FOUND
        )
    )
)

echo [!] ERROR: Python is not found.
echo [!] Please install Python from Windows Store or ask Administrator.
pause
exit /b

:PYTHON_FOUND
echo [+] Python is present (%PYTHON_CMD%).

:: 2. Check Libraries
echo [2/3] Checking required libraries (pandas, openpyxl, tkcalendar, ruamel.yaml)...
%PYTHON_CMD% -c "import pandas; import openpyxl; import yaml; import ruamel.yaml; import tkcalendar" >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Some libraries are missing. Installing now...
    %PYTHON_CMD% -m pip install pandas openpyxl pyyaml ruamel.yaml tkcalendar --user --no-warn-script-location --disable-pip-version-check
    if %errorlevel% neq 0 (
        echo [!] ERROR: Failed to install libraries. Check internet connection.
        pause
        exit /b
    )
    echo [+] Libraries installed successfully.
) else (
    echo [+] Libraries are present.
)

:: 3. Launch App
echo [3/3] Launching Master Report...
echo.
start "" %PYTHONW_CMD% main.py
if %errorlevel% neq 0 (
    echo [!] ERROR: Failed to start main.py.
    pause
    exit /b
)

echo ========================================================
echo   APP STARTED! YOU CAN CLOSE THIS WINDOW NOW.
echo ========================================================
timeout /t 5 >nul
exit
