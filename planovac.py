"""Úlohy plánovače: denní počty e-mailem a další spouštěče vedle EXE."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Sequence

from runtime_paths import application_directory
from stravovaci_sestava import ConfigError


SCHEDULE_TYPES = ("daily", "hourly", "interval")
ACTION_POCTY = "poctyemailem"
ACTION_CLOSING = "uzaverka"
ACTION_SPECIAL = "special"
ACTION_CUSTOM = "vlastni"
KNOWN_ACTIONS = (ACTION_POCTY, ACTION_CLOSING, ACTION_SPECIAL, ACTION_CUSTOM)

ACTION_LABELS = {
    ACTION_POCTY: "Denní stav",
    ACTION_CLOSING: "Uzávěrka",
    ACTION_SPECIAL: "Special",
    ACTION_CUSTOM: "Vlastní soubor",
}

_FUNCTION_LAUNCHERS = {
    ACTION_POCTY: "spustit_poctyemailem.bat",
    ACTION_CLOSING: "spustit_uzaverku.bat",
    ACTION_SPECIAL: "spustit_z17.bat",
}


@dataclass(frozen=True)
class PlannedJob:
    name: str
    action: str
    path: str
    schedule_type: str
    enabled: bool
    time: str | None = None
    minute: int | None = None
    minutes: int | None = None

    def schedule_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"type": self.schedule_type}
        if self.schedule_type == "daily" and self.time:
            payload["time"] = self.time
        elif self.schedule_type == "hourly" and self.minute is not None:
            payload["minute"] = self.minute
        elif self.schedule_type == "interval" and self.minutes is not None:
            payload["minutes"] = self.minutes
        return payload

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "action": self.action,
            "path": self.path,
            "schedule": self.schedule_dict(),
            "enabled": self.enabled,
        }


def scheduler_config_path(config_directory: Path | None = None) -> Path:
    base = config_directory if config_directory is not None else application_directory()
    return Path(base) / "planovac.json"


def default_launcher_path(
    action: str, config_directory: Path | None = None
) -> Path:
    base = config_directory if config_directory is not None else application_directory()
    exe = Path(base) / "MailPilot.exe"
    if exe.exists():
        return exe
    return Path(base) / _FUNCTION_LAUNCHERS.get(action, "spustit_poctyemailem.bat")


def default_pocty_path(config_directory: Path | None = None) -> Path:
    return default_launcher_path(ACTION_POCTY, config_directory)


def previous_closing_period(reference: datetime | None = None) -> str:
    """MMRRRR předchozího měsíce pro naplánovanou uzávěrku."""
    now = reference or datetime.now()
    month = now.month - 1
    year = now.year
    if month == 0:
        month = 12
        year -= 1
    return f"{month:02d}{year:04d}"


def scheduled_z17_year(reference: datetime | None = None) -> int:
    now = reference or datetime.now()
    return now.year


def format_schedule(job: PlannedJob) -> str:
    if job.schedule_type == "daily":
        return f"Denně v {job.time or '??:??'}"
    if job.schedule_type == "hourly":
        return f"Každou hodinu v :{job.minute if job.minute is not None else '?'}"
    if job.schedule_type == "interval":
        return f"Každých {job.minutes or '?'} min"
    return "Neznámý plán"


def _parse_time(value: object, job_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Úloha '{job_name}' potřebuje čas ve tvaru HH:MM.")
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ConfigError(f"Úloha '{job_name}' má neplatný čas; použijte HH:MM.")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as exc:
        raise ConfigError(f"Úloha '{job_name}' má neplatný čas; použijte HH:MM.") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ConfigError(f"Úloha '{job_name}' má čas mimo rozsah 00:00–23:59.")
    return f"{hour:02d}:{minute:02d}"


def parse_job(raw: dict[str, Any], config_directory: Path | None = None) -> PlannedJob:
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError("Každá úloha musí mít neprázdný název.")
    name = name.strip()

    action = raw.get("action", ACTION_CUSTOM)
    if action not in KNOWN_ACTIONS:
        raise ConfigError(
            f"Úloha '{name}' má neznámou akci '{action}'. "
            "Povolené jsou poctyemailem, uzaverka, special a vlastni."
        )

    path_value = raw.get("path")
    if action in {ACTION_POCTY, ACTION_CLOSING, ACTION_SPECIAL} and not path_value:
        path_value = str(default_launcher_path(action, config_directory))
    if not isinstance(path_value, str) or not path_value.strip():
        raise ConfigError(f"Úloha '{name}' musí mít cestu ke spouštěči.")
    path_value = path_value.strip()

    schedule = raw.get("schedule")
    if not isinstance(schedule, dict):
        raise ConfigError(f"Úloha '{name}' musí mít objekt 'schedule'.")
    schedule_type = str(schedule.get("type", "")).strip().lower()
    if schedule_type not in SCHEDULE_TYPES:
        raise ConfigError(
            f"Úloha '{name}' má neplatný typ plánu. "
            "Povolené: daily, hourly, interval."
        )

    time_value: str | None = None
    minute_value: int | None = None
    minutes_value: int | None = None
    if schedule_type == "daily":
        time_value = _parse_time(schedule.get("time"), name)
    elif schedule_type == "hourly":
        try:
            minute_value = int(schedule.get("minute", 0))
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"Úloha '{name}' má neplatnou minutu.") from exc
        if not 0 <= minute_value <= 59:
            raise ConfigError(f"Úloha '{name}' má minutu mimo 0–59.")
    else:
        try:
            minutes_value = int(schedule.get("minutes", 0))
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"Úloha '{name}' má neplatný interval.") from exc
        if minutes_value <= 0:
            raise ConfigError(f"Úloha '{name}' musí mít kladný interval v minutách.")

    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ConfigError(f"Úloha '{name}' má neplatnou hodnotu 'enabled'.")

    return PlannedJob(
        name=name,
        action=action,
        path=path_value,
        schedule_type=schedule_type,
        enabled=enabled,
        time=time_value,
        minute=minute_value,
        minutes=minutes_value,
    )


def load_jobs(path: Path, config_directory: Path | None = None) -> list[PlannedJob]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"Neplatný JSON v {path} (řádek {exc.lineno}, sloupec {exc.colno})."
        ) from exc
    if not isinstance(payload, dict):
        raise ConfigError("Kořen planovac.json musí být JSON objekt.")
    jobs_raw = payload.get("jobs", [])
    if not isinstance(jobs_raw, list):
        raise ConfigError("'jobs' musí být JSON pole.")
    jobs = [parse_job(item, config_directory) for item in jobs_raw if isinstance(item, dict)]
    names = [job.name.casefold() for job in jobs]
    if len(names) != len(set(names)):
        raise ConfigError("Názvy úloh v plánovači se nesmí opakovat.")
    return jobs


def save_jobs(path: Path, jobs: Sequence[PlannedJob]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "//": [
            "Plánovač MailPilotu. Úloha se přiřadí k funkci: denní stav, uzávěrka, special.",
            "Soubor používá interní scheduler runtime MailPilotu.",
        ],
        "jobs": [job.to_json() for job in jobs],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def next_run_at(job: PlannedJob, *, reference: datetime | None = None) -> datetime | None:
    if not job.enabled:
        return None
    now = reference or datetime.now()
    if job.schedule_type == "daily" and job.time:
        hour, minute = (int(part) for part in job.time.split(":"))
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate
    if job.schedule_type == "hourly" and job.minute is not None:
        candidate = now.replace(minute=job.minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(hours=1)
        return candidate
    if job.schedule_type == "interval" and job.minutes:
        return now + timedelta(minutes=job.minutes)
    return None


def launcher_command(
    job: PlannedJob, *, reference: datetime | None = None
) -> list[str]:
    """Příkaz, který má plánovač nebo Jídelna spustit."""
    path = Path(job.path)
    suffix = path.suffix.lower()
    if job.action == ACTION_POCTY and suffix == ".exe":
        return [str(path), "--poctyemailem"]
    if job.action == ACTION_CLOSING:
        token = previous_closing_period(reference)
        argument = f"--zaverka_{token}" if suffix == ".exe" else token
        return [str(path), argument]
    if job.action == ACTION_SPECIAL:
        year = scheduled_z17_year(reference)
        argument = f"--z17_{year}" if suffix == ".exe" else str(year)
        return [str(path), argument]
    return [str(path)]
