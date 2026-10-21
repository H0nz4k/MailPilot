#!/usr/bin/env bash
# Fast Windows/Git Bash GUI test: no PyInstaller rebuild needed.
# Usage: bash scripts/run_web_dev_windows.sh
set -Eeuo pipefail

case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) ;;
  *) echo "CHYBA: spoustej ve Windows v Git Bash." >&2; exit 2 ;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PY="$ROOT/.venv-web/Scripts/python.exe"

if [[ ! -f "$PY" ]]; then
  echo "Chybi .venv-web. Nejdrive proved: bash scripts/build_web_windows.sh" >&2
  exit 2
fi

# Run the current source files but use the existing bundled deployment's
# configuration, so testing shows the same DB and mail-task settings.
CONFIG="$ROOT/dist-web/MailPilot-Web/config.json"
if [[ ! -f "$CONFIG" ]]; then
  CONFIG="$ROOT/config.json"
fi
if [[ ! -f "$CONFIG" ]]; then
  echo "Chybi config.json. Nejdrive nastav aplikaci po prvnim Windows buildu." >&2
  exit 2
fi

echo "Spoustim aktualni webove GUI ze zdrojoveho kodu."
echo "Pouzita konfigurace: $CONFIG"
echo "Pouze GUI; tato cesta NESPLOUSTI sluzbu odesilani."
WIN_CONFIG="$(cygpath -w "$CONFIG")"
exec "$PY" "$ROOT/stravovaci_nicegui.py" --browser --config "$WIN_CONFIG"
