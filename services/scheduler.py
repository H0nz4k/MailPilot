"""Plánované úlohy pro desktopové rozhraní.

Tenká vrstva nad ``planovac.py``; formátování a validaci drží mimo GUI.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Sequence

from planovac import (
    ACTION_CLOSING,
    ACTION_CUSTOM,
    ACTION_LABELS,
    ACTION_POCTY,
    ACTION_SPECIAL,
    KNOWN_ACTIONS,
    SCHEDULE_TYPES,
    PlannedJob,
    default_launcher_path,
    format_schedule,
    launcher_command,
    load_jobs,
    next_run_at,
    parse_job,
    save_jobs,
    scheduler_config_path,
)
from services.config_io import CZECH_DATE_FORMAT
from stravovaci_sestava import ConfigError


SCHEDULE_LABELS = {
    "daily": "Denně",
    "hourly": "Každou hodinu",
    "interval": "Interval",
}

__all__ = [
    "ACTION_CLOSING",
    "ACTION_CUSTOM",
    "ACTION_LABELS",
    "ACTION_POCTY",
    "ACTION_SPECIAL",
    "KNOWN_ACTIONS",
    "SCHEDULE_LABELS",
    "SCHEDULE_TYPES",
    "PlannedJob",
    "build_job",
    "default_launcher_path",
    "describe_command",
    "describe_next_run",
    "describe_schedule",
    "read_jobs",
    "run_job_now",
    "scheduler_path",
    "write_jobs",
]


def scheduler_path(config_path: Path) -> Path:
    """Plánovač bydlí v ``planovac.json`` vedle config.json."""
    return scheduler_config_path(Path(config_path).resolve().parent)


def read_jobs(path: Path) -> list[PlannedJob]:
    return load_jobs(Path(path), Path(path).resolve().parent)


def write_jobs(path: Path, jobs: Sequence[PlannedJob]) -> None:
    save_jobs(Path(path), jobs)


def build_job(
    *,
    name: str,
    action: str,
    schedule_type: str,
    launcher: str,
    enabled: bool,
    time: str = "",
    minute: int = 0,
    minutes: int = 0,
    config_directory: Path | None = None,
) -> PlannedJob:
    """Sestaví úlohu z formuláře a nechá ji ověřit parserem plánovače."""
    schedule: dict[str, object] = {"type": schedule_type}
    if schedule_type == "daily":
        schedule["time"] = time
    elif schedule_type == "hourly":
        schedule["minute"] = minute
    else:
        schedule["minutes"] = minutes
    payload = {
        "name": name.strip(),
        "action": action,
        "path": launcher.strip(),
        "schedule": schedule,
        "enabled": bool(enabled),
    }
    return parse_job(payload, config_directory)


def ensure_unique(jobs: Sequence[PlannedJob], candidate: PlannedJob) -> None:
    """Plánovač neumí dvě úlohy stejného jména."""
    if any(job.name.casefold() == candidate.name.casefold() for job in jobs):
        raise ConfigError(f"Úloha '{candidate.name}' už v plánovači existuje.")


def describe_schedule(job: PlannedJob) -> str:
    return format_schedule(job)


def describe_next_run(job: PlannedJob, *, reference: datetime | None = None) -> str:
    """Čitelné příští spuštění; vypnutá úloha vrací pomlčku."""
    moment = next_run_at(job, reference=reference)
    if moment is None:
        return "—"
    now = reference or datetime.now()
    if moment.date() == now.date():
        return f"dnes {moment.strftime('%H:%M')}"
    if (moment.date() - now.date()).days == 1:
        return f"zítra {moment.strftime('%H:%M')}"
    return moment.strftime(f"{CZECH_DATE_FORMAT} %H:%M")


def describe_command(job: PlannedJob, *, reference: datetime | None = None) -> str:
    return " ".join(launcher_command(job, reference=reference))


def run_job_now(job: PlannedJob, *, config_directory: Path) -> tuple[int, str]:
    """Spustí konkrétní úlohu hned teď a vrátí kód + stručný výstup."""
    command = launcher_command(job, reference=datetime.now())
    done = subprocess.run(  # noqa: S603
        command,
        cwd=str(Path(config_directory).resolve()),
        capture_output=True,
        text=True,
        check=False,
    )
    snippet = (done.stdout or done.stderr or "").strip().replace("\n", " ")
    return done.returncode, snippet[:400]
