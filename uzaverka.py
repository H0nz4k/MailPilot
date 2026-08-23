#!/usr/bin/env python3
"""Tichá měsíční uzávěrka: PDF sestavy, ZIP a odeslání účetní."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

from credential_store import CredentialStoreError
from env_store import EnvStoreError, get_resend_api_key
from fksp_sestava import export_fksp_pdf
from rekapitulace_sestava import export_recap_pdf
from stravovaci_arch import export_arch_pdf
from mail_service import (
    normalize_recipient,
    normalize_recipients,
    send_files_via_mailsender,
)
from runtime_paths import application_directory
from stravovaci_sestava import (
    AppConfig,
    ConfigError,
    existing_categories,
    load_config,
    read_jidelna_period,
)
from uzaverka_nastaveni import (
    SESTAVA_ARCH,
    SESTAVA_FKSP,
    SESTAVA_REKAPITULACE,
    CLOSING_FLAG_HELP,
    CURRENT_CLOSING_PERIOD,
    ClosingSettings,
    closing_flag,
    czech_month_name,
    parse_closing_settings,
    parse_period,
    require_closing_flag,
)
from uzaverka_podklady import fetch_closing_podklady


LOG_MAX_BYTES = 5 * 1024 * 1024
ProgressFn = Callable[[int, str], None]

REPORT_WEIGHTS = {
    SESTAVA_FKSP: 12,
    SESTAVA_ARCH: 70,
    SESTAVA_REKAPITULACE: 18,
}
REPORT_LABELS = {
    SESTAVA_FKSP: "FKSP",
    SESTAVA_ARCH: "stravovací archy",
    SESTAVA_REKAPITULACE: "rekapitulace",
}


def emit_progress(on_progress: ProgressFn | None, percent: int, message: str) -> None:
    if on_progress is None:
        return
    on_progress(max(0, min(100, percent)), message)


def bind_progress(on_progress: ProgressFn | None, start: int, end: int) -> Callable[[float, str], None]:
    def bound(fraction: float, message: str) -> None:
        span = end - start
        percent = int(round(start + span * max(0.0, min(1.0, fraction))))
        emit_progress(on_progress, percent, message)

    return bound


def report_ranges(reports: Sequence[str], *, start: int = 6, end: int = 90) -> dict[str, tuple[int, int]]:
    weights = [REPORT_WEIGHTS.get(name, 10) for name in reports]
    total = sum(weights) or 1
    span = end - start
    ranges: dict[str, tuple[int, int]] = {}
    cursor = float(start)
    for name, weight in zip(reports, weights):
        piece = span * (weight / total)
        next_cursor = cursor + piece
        ranges[name] = (int(round(cursor)), int(round(next_cursor)))
        cursor = next_cursor
    return ranges


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    remaining, period = require_closing_flag(raw_argv)
    parser = argparse.ArgumentParser(
        description=(
            "Vytvoří měsíční uzávěrkové PDF a odešle je podle nastavení. "
            f"Období je povinné, například {closing_flag(2026, 7)} "
            "nebo --zaverka_am pro aktuální měsíc z Jídelny."
        )
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
        default=application_directory() / "logy" / "uzaverka.log",
        help="cesta k provoznímu logu",
    )
    args = parser.parse_args(remaining)
    args.uzaverka_current = period == CURRENT_CLOSING_PERIOD
    if args.uzaverka_current:
        args.rok = None
        args.mesic = None
        args.uzaverka_flag = "--zaverka_am"
    else:
        args.rok, args.mesic = period
        args.uzaverka_flag = closing_flag(*period)
    return args


def read_saved_settings(path: Path) -> dict[str, Any]:
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


def closing_mail_settings(
    raw: dict[str, Any],
    settings: ClosingSettings,
) -> tuple[tuple[str, ...], str, str]:
    """Příjemce uzávěrky; nepoužívá adresy denního stavu."""
    _ignored, sender, _ignored_body = mail_settings_from_raw(raw)
    recipients = settings.recipients or ()
    body = settings.mail_body if settings.mail_body is not None else ""
    if not recipients:
        raise ConfigError(
            "Přiřaďte v Nastavení příjemce k funkci Uzávěrka. "
            "Adresy denního stavu se pro uzávěrku nepoužívají."
        )
    return recipients, sender, body


def mail_settings_from_raw(raw: dict[str, Any]) -> tuple[tuple[str, ...], str, str]:
    recipients = normalize_recipients(raw.get("mail_prijemci"), allow_empty=True)
    sender = normalize_recipient(raw.get("mail_odesilatel"))
    body = raw.get("mail_text", "")
    if not isinstance(body, str):
        raise ConfigError("'mail_text' musí být textová hodnota.")
    return recipients, sender, body


def closing_subject(settings: ClosingSettings) -> str:
    return f"Uzávěrka stravného: {settings.period_label}"


def rotate_log(path: Path) -> None:
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


def resolve_categories(config: AppConfig, settings: ClosingSettings) -> AppConfig:
    if not settings.use_all_categories:
        return config
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "Chybí balíček psycopg. Nainstalujte závislosti z requirements.txt."
        ) from exc
    with psycopg.connect(**config.database) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT BTRIM(oznaceni)
                FROM public.kategor
                WHERE NULLIF(BTRIM(oznaceni), '') IS NOT NULL
                ORDER BY LOWER(BTRIM(oznaceni)), BTRIM(oznaceni)
                """
            )
            codes = [row[0] for row in cursor.fetchall()]
    categories = existing_categories(tuple(str(code) for code in codes), codes)
    if not categories:
        raise ConfigError("V public.kategor nejsou žádné kategorie pro uzávěrku.")
    return AppConfig(
        database=config.database,
        report_date=config.report_date,
        categories=categories,
        language=config.language,
        menu_list_number=config.menu_list_number,
        category_separation=config.category_separation,
        show_by_categories=config.show_by_categories,
        show_by_norms=config.show_by_norms,
        pdf_output=config.pdf_output,
        pdf_orientation=config.pdf_orientation,
        pdf_data_font_size=config.pdf_data_font_size,
        pdf_label_font_size=config.pdf_label_font_size,
        pdf_bold=config.pdf_bold,
    )


