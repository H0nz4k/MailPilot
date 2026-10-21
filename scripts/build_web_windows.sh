#!/usr/bin/env bash
# Build browser-based MailPilot for Windows, using Git Bash (not PowerShell).
# Produces dist-web/MailPilot-Web/MailPilot-Web.exe and MailPilot-Web-Worker.exe.
set -Eeuo pipefail

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) ;;
  *) echo "CHYBA: tento build spoustej na Windows v Git Bash." >&2; exit 2 ;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
VENV="$ROOT/.venv-web"
PY="$VENV/Scripts/python.exe"
if [[ ! -f "$PY" ]]; then
  command -v py >/dev/null 2>&1 || { echo "CHYBA: nainstaluj Python 3 pro Windows (py launcher)." >&2; exit 2; }
  py -3 -m venv "$VENV"
fi
echo "[1/3] Instaluji zavislosti webove verze..."
"$PY" -m pip install --disable-pip-version-check -r "$ROOT/requirements-web-build.txt"

WIN_ROOT="$(cygpath -w "$ROOT")"
DIST="$ROOT/dist-web"
mkdir -p "$DIST"
echo "[2/3] Sestavuji webovou aplikaci pro prohlizec..."
"$PY" -m PyInstaller --noconfirm --clean --onedir --console --noupx \
  --name MailPilot-Web \
  --distpath "$DIST" \
  --workpath "$ROOT/build/web-gui" \
  --specpath "$ROOT/build/web-spec" \
  --icon "$WIN_ROOT\\assets\\app_icon.ico" \
  --collect-all nicegui \
  --collect-submodules psycopg \
  --hidden-import services.web_mail_gui \
  --hidden-import services.web_mail_settings_gui \
  --hidden-import services.web_mail_cooking_days \
  --add-data "$WIN_ROOT\\assets;assets" \
  --add-data "$WIN_ROOT\\config.example.json;." \
  "$WIN_ROOT\\stravovaci_nicegui.py"

echo "[3/3] Sestavuji bezobsluznou sluzbu pro NSSM..."
"$PY" -m PyInstaller --noconfirm --clean --onefile --console --noupx \
  --name MailPilot-Web-Worker \
  --distpath "$ROOT/dist-web-worker" \
  --workpath "$ROOT/build/web-worker" \
  --specpath "$ROOT/build/web-spec" \
  --collect-submodules psycopg \
  "$WIN_ROOT\\web_mail_worker_main.py"

APP="$DIST/MailPilot-Web"
cp "$ROOT/dist-web-worker/MailPilot-Web-Worker.exe" "$APP/"
cp "$ROOT/config.example.json" "$APP/config.example.json"
if [[ ! -f "$APP/config.json" ]]; then
  cp "$APP/config.example.json" "$APP/config.json"
fi
cat > "$APP/START_WEB.cmd" <<'CMD'
@echo off
cd /d "%~dp0"
"%~dp0MailPilot-Web.exe" --browser
if errorlevel 1 pause
CMD
cat > "$APP/START_WORKER_MANUAL.cmd" <<'CMD'
@echo off
cd /d "%~dp0"
"%~dp0MailPilot-Web-Worker.exe" --config "%~dp0config.json"
if errorlevel 1 pause
CMD
echo "HOTOVO: $APP/MailPilot-Web.exe"
echo "OTEVRENI: v Git Bash spust ./dist-web/MailPilot-Web/MailPilot-Web.exe --browser"
echo "NSSM instaluje sluzbu z MailPilot-Web-Worker.exe az po tvem kliknuti v nastaveni."
