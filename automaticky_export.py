#!/usr/bin/env python3
"""Bezobslužný denní export pro Windows Plánovač úloh."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import socket
import sys
import time
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Sequence

from credential_store import CredentialStoreError
from env_store import EnvStoreError, get_resend_api_key
from gui_qt import APP_TITLE, APP_VERSION
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
from services.pricing_mode import detect_pricing_mode_info, pricing_mode_label
from stravovaci_sestava import ConfigError, create_pdf, fetch_report, load_config


LOG_MAX_BYTES = 5 * 1024 * 1024
RETRY_DELAYS_SECONDS = (60, 300, 900)
_HTTP_STATUS_RE = re.compile(r"\b([1-5]\d{2})\b")
_RETRY_AFTER_RE = re.compile(
    r"retry[- ]after\s*[:=]?\s*([0-9]+)", re.IGNORECASE
)


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


def _extract_http_status(message: str) -> int | None:
    for token in _HTTP_STATUS_RE.findall(message):
        try:
            value = int(token)
        except ValueError:
            continue
        if 100 <= value <= 599:
            return value
    return None


def _extract_retry_after_seconds(message: str) -> int | None:
    match = _RETRY_AFTER_RE.search(message)
    if match:
        try:
            return max(1, int(match.group(1)))
        except ValueError:
            return None
    # Fallback na HTTP-date formát.
    marker = message.lower().find("retry-after:")
    if marker < 0:
        return None
    raw = message[marker + len("retry-after:") :].splitlines()[0].strip()
    if not raw:
        return None
    try:
        target = parsedate_to_datetime(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    delta = int((target - datetime.now(target.tzinfo)).total_seconds())
    return max(1, delta)


def _is_retryable(exc: Exception) -> bool:
    text = str(exc)
    lower = text.lower()
    status = _extract_http_status(text)
    if status == 429 or status == 408 or (status is not None and 500 <= status <= 599):
        return True
    if status in {400, 401, 403, 404, 422}:
        return False
    permanent_tokens = (
        "invalid api key",
        "neplatný api klíč",
        "unauthorized",
        "forbidden",
        "invalid recipient",
        "validation error",
        "neplatná e-mailová adresa",
        "chybí resend api klíč",
        "zadejte resend api klíč",
    )
    if any(token in lower for token in permanent_tokens):
        return False
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
        "too many requests",
        "rate limit",
        "retry-after",
    )
    return any(token in lower for token in retry_tokens)


def run_scheduled_export_with_retry(
    config_path: Path,
    run_date: date,
    log_path: Path,
) -> dict[str, Any]:
    attempts = 1 + len(RETRY_DELAYS_SECONDS)
    last_error: Exception | None = None
    for index in range(attempts):
        attempt_no = index + 1
        write_log(
            log_path,
            "INFO",
            f"Automatický export attempt {attempt_no}/{attempts}.",
        )
        if not _has_internet():
            write_log(
                log_path,
                "WARN",
                "Diagnostika: internet check selhal, zkouším API volání i tak.",
            )
        try:
            result = run_scheduled_export(config_path, run_date)
            write_log(
                log_path,
                "INFO",
                f"Automatický export attempt {attempt_no}/{attempts} uspěl.",
            )
            return result
        except (ConfigError, CredentialStoreError, EnvStoreError, RuntimeError) as exc:
            last_error = exc
            retryable = _is_retryable(exc)
            status = _extract_http_status(str(exc))
            retry_after = (
                _extract_retry_after_seconds(str(exc)) if status == 429 else None
            )
            if index >= len(RETRY_DELAYS_SECONDS) or not retryable:
                write_log(
                    log_path,
                    "ERROR",
                    f"Attempt {attempt_no}/{attempts} selhal: {exc} "
                    f"(retry={retryable}).",
                )
                raise
            delay = RETRY_DELAYS_SECONDS[index]
            if retry_after is not None:
                delay = max(delay, retry_after)
            write_log(
                log_path,
                "WARN",
                f"Attempt {attempt_no}/{attempts} selhal: {exc}; "
                f"další retry za {delay} s.",
            )
            time.sleep(delay)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Automatický export selhal bez detailu.")


def _runtime_identity() -> str:
    user = getpass.getuser().strip()
    domain = str(os.environ.get("USERDOMAIN") or "").strip()
    if domain and "\\" not in user:
        return f"{domain}\\{user}"
    return user or "unknown"


def _detect_pricing_mode(config_path: Path, run_date: date) -> str:
    try:
        import psycopg
    except ImportError:
        return "nelze určit (chybí psycopg)"
    try:
        config = load_config(config_path, date_override=run_date.strftime("%d.%m.%Y"))
    except Exception as exc:
        return f"nelze určit ({exc})"
    try:
        with psycopg.connect(**config.database) as connection:
            with connection.cursor() as cursor:
                info = detect_pricing_mode_info(cursor)
    except Exception as exc:
        return f"nelze určit ({exc})"
    return f"{pricing_mode_label(info.mode)} [{info.source}]"


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    today = date.today()
    write_log(
        args.log,
        "START",
        f"{APP_TITLE} {APP_VERSION} · mode=automatic_export · "
        f"identity={_runtime_identity()} · date={today.strftime('%d.%m.%Y')}",
    )
    write_log(args.log, "INFO", f"Cenový režim: {_detect_pricing_mode(args.config, today)}")
    warning_settings = None

    def warning_failure(reason: str, detail: str = "") -> None:
        if warning_settings is None:
            return
        message = f"{reason}: {detail}".strip(": ").strip()
        note = show_jidelnasql_mail_warning(
            warning_settings,
            when=datetime.now(),
            message=message,
        )
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
        warning_failure("Automatický export selhal", str(exc))
        print(f"CHYBA: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        write_log(args.log, "ERROR", f"Neočekávaná chyba: {exc}")
        warning_failure("Automatický export selhal", str(exc))
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
