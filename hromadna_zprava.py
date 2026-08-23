"""Hromadná zpráva strávníkům podle třídy nebo kategorie."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from mail_service import EMAIL_PATTERN, ConfigError, MailDispatchResult, send_text_via_mailsender


FILTER_CLASS = "trida"
FILTER_CATEGORY = "kategorie"
FILTER_LABELS = {
    FILTER_CLASS: "Třída",
    FILTER_CATEGORY: "Kategorie",
}


def option_label(code: str, extra: str) -> str:
    note = extra.strip()
    if note and note.casefold() != code.casefold():
        return f"{code} — {note}"
    return code


@dataclass(frozen=True)
class BulkDiner:
    evidcislo: int
    name: str
    email: str | None
    class_name: str | None
    category: str


@dataclass(frozen=True)
class BulkPreview:
    filter_type: str
    filter_value: str
    diners: tuple[BulkDiner, ...]
    recipients: tuple[str, ...]
    missing: tuple[BulkDiner, ...]
    filter_values: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.filter_values:
            object.__setattr__(
                self,
                "filter_values",
                tuple(
                    part.strip()
                    for part in str(self.filter_value or "").split(",")
                    if part.strip()
                )
                or ((self.filter_value,) if self.filter_value else ()),
            )

    @property
    def diner_count(self) -> int:
        return len(self.diners)

    @property
    def recipient_count(self) -> int:
        return len(self.recipients)

    @property
    def missing_count(self) -> int:
        return len(self.missing)


def _group_count_label(filter_type: str, count: int) -> str:
    if filter_type == FILTER_CLASS:
        if count == 1:
            return "1 třída"
        if count < 5:
            return f"{count} třídy"
        return f"{count} tříd"
    if count == 1:
        return "1 kategorie"
    if count < 5:
        return f"{count} kategorie"
    return f"{count} kategorií"


def bulk_preview_summary(preview: BulkPreview) -> str:
    """Srozumitelný stav výběru: kolik příjemců, kolik lidí bez e-mailu."""
    groups = _group_count_label(
        preview.filter_type, len(preview.filter_values) or 1
    )
    if preview.diner_count == 0:
        return (
            f"{groups}: ve výběru nejsou žádní strávníci. "
            "Zpráva by nedorazila nikomu."
        )
    text = (
        f"{groups}: {preview.recipient_count} příjemců "
        f"z {preview.diner_count} strávníků."
    )
    if preview.recipient_count == 0:
        return (
            f"{text} Nikdo z nich nemá vyplněný e-mail, "
            "zpráva by nedorazila nikomu."
        )
    if preview.missing_count:
        return (
            f"{text} {preview.missing_count} lidem zpráva nedorazí "
            "(chybí e-mail)."
        )
    return text


CLASSES_QUERY = """
        SELECT
            BTRIM(zdroj.trida) AS trida,
            MAX(NULLIF(BTRIM(zdroj.poznamka), '')) AS poznamka
        FROM (
            SELECT trida, poznamka FROM public.tridy
            UNION ALL
            SELECT trida, NULL::varchar
            FROM public.stravnik
            WHERE COALESCE(deleted, false) = false
        ) AS zdroj
        WHERE NULLIF(BTRIM(zdroj.trida), '') IS NOT NULL
        GROUP BY BTRIM(zdroj.trida)
        ORDER BY LOWER(BTRIM(zdroj.trida)), BTRIM(zdroj.trida)
"""

CATEGORIES_QUERY = """
        SELECT BTRIM(oznaceni), COALESCE(NULLIF(BTRIM(nazev), ''), '')
        FROM public.kategor
        WHERE NULLIF(BTRIM(oznaceni), '') IS NOT NULL
        ORDER BY LOWER(BTRIM(oznaceni)), BTRIM(oznaceni)
"""

DINER_SELECT = """
            s.evidcislo,
            COALESCE(NULLIF(BTRIM(s.jmeno), ''), '[bez jména]') AS jmeno,
            NULLIF(BTRIM(s.email), '') AS email,
            NULLIF(BTRIM(s.trida), '') AS trida,
            COALESCE(BTRIM(s.kategorie), '') AS kategorie
