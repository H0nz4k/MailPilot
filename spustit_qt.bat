@echo off
setlocal
cd /d "%~dp0"
echo Spoustim MailPilot v12.7 (desktopove rozhrani PySide6)...

if exist "%~dp0MailPilot.exe" (
    echo Nalezen MailPilot.exe, spoustim ho.
    start "" "%~dp0MailPilot.exe"
    exit /b 0
)

set "VENV_PYTHON=%~dp0.venv\Scripts\python.exe"
set "BUILD_PYTHON=%~dp0.build-venv\Scripts\python.exe"
if exist "%VENV_PYTHON%" (
    echo Pouzivam .venv
    "%VENV_PYTHON%" "%~dp0AutoReport_qt.py" %*
) else if exist "%BUILD_PYTHON%" (
    echo Pouzivam .build-venv
    "%BUILD_PYTHON%" "%~dp0AutoReport_qt.py" %*
) else (
    echo Pouzivam py -3
    py -3 "%~dp0AutoReport_qt.py" %*
)

if errorlevel 1 (
    echo.
    echo Spusteni selhalo. Podivejte se na chybu vyse.
    echo Chybi-li PySide6, nainstalujte je: py -3 -m pip install -r requirements.txt
    pause
)
