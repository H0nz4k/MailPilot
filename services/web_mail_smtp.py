"""Optional SMTP PDF transport, configured by web_mail_settings.json."""
from __future__ import annotations
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from mail_service import normalize_recipient, normalize_recipients


def smtp_send(settings: dict, recipients, subject: str, body: str, attachment: Path):
    host = str(settings.get("smtp_host", "")).strip()
    port = int(settings.get("smtp_port", 587))
    security = settings.get("smtp_security", "starttls")
    sender = normalize_recipient(settings.get("from_email"))
    destinations = normalize_recipients(list(recipients))
    if not host:
        raise ValueError("Není nastaven SMTP server.")
    if security == "none":
        raise ValueError("Nešifrované SMTP není pro automatické odesílání povoleno.")
    username = str(settings.get("smtp_username", "")).strip()
    password = os.environ.get("MAILPILOT_SMTP_PASSWORD", "")
    if username and not password:
        raise ValueError("Není nastavena proměnná MAILPILOT_SMTP_PASSWORD.")
    message = EmailMessage()
    display_name = str(settings.get("from_name") or "").strip()
    if display_name:
        from email.utils import formataddr
        message["From"] = formataddr((display_name, sender))
    else:
        message["From"] = sender
    message["To"] = ", ".join(destinations)
    message["Subject"] = subject
    message.set_content(body)
    path = Path(attachment)
    message.add_attachment(path.read_bytes(), maintype="application", subtype="pdf", filename=path.name)
    context = ssl.create_default_context()
    if security == "ssl":
        client = smtplib.SMTP_SSL(host, port, timeout=30, context=context)
    elif security == "starttls":
        client = smtplib.SMTP(host, port, timeout=30)
    else:
        raise ValueError("Neznámé zabezpečení SMTP.")
    with client:
        client.ehlo()
        if security == "starttls":
            client.starttls(context=context)
            client.ehlo()
        if username:
            client.login(username, password)
        client.send_message(message)
    return destinations