"""

DINERS_ALL_QUERY = f"""
        SELECT {DINER_SELECT}
        FROM public.stravnik AS s
        WHERE COALESCE(s.deleted, false) = false
          AND COALESCE(s.hromadny, false) = false
        ORDER BY LOWER(BTRIM(s.jmeno)) NULLS LAST, BTRIM(s.jmeno) NULLS LAST, s.evidcislo
"""

DINERS_QUERY = f"""
        SELECT {DINER_SELECT}
        FROM public.stravnik AS s
        WHERE COALESCE(s.deleted, false) = false
          AND COALESCE(s.hromadny, false) = false
          AND (
                (%s = 'trida' AND BTRIM(COALESCE(s.trida, '')) = ANY(%s))
             OR (%s = 'kategorie' AND BTRIM(COALESCE(s.kategorie, '')) = ANY(%s))
          )
        ORDER BY LOWER(BTRIM(s.jmeno)) NULLS LAST, BTRIM(s.jmeno) NULLS LAST, s.evidcislo
"""


def peek_bulk_ui(raw: dict[str, Any] | None) -> dict[str, str]:
    block = raw.get("hromadna_zprava") if isinstance(raw, dict) else None
    if not isinstance(block, dict):
        block = {}
    subject = block.get("predmet", "")
    body = block.get("text", "")
    return {
        "predmet": str(subject or ""),
        "text": str(body or ""),
    }


def apply_bulk_ui(raw: dict[str, Any], *, subject: str, body: str) -> dict[str, Any]:
    updated = dict(raw)
    block = updated.get("hromadna_zprava")
    if not isinstance(block, dict):
        block = {}
    else:
        block = dict(block)
    block["predmet"] = subject.strip()
    block["text"] = body
    updated["hromadna_zprava"] = block
    return updated


def diner_from_row(row: Sequence[Any]) -> BulkDiner:
    evidcislo, name, email, class_name, category = row
    return BulkDiner(
        evidcislo=int(evidcislo),
        name=str(name or "").strip() or "[bez jména]",
        email=diner_email(email),
        class_name=(str(class_name).strip() if class_name else None) or None,
        category=str(category or "").strip(),
    )


def diner_group_value(diner: BulkDiner, filter_type: str) -> str:
    if filter_type == FILTER_CLASS:
        return diner.class_name or ""
    return diner.category


def missing_email_counts(
    diners: Sequence[BulkDiner], filter_type: str
) -> dict[str, int]:
    """Kolik strávníků ve třídě/kategorii nemá platný e-mail."""
    counts: dict[str, int] = {}
    for diner in diners:
        key = diner_group_value(diner, filter_type)
        if not key or diner.email is not None:
            continue
        counts[key] = counts.get(key, 0) + 1
    return counts


def missing_email_diners(
    diners: Sequence[BulkDiner],
    *,
    filter_type: str,
    filter_value: str,
) -> tuple[BulkDiner, ...]:
    value = str(filter_value or "").strip()
    return tuple(
        diner
        for diner in diners
        if diner_group_value(diner, filter_type) == value and diner.email is None
    )


def diner_email(value: object) -> str | None:
    """Vrátí platný e-mail, nebo None když chybí či je neplatný."""
    if not isinstance(value, str) or not value.strip():
        return None
    address = value.strip()
    if len(address) > 254 or not EMAIL_PATTERN.fullmatch(address):
        return None
    return address


def assemble_preview(
    diners: Sequence[BulkDiner],
    *,
    filter_type: str,
    filter_values: Sequence[str],
) -> BulkPreview:
    values = tuple(str(value).strip() for value in filter_values if str(value).strip())
    recipients: list[str] = []
    missing: list[BulkDiner] = []
    seen: set[str] = set()
    for diner in diners:
        if diner.email is None:
            missing.append(diner)
            continue
        key = diner.email.casefold()
        if key not in seen:
            seen.add(key)
            recipients.append(diner.email)
    display = values[0] if len(values) == 1 else ", ".join(values)
    return BulkPreview(
        filter_type=filter_type,
        filter_value=display,
        filter_values=values,
        diners=tuple(diners),
        recipients=tuple(recipients),
        missing=tuple(missing),
    )


def preview_from_diners(
    diners: Sequence[BulkDiner],
    *,
    filter_type: str,
    filter_values: Sequence[str],
) -> BulkPreview:
    values = tuple(str(value).strip() for value in filter_values if str(value).strip())
    wanted = set(values)
    matched = [
        diner
        for diner in diners
        if diner_group_value(diner, filter_type) in wanted
    ]
    return assemble_preview(
        matched, filter_type=filter_type, filter_values=values
    )


def build_preview(
    rows: Sequence[tuple[Any, ...]],
    *,
    filter_type: str,
    filter_value: str | Sequence[str],
) -> BulkPreview:
    if isinstance(filter_value, str):
        values: tuple[str, ...] = (filter_value,) if filter_value.strip() else ()
    else:
        values = tuple(str(item).strip() for item in filter_value if str(item).strip())
    diners = [diner_from_row(row) for row in rows]
    return assemble_preview(diners, filter_type=filter_type, filter_values=values)


def fetch_bulk_filters(
    database: dict[str, Any],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[BulkDiner]]:
    """Vrátí (třídy, kategorie, strávníky) pro hromadnou zprávu."""
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Chybí psycopg. Nainstalujte requirements.txt.") from exc
    with psycopg.connect(**database) as connection:
        with connection.cursor() as cursor:
            cursor.execute(CLASSES_QUERY)
            classes = [
                (str(code), str(note).strip() if note else "")
                for code, note in cursor.fetchall()
            ]
            cursor.execute(CATEGORIES_QUERY)
            categories = [(str(code), str(name)) for code, name in cursor.fetchall()]
            cursor.execute(DINERS_ALL_QUERY)
            diners = [diner_from_row(row) for row in cursor.fetchall()]
    return classes, categories, diners


def fetch_bulk_diners(database: dict[str, Any]) -> list[BulkDiner]:
    """Načte strávníky pro náhled e-mailů u hromadné zprávy."""
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Chybí psycopg. Nainstalujte requirements.txt.") from exc
    with psycopg.connect(**database) as connection:
        with connection.cursor() as cursor:
            cursor.execute(DINERS_ALL_QUERY)
            return [diner_from_row(row) for row in cursor.fetchall()]


def _filter_values(filter_value: str | Sequence[str]) -> list[str]:
    if isinstance(filter_value, str):
        values = [filter_value.strip()] if filter_value.strip() else []
    else:
        values = [str(item).strip() for item in filter_value if str(item).strip()]
    return values


def preview_bulk_recipients(
    database: dict[str, Any],
    *,
    filter_type: str,
    filter_value: str | Sequence[str],
) -> BulkPreview:
    if filter_type not in FILTER_LABELS:
        raise ConfigError("Filtr hromadné zprávy musí být třída, nebo kategorie.")
    values = _filter_values(filter_value)
    if not values:
        raise ConfigError(
            f"Zvolte {FILTER_LABELS[filter_type].casefold()} pro hromadnou zprávu."
        )
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Chybí psycopg. Nainstalujte requirements.txt.") from exc
    with psycopg.connect(**database) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                DINERS_QUERY, (filter_type, values, filter_type, values)
            )
            rows = cursor.fetchall()
    return build_preview(rows, filter_type=filter_type, filter_value=values)


def send_bulk_message(
    preview: BulkPreview,
    *,
    subject: str,
    body: str,
    api_key: str,
    sender_email: str,
    sender=None,
) -> MailDispatchResult:
    if not preview.recipients:
        raise ConfigError(
            "Ve zvoleném filtru nemá žádný strávník vyplněný e-mail. "
            "Zpráva by nedorazila nikomu."
        )
    cleaned_subject = str(subject or "").strip()
    if not cleaned_subject:
        raise ConfigError("Zadejte předmět hromadné zprávy.")
    cleaned_body = str(body or "").strip()
    if not cleaned_body:
        raise ConfigError("Zadejte text hromadné zprávy.")
    return send_text_via_mailsender(
        preview.recipients,
        cleaned_subject,
        cleaned_body,
        api_key=api_key,
        sender_email=sender_email,
        sender=sender,
    )
