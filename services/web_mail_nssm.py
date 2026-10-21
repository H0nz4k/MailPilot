"""Windows NSSM service management; no command shell invocation."""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

from services.web_mail_settings import load_settings, settings_path

def service_command(config_directory: Path, action: str) -> str:
    if action not in ("install", "start", "stop", "restart", "status"):
        raise ValueError("Neznámá operace služby.")
    settings = load_settings(settings_path(config_directory))
    nssm = Path(settings["nssm_path"])
    if not nssm.is_file():
        raise ValueError("NSSM.exe nebyl nalezen. Nastavte jeho cestu.")
    name = str(settings["service_name"]).strip()
    if not name or not all(c.isascii() and (c.isalnum() or c in "_-") for c in name):
        raise ValueError("Neplatný název služby.")
    config = (Path(config_directory) / "config.json").resolve()
    base = [str(nssm)]
    if action == "install":
        commands = [
            base + ["install", name, sys.executable, "-m", "services.web_mail_worker", "--config", str(config)],
            base + ["set", name, "AppDirectory", str(config.parent)],
            base + ["set", name, "Start", "SERVICE_AUTO_START"],
            base + ["set", name, "AppExit", "Default", "Restart"],
        ]
    elif action == "restart":
        commands = [base + ["stop", name], base + ["start", name]]
    else:
        commands = [base + [action, name]]
    results = []
    for command in commands:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=30,
                                   stdin=subprocess.DEVNULL, check=False)
        output = (completed.stdout + "\n" + completed.stderr).strip()
        if completed.returncode:
            raise RuntimeError(output or f"NSSM selhal, kód {completed.returncode}.")
        results.append(output)
    return "\n".join(results).strip() or f"{action}: OK"
