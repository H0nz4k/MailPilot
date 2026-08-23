"""Mailová logika a bezpečný most k aplikaci MailSender.

Samotný transport je záměrně oddělený v modulu ``mailsender_bridge``. Díky tomu
UI, kontrola varných dnů ani tvorba PDF nezávisí na konkrétním API MailSenderu.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

from stravovaci_sestava import AppConfig, ConfigError

try:
    import mailsender_bridge as _mailsender_bridge
except ImportError:  # pragma: no cover - ochrana nekompletni rucni instalace
    _mailsender_bridge = None


EMAIL_PATTERN = re.compile(
    r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
    r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+$",
    re.IGNORECASE,
)


class MailServiceError(RuntimeError):
    """Chyba přípravy nebo odeslání mailu."""


class MailSenderUnavailable(MailServiceError):
    """Most ke konkrétní implementaci MailSenderu není nainstalovaný."""


@dataclass(frozen=True)
class CookingStatus:
    meal_type: str
    is_cooking_day: bool


@dataclass(frozen=True)
class MailDispatchResult:
    recipients: tuple[str, ...]
    detail: str | None = None


def normalize_recipient(value: object) -> str:
    """Ověří jednu adresu a vrátí její normalizovaný zápis."""
    if not isinstance(value, str) or not value.strip():
        raise ConfigError("E-mailová adresa nesmí být prázdná.")
    address = value.strip()
    if len(address) > 254 or not EMAIL_PATTERN.fullmatch(address):
        raise ConfigError(f"Neplatná e-mailová adresa: {address}")
    return address


def normalize_recipients(values: object, *, allow_empty: bool = False) -> tuple[str, ...]:
    """Ověří seznam adres, odstraní duplicity a zachová pořadí."""
    if values is None and allow_empty:
        return ()
    if not isinstance(values, (list, tuple)):
        raise ConfigError("'mail_prijemci' musí být JSON pole e-mailových adres.")

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        address = normalize_recipient(value)
        key = address.casefold()
        if key not in seen:
            seen.add(key)
            result.append(address)

    if not result and not allow_empty:
        raise ConfigError("Přidejte alespoň jednu e-mailovou adresu příjemce.")
    return tuple(result)


def mail_subject(report_date: Any) -> str:
    """Pevný předmět požadovaný pro export sestavy."""
    return f"Seznam strávníků: {report_date.strftime('%d.%m.%Y')}"


def should_send_on_cooking_day(statuses: Sequence[CookingStatus]) -> bool:
    """Mail je povolen, když se vaří alespoň jeden relevantní typ stravy."""
    return any(item.is_cooking_day for item in statuses)


def cooking_status_message(statuses: Sequence[CookingStatus]) -> str:
    if not statuses:
        return "Vybrané kategorie nemají pro daný den žádnou objednávku."
    cooking = [item.meal_type for item in statuses if item.is_cooking_day]
    if cooking:
        return "Varný den pro: " + ", ".join(cooking)
    relevant = ", ".join(item.meal_type for item in statuses)
    return f"Pro relevantní typy stravy není varný den: {relevant}."


def fetch_cooking_status(config: AppConfig) -> tuple[CookingStatus, ...]:
    """Vrátí stav varného dne jen pro objednávky vybraných kategorií."""
    try:
        import psycopg
        from psycopg import sql
    except ImportError as exc:
        raise MailServiceError(
            "Chybí psycopg. Nainstalujte závislosti z requirements.txt."
        ) from exc

    day_column = sql.Identifier(f"d{config.report_date.day:02d}")
    query = sql.SQL(
        """
        WITH relevantni_typy AS (
            SELECT DISTINCT BTRIM(p.typsluzby) AS typ_stravy
            FROM public.prihlas AS p
            JOIN public.stravnik AS s
              ON s.evidcislo = p.stravnik
            WHERE p.rok = %s
              AND p.mesic = %s
              AND BTRIM(s.kategorie) = ANY(%s::varchar[])
              AND COALESCE(s.deleted, false) = false
              AND p.{day_column} ~ '^[1-9]$'
              AND NULLIF(BTRIM(p.typsluzby), '') IS NOT NULL
        )
        SELECT
            r.typ_stravy,
            COALESCE(UPPER(BTRIM(v.{day_column})) = 'A', false) AS vari_se
        FROM relevantni_typy AS r
        LEFT JOIN public.varnedny AS v
          ON v.rok = %s
         AND v.mesic = %s
         AND LOWER(BTRIM(v.typsluzby)) = LOWER(r.typ_stravy)
        ORDER BY LOWER(r.typ_stravy), r.typ_stravy
        """
    ).format(day_column=day_column)

    with psycopg.connect(**config.database) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                query,
                (
                    config.report_date.year,
                    config.report_date.month,
                    list(config.categories),
                    config.report_date.year,
                    config.report_date.month,
                ),
            )
            return tuple(
                CookingStatus(str(meal_type), bool(is_cooking))
                for meal_type, is_cooking in cursor.fetchall()
            )


def _load_bridge() -> Callable[..., Any]:
    if _mailsender_bridge is None:
        raise MailSenderUnavailable(
            "Chybí napojení na MailSender (soubor mailsender_bridge.py). "
            "Nainstalujte znovu úplný balíček AutoReportu."
        )

    sender = getattr(_mailsender_bridge, "send_pdf", None)
    if not callable(sender):
        raise MailSenderUnavailable(
            "mailsender_bridge.py musí obsahovat funkci send_pdf()."
        )
    return sender


def _load_files_bridge() -> Callable[..., Any]:
    if _mailsender_bridge is None:
        raise MailSenderUnavailable(
            "Chybí napojení na MailSender (soubor mailsender_bridge.py). "
            "Nainstalujte znovu úplný balíček AutoReportu."
        )
    sender = getattr(_mailsender_bridge, "send_files", None)
    if not callable(sender):
        raise MailSenderUnavailable(
            "mailsender_bridge.py musí obsahovat funkci send_files()."
        )
    return sender


def send_files_via_mailsender(
    recipients: Sequence[str],
    subject: str,
    body: str,
    files: Sequence[Path],
    *,
    api_key: str,
    sender_email: str,
    sender: Callable[..., Any] | None = None,
) -> MailDispatchResult:
    """Odešle jednu nebo více příloh přes izolovaný adaptér MailSenderu."""
    normalized = normalize_recipients(list(recipients))
    normalized_sender = normalize_recipient(sender_email)
    attachments = [path.resolve() for path in files]
    if not attachments:
        raise MailServiceError("Mailová zpráva musí obsahovat alespoň jednu přílohu.")
    for attachment in attachments:
        if not attachment.is_file():
            raise MailServiceError(f"Příloha neexistuje: {attachment}")
        if attachment.suffix.lower() not in {".pdf", ".zip"}:
            raise MailServiceError("Mailová příloha musí být PDF nebo ZIP soubor.")
    if not isinstance(subject, str) or not subject.strip():
        raise MailServiceError("Předmět mailu nesmí být prázdný.")
    if not isinstance(body, str):
        raise MailServiceError("Text mailu musí být textová hodnota.")
    if not isinstance(api_key, str) or not api_key.strip():
        raise MailServiceError("Zadejte Resend API klíč.")

    send = sender or _load_files_bridge()
    try:
        result = send(
            recipients=list(normalized),
            subject=subject.strip(),
            body=body,
            files=attachments,
            api_key=api_key.strip(),
            sender_email=normalized_sender,
        )
    except MailServiceError:
        raise
    except Exception as exc:
        raise MailServiceError(f"MailSender odeslání odmítl: {exc}") from exc

    detail = str(result).strip() if result not in (None, "") else None
    return MailDispatchResult(recipients=normalized, detail=detail)


def send_pdf_via_mailsender(
    recipients: Sequence[str],
    subject: str,
    body: str,
    pdf_path: Path,
    *,
    api_key: str,
    sender_email: str,
    sender: Callable[..., Any] | None = None,
) -> MailDispatchResult:
    """Odešle jedno PDF přes izolovaný adaptér MailSenderu."""
    if sender is not None:
        return send_files_via_mailsender(
            recipients,
            subject,
            body,
            [pdf_path],
            api_key=api_key,
            sender_email=sender_email,
            sender=lambda **values: sender(
                recipients=values["recipients"],
                subject=values["subject"],
                body=values["body"],
                pdf_path=values["files"][0],
                api_key=values["api_key"],
                sender_email=values["sender_email"],
            ),
        )
    return send_files_via_mailsender(
        recipients,
        subject,
        body,
        [pdf_path],
        api_key=api_key,
        sender_email=sender_email,
    )


def _load_text_bridge() -> Callable[..., Any]:
    if _mailsender_bridge is None:
        raise MailSenderUnavailable(
            "Chybí napojení na MailSender (soubor mailsender_bridge.py). "
            "Nainstalujte znovu úplný balíček AutoReportu."
        )
    sender = getattr(_mailsender_bridge, "send_text", None)
    if not callable(sender):
        raise MailSenderUnavailable(
            "mailsender_bridge.py musí obsahovat funkci send_text()."
        )
    return sender


def send_text_via_mailsender(
    recipients: Sequence[str],
    subject: str,
    body: str,
    *,
    api_key: str,
    sender_email: str,
    sender: Callable[..., Any] | None = None,
) -> MailDispatchResult:
    """Odešle textovou zprávu bez přílohy, každému příjemci zvlášť."""
    normalized = normalize_recipients(list(recipients))
    normalized_sender = normalize_recipient(sender_email)
    if not isinstance(subject, str) or not subject.strip():
        raise MailServiceError("Předmět mailu nesmí být prázdný.")
    if not isinstance(body, str) or not body.strip():
        raise MailServiceError("Text mailu nesmí být prázdný.")
    if not isinstance(api_key, str) or not api_key.strip():
        raise MailServiceError("Zadejte Resend API klíč.")

    send = sender or _load_text_bridge()
    try:
        result = send(
            recipients=list(normalized),
            subject=subject.strip(),
            body=body.strip(),
            api_key=api_key.strip(),
            sender_email=normalized_sender,
        )
    except MailServiceError:
        raise
    except Exception as exc:
        raise MailServiceError(f"MailSender odeslání odmítl: {exc}") from exc

    detail = str(result).strip() if result not in (None, "") else None
    return MailDispatchResult(recipients=normalized, detail=detail)
