"""Stav automatického denního odesílání pro User přehled."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
import re
from typing import Sequence

from automaticky_export import (
    read_saved_settings,
    run_scheduled_export_with_retry,
    write_log,
)
from planovac import ACTION_POCTY, next_run_at
from services.jidelnasql_warning import (
    peek_warning_settings,
    show_jidelnasql_mail_warning,
    clear_jidelnasql_mail_warning,
)
from services.scheduler import read_jobs, scheduler_path
from services.scheduler_runtime import peek_service_config, read_runtime_snapshot
from stravovaci_sestava import ConfigError

LOG_RELATIVE = Path("logy") / "automaticky_export.log"


@dataclass(frozen=True)
class AutoMailOverview:
    configured: bool
    enabled: bool
    last_success: str
    next_send: str
    errors: tuple[str, ...]
    job_names: tuple[str, ...] = ()
    next_send_from: str = "—"
    runtime_running: bool = False
    runtime_type: str = "not running"
    service_account: str = "—"
    last_runtime_run: str = "—"
    last_runtime_result: str = "—"
    scheduler_next_run: str = "—"
    scheduler_error: str = "—"
    credential_ok: bool = False
    credential_detail: str = ""


@dataclass(frozen=True)
class RetryResult:
    success: bool
    message: str


def load_automail_overview(config_path: Path) -> AutoMailOverview:
    config_path = Path(config_path).resolve()
    raw = read_saved_settings(config_path)
    jobs = _read_jobs_safe(config_path)
    pocty_jobs = [job for job in jobs if job.action == ACTION_POCTY]
    configured = bool(pocty_jobs)
    enabled_jobs = [job for job in pocty_jobs if job.enabled]
    service_cfg = peek_service_config(raw)
    snapshot = read_runtime_snapshot(
        config_path,
        service_cfg.service_name,
        probe_service=True,
    )
    next_run, next_job_name = _next_run_with_job(enabled_jobs)
    if not snapshot.running or not snapshot.credential_ok:
        next_run = None
        next_job_name = ""
    log_path = config_path.parent / LOG_RELATIVE
    last_ok, errors = _parse_log(log_path)
    next_text = _format_next(
        next_run,
        configured=configured,
        enabled=bool(enabled_jobs),
        runtime_running=snapshot.running,
        credential_ok=snapshot.credential_ok,
    )
    job_names = tuple(job.name for job in pocty_jobs)
    next_from = next_job_name or (
        "—" if not job_names else ", ".join(job_names)
    )
    return AutoMailOverview(
        configured=configured,
        enabled=bool(enabled_jobs),
        last_success=last_ok or "zatím neodesláno",
        next_send=next_text,
        errors=errors,
        job_names=job_names,
        next_send_from=next_from,
        runtime_running=snapshot.running,
        runtime_type=snapshot.runtime_type,
        service_account=snapshot.service_account,
        last_runtime_run=snapshot.last_run,
        last_runtime_result=snapshot.last_result,
        scheduler_next_run=snapshot.next_run,
        scheduler_error=snapshot.last_error,
        credential_ok=snapshot.credential_ok,
        credential_detail=snapshot.credential_detail,
    )


def retry_daily_mail(config_path: Path) -> RetryResult:
    config_path = Path(config_path).resolve()
    log_path = config_path.parent / LOG_RELATIVE
    warning = peek_warning_settings(read_saved_settings(config_path))
    write_log(log_path, "START", "Ruční opakované odeslání denního stavu")
    try:
        result = run_scheduled_export_with_retry(config_path, date.today(), log_path)
    except Exception as exc:
        write_log(log_path, "ERROR", f"Ruční opakování selhalo: {exc}")
        note = show_jidelnasql_mail_warning(warning, when=datetime.now())
        if note:
            write_log(log_path, "WARN", note)
        return RetryResult(False, f"Odeslání selhalo: {exc}")
    if result["status"] == "skipped":
        text = str(result["message"])
        write_log(log_path, "SKIP", f"Ruční opakování: {text}")
        return RetryResult(False, f"Neodesláno: {text}")
    count = len(result["recipients"])
    detail = f"; {result['detail']}" if result.get("detail") else ""
    write_log(
        log_path,
        "OK",
        f"Ruční opakování: odesláno {count} příjemcům; PDF: {result['path']}{detail}",
    )
    note = clear_jidelnasql_mail_warning(warning)
    if note:
        write_log(log_path, "WARN", note)
    return RetryResult(True, f"Odesláno {count} příjemcům.")


def _read_jobs_safe(config_path: Path) -> Sequence:
    try:
        return read_jobs(scheduler_path(config_path))
    except (ConfigError, OSError):
        return ()


def _next_run_with_job(jobs: Sequence) -> tuple[datetime | None, str]:
    pairs: list[tuple[datetime, str]] = []
    for job in jobs:
        moment = next_run_at(job)
        if moment is not None:
            pairs.append((moment, job.name))
    if not pairs:
        return None, ""
    moment, name = min(pairs, key=lambda pair: pair[0])
    return moment, name


def _format_next(
    next_run: datetime | None,
    *,
    configured: bool,
    enabled: bool,
    runtime_running: bool,
    credential_ok: bool,
) -> str:
    if not configured:
        return "není nastavená žádná úloha denního stavu"
    if not enabled:
        return "úloha denního stavu je vytvořená, ale vypnutá"
    if not runtime_running:
        return "plánovač je vytvořený, ale runtime neběží"
    if not credential_ok:
        return "plánovač běží, ale nemá dostupné DB credentials"
    if next_run is None:
        return "čas dalšího spuštění není dostupný"
    return next_run.strftime("%d.%m.%Y %H:%M")


def _parse_log(path: Path) -> tuple[str, tuple[str, ...]]:
    if not path.is_file():
        return "", ()
    pattern = re.compile(
        r"^(?P<date>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} [+-]\d{4}) "
        r"\[(?P<level>[A-Z]+)\] (?P<text>.*)$"
    )
    last_ok = ""
    errors: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = pattern.match(line.strip())
        if not match:
            continue
        date_text = match.group("date")
        level = match.group("level")
        text = match.group("text")
        stamp = _to_cz(date_text)
        if level == "OK":
            last_ok = stamp
        if level in {"ERROR", "WARN"}:
            errors.append(f"{stamp} [{level}] {text}")
    return last_ok, tuple(errors[-5:])


def _to_cz(value: str) -> str:
    try:
        moment = datetime.strptime(value, "%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        return value
    return moment.strftime("%d.%m.%Y %H:%M")
