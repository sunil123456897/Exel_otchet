@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul

title Master Report Launcher

set "APPDIR=%~dp0APP"
set "MAINFILE=%APPDIR%\main.py"
set "LOGFILE=%~dp0startup_log.txt"
set "TARGET_PY=3.12"
set "REQ_PACKAGES=pandas openpyxl pyyaml ruamel.yaml tkcalendar"

set "PYTHON_CMD="
set "PYTHONW_CMD="

break > "%LOGFILE%"

call :log ========================================================
call :log MASTER REPORT CONSOLIDATOR v5.5
call :log ========================================================
call :log Start time: %date% %time%
call :log Script dir: %~dp0
call :log APP dir: %APPDIR%
call :log Main file: %MAINFILE%
call :log.

echo ========================================================
echo MASTER REPORT CONSOLIDATOR v5.5
echo ========================================================
echo.
echo Лог будет сохранён в:
echo "%LOGFILE%"
echo.

if not exist "%MAINFILE%" (
    call :fail "Не найден файл main.py в папке APP."
)

cd /d "%APPDIR%" || call :fail "Не удалось перейти в папку APP."

call :step "Шаг 1/5. Поиск Python"
call :refresh_paths
call :find_python

if not defined PYTHON_CMD (
    call :log Python не найден. Пытаюсь установить автоматически...
    call :install_python
    call :refresh_paths
    call :find_python
)

if not defined PYTHON_CMD (
    call :fail "Python не найден и не установился автоматически."
)

call :log Python найден: %PYTHON_CMD%
if defined PYTHONW_CMD call :log Pythonw найден: %PYTHONW_CMD%

call :step "Шаг 2/5. Проверка pip"
call :runpy -m pip --version
if errorlevel 1 (
    call :log pip не найден. Пытаюсь восстановить через ensurepip...
    call :runpy -m ensurepip --upgrade
    call :runpy -m pip --version
    if errorlevel 1 (
        call :fail "pip недоступен даже после ensurepip."
    )
)
call :log pip доступен.

call :step "Шаг 3/5. Обновление базовых инструментов"
call :runpy -m pip install --user --disable-pip-version-check --no-warn-script-location --upgrade pip setuptools wheel

call :step "Шаг 4/5. Проверка и установка библиотек"
call :runpy -c "import tkinter; import pandas; import openpyxl; import yaml; import ruamel.yaml; import tkcalendar"
if errorlevel 1 (
    call :log Не все библиотеки установлены или отсутствует tkinter. Запускаю установку...
    call :runpy -m pip install --user --disable-pip-version-check --no-warn-script-location -r "%~dp0requirements.txt"
    if errorlevel 1 (
        call :fail "Не удалось установить библиотеки."
    )
    call :runpy -c "import tkinter; import pandas; import openpyxl; import yaml; import ruamel.yaml; import tkcalendar"
    if errorlevel 1 (
        call :fail "После установки библиотеки всё равно не импортируются. Если ошибка в tkinter — переустановите Python с галочкой 'tcl/tk and IDLE'."
    )
)
call :log Библиотеки готовы.

call :step "Шаг 5/5. Запуск приложения"
set "LAUNCHED=0"
if defined PYTHONW_CMD if exist "%PYTHONW_CMD%" (
    call :log Попытка запуска через pythonw: "%PYTHONW_CMD%" "%MAINFILE%"
    start "" "%PYTHONW_CMD%" "%MAINFILE%"
    set "LAUNCHED=1"
    rem Мы не можем легко проверить успех start, поэтому просто логируем
)

if "%LAUNCHED%"=="0" (
    call :log Запуск через python (в этом окне): "%PYTHON_CMD%" "%MAINFILE%"
    "%PYTHON_CMD%" "%MAINFILE%"
    if errorlevel 1 (
        call :fail "Приложение завершилось с ошибкой. Проверьте логи выше."
    )
)

call :log Скрипт завершил работу.
echo.
echo ========================================================
echo ГОТОВО. Если окно GUI не открылось — проверьте startup_log.txt
echo ========================================================
pause
exit /b 0


:step
echo %~1
call :log %~1
exit /b 0


:log
echo %~1
>> "%LOGFILE%" echo [%date% %time%] %~1
exit /b 0


:fail
echo.
echo [ОШИБКА] %~1
echo Лог: "%LOGFILE%"
call :log [ОШИБКА] %~1
call :log Завершение с ошибкой.
pause
exit /b 1


:runpy
call :log CMD: "%PYTHON_CMD%" %*
"%PYTHON_CMD%" %1 %2 %3 %4 %5 %6 %7 %8 %9 >> "%LOGFILE%" 2>&1
exit /b %errorlevel%