def pack_zip(files: Sequence[Path], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=path.name)
    return destination


def generate_reports(
    config: AppConfig,
    settings: ClosingSettings,
    on_progress: ProgressFn | None = None,
) -> list[Path]:
    created: list[Path] = []
    emit_progress(on_progress, 6, "Kontroluji uložené podklady k tisku…")
    podklady = fetch_closing_podklady(
        config,
        on_progress=bind_progress(on_progress, 6, 58),
    )
    source = "uložených podkladů" if podklady.from_cache else "aktuálního výpočtu"
    emit_progress(on_progress, 58, f"Podklady z {source} hotové, skládám PDF…")
    ranges = report_ranges(settings.reports, start=58, end=90)
    exporters = {
        SESTAVA_FKSP: export_fksp_pdf,
        SESTAVA_ARCH: export_arch_pdf,
        SESTAVA_REKAPITULACE: export_recap_pdf,
    }
    for report_name in settings.reports:
        exporter = exporters.get(report_name)
        if exporter is None:
            raise ConfigError(f"Sestava {report_name} zatím není implementovaná.")
        start, end = ranges[report_name]
        label = REPORT_LABELS.get(report_name, report_name)
        emit_progress(on_progress, start, f"Začínám sestavu {label}…")
        created.append(
            exporter(
                config,
                settings,
                on_progress=bind_progress(on_progress, start, end),
                podklady=podklady,
            )
        )
    return created


def fetch_current_jidelna_period(config_path: Path) -> tuple[int, int]:
    """Aktuální měsíc a rok z public.parametry (BACKUP / TentoMesic, TentoRok)."""
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Chybí psycopg. Nainstalujte requirements.txt.") from exc
    config = load_config(config_path, date_override="01.01.2000")
    with psycopg.connect(**config.database) as connection:
        with connection.cursor() as cursor:
            return read_jidelna_period(cursor)


