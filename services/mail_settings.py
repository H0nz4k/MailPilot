"""Nastavení e-mailů pro jednotlivé funkce AutoReportu.

Vrstva bez GUI: čte a zapisuje stejné klíče config.json jako NiceGUI verze
a Resend API klíč drží v souboru ``.env`` vedle aplikace.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping

from credential_store import sanitize_config
from env_store import EnvStoreError, get_resend_api_key, set_resend_api_key
from funkce import (
    FUNCTION_CLOSING,
    FUNCTION_DAILY,
    FUNCTION_IDS,
    FUNCTION_LABELS,
    FUNCTION_SPECIAL,
    apply_function_mails,
    load_function_mails,
)
from mail_service import normalize_recipient, normalize_recipients
from stravovaci_sestava import ConfigError


DEFAULT_SENDER = "podpora@altisima.cz"

# Jen denní stav umí filtr varných dnů; ostatní funkce ho ignorují.
COOKING_DAY_FUNCTIONS = (FUNCTION_DAILY,)

__all__ = [
    "COOKING_DAY_FUNCTIONS",
    "DEFAULT_SENDER",
    "FUNCTION_CLOSING",
    "FUNCTION_DAILY",
    "FUNCTION_IDS",
    "FUNCTION_LABELS",
    "FUNCTION_SPECIAL",
    "FunctionMail",
    "MailSettings",
    "add_recipient",
    "apply_mail_settings",
    "peek_mail_settings",
    "read_api_key",
    "save_api_key",
]


@dataclass(frozen=True)
class FunctionMail:
    """Příjemci a text jedné funkce."""

    recipients: tuple[str, ...] = ()
    body: str = ""
    only_cooking_days: bool = False


def _empty_functions() -> dict[str, FunctionMail]:
    return {key: FunctionMail() for key in FUNCTION_IDS}


@dataclass(frozen=True)
class MailSettings:
    """Společný odesílatel a nastavení všech funkcí."""

    sender: str = ""
    functions: Mapping[str, FunctionMail] = field(default_factory=_empty_functions)

    def function(self, key: str) -> FunctionMail:
        return self.functions.get(key, FunctionMail())

    def with_function(self, key: str, mail: FunctionMail) -> "MailSettings":
        functions = dict(self.functions)
        functions[key] = mail
        return replace(self, functions=functions)

    def with_sender(self, sender: str) -> "MailSettings":
        return replace(self, sender=sender)


def peek_mail_settings(raw: dict[str, Any] | None) -> MailSettings:
    """Načte nastavení mailů pro všechny funkce."""
    source = raw if isinstance(raw, dict) else {}
    loaded = load_function_mails(source)
    functions = {
        key: FunctionMail(
            recipients=tuple(loaded[key]["prijemci"]),
            body=str(loaded[key]["text"] or ""),
            only_cooking_days=bool(loaded[key]["jen_varne_dny"]),
        )
        for key in FUNCTION_IDS
    }
    sender = str(source.get("mail_odesilatel") or "").strip()
    return MailSettings(sender=sender, functions=functions)


def validate_mail_settings(settings: MailSettings) -> None:
    """Ověří odesílatele i příjemce; chyby hlásí jako ConfigError."""
    if settings.sender.strip():
        normalize_recipient(settings.sender)
    for key in FUNCTION_IDS:
        normalize_recipients(
            list(settings.function(key).recipients), allow_empty=True
        )


def apply_mail_settings(
    raw: dict[str, Any], settings: MailSettings
) -> dict[str, Any]:
    """Zapíše nastavení mailů do configu; ostatní bloky zachová."""
    validate_mail_settings(settings)
    updated = sanitize_config(raw)
    payload = {
        key: {
            "prijemci": list(settings.function(key).recipients),
            "text": settings.function(key).body,
            "jen_varne_dny": settings.function(key).only_cooking_days,
        }
        for key in FUNCTION_IDS
    }
    sender = settings.sender.strip() or DEFAULT_SENDER
    return apply_function_mails(updated, payload, sender=sender)


def add_recipient(existing: Iterable[str], value: str) -> tuple[str, ...]:
    """Přidá ověřenou adresu; duplicitu bez ohledu na velikost písmen ignoruje."""
    address = normalize_recipient(value)
    current = list(existing)
    if any(item.casefold() == address.casefold() for item in current):
        raise ConfigError(f"Adresa {address} už je v seznamu.")
    current.append(address)
    return tuple(current)


def read_api_key() -> str:
    """Resend API klíč z .env; prázdný text znamená nenastaveno."""
    try:
        return get_resend_api_key() or ""
    except EnvStoreError:
        return ""


def save_api_key(api_key: str) -> None:
    """Uloží Resend API klíč do .env vedle aplikace."""
    set_resend_api_key(api_key)
