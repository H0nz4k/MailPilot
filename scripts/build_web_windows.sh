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
echo "[1/4] Instaluji zavislosti webove verze..."
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
echo "[2/4] Sestavuji webovou aplikaci pro prohlizec..."
"$PY" -m PyInstaller --noconfirm --clean --onedir --console --noupx \
  --name DataShip \
  --icon "$WIN_ROOT\\assets\\dataship.ico" \
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

echo "[3/4] Sestavuji bezobsluznou sluzbu pro NSSM..."
"$PY" -m PyInstaller --noconfirm --clean --onefile --console --noupx \
  --name DataShip-Worker \
  --icon "$WIN_ROOT\\assets\\dataship-worker.ico" \
  --distpath "$ROOT/dist-web-worker" \
  --workpath "$ROOT/build/web-worker" \
  --specpath "$ROOT/build/web-spec" \
  --collect-submodules psycopg \
  --add-data "$WIN_ROOT\\assets;assets" \
  "$WIN_ROOT\\web_mail_worker_main.py"

cp "$ROOT/dist-web-worker/DataShip-Worker.exe" "$APP/"
expected_build="$("$PY" -c 'from services.web_branding import WEB_BUILD; print(WEB_BUILD)')"
for executable in DataShip.exe DataShip-Worker.exe; do
  reported_version="$("$APP/$executable" --version)"
  reported_version="${reported_version//$'\r'/}"
  if [[ "$reported_version" != *" build $expected_build" ]]; then
    echo "CHYBA: $executable nema ocekavane sestaveni $expected_build: $reported_version" >&2
    exit 2
  fi
  echo "OVERENO: $executable: $reported_version"
done
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
echo "[4/4] Pridavam overeny NSSM pro Windows sluzbu..."
"$PY" "$ROOT/scripts/package_web_release.py" --install-nssm "$APP"
echo "HOTOVO: $APP/DataShip.exe"
echo "OTEVRENI: v Git Bash spust ./dist-web/DataShip/DataShip.exe --browser"
echo "NSSM instaluje sluzbu z DataShip-Worker.exe az po tvem kliknuti v nastaveni."