:refresh_paths
if exist "%USERPROFILE%\AppData\Local\Microsoft\WindowsApps" (
    set "PATH=%PATH%;%USERPROFILE%\AppData\Local\Microsoft\WindowsApps"
)
if exist "%LocalAppData%\Programs\Python\Launcher" (
    set "PATH=%PATH%;%LocalAppData%\Programs\Python\Launcher"
)
if exist "%LocalAppData%\Python\bin" (
    set "PATH=%PATH%;%LocalAppData%\Python\bin"
)
call :log PATH обновлён для текущего окна.
exit /b 0


:find_python
set "PYTHON_CMD="
set "PYTHONW_CMD="

call :log Ищу python через where...
where python >> "%LOGFILE%" 2>&1
if not errorlevel 1 (
    for /f "delims=" %%I in ('where python 2^>nul') do (
        if not defined PYTHON_CMD set "PYTHON_CMD=%%~fI"
    )
)

call :log Ищу pythonw через where...
where pythonw >> "%LOGFILE%" 2>&1
if not errorlevel 1 (
    for /f "delims=" %%I in ('where pythonw 2^>nul') do (
        if not defined PYTHONW_CMD set "PYTHONW_CMD=%%~fI"
    )
)

if not defined PYTHON_CMD (
    call :log Ищу Python в LocalAppData\Programs\Python...
    if exist "%LocalAppData%\Programs\Python" (
        for /d %%D in ("%LocalAppData%\Programs\Python\Python*") do (
            if exist "%%~fD\python.exe" if not defined PYTHON_CMD set "PYTHON_CMD=%%~fD\python.exe"
            if exist "%%~fD\pythonw.exe" if not defined PYTHONW_CMD set "PYTHONW_CMD=%%~fD\pythonw.exe"
        )
    )
)

if not defined PYTHON_CMD (
    call :log Проверяю launcher py...
    py --version >> "%LOGFILE%" 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py"
)

if not defined PYTHONW_CMD (
    where pyw >> "%LOGFILE%" 2>&1
    if not errorlevel 1 set "PYTHONW_CMD=pyw"
)

if defined PYTHON_CMD (
    call :log Python найден: %PYTHON_CMD%
) else (
    call :log Python пока не найден.
)

exit /b 0


:install_python
call :log === Попытка установки Python ===

call :try_winget_runtime
if not errorlevel 1 exit /b 0

call :try_winget_pymanager
if not errorlevel 1 exit /b 0

call :try_python_org_installer
if not errorlevel 1 exit /b 0

call :log Все автоматические способы установки исчерпаны.
exit /b 1


:try_winget_runtime
call :log [A] Пытаюсь установить Python через WinGet runtime...
winget --version >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    call :log WinGet недоступен.
    exit /b 1
)

winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements --disable-interactivity >> "%LOGFILE%" 2>&1
timeout /t 4 >nul
call :refresh_paths
call :find_python
if defined PYTHON_CMD (
    call :log Установка через WinGet runtime успешна.
    exit /b 0
)
call :log WinGet runtime не помог.
exit /b 1


:try_winget_pymanager
call :log [B] Пытаюсь установить Python Install Manager...
winget --version >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    call :log WinGet недоступен.
    exit /b 1
)

winget install 9NQ7512CXL7T -e --accept-package-agreements --accept-source-agreements --disable-interactivity >> "%LOGFILE%" 2>&1
timeout /t 5 >nul
call :refresh_paths

py --version >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    call :log После установки Python Install Manager команда py недоступна.
    exit /b 1
)

py install %TARGET_PY% >> "%LOGFILE%" 2>&1
timeout /t 5 >nul
call :refresh_paths
call :find_python
if defined PYTHON_CMD (
    call :log Установка через Python Install Manager успешна.
    exit /b 0
)

call :log Python Install Manager не помог.
exit /b 1


:try_python_org_installer
call :log [C] Пытаюсь скачать официальный установщик Python...
set "TMP_EXE=%TEMP%\python-%TARGET_PY%-setup.exe"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ProgressPreference='SilentlyContinue';" ^
    "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile '%TMP_EXE%'" >> "%LOGFILE%" 2>&1

if not exist "%TMP_EXE%" (
    call :log Не удалось скачать официальный установщик.
    exit /b 1
)

call :log Запускаю тихую установку Python...
"%TMP_EXE%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_pip=1 AssociateFiles=0 >> "%LOGFILE%" 2>&1
timeout /t 8 >nul

call :refresh_paths
call :find_python
if defined PYTHON_CMD (
    call :log Установка через python.org installer успешна.
    exit /b 0
)

call :log Официальный установщик не помог.
exit /b 1