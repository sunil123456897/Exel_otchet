@echo off
chcp 65001 >nul
title Полная диагностика Master-Report

REM Запуск полной диагностики двойным кликом.
REM Использует python из .venv проекта; отчёты сохраняются рядом.

set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"

if not exist "%PY%" (
    echo.
    echo [ОШИБКА] Не найден Python: %PY%
    echo          Запустите сначала ЗАПУСК.bat один раз, чтобы создать окружение.
    echo.
    pause
    exit /b 1
)

cd /d "%ROOT%"
"%PY%" "Диагностика.py" %*
if errorlevel 1 (
    echo.
    echo [ОШИБКА] Диагностика завершилась с ошибкой. См. ДИАГНОСТИКА_ОТЧЁТ.txt
    pause
    exit /b 1
)

exit /b 0
