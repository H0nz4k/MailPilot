"""NSSM service operations for the DataShip scheduler on Windows.

The GUI is not the service. In a frozen build the executable is the
DataShip-Worker.exe in the same directory. In a Git Bash developer run,
Python starts the worker entrypoint from the repository root, not via
-m from the config directory (which would break imports).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from services.web_branding import WORKER_EXE_NAME
from services.web_mail_settings import load_settings, settings_path


ALLOWED_ACTIONS = {"install", "start", "stop", "restart", "status"}


def _is_windows_admin() -> bool:
    """Only service-changing commands require elevation; status does not."""
    if sys.platform != "win32":
        return True  # Mocked Linux tests; Windows restriction applies on Windows.
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def _nssm_binary(configured_path: str) -> Path:
    raw = configured_path.strip().strip('"')
    if raw:
        binary = Path(raw).expanduser()
    else:
        found = shutil.which("nssm.exe") or shutil.which("nssm")
        binary = Path(found) if found else Path("nssm.exe")
    if not binary.is_file():
        raise ValueError(
            "NSSM.exe nebyl nalezen. V Administraci → Nastavení odesílání "
            "vyplňte úplnou cestu k nssm.exe (např. C:\\Tools\\nssm.exe)."
        )
    return binary.resolve()


def _worker_launch(config: Path) -> tuple[Path, list[str], Path]:
    """Absolute program, argv, working directory."""
    if getattr(sys, "frozen", False):
        program = Path(sys.executable).resolve().with_name(WORKER_EXE_NAME)
        if not program.is_file():
            raise ValueError(
                f"Vedle DataShip.exe chybí {WORKER_EXE_NAME}. "
                "Pro NSSM nejprve vytvořte kompletní Windows build."
            )
        return program, ["--config", str(config)], program.parent

    # Running from source: 'python -m services.web_mail_worker' works
    # only when Python can import packages from its working directory.
    # Using an absolute entry script is reliable for an NSSM service.
    entrypoint = Path(__file__).resolve().parent.parent / "web_mail_worker_main.py"
    if not entrypoint.is_file():
        raise ValueError(f"Chybí vstupní soubor Workeru: {entrypoint}")
    return (
        Path(sys.executable).resolve(),
        [str(entrypoint), "--config", str(config)],
        entrypoint.parent,
    )


def _invoke(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, errors="replace",
            timeout=30, stdin=subprocess.DEVNULL, check=False,
        )
    except OSError as exc:
        raise RuntimeError(f"Nelze spustit NSSM: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("NSSM do 30 sekund neodpověděl.") from exc
    output = "\n".join(
        item.strip() for item in (completed.stdout, completed.stderr)
        if item and item.strip()
    )
    if completed.returncode:
        raise RuntimeError(
            (output or f"NSSM skončil s kódem {completed.returncode}.")
            + "\nOvěřte stav služby, oprávnění správce a název služby."
        )
    return output


def service_command(config_directory: Path, action: str) -> str:
    """Run a requested NSSM action. Does not install without explicit action."""
    if action not in ALLOWED_ACTIONS:
        raise ValueError("Neznámá operace služby.")
    folder = Path(config_directory).resolve()
    settings = load_settings(settings_path(folder))
    nssm = _nssm_binary(str(settings.get("nssm_path") or ""))
    name = str(settings["service_name"]).strip()
    if not name or not all(c.isascii() and (c.isalnum() or c in "_-") for c in name):
        raise ValueError("Neplatný název služby.")

    if action != "status" and not _is_windows_admin():
        raise PermissionError(
            "Správa Windows služby vyžaduje administrátorská práva. "
            "Ukončete DataShip a spusťte Git Bash / aplikaci jako správce, "
            "poté operaci opakujte."
        )

    base = [str(nssm),]
    if action == "status":
        output = _invoke(base + ["status", name])
        return f"{name}: {output}"

    if action == "install":
        config = folder / "config.json"
        if not config.is_file():
            raise ValueError(f"Chybí konfigurační soubor: {config}")
        program, params, working_dir = _worker_launch(config)
        log_dir = folder / "logy"
        log_dir.mkdir(exist_ok=True)
        commands = [
            base + ["install", name, str(program), *params],
            base + ["set", name, "AppDirectory", str(working_dir)],
            base + ["set", name, "Start", "SERVICE_AUTO_START"],
            base + ["set", name, "AppExit", "Default", "Restart"],
            base + ["set", name, "AppRestartDelay", "5000"],
            base + ["set", name, "AppStdout", str(log_dir / "dataship_nssm_stdout.log")],
            base + ["set", name, "AppStderr", str(log_dir / "dataship_nssm_stderr.log")],
        ]
        for command in commands:
            _invoke(command)
        return (
            f"Služba {name} je nainstalovaná (zatím není spuštěná). "
            f"Program: {program}; pracovní složka: {working_dir}. "
            "Další krok: Spustit. Pozor, po spuštění může odeslat splatné e-maily."
        )

    if action == "restart":
        # NSSM restart exists and avoids two separate stop/start invocations.
        return _invoke(base + ["restart", name]) or f"{name}: restart dokončen."
    return _invoke(base + [action, name]) or f"{name}: {action} OK"
