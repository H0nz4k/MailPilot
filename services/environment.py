"""Přehled souborů a příkazů pro běh bez grafického rozhraní."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from credential_store import CredentialStoreError, credential_account
from env_store import RESEND_KEY_NAME
from planovac import previous_closing_period, scheduled_z17_year
from services.scheduler import scheduler_path


LOG_DIRECTORY = "logy"

__all__ = [
    "CliCommand",
    "FileEntry",
    "application_files",
    "cli_commands",
    "secret_locations",
]


@dataclass(frozen=True)
class CliCommand:
    """Jeden příkaz, který zvládne aplikaci spustit bez okna."""

    label: str
    command: str
    description: str
    log: str


@dataclass(frozen=True)
class FileEntry:
    """Soubor nebo složka, se kterou aplikace pracuje."""

    label: str
    path: Path
    note: str

    @property
    def exists(self) -> bool:
        return self.path.exists()


def cli_commands(*, reference: datetime | None = None) -> tuple[CliCommand, ...]:
    """Příkazy včetně příkladů období odvozených od dnešního data."""
    period = previous_closing_period(reference)
    year = scheduled_z17_year(reference)
    return (
        CliCommand(
            label="Denní stav e-mailem",
            command="MailPilot.exe --poctyemailem",
            description=(
                "Vytvoří PDF k dnešnímu datu a odešle ho příjemcům funkce "
                "Denní stav. Respektuje volbu „jen ve varných dnech“."
            ),
            log=f"{LOG_DIRECTORY}\\automaticky_export.log",
        ),
        CliCommand(
            label="Uzávěrka za měsíc",
            command=f"MailPilot.exe --zaverka_{period}",
            description="Zpracuje uzávěrku za zadaný měsíc ve tvaru MMRRRR.",
            log=f"{LOG_DIRECTORY}\\uzaverka.log",
        ),
        CliCommand(
            label="Uzávěrka aktuálního měsíce",
            command="MailPilot.exe --zaverka_am",
            description="Měsíc si vezme z databáze, hodí se pro plánovač.",
            log=f"{LOG_DIRECTORY}\\uzaverka.log",
        ),
        CliCommand(
            label="Podklad Z 17-01",
            command=f"MailPilot.exe --z17_{year}",
            description="Vytvoří roční podklad Z 17-01 za zadaný rok.",
            log=f"{LOG_DIRECTORY}\\z17.log",
        ),
    )


def application_files(config_path: Path) -> tuple[FileEntry, ...]:
    """Cesty, které se hodí při hledání nastavení a logů."""
    config_path = Path(config_path).resolve()
    directory = config_path.parent
    return (
        FileEntry(
            label="Nastavení",
            path=config_path,
            note="Sdílené s původním rozhraním i s během bez GUI.",
        ),
        FileEntry(
            label="Resend API klíč",
            path=directory / ".env",
            note=f"Proměnná {RESEND_KEY_NAME}; soubor nesdílejte.",
        ),
        FileEntry(
            label="Plánovač",
            path=scheduler_path(config_path),
            note="Seznam naplánovaných úloh.",
        ),
        FileEntry(
            label="Logy",
            path=directory / LOG_DIRECTORY,
            note="Záznamy běhů bez GUI; rotují po 5 MB.",
        ),
    )


def secret_locations(database: dict | None = None) -> tuple[str, ...]:
    """Kde končí hesla, aby je nikdo nehledal v config.json."""
    try:
        account = credential_account(database or {})
    except CredentialStoreError:
        account = "účet podle připojení"
    return (
        f"Heslo databáze: Správce přihlašovacích údajů Windows ({account}).",
        "Heslo administrace: Správce přihlašovacích údajů Windows.",
        f"Resend API klíč: soubor .env, proměnná {RESEND_KEY_NAME}.",
    )
