#!/usr/bin/env bash
# Build browser-based DataShip for Windows, using Git Bash (not PowerShell).
# Produces dist-web/DataShip/DataShip.exe and DataShip-Worker.exe.
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
  command -v py >/dev/null 2>&1 || { echo "CHYBA: nainstaluj Python 3.12 pro Windows (py launcher)." >&2; exit 2; }
  py -3.12 -m venv "$VENV" || { echo "CHYBA: nainstaluj Python 3.12 x64 a zopakuj build." >&2; exit 2; }
fi
echo "[1/3] Instaluji zavislosti webove verze..."
"$PY" -m pip install --disable-pip-version-check -r "$ROOT/requirements-web-build.txt"

WIN_ROOT="$(cygpath -w "$ROOT")"
DIST="$ROOT/dist-web"
APP="$DIST/DataShip"
LEGACY_APP="$DIST/MailPilot-Web"
PRESERVE="$ROOT/build/dataship-preserved"
mkdir -p "$DIST" "$ROOT/build" "$PRESERVE"
# Keep config, scheduled tasks and mail preferences across upgrades. On the
# first DataShip build, import from the former MailPilot-Web install without
# deleting/moving it. Future builds prefer the existing DataShip files.
for name in config.json daily_reports.json web_mail_settings.json web_mail_tasks.json web_mail_worker_state.json .env planovac.json; do
  rm -f "$PRESERVE/$name"
  if [[ -f "$APP/$name" ]]; then
    cp "$APP/$name" "$PRESERVE/$name"
  elif [[ -f "$LEGACY_APP/$name" ]]; then
    cp "$LEGACY_APP/$name" "$PRESERVE/$name"
  fi
done
echo "[2/3] Sestavuji webovou aplikaci pro prohlizec..."
"$PY" -m PyInstaller --noconfirm --clean --onedir --console --noupx \
  --name DataShip \
  --distpath "$DIST" \
  --workpath "$ROOT/build/web-gui" \
  --specpath "$ROOT/build/web-spec" \
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
  --name DataShip-Worker \
  --distpath "$ROOT/dist-web-worker" \
  --workpath "$ROOT/build/web-worker" \
  --specpath "$ROOT/build/web-spec" \
  --collect-submodules psycopg \
  --add-data "$WIN_ROOT\\assets;assets" \
  "$WIN_ROOT\\web_mail_worker_main.py"

cp "$ROOT/dist-web-worker/DataShip-Worker.exe" "$APP/"
cp "$ROOT/config.example.json" "$APP/config.example.json"
if [[ -f "$PRESERVE/config.json" ]]; then
  cp "$PRESERVE/config.json" "$APP/config.json"
else
  cp "$APP/config.example.json" "$APP/config.json"
fi
for name in daily_reports.json web_mail_settings.json web_mail_tasks.json web_mail_worker_state.json .env planovac.json; do
  if [[ -f "$PRESERVE/$name" ]]; then
    cp "$PRESERVE/$name" "$APP/$name"
  fi
done
cat > "$APP/START_WEB.cmd" <<'CMD'
@echo off
cd /d "%~dp0"
"%~dp0DataShip.exe" --browser
if errorlevel 1 pause
CMD
cat > "$APP/START_WORKER_MANUAL.cmd" <<'CMD'
@echo off
cd /d "%~dp0"
"%~dp0DataShip-Worker.exe" --config "%~dp0config.json"
if errorlevel 1 pause
CMD
echo "HOTOVO: $APP/DataShip.exe"
echo "OTEVRENI: v Git Bash spust ./dist-web/DataShip/DataShip.exe --browser"
echo "NSSM instaluje sluzbu z DataShip-Worker.exe az po tvem kliknuti v nastaveni."

