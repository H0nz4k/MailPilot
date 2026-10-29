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
DIST="$ROOT/dist-web"
INSTALL_APP="$DIST/DataShip"
LEGACY_APP="$DIST/MailPilot-Web"
RECOVERY="$ROOT/build/dataship-preserved"
# Stop before pip/PyInstaller if the currently installed EXEs are in use.
"$PY" "$ROOT/scripts/deploy_web_build.py" --app "$INSTALL_APP" --check-only
mkdir -p "$DIST" "$ROOT/build"
# PyInstaller may delete only its new temporary directory, never the installation.
STAGE_ROOT="$(mktemp -d "$DIST/.dataship-build-XXXXXX")"
APP="$STAGE_ROOT/DataShip"
trap 'echo "CHYBA: build selhal; puvodni instalace se nemaze. Pracovni slozka: $STAGE_ROOT" >&2' ERR

echo "[1/5] Instaluji zavislosti webove verze..."
"$PY" -m pip install --disable-pip-version-check -r "$ROOT/requirements-web-build.txt"
WIN_ROOT="$(cygpath -w "$ROOT")"
echo "[2/5] Sestavuji webovou aplikaci pro prohlizec..."
"$PY" -m PyInstaller --noconfirm --clean --onedir --console --noupx \
  --name DataShip \
  --icon "$WIN_ROOT\\assets\\dataship.ico" \
  --distpath "$STAGE_ROOT" \
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

echo "[3/5] Sestavuji bezobsluznou sluzbu pro NSSM..."
"$PY" -m PyInstaller --noconfirm --clean --onefile --console --noupx \
  --name DataShip-Worker \
  --icon "$WIN_ROOT\\assets\\dataship-worker.ico" \
  --distpath "$STAGE_ROOT/worker" \
  --workpath "$ROOT/build/web-worker" \
  --specpath "$ROOT/build/web-spec" \
  --collect-submodules psycopg \
  --add-data "$WIN_ROOT\\assets;assets" \
  "$WIN_ROOT\\web_mail_worker_main.py"

cp "$STAGE_ROOT/worker/DataShip-Worker.exe" "$APP/"
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
cp "$APP/config.example.json" "$APP/config.json"
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
echo "[4/5] Pridavam overeny NSSM pro Windows sluzbu..."
"$PY" "$ROOT/scripts/package_web_release.py" --install-nssm "$APP"
echo "[5/5] Nasazuji overene sestaveni a zachovavam nastaveni..."
"$PY" "$ROOT/scripts/deploy_web_build.py" \
  --app "$INSTALL_APP" --stage "$APP" --recovery "$RECOVERY" --legacy "$LEGACY_APP"
# Only disposable build output remains here. The previous installation stays
# in its named backup beside DataShip; it is never deleted by this script.
rm -rf "$STAGE_ROOT"
echo "HOTOVO: $INSTALL_APP/DataShip.exe"
echo "OTEVRENI: v Git Bash spust ./dist-web/DataShip/DataShip.exe --browser"
echo "NSSM instaluje sluzbu z DataShip-Worker.exe az po tvem kliknuti v nastaveni."
