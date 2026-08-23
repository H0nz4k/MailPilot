"""Internal scheduler runtime inspired by MUJ_SCHEDULER."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from planovac import PlannedJob, launcher_command
from runtime_paths import application_directory
from services.scheduler import read_jobs, scheduler_path

STATE_FILE = "planovac_runtime.json"
PID_FILE = "planovac_runtime.pid"
LOG_FILE = "mailpilot_scheduler.log"
SERVICE_NAME_PREFIX = "MailPilot_"
DEFAULT_SERVICE_NAME = "MailPilot_denniprehled"
_LEGACY_DEFAULT_SERVICE_NAME = "MailPilotScheduler"
DEFAULT_NSSM_CANDIDATES = (
    r"C:\nssm\nssm.exe",
    r"C:\tools\nssm\nssm.exe",
    r"C:\Program Files\nssm\nssm.exe",
)


@dataclass(frozen=True)
class RuntimeStatus:
    running: bool
    pid: int | None
    detail: str
    state_path: Path
    log_path: Path


@dataclass(frozen=True)
class SchedulerServiceStatus:
    installed: bool
    running: bool
    service_name: str
    detail: str


@dataclass(frozen=True)
class SchedulerServiceConfig:
    service_name: str
    nssm_path: str


def _runtime_paths(config_path: Path) -> tuple[Path, Path, Path]:
    base = Path(config_path).resolve().parent
    log_dir = base / "logy"
    log_dir.mkdir(parents=True, exist_ok=True)
    return base / STATE_FILE, base / PID_FILE, log_dir / LOG_FILE


def _service_block(raw: dict[str, Any]) -> dict[str, Any]:
    block = raw.get("planovac_service")
    return dict(block) if isinstance(block, dict) else {}


def _bundled_nssm_candidates() -> tuple[Path, ...]:
    base = application_directory()
    return (
        base / "nssm" / "win64" / "nssm.exe",
        base / "nssm" / "win32" / "nssm.exe",
        base / "nssm" / "nssm.exe",
    )


def _default_nssm_path() -> str:
    for candidate in _bundled_nssm_candidates():
        if candidate.is_file():
            return str(candidate.resolve())
    return ""


def normalize_service_name(value: str) -> str:
    raw = str(value or "").strip()
    if not raw or raw == _LEGACY_DEFAULT_SERVICE_NAME:
        return DEFAULT_SERVICE_NAME
    if raw == "MailPilot":
        return DEFAULT_SERVICE_NAME
    if raw.lower().startswith("mailpilot"):
        suffix = raw[len("MailPilot") :].strip(" _-")
        return (
            f"{SERVICE_NAME_PREFIX}{suffix}"
            if suffix
            else DEFAULT_SERVICE_NAME
        )
    clean = raw.strip(" _-")
    return (
        f"{SERVICE_NAME_PREFIX}{clean}"
        if clean
        else DEFAULT_SERVICE_NAME
    )


def peek_service_config(raw: dict[str, Any]) -> SchedulerServiceConfig:
    block = _service_block(raw)
    name = normalize_service_name(str(block.get("name") or ""))
    nssm = str(block.get("nssm_path") or "").strip() or _default_nssm_path()
    return SchedulerServiceConfig(service_name=name, nssm_path=nssm)


def apply_service_config(
    raw: dict[str, Any],
    *,
    service_name: str,
    nssm_path: str,
) -> dict[str, Any]:
    updated = dict(raw)
    updated["planovac_service"] = {
        "name": normalize_service_name(service_name),
        "nssm_path": nssm_path.strip(),
    }
    return updated


def _pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _service_exists(service_name: str) -> bool:
    try:
        done = subprocess.run(  # noqa: S603
            ["sc", "query", service_name],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.2,
        )
    except subprocess.TimeoutExpired:
        return False
    output = f"{done.stdout}\n{done.stderr}".upper()
    if "FAILED 1060" in output:
        return False
    return done.returncode == 0


def _service_running(service_name: str) -> bool:
    try:
        done = subprocess.run(  # noqa: S603
            ["sc", "query", service_name],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.2,
        )
    except subprocess.TimeoutExpired:
        return False
    text = f"{done.stdout}\n{done.stderr}".upper()
    return "RUNNING" in text and done.returncode == 0


def resolve_nssm_path(nssm_path: str) -> Path:
    raw = nssm_path.strip()
    if raw:
        path = Path(raw).expanduser()
        if path.is_dir():
            path = path / "nssm.exe"
        if path.is_file():
            return path.resolve()
        raise FileNotFoundError(f"NSSM nebyl nalezen na cestě: {path}")
    on_path = shutil.which("nssm")
    if on_path:
        return Path(on_path).resolve()
    for candidate in _bundled_nssm_candidates():
        if candidate.is_file():
            return candidate.resolve()
    for candidate in DEFAULT_NSSM_CANDIDATES:
        path = Path(candidate)
        if path.is_file():
            return path.resolve()
    raise FileNotFoundError(
        "NSSM nebyl nalezen. Nastavte cestu k nssm.exe v administraci."
    )


def read_service_status(service_name: str) -> SchedulerServiceStatus:
    service_name = normalize_service_name(service_name)
    exists = _service_exists(service_name)
    running = _service_running(service_name) if exists else False
    if not exists:
        detail = f"Služba '{service_name}' není nainstalovaná"
    elif running:
        detail = f"Služba '{service_name}' běží"
    else:
        detail = f"Služba '{service_name}' je nainstalovaná, ale není spuštěná"
    return SchedulerServiceStatus(
        installed=exists,
        running=running,
        service_name=service_name,
        detail=detail,
    )


def install_service(
    config_path: Path,
    *,
    service_name: str,
    nssm_path: str,
) -> str:
    service_name = normalize_service_name(service_name)
    resolved = resolve_nssm_path(nssm_path)
    base = Path(config_path).resolve().parent
    exe = base / "MailPilot.exe"
    if exe.is_file():
        app = str(exe)
        args = f"--scheduler --config \"{config_path}\""
    else:
        app = sys.executable
        args = f"\"{Path(__file__).resolve().parents[1] / 'AutoReport_qt.py'}\" --scheduler --config \"{config_path}\""
    if _service_exists(service_name):
        return f"Služba '{service_name}' už existuje."
    run1 = subprocess.run(  # noqa: S603
        [str(resolved), "install", service_name, app, args],
        cwd=str(base),
        capture_output=True,
        text=True,
        check=False,
    )
    if run1.returncode != 0:
        text = (run1.stderr or run1.stdout or "").strip()
        raise RuntimeError(text or "NSSM install selhal.")
    subprocess.run(  # noqa: S603
        [str(resolved), "set", service_name, "AppDirectory", str(base)],
        cwd=str(base),
        capture_output=True,
        text=True,
        check=False,
    )
    run2 = subprocess.run(  # noqa: S603
        [str(resolved), "start", service_name],
        cwd=str(base),
        capture_output=True,
        text=True,
        check=False,
    )
    if run2.returncode != 0:
        text = (run2.stderr or run2.stdout or "").strip()
        return (
            f"Služba '{service_name}' nainstalovaná, ale start selhal: "
            f"{text or 'neznámá chyba'}"
        )
    return f"Služba '{service_name}' byla nainstalována a spuštěna."


def remove_service(*, service_name: str, nssm_path: str) -> str:
    service_name = normalize_service_name(service_name)
    resolved = resolve_nssm_path(nssm_path)
    if not _service_exists(service_name):
        return f"Služba '{service_name}' není nainstalovaná."
    subprocess.run(  # noqa: S603
        [str(resolved), "stop", service_name],
        capture_output=True,
        text=True,
        check=False,
    )
    run = subprocess.run(  # noqa: S603
        [str(resolved), "remove", service_name, "confirm"],
        capture_output=True,
        text=True,
        check=False,
    )
    if run.returncode != 0:
        text = (run.stderr or run.stdout or "").strip()
        raise RuntimeError(text or "NSSM remove selhal.")
    # Windows někdy službu po remove chvíli drží v registru.
    for _ in range(10):
        if not _service_exists(service_name):
            return f"Služba '{service_name}' byla odstraněna."
        time.sleep(0.2)
    # Fallback přes SC, pokud NSSM odregistrování nedokončilo.
    subprocess.run(  # noqa: S603
        ["sc", "delete", service_name],
        capture_output=True,
        text=True,
        check=False,
    )
    for _ in range(10):
        if not _service_exists(service_name):
            return f"Služba '{service_name}' byla odstraněna."
        time.sleep(0.2)
    return f"Služba '{service_name}' byla odstraněna."


def restart_service(*, service_name: str, nssm_path: str) -> str:
    service_name = normalize_service_name(service_name)
    resolved = resolve_nssm_path(nssm_path)
    if not _service_exists(service_name):
        return f"Služba '{service_name}' není nainstalovaná."
    run = subprocess.run(  # noqa: S603
        [str(resolved), "restart", service_name],
        capture_output=True,
        text=True,
        check=False,
    )
    if run.returncode != 0:
        text = (run.stderr or run.stdout or "").strip()
        raise RuntimeError(text or "NSSM restart selhal.")
    return f"Služba '{service_name}' byla restartována."


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _append_log(path: Path, level: str, message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp} {level:<5} {message}\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)


def read_runtime_status(config_path: Path) -> RuntimeStatus:
    state_path, pid_path, log_path = _runtime_paths(config_path)
    state = _load_json(state_path)
    pid: int | None = None
    text = str(state.get("last_heartbeat") or "").strip()
    if pid_path.is_file():
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            pid = None
    running = bool(pid and _pid_running(pid))
    if pid is not None and not running:
        pid_path.unlink(missing_ok=True)
        pid = None
    if running:
        detail = f"Běží (PID {pid})"
        if text:
            detail += f" · heartbeat {text}"
    else:
        detail = "Neběží"
    return RuntimeStatus(
        running=running,
        pid=pid,
        detail=detail,
        state_path=state_path,
        log_path=log_path,
    )


def start_runtime(config_path: Path) -> str:
    status = read_runtime_status(config_path)
    if status.running:
        return status.detail
    root = Path(__file__).resolve().parents[1]
    base = Path(config_path).resolve().parent
    exe = base / "MailPilot.exe"
    if exe.is_file():
        command = [str(exe), "--scheduler", "--config", str(config_path)]
    else:
        command = [
            sys.executable,
            str(root / "AutoReport_qt.py"),
            "--scheduler",
            "--config",
            str(config_path),
        ]
    flags = 0
    flags |= getattr(subprocess, "DETACHED_PROCESS", 0)
    flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen(  # noqa: S603
        command,
        cwd=str(base),
        creationflags=flags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )
    return "Interní plánovač se spouští…"


def stop_runtime(config_path: Path) -> str:
    _state_path, pid_path, _log_path = _runtime_paths(config_path)
    if not pid_path.is_file():
        return "Interní plánovač neběží."
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        pid_path.unlink(missing_ok=True)
        return "Interní plánovač neběží."
    if not _pid_running(pid):
        pid_path.unlink(missing_ok=True)
        return "Interní plánovač neběží."
    done = subprocess.run(  # noqa: S603
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True,
        text=True,
        check=False,
    )
    pid_path.unlink(missing_ok=True)
    if done.returncode == 0:
        return "Interní plánovač byl zastaven."
    stderr = (done.stderr or done.stdout or "").strip()
    return f"Zastavení plánovače selhalo: {stderr or 'neznámá chyba'}"


def _next_run(job: PlannedJob, reference: datetime) -> datetime | None:
    if not job.enabled:
        return None
    if job.schedule_type == "daily" and job.time:
        hour, minute = (int(part) for part in job.time.split(":"))
        candidate = reference.replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if candidate <= reference:
            candidate += timedelta(days=1)
        return candidate
    if job.schedule_type == "hourly" and job.minute is not None:
        candidate = reference.replace(
            minute=job.minute, second=0, microsecond=0
        )
        if candidate <= reference:
            candidate += timedelta(hours=1)
        return candidate
    if job.schedule_type == "interval" and job.minutes:
        return reference + timedelta(minutes=job.minutes)
    return None


def _run_due_jobs(
    config_path: Path,
    state: dict[str, Any],
    state_path: Path,
    log_path: Path,
) -> None:
    now = datetime.now()
    jobs = read_jobs(scheduler_path(config_path))
    job_state = state.get("jobs")
    if not isinstance(job_state, dict):
        job_state = {}
    active_keys = {job.name for job in jobs}
    for stale in tuple(job_state):
        if stale not in active_keys:
            job_state.pop(stale, None)
    for job in jobs:
        info = job_state.get(job.name)
        if not isinstance(info, dict):
            info = {}
            job_state[job.name] = info
        if not job.enabled:
            info["next_run"] = None
            continue
        next_raw = str(info.get("next_run") or "").strip()
        try:
            next_run = datetime.fromisoformat(next_raw) if next_raw else None
        except ValueError:
            next_run = None
        if next_run is None:
            next_run = _next_run(job, now)
            info["next_run"] = next_run.isoformat() if next_run else None
        if next_run is None or next_run > now:
            continue
        command = launcher_command(job, reference=now)
        _append_log(log_path, "INFO", f"Spouštím úlohu '{job.name}': {' '.join(command)}")
        done = subprocess.run(  # noqa: S603
            command,
            cwd=str(Path(config_path).resolve().parent),
            capture_output=True,
            text=True,
            check=False,
        )
        info["last_run"] = now.isoformat()
        info["last_exit_code"] = done.returncode
        snippet = (done.stdout or done.stderr or "").strip().replace("\n", " ")
        info["last_note"] = snippet[:240]
        level = "INFO" if done.returncode == 0 else "ERROR"
        _append_log(
            log_path,
            level,
            f"Úloha '{job.name}' skončila kódem {done.returncode}.",
        )
        next_after = _next_run(job, datetime.now())
        info["next_run"] = next_after.isoformat() if next_after else None
    state["jobs"] = job_state
    _save_json(state_path, state)


def run_scheduler_loop(
    config_path: Path,
    *,
    once: bool = False,
    poll_seconds: int = 20,
) -> int:
    state_path, pid_path, log_path = _runtime_paths(config_path)
    pid_path.write_text(str(os.getpid()), encoding="utf-8")
    _append_log(log_path, "INFO", "Scheduler runtime start")
    state = _load_json(state_path)
    try:
        while True:
            state["last_heartbeat"] = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            _save_json(state_path, state)
            _run_due_jobs(config_path, state, state_path, log_path)
            if once:
                break
            time.sleep(max(5, int(poll_seconds)))
    except Exception as exc:  # pragma: no cover - runtime guard
        _append_log(log_path, "ERROR", f"Scheduler runtime crash: {exc}")
        return 1
    finally:
        pid_path.unlink(missing_ok=True)
        _append_log(log_path, "INFO", "Scheduler runtime stop")
    return 0
