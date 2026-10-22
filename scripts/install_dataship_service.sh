#!/usr/bin/env bash
# Run from an elevated Git Bash after configuring and checking the application.
# Installs the worker; starting the service remains an explicit separate action.
set -Eeuo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -f "$APP_DIR/DataShip-Worker.exe" ]]; then
  APP_DIR="$(cd "$APP_DIR/../dist-web/DataShip" && pwd)"
fi
SERVICE="${1:-DataShipScheduler}"
[[ "$SERVICE" =~ ^[a-zA-Z0-9_-]+$ ]] || { echo 'Neplatny nazev sluzby.' >&2; exit 2; }
NSSM="$APP_DIR/nssm/nssm.exe"
[[ -f "$NSSM" && -f "$APP_DIR/config.json" ]] || { echo 'Chybi nssm/nssm.exe nebo config.json.' >&2; exit 2; }
# An installed service must be updated deliberately, never duplicated/replaced.
if "$NSSM" get "$SERVICE" Application >/dev/null 2>&1; then
  echo "Sluzba $SERVICE uz existuje. Pouzij nastaveni aplikace k jeji sprave." >&2
  exit 2
fi
mkdir -p "$APP_DIR/logy"
"$NSSM" install "$SERVICE" "$(cygpath -w "$APP_DIR/DataShip-Worker.exe")" --config "$(cygpath -w "$APP_DIR/config.json")"
"$NSSM" set "$SERVICE" AppDirectory "$(cygpath -w "$APP_DIR")"
"$NSSM" set "$SERVICE" Start SERVICE_AUTO_START
"$NSSM" set "$SERVICE" AppExit Default Restart
"$NSSM" set "$SERVICE" AppRestartDelay 10000
"$NSSM" set "$SERVICE" AppStdout "$(cygpath -w "$APP_DIR/logy/nssm-stdout.log")"
"$NSSM" set "$SERVICE" AppStderr "$(cygpath -w "$APP_DIR/logy/nssm-stderr.log")"
echo "Sluzba $SERVICE nainstalovana, zatim NEBEZI."
echo 'Pred spustenim over ucet sluzby, pristup k DB a prijemce e-mailu.'
echo "Spusteni: ./nssm/nssm.exe start $SERVICE"
