"""Persistent central scheduler for independent DataShip web tasks.

Usage: python -m services.web_mail_worker --config C:\\MailPilot\\config.json
Run only one worker instance per installation (normally via NSSM).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import time
import threading
import tempfile
from datetime import date, datetime
from pathlib import Path

from automaticky_export import read_saved_settings
from env_store import get_resend_api_key
from mail_service import mail_subject, normalize_recipient, send_pdf_via_mailsender
from services.jidelnasql_warning import (
    peek_warning_settings, show_jidelnasql_mail_warning,
)
from services.web_mail_task_store import load_tasks, task_file
from services.web_mail_settings import load_settings, settings_path
from services.web_branding import WEB_VERSION
from services.web_mail_smtp import smtp_send
from services.jidelnasql_warning import JidelnaWarningSettings
from services.web_mail_cooking_days import resolve_task_date, report_is_cooking_day
from services.web_daily_profiles import task_report_config
from stravovaci_sestava import load_config, fetch_report, create_pdf

from services.web_activity import record_event, friendly_error
from services.web_worker_status import write_runtime

LOG = logging.getLogger("mailpilot.web_worker")
STOP = False
RUNTIME = {"phase": "waiting", "task_id": None}


def runtime_status(config_path, phase=None, task_id=None):
    if phase is not None:
        RUNTIME.update(phase=phase, task_id=task_id)
    try:
        write_runtime(config_path.parent, **RUNTIME.copy())
    except OSError:
        LOG.exception("Cannot update scheduler heartbeat")


def request_stop(*_):
    global STOP
    STOP = True


def deliver_daily(config_path: Path, task, report_date: date) -> None:
    raw = read_saved_settings(config_path)
    config = load_config(config_path, date_override=report_date.strftime("%d.%m.%Y"))
    config = task_report_config(config, raw, task, config_path.parent)
    report = fetch_report(config)
    if getattr(task, "output_mode", "email") == "pdf":
        from services.web_mail_tasks import validate_pdf_destination
        folder, filename = validate_pdf_destination(task.output_directory, task.output_filename)
        if not Path(folder).is_absolute():
            raise ValueError("Složka PDF musí být úplná cesta platná v tomto systému.")
        output = Path(folder) / filename.format(date=report_date.isoformat())
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".dataship-", suffix=".pdf", delete=False) as file:
                temporary = Path(file.name)
            create_pdf(config, report, output_path=temporary)
            os.replace(temporary, output)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
        record_event(config_path.parent, "exported", f"PDF uloženo: {output}",
                     task_id=task.id, task_name=task.name, report_date=report_date)
        LOG.info("Exported task=%s date=%s file=%s", task.id, report_date, output)
        return
    settings = load_settings(settings_path(config_path.parent))
    if getattr(task, "profile_id", None):
        # Profile outputs must not overwrite a global or other profile's PDF.
        from hashlib import sha256
        suffix = sha256(task.profile_id.encode("utf-8")).hexdigest()[:12]
        output = config.pdf_output.with_name(f"{config.pdf_output.stem}_prehled_{suffix}{config.pdf_output.suffix}")
        pdf = create_pdf(config, report, output_path=output)
    else:
        pdf = create_pdf(config, report)
    report_label = "Denní stav"
    data = {"report": report_label, "date": report_date.strftime("%d.%m.%Y")}
    subject = settings["subject_template"].format(**data)
    body = settings["body_template"].format(**data)
    if settings["transport"] == "smtp":
        result = smtp_send(settings, task.recipients, subject, body, pdf)
    else:
        sender = normalize_recipient(settings["from_email"] or raw.get("mail_odesilatel"))
        api_key = get_resend_api_key()
        if not api_key:
            raise ValueError("Chybí Resend API klíč.")
        sent = send_pdf_via_mailsender(
            task.recipients, subject, body, pdf,
            api_key=api_key, sender_email=sender,
        )
        result = sent.recipients
    record_event(config_path.parent, "sent", "Odesláno.", task_id=task.id, task_name=getattr(task, "name", ""), report_date=report_date)
    LOG.info("Sent task=%s date=%s recipients=%s", task.id, report_date, result)

def dispatch(config_path: Path, task, sent_on: date) -> None:
    if task.report != "daily":
        raise ValueError("Souhrn počtu jídel zatím není propojen se sestavou.")
    # Resolve from real public.varnedny data (A/N), never from weekdays.
    report_date = resolve_task_date(config_path, task, sent_on)
    if not report_is_cooking_day(config_path, task, report_date):
        message = f"Přeskočeno: pro {report_date:%d.%m.%Y} není varný den vybraného typu stravy."
        record_event(config_path.parent, "skipped", message, task_id=task.id, task_name=task.name, report_date=report_date)
        LOG.info("Skipped task=%s date=%s: target is not a cooking day", task.id, report_date)
        return
    deliver_daily(config_path, task, report_date)


def state_path(config_path: Path) -> Path:
    return config_path.parent / "web_mail_worker_state.json"


def load_state(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not isinstance(raw.get("completed"), dict):
            raise ValueError("Invalid worker state")
        return raw["completed"]
    except FileNotFoundError:
        return {}


def save_state(path: Path, completed: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with tmp.open("w", encoding="utf-8") as file:
            json.dump({"completed": completed}, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def tick(config_path: Path, now: datetime | None = None) -> None:
    now = now or datetime.now()
    completed_path = state_path(config_path)
    completed = load_state(completed_path)
    tasks = load_tasks(task_file(config_path.parent))
    for task in tasks:
        if not task.enabled or task.id in completed and completed[task.id] == now.date().isoformat():
            continue
        if getattr(task, "first_send_date", None) and now.date() < date.fromisoformat(task.first_send_date):
            continue
        hh, mm = map(int, task.send_time.split(":"))
        if (now.hour, now.minute) < (hh, mm):
            continue
        try:
            runtime_status(config_path, "running", task.id)
            dispatch(config_path, task, now.date())
        except Exception as exc:
            LOG.exception("Task %s failed", task.name)
            summary = friendly_error(exc)
            failure = "PDF nebylo vytvořeno: " if task.output_mode == "pdf" else "Neodesláno: "
            record_event(config_path.parent, "error", failure + summary + " Další automatický pokus bude nejdříve zítra.", task_id=task.id, task_name=task.name)
            # The warning only adds information; it must not mask delivery errors.
            try:
                web_settings = load_settings(settings_path(config_path.parent))
                settings = JidelnaWarningSettings(
                    enabled=web_settings["dashboard_enabled"],
                    template_path=Path(web_settings["dashboard_path"]),
                )
                warning_error = show_jidelnasql_mail_warning(
                    settings, message=f"MailShip: úloha {task.name} selhala. {summary}"
                )
                if warning_error:
                    LOG.error("Dashboard warning: %s", warning_error)
            except Exception:
                LOG.exception("Cannot update JídelnaSQL dashboard")
            # Avoid rapid retry storms. Retry on next scheduled day until
            # an explicit retry policy with backoff is implemented.
            completed[task.id] = now.date().isoformat()
            save_state(completed_path, completed)
            runtime_status(config_path, "waiting")
            continue
        completed[task.id] = now.date().isoformat()
        save_state(completed_path, completed)
        runtime_status(config_path, "waiting")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version", version=f"DataShip Worker {WEB_VERSION}")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--interval", type=int, default=30)
    args = parser.parse_args()
    if args.interval < 10:
        parser.error("--interval must be >= 10")
    config_path = args.config.resolve()
    log_dir = config_path.parent / "logy"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "web_mail_worker.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    LOG.info("DataShip scheduler started: %s", config_path)
    record_event(config_path.parent, "started", "Plánovač byl spuštěn.")
    heartbeat_stop = threading.Event()
    def heartbeat():
        while not heartbeat_stop.wait(15):
            runtime_status(config_path)
    runtime_status(config_path, "waiting")
    heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
    heartbeat_thread.start()
    while not STOP:
        try:
            tick(config_path)
        except Exception:
            LOG.exception("Scheduler tick failed")
            record_event(config_path.parent, "error", "Plánovač nemohl načíst nebo zpracovat úlohy. Zkontrolujte konfiguraci a technický log.")
        runtime_status(config_path, "waiting")
        time.sleep(args.interval)
    LOG.info("DataShip scheduler stopped")
    heartbeat_stop.set()
    heartbeat_thread.join(timeout=2)
    runtime_status(config_path, "stopped")
    record_event(config_path.parent, "stopped", "Plánovač byl zastaven.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())




