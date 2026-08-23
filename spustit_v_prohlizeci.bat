@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0MailPilot.exe" (
    start "" "%~dp0MailPilot.exe"
    exit /b 0
)

set "VENV_PYTHON=%~dp0.venv\Scripts\python.exe"
if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" "%~dp0stravovaci_nicegui.py" --browser
) else (
    py -3 "%~dp0stravovaci_nicegui.py" --browser
)

if errorlevel 1 pause
