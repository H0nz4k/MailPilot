"""Načtení a bezpečný zápis Resend API klíče do lokálního .env."""

from __future__ import annotations

from pathlib import Path

from runtime_paths import application_directory


DEFAULT_ENV_PATH = application_directory() / ".env"
RESEND_KEY_NAME = "RESEND_API_KEY"


class EnvStoreError(RuntimeError):
    """Soubor .env nelze přečíst nebo aktualizovat."""


def _dotenv_functions():
    try:
        from dotenv import dotenv_values, set_key
    except ImportError as exc:
        raise EnvStoreError(
            "Chybí python-dotenv. Nainstalujte závislosti z requirements.txt."
        ) from exc
    return dotenv_values, set_key


def get_resend_api_key(path: Path = DEFAULT_ENV_PATH) -> str | None:
    """Vrátí RESEND_API_KEY z .env; prázdný či vzorový klíč odmítne."""
    dotenv_values, _set_key = _dotenv_functions()
    try:
        values = dotenv_values(path)
    except OSError as exc:
        raise EnvStoreError(f"Soubor .env nelze přečíst: {path}") from exc
    value = values.get(RESEND_KEY_NAME)
    if not isinstance(value, str) or not value.strip():
        return None
    key = value.strip()
    if key == "re_123456789_abcdefghijklmnopqrstuvwxyz":
        return None
    return key


def set_resend_api_key(api_key: str, path: Path = DEFAULT_ENV_PATH) -> None:
    """Uloží RESEND_API_KEY do .env bez zásahu do config.json."""
    if not isinstance(api_key, str) or not api_key.strip():
        raise EnvStoreError("Resend API klíč nesmí být prázdný.")
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    _dotenv_values, set_key = _dotenv_functions()
    try:
        if not path.exists():
            path.write_text(
                "# API klíč z Resend.com; soubor .env nesdílejte.\n",
                encoding="utf-8",
            )
        set_key(str(path), RESEND_KEY_NAME, api_key.strip(), quote_mode="never")
    except OSError as exc:
        raise EnvStoreError(f"Resend API klíč nelze uložit do {path}") from exc
