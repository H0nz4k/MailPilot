"""Čtení, zápis a interpretace config.json bez závislosti na GUI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

from credential_store import write_config
from runtime_paths import bundled_path
from stravovaci_sestava import ConfigError
from uzaverka_nastaveni import czech_month_name


CZECH_DATE_FORMAT = "%d.%m.%Y"
DEFAULT_PDF_OUTPUT = "vystup/AutoReport_{datum}.pdf"


def load_raw_config(path: Path) -> dict[str, Any]:
    """Načte provozní config, nebo bezpečný vzor při prvním spuštění."""
    source = path if path.is_file() else bundled_path("config.example.json")
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Konfigurační soubor neexistuje: {source}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"Neplatný JSON v {source} (řádek {exc.lineno}, sloupec {exc.colno})."
        ) from exc
    if not isinstance(raw, dict):
        raise ConfigError("Kořen configu musí být JSON objekt.")
    return raw


def save_raw_config(path: Path, raw: dict[str, Any]) -> None:
    """Uloží config bez hesla a API klíčů (atomický zápis)."""
    write_config(path, raw)


def database_parameters(raw: dict[str, Any]) -> dict[str, Any]:
    database = raw.get("databaze", {})
    if not isinstance(database, dict):
        database = {}
    return {
        "host": str(database.get("host", "127.0.0.1")).strip(),
        "port": database.get("port", 5432),
        "dbname": str(database.get("dbname", "jidelna")).strip(),
        "user": str(database.get("user", "altisima-client")).strip(),
        "sslmode": str(database.get("sslmode", "prefer")).strip() or "prefer",
        "connect_timeout": int(database.get("connect_timeout", 10)),
    }


def normalize_database(values: dict[str, Any]) -> dict[str, Any]:
    """Zvaliduje ručně zadané připojení z formuláře administrace."""
    host = str(values.get("host") or "").strip()
    dbname = str(values.get("dbname") or "").strip()
    user = str(values.get("user") or "").strip()
    if not host or not dbname or not user:
        raise ConfigError("IP/server, název databáze a uživatel jsou povinné.")
    try:
        port = int(values.get("port"))
    except (TypeError, ValueError) as exc:
        raise ConfigError("Port musí být celé číslo.") from exc
    if not 1 <= port <= 65535:
        raise ConfigError("Port musí být v rozsahu 1–65535.")
    sslmode = str(values.get("sslmode") or "prefer").strip() or "prefer"
    return {
        "host": host,
        "port": port,
        "dbname": dbname,
        "user": user,
        "sslmode": sslmode,
        "connect_timeout": int(values.get("connect_timeout", 10)),
    }


def connection_identity(
    subject_name: str | None,
    database_name: str,
    database: dict[str, Any],
    jidelna_period: tuple[int, int] | None = None,
) -> tuple[str, str]:
    """Připraví výraznou identitu právě ověřeného databázového připojení."""
    subject = str(subject_name or "").strip()
    if not subject:
        subject = "Název provozovny není v databázi nastaven"
    host = str(database.get("host", "")).strip()
    port = database.get("port", "")
    details = f"Databáze: {database_name} · Server: {host}:{port}"
    if jidelna_period is not None:
        year, month = jidelna_period
        details += (
            f" · Aktuální měsíc: {czech_month_name(month)} {year} "
            f"({month:02d}{year:04d})"
        )
    return subject, details


def configured_date(raw: dict[str, Any]) -> date:
    value = raw.get("datum")
    if isinstance(value, str):
        try:
            day, month, year = (int(part) for part in value.split("."))
            return date(year, month, day)
        except (TypeError, ValueError):
            pass
    return date.today()


def parse_czech_date(value: object) -> date:
    """Převede datum z UI ve formátu DD.MM.RRRR na date."""
    text = str(value or "").strip()
    try:
        parsed = datetime.strptime(text, CZECH_DATE_FORMAT).date()
    except ValueError as exc:
        raise ConfigError(
            "Zvolené datum není platné; použijte formát DD.MM.RRRR."
        ) from exc
    if parsed.strftime(CZECH_DATE_FORMAT) != text:
        raise ConfigError(
            "Zvolené datum není platné; použijte formát DD.MM.RRRR."
        )
    return parsed


def placeholder_tail(path: str) -> tuple[str, ...]:
    """Koncové části cesty se zástupnou hodnotou, například ``{rok}``."""
    parts = [part for part in str(path or "").replace("\\", "/").split("/") if part]
    tail: list[str] = []
    for part in reversed(parts):
        if "{" in part and "}" in part:
            tail.insert(0, part)
            continue
        break
    return tuple(tail)


def join_picked_directory(current: str, chosen: str) -> str:
    """Po výběru složky zachová zástupné hodnoty z původní cesty."""
    picked = Path(str(chosen or "").strip())
    tail = placeholder_tail(current)
    for part in tail:
        picked = picked / part
    return str(picked)


def open_document(path: Path) -> None:
    """Otevře vytvořené PDF ve výchozí systémové aplikaci."""
    path = path.resolve()
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
