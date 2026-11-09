"""Bezpečné uložení DB hesla a Resend API klíče mimo JSON konfiguraci."""

from __future__ import annotations

import base64
import copy
import ctypes
import json
import os
from pathlib import Path
from typing import Any
from ctypes import wintypes


SERVICE_NAME = "Altisima.MailPilot"
LEGACY_SERVICE_NAMES = ("Altisima.AutoReport", "Altisima.StravovaciSestava")
RESEND_ACCOUNT = "Resend.APIKey"
ADMIN_ACCOUNT = "Admin.Heslo"
RESEND_SECRET_KEYS = (
    "resend_api_key",
    "mail_api_key",
    "RESEND_API_KEY",
)
_MACHINE_SECRET_FILE = "mailpilot_machine_secrets.json"
_MACHINE_STORE_VERSION = 1
_MACHINE_DB_PASSWORDS_KEY = "db_passwords"
_CRYPTPROTECT_LOCAL_MACHINE = 0x4


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


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


def _is_windows() -> bool:
    return os.name == "nt"


def _machine_store_path() -> Path:
    root = Path(os.environ.get("PROGRAMDATA") or Path.home())
    return root / "MailPilot" / _MACHINE_SECRET_FILE


def _load_machine_store() -> dict[str, Any]:
    path = _machine_store_path()
    if not path.is_file():
        return {"version": _MACHINE_STORE_VERSION, _MACHINE_DB_PASSWORDS_KEY: {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": _MACHINE_STORE_VERSION, _MACHINE_DB_PASSWORDS_KEY: {}}
    if not isinstance(payload, dict):
        return {"version": _MACHINE_STORE_VERSION, _MACHINE_DB_PASSWORDS_KEY: {}}
    payload.setdefault("version", _MACHINE_STORE_VERSION)
    block = payload.get(_MACHINE_DB_PASSWORDS_KEY)
    if not isinstance(block, dict):
        payload[_MACHINE_DB_PASSWORDS_KEY] = {}
    return payload


def _save_machine_store(payload: dict[str, Any]) -> None:
    path = _machine_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _blob_from_bytes(data: bytes) -> tuple[_DataBlob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data)
    blob = _DataBlob(
        cbData=len(data),
        pbData=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)),
    )
    return blob, buffer


def _dpapi_encrypt_machine(data: bytes, *, flags: int = _CRYPTPROTECT_LOCAL_MACHINE) -> str:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    in_blob, _in_buffer = _blob_from_bytes(data)
    out_blob = _DataBlob()
    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "MailPilot",
        None,
        None,
        None,
        flags,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise OSError("CryptProtectData selhal.")
    try:
        encrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)
    return base64.b64encode(encrypted).decode("ascii")


def _dpapi_decrypt_machine(token: str, *, flags: int = _CRYPTPROTECT_LOCAL_MACHINE) -> str | None:
    if not token:
        return None
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    encrypted = base64.b64decode(token.encode("ascii"))
    in_blob, _in_buffer = _blob_from_bytes(encrypted)
    out_blob = _DataBlob()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        None,
        flags,
        ctypes.byref(out_blob),
    )
    if not ok:
        return None
    try:
        plain = ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)
    return plain.decode("utf-8")


def _read_machine_password(account: str) -> str | None:
    if not _is_windows():
        return None
    payload = _load_machine_store()
    block = payload.get(_MACHINE_DB_PASSWORDS_KEY)
    if not isinstance(block, dict):
        return None
    token = str(block.get(account) or "").strip()
    if not token:
        return None
    return _dpapi_decrypt_machine(token)


def _write_machine_password(account: str, password: str) -> None:
    if not _is_windows():
        return
    payload = _load_machine_store()
    block = payload.get(_MACHINE_DB_PASSWORDS_KEY)
    if not isinstance(block, dict):
        block = {}
    block[account] = _dpapi_encrypt_machine(password.encode("utf-8"))
    payload[_MACHINE_DB_PASSWORDS_KEY] = block
    payload["version"] = _MACHINE_STORE_VERSION
    _save_machine_store(payload)


def machine_password_available(database: dict[str, Any]) -> bool:
    """Vrátí True, pokud je DB heslo dostupné v machine-scope úložišti."""
    try:
        account = credential_account(database)
    except CredentialStoreError:
        return False
    try:
        value = _read_machine_password(account)
    except Exception:
        return False
    return bool(value)


def _migrate_to_mailpilot_key(
    keyring: Any,
    *,
    account: str,
    password: str,
) -> None:
    keyring.set_password(SERVICE_NAME, account, password)
    try:
        _write_machine_password(account, password)
    except Exception:
        # Machine-store fallback je best effort; primárně zůstává keyring.
        pass


def _read_from_legacy_keyring(keyring: Any, account: str) -> str | None:
    for legacy_service in LEGACY_SERVICE_NAMES:
        password = keyring.get_password(legacy_service, account)
        if password:
            _migrate_to_mailpilot_key(
                keyring, account=account, password=password
            )
            return password
    return None


