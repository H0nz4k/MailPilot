"""Bezpečné uložení DB hesla a Resend API klíče mimo JSON konfiguraci."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any


SERVICE_NAME = "Altisima.AutoReport"
LEGACY_SERVICE_NAMES = ("Altisima.StravovaciSestava",)
RESEND_ACCOUNT = "Resend.APIKey"
ADMIN_ACCOUNT = "Admin.Heslo"
RESEND_SECRET_KEYS = (
    "resend_api_key",
    "mail_api_key",
    "RESEND_API_KEY",
)


class CredentialStoreError(RuntimeError):
    """Systémové úložiště přihlašovacích údajů není dostupné."""


def credential_account(database: dict[str, Any]) -> str:
    """Vrátí stabilní identifikátor účtu pro konkrétní DB připojení."""
    required = ("host", "port", "dbname", "user")
    missing = [key for key in required if database.get(key) in (None, "")]
    if missing:
        raise CredentialStoreError(
            "Nelze určit účet pro heslo; chybí: " + ", ".join(missing)
        )
    host = str(database["host"]).strip().casefold()
    port = str(database["port"]).strip()
    dbname = str(database["dbname"]).strip().casefold()
    user = str(database["user"]).strip().casefold()
    return f"{user}@{host}:{port}/{dbname}"


def _keyring_module():
    try:
        import keyring
        from keyring.errors import KeyringError
    except ImportError as exc:
        raise CredentialStoreError(
            "Chybí knihovna keyring. Spusťte instalaci z requirements.txt."
        ) from exc
    return keyring, KeyringError


def get_password(database: dict[str, Any]) -> str | None:
    """Načte heslo ze systémového trezoru (ve Windows Credential Manager)."""
    keyring, keyring_error = _keyring_module()
    try:
        account = credential_account(database)
        password = keyring.get_password(SERVICE_NAME, account)
        if password:
            return password
        for legacy_service in LEGACY_SERVICE_NAMES:
            password = keyring.get_password(legacy_service, account)
            if password:
                keyring.set_password(SERVICE_NAME, account, password)
                return password
        return None
    except keyring_error as exc:
        raise CredentialStoreError(
            "Systémové úložiště hesel není dostupné."
        ) from exc


def set_password(database: dict[str, Any], password: str) -> None:
    """Uloží heslo do systémového trezoru, nikdy do config.json."""
    if not isinstance(password, str) or not password:
        raise CredentialStoreError("Heslo nesmí být prázdné.")
    keyring, keyring_error = _keyring_module()
    try:
        keyring.set_password(
            SERVICE_NAME,
            credential_account(database),
            password,
        )
    except keyring_error as exc:
        raise CredentialStoreError(
            "Heslo se nepodařilo uložit do systémového úložiště."
        ) from exc


def get_admin_password() -> str | None:
    """Načte heslo administrátorského UI ze systémového trezoru."""
    keyring, keyring_error = _keyring_module()
    try:
        return keyring.get_password(SERVICE_NAME, ADMIN_ACCOUNT)
    except keyring_error as exc:
        raise CredentialStoreError(
            "Heslo administrátora nelze načíst ze systémového úložiště."
        ) from exc


def set_admin_password(password: str) -> None:
    """Uloží heslo administrátorského UI mimo config.json."""
    if not isinstance(password, str) or not password.strip():
        raise CredentialStoreError("Heslo administrátora nesmí být prázdné.")
    if len(password.strip()) < 4:
        raise CredentialStoreError("Heslo administrátora musí mít alespoň 4 znaky.")
    keyring, keyring_error = _keyring_module()
    try:
        keyring.set_password(SERVICE_NAME, ADMIN_ACCOUNT, password.strip())
    except keyring_error as exc:
        raise CredentialStoreError(
            "Heslo administrátora se nepodařilo uložit do systémového úložiště."
        ) from exc


def get_resend_api_key() -> str | None:
    """Načte Resend API klíč ze systémového trezoru."""
    keyring, keyring_error = _keyring_module()
    try:
        return keyring.get_password(SERVICE_NAME, RESEND_ACCOUNT)
    except keyring_error as exc:
        raise CredentialStoreError(
            "Resend API klíč nelze načíst ze systémového úložiště."
        ) from exc


def set_resend_api_key(api_key: str) -> None:
    """Uloží Resend API klíč mimo config.json."""
    if not isinstance(api_key, str) or not api_key.strip():
        raise CredentialStoreError("Resend API klíč nesmí být prázdný.")
    keyring, keyring_error = _keyring_module()
    try:
        keyring.set_password(SERVICE_NAME, RESEND_ACCOUNT, api_key.strip())
    except keyring_error as exc:
        raise CredentialStoreError(
            "Resend API klíč se nepodařilo uložit do systémového úložiště."
        ) from exc


def sanitize_config(raw: dict[str, Any]) -> dict[str, Any]:
    """Vrátí kopii configu bez databázového hesla a API klíčů."""
    sanitized = copy.deepcopy(raw)
    database = sanitized.get("databaze")
    if isinstance(database, dict):
        database.pop("password", None)
    for key in RESEND_SECRET_KEYS:
        sanitized.pop(key, None)
    mail = sanitized.get("mail")
    if isinstance(mail, dict):
        for key in RESEND_SECRET_KEYS:
            mail.pop(key, None)
    return sanitized


def write_config(path: Path, raw: dict[str, Any]) -> None:
    """Atomicky zapíše bezpečný JSON bez hesla."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    sanitized = sanitize_config(raw)
    temporary = path.with_name(f".{path.name}.tmp")
    text = json.dumps(sanitized, ensure_ascii=False, indent=2) + "\n"
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
