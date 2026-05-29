@echo off
setlocal

set "APP_DIR=%~dp0"
set "PYTHONW=%APP_DIR%.venv\Scripts\pythonw.exe"
set "APP_MAIN=%APP_DIR%main.py"

if not exist "%PYTHONW%" (
    echo pythonw.exe not found: "%PYTHONW%"
    pause
    exit /b 1
)

if not exist "%APP_MAIN%" (
    echo main.py not found: "%APP_MAIN%"
    pause
    exit /b 1
)

start "" /D "%APP_DIR%" "%PYTHONW%" "%APP_MAIN%"