def get_password(database: dict[str, Any]) -> str | None:
    """Načte heslo ze systémového trezoru (ve Windows Credential Manager)."""
    account = credential_account(database)
    try:
        machine_password = _read_machine_password(account)
    except Exception:
        machine_password = None
    keyring = None
    keyring_error = Exception
    try:
        keyring, keyring_error = _keyring_module()
        password = keyring.get_password(SERVICE_NAME, account)
        if password:
            return password
        password = _read_from_legacy_keyring(keyring, account)
        if password:
            return password
    except keyring_error as exc:
        if machine_password:
            return machine_password
        raise CredentialStoreError("Systémové úložiště hesel není dostupné.") from exc
    if machine_password:
        if keyring is not None:
            try:
                keyring.set_password(SERVICE_NAME, account, machine_password)
            except Exception:
                pass
        return machine_password
    return None


def set_password(database: dict[str, Any], password: str) -> None:
    """Uloží heslo do systémového trezoru, nikdy do config.json."""
    if not isinstance(password, str) or not password:
        raise CredentialStoreError("Heslo nesmí být prázdné.")
    account = credential_account(database)
    stored_somewhere = False
    errors: list[Exception] = []
    try:
        keyring, _keyring_error = _keyring_module()
        keyring.set_password(SERVICE_NAME, account, password)
        stored_somewhere = True
    except Exception as exc:
        errors.append(exc)
    try:
        _write_machine_password(account, password)
        stored_somewhere = True
    except Exception as exc:
        errors.append(exc)
    if not stored_somewhere:
        raise CredentialStoreError(
            "Heslo se nepodařilo uložit do zabezpečeného úložiště."
        ) from (errors[0] if errors else None)


def _user_admin_path() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
    return root / "DataShip" / "admin.dpapi"


def _read_user_admin_password() -> str | None:
    if not _is_windows():
        return None
    path = _user_admin_path()
    try:
        token = path.read_text(encoding="ascii")
    except FileNotFoundError:
        # Keep administrator access for existing MailShip installations.
        legacy_path = path.parent.parent / "MailShip" / path.name
        try:
            token = legacy_path.read_text(encoding="ascii")
        except FileNotFoundError:
            return None
    password = _dpapi_decrypt_machine(token, flags=0)
    if not password:
        raise CredentialStoreError("Heslo nastavení nelze odemknout v tomto účtu Windows.")
    return password


def _write_user_admin_password(password: str) -> None:
    if not _is_windows():
        raise CredentialStoreError("Systémové úložiště hesel není dostupné.")
    import tempfile
    path = _user_admin_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    token = _dpapi_encrypt_machine(password.encode("utf-8"), flags=0)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="ascii", dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(token)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def get_admin_password() -> str | None:
    """Read UI credentials without requiring access to machine-wide files."""
    try:
        fallback = _read_user_admin_password()
        if fallback:
            return fallback
        keyring, _keyring_error = _keyring_module()
        password = keyring.get_password(SERVICE_NAME, ADMIN_ACCOUNT)
        if password:
            return password
        for legacy_service in LEGACY_SERVICE_NAMES:
            password = keyring.get_password(legacy_service, ADMIN_ACCOUNT)
            if password:
                # A failed migration must not prevent reading an existing password.
                try:
                    keyring.set_password(SERVICE_NAME, ADMIN_ACCOUNT, password)
                except Exception:
                    pass
                return password
        return None
    except Exception as exc:
        raise CredentialStoreError(
            "Heslo nastavení nelze načíst pro aktuální účet Windows. "
            "Zkontrolujte přístup k uživatelskému úložišti hesel."
        ) from exc


def set_admin_password(password: str) -> None:
    """Save in the user's vault, or user-bound DPAPI under LOCALAPPDATA."""
    if not isinstance(password, str) or not password.strip():
        raise CredentialStoreError("Heslo administrátora nesmí být prázdné.")
    if len(password.strip()) < 4:
        raise CredentialStoreError("Heslo administrátora musí mít alespoň 4 znaky.")
    try:
        if _user_admin_path().is_file() and _is_windows():
            _write_user_admin_password(password.strip())
            return
        keyring, _keyring_error = _keyring_module()
        keyring.set_password(SERVICE_NAME, ADMIN_ACCOUNT, password.strip())
    except Exception:
        try:
            _write_user_admin_password(password.strip())
        except Exception as exc:
            raise CredentialStoreError(
                "Heslo nastavení se nepodařilo uložit v profilu uživatele. "
                "Zkontrolujte oprávnění složky LOCALAPPDATA."
            ) from exc


def get_resend_api_key() -> str | None:
    """Načte Resend API klíč ze systémového trezoru."""
    keyring, keyring_error = _keyring_module()
    try:
        password = keyring.get_password(SERVICE_NAME, RESEND_ACCOUNT)
        if password:
            return password
        for legacy_service in LEGACY_SERVICE_NAMES:
            password = keyring.get_password(legacy_service, RESEND_ACCOUNT)
            if password:
                keyring.set_password(SERVICE_NAME, RESEND_ACCOUNT, password)
                return password
        return None
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

