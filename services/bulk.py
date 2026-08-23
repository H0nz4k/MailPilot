"""Hromadná zpráva pro libovolnou prezentační vrstvu.

Obal nad ``hromadna_zprava.py``: načtení příjemců z databáze, filtrování
podle tříd nebo kategorií, souhrn a odeslání. Vlastní odesílání i SQL
zůstávají v původním modulu.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from hromadna_zprava import (
    FILTER_CATEGORY,
    FILTER_CLASS,
    FILTER_LABELS,
    BulkDiner,
    BulkPreview,
    apply_bulk_ui,
    bulk_preview_summary,
    fetch_bulk_filters,
    missing_email_counts,
    missing_email_diners,
    option_label,
    peek_bulk_ui,
    preview_from_diners,
    send_bulk_message,
)
from mail_service import MailDispatchResult
from stravovaci_sestava import ConfigError


FILTER_TYPES = (FILTER_CLASS, FILTER_CATEGORY)

__all__ = [
    "FILTER_CATEGORY",
    "FILTER_CLASS",
    "FILTER_LABELS",
    "FILTER_TYPES",
    "BulkData",
    "BulkForm",
    "BulkDiner",
    "BulkPreview",
    "apply_bulk_form",
    "bulk_preview_summary",
    "filter_options",
    "load_bulk_data",
    "missing_email_counts",
    "missing_email_diners",
    "option_label",
    "peek_bulk_form",
    "preview_for",
    "recipient_rows",
    "send_bulk",
    "validate_message",
]


@dataclass(frozen=True)
class BulkForm:
    """Předmět a text uložené v bloku ``hromadna_zprava``."""

    subject: str = ""
    body: str = ""


@dataclass(frozen=True)
class BulkData:
    """Číselníky a strávníci načtení jedním dotazem po testu připojení."""

    classes: tuple[tuple[str, str], ...] = ()
    categories: tuple[tuple[str, str], ...] = ()
    diners: tuple[BulkDiner, ...] = ()

    def options(self, filter_type: str) -> tuple[tuple[str, str], ...]:
        return self.classes if filter_type == FILTER_CLASS else self.categories


def peek_bulk_form(raw: dict[str, Any] | None) -> BulkForm:
    values = peek_bulk_ui(raw if isinstance(raw, dict) else {})
    return BulkForm(subject=values["predmet"], body=values["text"])


def apply_bulk_form(raw: dict[str, Any], form: BulkForm) -> dict[str, Any]:
    return apply_bulk_ui(raw, subject=form.subject, body=form.body)


def load_bulk_data(database: dict[str, Any], password: str) -> BulkData:
    """Jeden průchod databází: třídy, kategorie a všichni strávníci."""
    classes, categories, diners = fetch_bulk_filters(
        dict(database, password=password)
    )
    return BulkData(
        classes=tuple((str(code), str(note)) for code, note in classes),
        categories=tuple((str(code), str(note)) for code, note in categories),
        diners=tuple(diners),
    )


def filter_options(
    data: BulkData, filter_type: str
) -> tuple[tuple[str, str], ...]:
    """Položky pro dialog výběru včetně poznámky o chybějících e-mailech."""
    missing = missing_email_counts(data.diners, filter_type)
    options: list[tuple[str, str]] = []
    for code, note in data.options(filter_type):
        parts = [part for part in (note,) if part]
        gap = missing.get(code, 0)
        if gap:
            parts.append(f"bez e-mailu: {gap}")
        options.append((code, " · ".join(parts)))
    return tuple(options)


def preview_for(
    data: BulkData, *, filter_type: str, values: Sequence[str]
) -> BulkPreview:
    return preview_from_diners(
        data.diners, filter_type=filter_type, filter_values=list(values)
    )


def recipient_rows(
    preview: BulkPreview | None,
) -> tuple[tuple[str, str, str, str], ...]:
    """Řádky tabulky: jméno, třída, kategorie, e-mail nebo poznámka."""
    if preview is None:
        return ()
    rows: list[tuple[str, str, str, str]] = []
    for diner in preview.diners:
        rows.append(
            (
                diner.name,
                diner.class_name or "—",
                diner.category or "—",
                diner.email or "chybí e-mail",
            )
        )
    rows.sort(key=lambda item: (item[3] == "chybí e-mail", item[0].casefold()))
    return tuple(rows)


def validate_message(form: BulkForm, preview: BulkPreview | None) -> None:
    """Stejné podmínky, jaké kontroluje i samotné odeslání."""
    if preview is None or not preview.recipients:
        raise ConfigError(
            "Vyberte alespoň jednu třídu nebo kategorii s platným e-mailem."
        )
    if not form.subject.strip():
        raise ConfigError("Zadejte předmět hromadné zprávy.")
    if not form.body.strip():
        raise ConfigError("Zadejte text hromadné zprávy.")


def send_bulk(
    preview: BulkPreview,
    *,
    subject: str,
    body: str,
    api_key: str,
    sender_email: str,
) -> MailDispatchResult:
    return send_bulk_message(
        preview,
        subject=subject,
        body=body,
        api_key=api_key,
        sender_email=sender_email,
    )