def run_monthly_closing(
    config_path: Path,
    *,
    year: int | None = None,
    month: int | None = None,
    current_month: bool = False,
    on_progress: ProgressFn | None = None,
) -> dict[str, Any]:
    config_path = config_path.resolve()
    emit_progress(on_progress, 0, "Spouštím měsíční uzávěrku…")
    raw = read_saved_settings(config_path)
    if current_month:
        emit_progress(on_progress, 1, "Zjišťuji aktuální měsíc z Jídelny…")
        year, month = fetch_current_jidelna_period(config_path)
        emit_progress(
            on_progress,
            2,
            f"Aktuální měsíc v Jídelně: {czech_month_name(month)} {year}.",
        )
    if year is None or month is None:
        raise ConfigError(CLOSING_FLAG_HELP)
    period_year, period_month = parse_period(year, month)
    emit_progress(
        on_progress,
        2,
        f"Období {czech_month_name(period_month)} {period_year}, načítám nastavení…",
    )
    settings = parse_closing_settings(
        raw,
        year=period_year,
        month=period_month,
        config_directory=config_path.parent,
    )
    config = load_config(
        config_path,
        date_override=f"01.{period_month:02d}.{period_year}",
    )
    emit_progress(on_progress, 4, "Načítám kategorie z databáze…")
    config = resolve_categories(config, settings)
    emit_progress(
        on_progress,
        6,
        f"Kategorie připravené ({len(config.categories)}), tvořím sestavy…",
    )

    pdf_files = generate_reports(config, settings, on_progress=on_progress)
    if settings.attachment_mode == "zip":
        emit_progress(on_progress, 92, "Balím PDF do ZIP…")
        zip_name = f"Uzaverka_{settings.period_stamp}.zip"
        attachments = [pack_zip(pdf_files, settings.output_directory / zip_name)]
        emit_progress(on_progress, 96, f"ZIP uložen: {attachments[0].name}")
    else:
        emit_progress(on_progress, 94, "Přílohy nechávám jako samostatné PDF.")
        attachments = pdf_files

    if not settings.send_mail:
        emit_progress(on_progress, 100, "Hotovo, mail se neodesílá.")
        return {
            "status": "exported",
            "year": period_year,
            "month": period_month,
            "files": list(pdf_files),
            "attachments": list(attachments),
            "recipients": (),
            "detail": "Mail se neodesílá (uzaverka.odeslat_mail=false).",
        }

    emit_progress(on_progress, 97, "Odesílám uzávěrku e-mailem…")
    recipients, sender, body = closing_mail_settings(raw, settings)
    api_key = get_resend_api_key() or ""
    if not api_key:
        raise ConfigError(
            "Není uložený Resend API klíč. Otevřete UI, vyplňte jej a uložte nastavení."
        )

    dispatch = send_files_via_mailsender(
        recipients,
        closing_subject(settings),
        body,
        attachments,
        api_key=api_key,
        sender_email=sender,
    )
    emit_progress(on_progress, 100, "Hotovo, uzávěrka odeslána.")
    return {
        "status": "sent",
        "year": period_year,
        "month": period_month,
        "files": list(pdf_files),
        "attachments": list(attachments),
        "recipients": dispatch.recipients,
        "detail": dispatch.detail,
    }


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_args(argv)
    except ConfigError as exc:
        print(f"CHYBA: {exc}", file=sys.stderr)
        return 2
    write_log(
        args.log,
        "START",
        f"Měsíční uzávěrka {args.uzaverka_flag}",
    )

    def on_progress(percent: int, message: str) -> None:
        write_log(args.log, "PRUBEH", f"{percent}% {message}")
        print(f"[{percent:3d} %] {message}", flush=True)

    try:
        result = run_monthly_closing(
            args.config,
            year=args.rok,
            month=args.mesic,
            current_month=args.uzaverka_current,
            on_progress=on_progress,
        )
    except (ConfigError, CredentialStoreError, EnvStoreError, RuntimeError) as exc:
        write_log(args.log, "ERROR", str(exc))
        print(f"CHYBA: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        write_log(args.log, "ERROR", f"Neočekávaná chyba: {exc}")
        print(f"CHYBA: {exc}", file=sys.stderr)
        return 1

    files = ", ".join(str(path) for path in result["attachments"])
    period = f"{result['month']:02d}/{result['year']}"
    if result["status"] == "exported":
        message = f"NEODESLÁNO: {period}; soubory: {files}; {result['detail']}"
    else:
        recipients = result["recipients"]
        detail = f"; {result['detail']}" if result.get("detail") else ""
        message = f"Odesláno {len(recipients)} příjemcům; {period}; {files}{detail}"
    write_log(args.log, "OK", message)
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
