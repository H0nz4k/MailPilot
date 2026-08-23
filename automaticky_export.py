#!/usr/bin/env python3
"""Bezobslužný denní export pro Windows Plánovač úloh."""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Sequence

from credential_store import CredentialStoreError
from env_store import EnvStoreError, get_resend_api_key
from mail_service import (
    cooking_status_message,
    fetch_cooking_status,
    mail_subject,
    normalize_recipient,
    normalize_recipients,
    send_pdf_via_mailsender,
    should_send_on_cooking_day,
)
from pocty_nastaveni import parse_client_categories
from runtime_paths import application_directory
from services.jidelnasql_warning import (
    clear_jidelnasql_mail_warning,
    peek_warning_settings,
    show_jidelnasql_mail_warning,
)
from stravovaci_sestava import ConfigError, create_pdf, fetch_report, load_config


LOG_MAX_BYTES = 5 * 1024 * 1024
RETRY_DELAYS_SECONDS = (60, 300, 900)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Vytvoří dnešní PDF a odešle je podle uloženého nastavení."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=application_directory() / "config.json",
        help="cesta ke config.json",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=application_directory() / "logy" / "automaticky_export.log",
        help="cesta k provoznímu logu",
    )
    return parser.parse_args(argv)


def read_saved_settings(path: Path) -> dict[str, Any]:
    """Načte uložený JSON pro bezobslužný běh."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Konfigurační soubor neexistuje: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"Neplatný JSON v {path} (řádek {exc.lineno}, sloupec {exc.colno})."
        ) from exc
    if not isinstance(raw, dict):
        raise ConfigError("Kořen configu musí být JSON objekt.")
    return raw


def cooking_day_filter_enabled(raw: dict[str, Any]) -> bool:
    """Vrátí bezpečně ověřený přepínač kontroly varných dnů."""
    only_cooking_days = raw.get("mail_jen_varne_dny", False)
    if not isinstance(only_cooking_days, bool):
        raise ConfigError(
            "'mail_jen_varne_dny' musí být JSON hodnota true nebo false."
        )
    return only_cooking_days


def mail_settings(raw: dict[str, Any]) -> tuple[tuple[str, ...], str, str]:
    """Ověří příjemce, odesílatele a tělo zprávy až před odesláním."""
    recipients = normalize_recipients(raw.get("mail_prijemci"))
    sender = normalize_recipient(raw.get("mail_odesilatel"))
    body = raw.get("mail_text", "")
    if not isinstance(body, str):
        raise ConfigError("'mail_text' musí být textová hodnota.")
    return recipients, sender, body


def rotate_log(path: Path) -> None:
    """Udrží provozní log v rozumné velikosti."""
    if path.is_file() and path.stat().st_size >= LOG_MAX_BYTES:
        archive = path.with_suffix(path.suffix + ".1")
        archive.unlink(missing_ok=True)
        path.replace(archive)


def write_log(path: Path, level: str, message: str) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    rotate_log(path)
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
    with path.open("a", encoding="utf-8") as stream:
        stream.write(f"{timestamp} [{level}] {message}\n")


def run_scheduled_export(config_path: Path, run_date: date) -> dict[str, Any]:
    """Provede jeden export; datum je záměrně předáno volajícím."""
    config_path = config_path.resolve()
    raw = read_saved_settings(config_path)
    only_cooking_days = cooking_day_filter_enabled(raw)
    client_categories = parse_client_categories(raw)

    # Uložené datum v configu se pro automatický běh vždy přepíše dnešním dnem.
    report_date = run_date.strftime("%d.%m.%Y")
    config = load_config(config_path, date_override=report_date)

    if only_cooking_days:
        statuses = fetch_cooking_status(config)
        if not should_send_on_cooking_day(statuses):
            return {
                "status": "skipped",
                "message": cooking_status_message(statuses),
                "date": run_date,
                "categories": client_categories,
            }

    # Mailová konfigurace a klíč nejsou potřeba, pokud se běh korektně přeskočil.
    recipients, sender, body = mail_settings(raw)
    api_key = get_resend_api_key() or ""
    if not api_key:
        raise ConfigError(
            "Není uložený Resend API klíč. Otevřete UI, vyplňte jej a uložte nastavení."
        )

    report = fetch_report(config)
    pdf_path = create_pdf(config, report)
    dispatch = send_pdf_via_mailsender(
        recipients,
        mail_subject(config.report_date),
        body,
        pdf_path,
        api_key=api_key,
        sender_email=sender,
    )
    return {
        "status": "sent",
        "date": run_date,
        "path": pdf_path,
        "recipients": dispatch.recipients,
        "detail": dispatch.detail,
        "categories": client_categories,
    }


def _has_internet() -> bool:
    probes = (("1.1.1.1", 53), ("8.8.8.8", 53), ("api.resend.com", 443))
    for host, port in probes:
        try:
            with socket.create_connection((host, port), timeout=3):
                return True
        except OSError:
            continue
    return False


def _is_retryable(exc: Exception) -> bool:
    text = str(exc).lower()
    retry_tokens = (
        "timeout",
        "timed out",
        "temporary",
        "temporar",
        "connection",
        "connect",
        "network",
        "internet",
        "could not translate host",
        "name or service not known",
        "server closed the connection",
        "connection reset",
        "refused",
    )
    return any(token in text for token in retry_tokens)


def run_scheduled_export_with_retry(
    config_path: Path,
    run_date: date,
    log_path: Path,
) -> dict[str, Any]:
    if not _has_internet():
        raise RuntimeError("Internet není dostupný (kontrola spojení selhala).")
    attempts = 1 + len(RETRY_DELAYS_SECONDS)
    last_error: Exception | None = None
    for index in range(attempts):
        attempt_no = index + 1
        try:
            if attempt_no > 1:
                write_log(
                    log_path,
                    "WARN",
                    f"Retry pokus {attempt_no}/{attempts} pro automatický export.",
                )
            return run_scheduled_export(config_path, run_date)
        except (ConfigError, CredentialStoreError, EnvStoreError, RuntimeError) as exc:
            last_error = exc
            if index >= len(RETRY_DELAYS_SECONDS) or not _is_retryable(exc):
                raise
            delay = RETRY_DELAYS_SECONDS[index]
            write_log(
                log_path,
                "WARN",
                f"Automatický export selhal ({exc}); další pokus za {delay} s.",
            )
            time.sleep(delay)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Automatický export selhal bez detailu.")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    today = date.today()
    write_log(args.log, "START", f"Automatický export pro {today.strftime('%d.%m.%Y')}")
    warning_settings = None

    def warning_failure(reason: str) -> None:
        if warning_settings is None:
            return
        note = show_jidelnasql_mail_warning(warning_settings, when=datetime.now())
        if note:
            write_log(
                args.log,
                "WARN",
                f"{reason}; dashboard warning se nepodařilo zapsat: {note}",
            )

    try:
        warning_settings = peek_warning_settings(read_saved_settings(args.config))
        result = run_scheduled_export_with_retry(args.config, today, args.log)
    except (ConfigError, CredentialStoreError, EnvStoreError, RuntimeError) as exc:
        write_log(args.log, "ERROR", str(exc))
        warning_failure("Automatický export selhal")
        print(f"CHYBA: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        write_log(args.log, "ERROR", f"Neočekávaná chyba: {exc}")
        warning_failure("Automatický export selhal")
        print(f"CHYBA: {exc}", file=sys.stderr)
        return 1

    if result["status"] == "skipped":
        message = str(result["message"])
        write_log(args.log, "SKIP", message)
        print(f"NEODESLÁNO: {message}")
        return 0

    recipients = result["recipients"]
    categories = result.get("categories") or ()
    detail = f"; {result['detail']}" if result.get("detail") else ""
    message = (
        f"Odesláno {len(recipients)} příjemcům; "
        f"kategorie klienta: {len(categories)}; "
        f"PDF: {result['path']}{detail}"
    )
    warning_note = clear_jidelnasql_mail_warning(warning_settings)
    if warning_note:
        write_log(args.log, "WARN", warning_note)
    write_log(args.log, "OK", message)
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
