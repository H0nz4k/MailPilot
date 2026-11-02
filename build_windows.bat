@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem MailPilot v12.9: jeden EXE bez konzole, ktery umi okno i bezobsluzne rezimy.

set "BUILD_VENV=%~dp0.venv"
if not exist "%BUILD_VENV%\Scripts\python.exe" set "BUILD_VENV=%~dp0.build-venv"
set "BUILD_PYTHON=%BUILD_VENV%\Scripts\python.exe"
set "OUTPUT=%~dp0dist\MailPilot"
set "ARCHIVE=%~dp0dist\MailPilot-v12.9-portable.zip"
set "APP_ICON=%~dp0assets\app_icon.ico"
set "NSSM_SOURCE=%~dp0..\nssm"

echo [1/6] Pripravuji build prostredi (%BUILD_VENV%)...
if not exist "%BUILD_PYTHON%" py -m venv "%BUILD_VENV%"
if errorlevel 1 goto :error

echo [2/5] Instaluji build zavislosti...
"%BUILD_PYTHON%" -m pip install -r "%~dp0requirements-build.txt"
if errorlevel 1 goto :error

echo [3/6] Generuji ikonu aplikace...
"%BUILD_PYTHON%" "%~dp0tools\generate_app_icon.py"
if errorlevel 1 goto :error

echo [4/6] Sestavuji aplikaci (PySide6, bez konzole)...
"%BUILD_PYTHON%" -m PyInstaller --noconfirm --clean ^
  --name MailPilot --onedir --windowed ^
  --specpath "%~dp0build" ^
  --icon "%APP_ICON%" ^
  --exclude-module nicegui ^
  --exclude-module webview ^
  --exclude-module tkinter ^
  --add-data "%~dp0assets;assets" ^
  --add-data "%~dp0config.example.json;." ^
  --add-data "%~dp0.env.example;." ^
  "%~dp0AutoReport_qt.py"
if errorlevel 1 goto :error

echo [5/6] Doplnuji spoustece a navod...
copy /Y "%~dp0README.md" "%OUTPUT%\README.md" >nul
copy /Y "%~dp0config.example.json" "%OUTPUT%\config.example.json" >nul
copy /Y "%~dp0.env.example" "%OUTPUT%\.env.example" >nul
copy /Y "%~dp0spustit_qt.bat" "%OUTPUT%\spustit_qt.bat" >nul
copy /Y "%~dp0spustit_automaticky_export.bat" "%OUTPUT%\spustit_automaticky_export.bat" >nul
copy /Y "%~dp0spustit_poctyemailem.bat" "%OUTPUT%\spustit_poctyemailem.bat" >nul
copy /Y "%~dp0spustit_uzaverku.bat" "%OUTPUT%\spustit_uzaverku.bat" >nul
copy /Y "%~dp0spustit_z17.bat" "%OUTPUT%\spustit_z17.bat" >nul
copy /Y "%~dp0UZIVATELSKY_NAVOD_MailPilot.pdf" "%OUTPUT%\UZIVATELSKY_NAVOD_MailPilot.pdf" >nul
copy /Y "%~dp0UZIVATELSKY_NAVOD_MailPilot_v12_8.pdf" "%OUTPUT%\UZIVATELSKY_NAVOD_MailPilot_v12_8.pdf" >nul
if exist "%NSSM_SOURCE%\*" (
  echo [5/6] Pribaluji NSSM do distribuce...
  robocopy "%NSSM_SOURCE%" "%OUTPUT%\nssm" /E /NFL /NDL /NJH /NJS /NC /NS >nul
)
"%OUTPUT%\MailPilot.exe" --version
if errorlevel 1 goto :error

echo [6/6] Vytvarim ZIP...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Compress-Archive -Path '%OUTPUT%\*' -DestinationPath '%ARCHIVE%' -Force"
if errorlevel 1 goto :error

echo.
echo HOTOVO: %ARCHIVE%
exit /b 0

:error
echo.
echo BUILD SELHAL. Zkontrolujte chybu vyse.
pause
exit /b 1
