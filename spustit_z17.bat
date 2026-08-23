@echo off
setlocal
cd /d "%~dp0"

if "%~1"=="" (
    echo Zadejte rok vykazu, napr. spustit_z17.bat 2026
    echo nebo primo: MailPilot.exe --z17_2026
    exit /b 2
)

set "FLAG=%~1"
echo %FLAG% | findstr /r /c:"^--z17_[0-9][0-9][0-9][0-9]$" >nul
if errorlevel 1 set "FLAG=--z17_%~1"

if exist "%~dp0MailPilot.exe" (
    "%~dp0MailPilot.exe" %FLAG%
    exit /b %errorlevel%
)

set "VENV_PYTHON=%~dp0.venv\Scripts\python.exe"
if exist "%VENV_PYTHON%" (
    "%VENV_PYTHON%" "%~dp0AutoReport_qt.py" %FLAG% --config "%~dp0config.json"
) else (
    py "%~dp0AutoReport_qt.py" %FLAG% --config "%~dp0config.json"
)

exit /b %ERRORLEVEL%
