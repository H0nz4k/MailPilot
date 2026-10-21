#!/usr/bin/env bash
# Install one central MailPilot Windows service from Git Bash.
# Usage: bash scripts/install_web_mail_service.sh /c/MailPilot /c/nssm/nssm.exe
set -euo pipefail
APP_DIR="${1:?Provide Git Bash path to MailPilot directory}"
NSSM="${2:?Provide Git Bash path to nssm.exe}"
SERVICE=MailPilotWebScheduler
APP_DIR="$(cd "$APP_DIR" && pwd -W)"
NSSM="$(cygpath -w "$NSSM")"
PYTHON="$(command -v python.exe || command -v python)"
PYTHON="$(cygpath -w "$PYTHON")"
CONFIG="$APP_DIR\\config.json"
"$NSSM" install "$SERVICE" "$PYTHON" -m services.web_mail_worker --config "$CONFIG"
"$NSSM" set "$SERVICE" AppDirectory "$APP_DIR"
"$NSSM" set "$SERVICE" Start SERVICE_AUTO_START
"$NSSM" set "$SERVICE" AppExit Default Restart
"$NSSM" start "$SERVICE"
echo "Installed and started $SERVICE. Logs: $APP_DIR\\logy\\web_mail_worker.log"
