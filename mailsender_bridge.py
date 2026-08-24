"""Napojení MailPilotu na Resend podle projektu MailSender.

Každý příjemce dostane samostatnou zprávu přes Resend Emails API. Batch API se
záměrně nepoužívá, protože Resend v dávkovém endpointu přílohy nepodporuje.
API klíč přichází z volající vrstvy, která jej načítá ze souboru .env; tento
modul ho nikam nezapisuje.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any


MAX_EMAIL_BYTES = 40 * 1024 * 1024
SIZE_SAFETY_RESERVE = 64 * 1024
DEFAULT_BODY = "V příloze zasíláme seznam strávníků."


class MailSenderBridgeError(RuntimeError):
    """Chyba konkrétního transportu Resend."""


def _response_ids(response: object) -> list[str]:
    """Bezpečně vytáhne ID zpráv z odpovědi různých verzí Resend SDK."""
    if not isinstance(response, dict):
        return []
    raw_items = response.get("data")
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    if not isinstance(raw_items, list):
        raw_items = [response]

    result: list[str] = []
    for item in raw_items:
        if isinstance(item, dict) and item.get("id"):
            result.append(str(item["id"]))
    return result


def _check_message_size(
    encoded_attachment: str,
    *,
    sender: str,
    recipient: str,
    subject: str,
    body: str,
) -> None:
    """Odmítne zprávu, která by po Base64 kódování překročila limit Resendu."""
    estimated_size = (
        len(encoded_attachment)
        + len(sender.encode("utf-8"))
        + len(recipient.encode("utf-8"))
        + len(subject.encode("utf-8"))
        + len(body.encode("utf-8"))
        + SIZE_SAFETY_RESERVE
    )
    if estimated_size > MAX_EMAIL_BYTES:
        raise MailSenderBridgeError(
            "PDF je po Base64 kódování příliš velké pro limit Resendu 40 MB."
        )


def _encode_attachment(path: Path) -> dict[str, str]:
    return {
        "filename": path.name,
        "content": base64.b64encode(path.read_bytes()).decode("ascii"),
    }


def send_files(
    *,
    recipients: list[str],
    subject: str,
    body: str,
    files: list[Path],
    api_key: str,
    sender_email: str,
    resend_module: Any | None = None,
) -> str:
    """Odešle každému příjemci samostatný e-mail se zadanými přílohami."""
    if not recipients:
        raise MailSenderBridgeError("Chybí příjemci mailu.")
    if not api_key or not api_key.strip():
        raise MailSenderBridgeError("Chybí Resend API klíč.")
    if not sender_email or not sender_email.strip():
        raise MailSenderBridgeError("Chybí e-mail odesílatele.")
    if not files:
        raise MailSenderBridgeError("Chybí soubory příloh.")
    for path in files:
        if not path.is_file():
            raise MailSenderBridgeError(f"Příloha neexistuje: {path}")

    if resend_module is None:
        try:
            import resend as resend_module
        except ImportError as exc:
            raise MailSenderBridgeError(
                "Chybí knihovna resend. Nainstalujte requirements.txt."
            ) from exc

    resend_module.api_key = api_key.strip()
    attachments = [_encode_attachment(path) for path in files]
    encoded_size = "".join(item["content"] for item in attachments)
    mail_text = body.strip() or DEFAULT_BODY
    sender = sender_email.strip()
    message_ids: list[str] = []
    for index, recipient in enumerate(recipients, start=1):
        _check_message_size(
            encoded_size,
            sender=sender,
            recipient=recipient,
            subject=subject,
            body=mail_text,
        )
        message = {
            "from": sender,
            "to": [recipient],
            "subject": subject,
            "text": mail_text,
            "attachments": attachments,
        }
        try:
            response = resend_module.Emails.send(message)
        except Exception as exc:
            raise MailSenderBridgeError(
                f"Resend odmítl zprávu {index} z {len(recipients)}: {exc}"
            ) from exc
        message_ids.extend(_response_ids(response))

    labels = ", ".join(path.suffix.lower().lstrip(".") or "soubor" for path in files)
    detail = f"Resend: {len(recipients)} samostatných zpráv s přílohami ({labels})"
    if message_ids:
        detail += f", potvrzeno {len(message_ids)} ID"
    return detail


def send_pdf(
    *,
    recipients: list[str],
    subject: str,
    body: str,
    pdf_path: Path,
    api_key: str,
    sender_email: str,
    resend_module: Any | None = None,
) -> str:
    """Odešle každému příjemci samostatný e-mail s PDF přílohou."""
    if not pdf_path.is_file():
        raise MailSenderBridgeError(f"PDF příloha neexistuje: {pdf_path}")
    detail = send_files(
        recipients=recipients,
        subject=subject,
        body=body,
        files=[pdf_path],
        api_key=api_key,
        sender_email=sender_email,
        resend_module=resend_module,
    )
    return detail.replace("s přílohami (pdf)", "s PDF")


def send_text(
    *,
    recipients: list[str],
    subject: str,
    body: str,
    api_key: str,
    sender_email: str,
    resend_module: Any | None = None,
) -> str:
    """Odešle každému příjemci samostatný e-mail bez přílohy."""
    if not recipients:
        raise MailSenderBridgeError("Chybí příjemci mailu.")
    if not api_key or not api_key.strip():
        raise MailSenderBridgeError("Chybí Resend API klíč.")
    if not sender_email or not sender_email.strip():
        raise MailSenderBridgeError("Chybí e-mail odesílatele.")
    mail_text = (body or "").strip()
    if not mail_text:
        raise MailSenderBridgeError("Text hromadné zprávy nesmí být prázdný.")
    cleaned_subject = (subject or "").strip()
    if not cleaned_subject:
        raise MailSenderBridgeError("Předmět hromadné zprávy nesmí být prázdný.")

    if resend_module is None:
        try:
            import resend as resend_module
        except ImportError as exc:
            raise MailSenderBridgeError(
                "Chybí knihovna resend. Nainstalujte requirements.txt."
            ) from exc

    resend_module.api_key = api_key.strip()
    sender = sender_email.strip()
    message_ids: list[str] = []
    for index, recipient in enumerate(recipients, start=1):
        message = {
            "from": sender,
            "to": [recipient],
            "subject": cleaned_subject,
            "text": mail_text,
        }
        try:
            response = resend_module.Emails.send(message)
        except Exception as exc:
            raise MailSenderBridgeError(
                f"Resend odmítl zprávu {index} z {len(recipients)}: {exc}"
            ) from exc
        message_ids.extend(_response_ids(response))

    detail = f"Resend: {len(recipients)} samostatných zpráv bez přílohy"
    if message_ids:
        detail += f", potvrzeno {len(message_ids)} ID"
    return detail
