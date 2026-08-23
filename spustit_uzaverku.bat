@echo off
setlocal
cd /d "%~dp0"

if "%~1"=="" (
    echo Zadejte obdobi ve tvaru MMYYYY, napr. spustit_uzaverku.bat 072026
    echo nebo aktualni mesic z Jidelny: spustit_uzaverku.bat am
    echo primo: MailPilot.exe --zaverka_072026  nebo  MailPilot.exe --zaverka_am
    exit /b 2
)

set "FLAG=%~1"
if /I "%FLAG%"=="am" set "FLAG=--zaverka_am"
if /I "%FLAG%"=="--zaverka_am" set "FLAG=--zaverka_am"
if /I "%FLAG%"=="--uzaverka_am" set "FLAG=--zaverka_am"
if /I not "%FLAG%"=="--zaverka_am" (
    echo %FLAG% | findstr /r /c:"^--uzaverka_[0-9][0-9][0-9][0-9][0-9][0-9]$" /c:"^--zaverka_[0-9][0-9][0-9][0-9][0-9][0-9]$" >nul
    if errorlevel 1 set "FLAG=--zaverka_%~1"
)

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
