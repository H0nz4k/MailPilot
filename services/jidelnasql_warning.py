"""Varování v dashboardu JídelnaSQL při selhání automatického mailu."""

from __future__ import annotations

import html
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

MAILPILOT_BEGIN = "<!-- MAILPILOT_WARNING_BEGIN -->"
MAILPILOT_END = "<!-- MAILPILOT_WARNING_END -->"
LEGACY_BEGIN = "<!-- AUTOREPORT_AUTOMAIL_BEGIN -->"
LEGACY_END = "<!-- AUTOREPORT_AUTOMAIL_END -->"
BEGIN = MAILPILOT_BEGIN
END = MAILPILOT_END
_MARKER_PAIRS = (
    (MAILPILOT_BEGIN, MAILPILOT_END),
    (LEGACY_BEGIN, LEGACY_END),
)
DEFAULT_TEMPLATE_PATH = Path(
    r"C:\Gastro\Programy\Templates\dashboard.template.html"
)
DEFAULT_MESSAGE = "Mail nebyl odeslán."


@dataclass(frozen=True)
class JidelnaWarningSettings:
    enabled: bool = True
    template_path: Path = DEFAULT_TEMPLATE_PATH


def peek_warning_settings(raw: dict[str, Any] | None) -> JidelnaWarningSettings:
    source = raw if isinstance(raw, dict) else {}
    block = source.get("jidelnasql_warning")
    if not isinstance(block, dict):
        block = {}
    enabled = block.get("enabled")
    template_path = str(block.get("template_path") or DEFAULT_TEMPLATE_PATH)
    return JidelnaWarningSettings(
        enabled=True if enabled is None else bool(enabled),
        template_path=Path(template_path),
    )


def apply_warning_settings(
    raw: dict[str, Any], settings: JidelnaWarningSettings
) -> dict[str, Any]:
    updated = dict(raw)
    updated["jidelnasql_warning"] = {
        "enabled": bool(settings.enabled),
        "template_path": str(settings.template_path),
    }
    return updated


def show_jidelnasql_mail_warning(
    settings: JidelnaWarningSettings,
    when: datetime | None = None,
    message: str = DEFAULT_MESSAGE,
) -> str | None:
    if not settings.enabled:
        return None
    path = settings.template_path
    if not path.is_file():
        return f"Dashboard šablona neexistuje: {path}"
    try:
        text, encoding = _read_text_detect(path)
        text = _remove_existing_block(text)
        anchor = _find_anchor(text)
        if anchor is None:
            return (
                "V dashboardu nebyl nalezen anchor Export "
                '(id="synchronizace-export"), warning nelze vložit.'
            )
        stamp = (when or datetime.now()).strftime("%d.%m.%Y %H:%M")
        safe_message = html.escape(message.strip() or DEFAULT_MESSAGE, quote=False)
        block = _build_error_block(safe_message, stamp)
        merged = text[: anchor.end()] + block + text[anchor.end() :]
        _make_backup(path)
        _write_text_same_encoding(path, merged, encoding)
        return None
    except OSError as exc:
        return f"Warning do dashboardu nešel zapsat: {exc}"
    except RuntimeError as exc:
        return str(exc)


def clear_jidelnasql_mail_warning(
    settings: JidelnaWarningSettings,
) -> str | None:
    if not settings.enabled:
        return None
    path = settings.template_path
    if not path.is_file():
        return f"Dashboard šablona neexistuje: {path}"
    try:
        text, encoding = _read_text_detect(path)
        cleaned = _remove_existing_block(text)
        if cleaned == text:
            return None
        _make_backup(path)
        _write_text_same_encoding(path, cleaned, encoding)
        return None
    except OSError as exc:
        return f"Warning v dashboardu nešel odstranit: {exc}"
    except RuntimeError as exc:
        return str(exc)


def is_jidelnasql_mail_warning_active(settings: JidelnaWarningSettings) -> bool:
    """Zkontroluje skutečný stav warningu přímo v dashboard.template.html."""
    path = settings.template_path
    if not path.is_file():
        return False
    try:
        text, _encoding = _read_text_detect(path)
    except (OSError, RuntimeError):
        return False
    for begin, end in _MARKER_PAIRS:
        if _contains_marker_pair(text, begin, end):
            return True
    return False


def _read_text_detect(path: Path) -> tuple[str, str]:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1250"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"Nepodařilo se rozpoznat kódování souboru {path}.")


def _write_text_same_encoding(path: Path, text: str, encoding: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    data = text.encode(encoding)
    with temporary.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _make_backup(path: Path) -> Path:
    backup = path.with_name(path.name + ".mailpilot-backup")
    if not backup.exists():
        shutil.copy2(path, backup)
    legacy_backup = path.with_name(path.name + ".autoreport-backup")
    if not legacy_backup.exists():
        shutil.copy2(path, legacy_backup)
    return backup


def _remove_existing_block(text: str) -> str:
    cleaned = text
    for begin, end in _MARKER_PAIRS:
        pattern = re.compile(
            re.escape(begin) + r".*?" + re.escape(end) + r"\s*",
            re.DOTALL,
        )
        cleaned = pattern.sub("", cleaned)
    return cleaned


def _find_anchor(text: str) -> re.Match[str] | None:
    anchor_re = re.compile(
        r'(<p>\s*<span class="popis">Export:</span>\s*'
        r'<span id="synchronizace-export"[^>]*>.*?</span>\s*</p>)',
        re.IGNORECASE | re.DOTALL,
    )
    return anchor_re.search(text)


def _build_error_block(message: str, when_text: str) -> str:
    return f"""
{MAILPILOT_BEGIN}
<style>
    #info-system .info-content {{
        padding-bottom: 3px !important;
    }}
</style>
<div id="mailpilot-automail-warning"
     style="display:block;
            width:158px;
            margin:8px 0 0 29px;
            padding:1px 2px;
            background:#fff3f3;
            border:1px solid #ff6666;
            border-radius:8px;
            color:#ff3030;
            line-height:inherit;
            font-family:inherit;
            font-weight:normal;
            box-sizing:border-box;">
    <p style="margin:0; padding:0;">
        <span style="color:#ff3030; font-weight:normal;">{message}</span>
    </p>
    <p style="margin:0; padding:0;">
        <span style="color:#ff3030; font-weight:normal;">Zkontrolujte MailPilot.</span>
    </p>
    <p style="margin:0; padding:0;">
        <span style="color:#ff3030; font-weight:normal;">{when_text}</span>
    </p>
</div>
{MAILPILOT_END}
"""


def _contains_marker_pair(text: str, begin: str, end: str) -> bool:
    pattern = re.compile(
        re.escape(begin) + r".*?" + re.escape(end),
        re.DOTALL,
    )
    if pattern.search(text):
        return True
    # Poškozený blok (jen BEGIN) stále bereme jako aktivní warning.
    return begin in text
