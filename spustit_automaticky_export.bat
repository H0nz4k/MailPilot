@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0MailPilot.exe" (
    "%~dp0MailPilot.exe" --automatic
    exit /b %errorlevel%
)

set "VENV_PYTHON=%~dp0.venv\Scripts\python.exe"
if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" "%~dp0AutoReport_qt.py" --automatic --config "%~dp0config.json"
) else (
    py "%~dp0AutoReport_qt.py" --automatic --config "%~dp0config.json"
)

exit /b %ERRORLEVEL%
