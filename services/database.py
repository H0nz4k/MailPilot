"""Ověření databázového připojení pro jakoukoli prezentační vrstvu."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from credential_store import get_password, set_password
from stravovaci_sestava import SUBJECT_NAME_QUERY, peek_jidelna_period

from services.config_io import connection_identity


CATEGORY_QUERY = """
SELECT BTRIM(oznaceni), COALESCE(NULLIF(BTRIM(nazev), ''), '')
FROM public.kategor
WHERE NULLIF(BTRIM(oznaceni), '') IS NOT NULL
ORDER BY LOWER(BTRIM(oznaceni)), BTRIM(oznaceni)
"""


@dataclass(frozen=True)
class ConnectionInfo:
    """Výsledek úspěšného testu připojení."""

    categories: tuple[tuple[str, str], ...] = ()
    database_name: str = ""
    subject_name: str | None = None
    period: tuple[int, int] | None = None
    database: dict[str, Any] = field(default_factory=dict)

    def identity(self) -> tuple[str, str]:
        return connection_identity(
            self.subject_name, self.database_name, self.database, self.period
        )

    @property
    def name(self) -> str:
        return self.identity()[0]

    @property
    def details(self) -> str:
        return self.identity()[1]

    @property
    def period_label(self) -> str:
        if self.period is None:
            return ""
        year, month = self.period
        return f"{month:02d}/{year:04d}"


def stored_password(database: dict[str, Any]) -> str:
    """Heslo ze systémového trezoru; prázdný text, pokud uložené není."""
    return get_password(database) or ""


def probe_connection(
    database: dict[str, Any], password: str, *, remember: bool = True
) -> ConnectionInfo:
    """Otevře spojení, načte kategorie, provozovnu a aktuální období."""
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - závisí na instalaci
        raise RuntimeError(
            "Chybí psycopg. Nainstalujte requirements.txt."
        ) from exc
    with psycopg.connect(**dict(database, password=password)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            database_name = str(cursor.fetchone()[0])
            cursor.execute(CATEGORY_QUERY)
            categories = tuple(
                (str(code), str(name)) for code, name in cursor.fetchall()
            )
            cursor.execute(SUBJECT_NAME_QUERY)
            subject_row = cursor.fetchone()
            subject_name = str(subject_row[0]) if subject_row else None
            period = peek_jidelna_period(cursor)
    if remember:
        set_password(database, password)
    return ConnectionInfo(
        categories=categories,
        database_name=database_name,
        subject_name=subject_name,
        period=period,
        database=dict(database),
    )