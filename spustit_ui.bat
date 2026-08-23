@echo off
setlocal
cd /d "%~dp0"
echo Spoustim MailPilot...

if exist "%~dp0MailPilot.exe" (
    echo Nalezen MailPilot.exe, spoustim ho.
    start "" "%~dp0MailPilot.exe"
    exit /b 0
)

set "VENV_PYTHON=%~dp0.venv\Scripts\python.exe"
if exist "%VENV_PYTHON%" (
    echo Pouzivam .venv
    "%VENV_PYTHON%" "%~dp0stravovaci_nicegui.py"
) else (
    echo Pouzivam py -3
    py -3 "%~dp0stravovaci_nicegui.py"
)

if errorlevel 1 (
    echo.
    echo Spusteni selhalo. Podivejte se na chybu vyse.
    pause
)
