@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

title Master Report Launcher v5.5

set "APPDIR=%~dp0APP"
set "MAINFILE=%APPDIR%\main.py"
set "LOGFILE=%~dp0startup_log.txt"
set "TARGET_PY=3.12"

set "PYTHON_CMD="
set "PYTHONW_CMD="

break > "%LOGFILE%"

call :log "========================================================"
call :log "MASTER REPORT CONSOLIDATOR v5.5"
call :log "========================================================"
call :log "Start time: %date% %time%"

echo ========================================================
echo MASTER REPORT CONSOLIDATOR v5.5
echo ========================================================
echo.
echo Проверка окружения...

if not exist "%MAINFILE%" (
    call :fail "Не найден файл main.py в папке APP."
)

cd /d "%APPDIR%" || call :fail "Не удалось перейти в папку APP."

call :step "Шаг 1/5. Поиск Python"
call :refresh_paths
call :find_python

if not defined PYTHON_CMD (
    call :log "Python не найден. Установите его с python.org"
    call :fail "Python не найден. Пожалуйста, установите Python 3.10 или выше."
)

call :step "Шаг 2/5. Проверка pip"
"%PYTHON_CMD%" -m pip --version >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    call :log "pip не найден. Восстанавливаю..."
    "%PYTHON_CMD%" -m ensurepip --upgrade >> "%LOGFILE%" 2>&1
)

call :step "Шаг 3/5. Обновление инструментов"
"%PYTHON_CMD%" -m pip install --user --upgrade pip setuptools wheel >> "%LOGFILE%" 2>&1

call :step "Шаг 4/5. Проверка библиотек"
"%PYTHON_CMD%" -c "import tkinter, pandas, openpyxl, yaml, ruamel.yaml, tkcalendar, pyxlsb, pydantic" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    call :log "Устанавливаю недостающие библиотеки..."
    "%PYTHON_CMD%" -m pip install --user -r "%~dp0requirements.txt" >> "%LOGFILE%" 2>&1
)

call :step "Шаг 5/5. Запуск приложения"
if defined PYTHONW_CMD (
    call :log "Запуск через pythonw (без консоли)"
    start "" "%PYTHONW_CMD%" "%MAINFILE%"
) else (
    call :log "Запуск через python (с консолью)"
    start "" "%PYTHON_CMD%" "%MAINFILE%"
)

echo.
echo -------------------------------------------------------
echo ГОТОВО! Программа запускается...
echo Это окно закроется автоматически через 3 секунды.
echo -------------------------------------------------------
timeout /t 3 >nul
exit /b 0


:step
echo %~1
call :log "%~1"
exit /b 0

:log
>> "%LOGFILE%" echo [%date% %time%] %~1
exit /b 0

:fail
echo.
echo [ОШИБКА] %~1
call :log "[ОШИБКА] %~1"
pause
exit /b 1

:refresh_paths
set "PATH=%PATH%;%USERPROFILE%\AppData\Local\Microsoft\WindowsApps;%LocalAppData%\Programs\Python\Launcher"
exit /b 0

:find_python
rem Ищем обычный python
for /f "delims=" %%I in ('where python 2^>nul') do (
    if not defined PYTHON_CMD set "PYTHON_CMD=%%~fI"
)
rem Ищем бесшумный pythonw
for /f "delims=" %%I in ('where pythonw 2^>nul') do (
    if not defined PYTHONW_CMD set "PYTHONW_CMD=%%~fI"
)
rem Если не нашли через where, пробуем лончер
if not defined PYTHON_CMD (
    py --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py"
)
if not defined PYTHONW_CMD (
    pyw --version >nul 2>&1
    if not errorlevel 1 set "PYTHONW_CMD=pyw"
)
exit /b 0
