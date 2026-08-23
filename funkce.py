"""Samostatné funkce AutoReportu: denní stav, uzávěrka a special."""

from __future__ import annotations

from typing import Any

from mail_service import normalize_recipient, normalize_recipients


FUNCTION_DAILY = "denni_stav"
FUNCTION_CLOSING = "uzaverka"
FUNCTION_SPECIAL = "special"
FUNCTION_IDS = (FUNCTION_DAILY, FUNCTION_CLOSING, FUNCTION_SPECIAL)

FUNCTION_LABELS = {
    FUNCTION_DAILY: "Denní stav",
    FUNCTION_CLOSING: "Uzávěrka",
    FUNCTION_SPECIAL: "Special",
}


def empty_mail_state() -> dict[str, Any]:
    return {"prijemci": [], "text": "", "jen_varne_dny": False}


def _json_object(raw: dict[str, Any] | None, key: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    block = raw.get(key)
    return dict(block) if isinstance(block, dict) else {}


def load_function_mails(raw: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Načte příjemce a text zvlášť pro každou funkci."""
    source = raw if isinstance(raw, dict) else {}
    closing = _json_object(source, "uzaverka")
    special = _json_object(source, "z17")
    return {
        FUNCTION_DAILY: {
            "prijemci": list(
                normalize_recipients(source.get("mail_prijemci", []), allow_empty=True)
            ),
            "text": str(source.get("mail_text") or ""),
            "jen_varne_dny": source.get("mail_jen_varne_dny") is True,
        },
        FUNCTION_CLOSING: {
            "prijemci": list(
                normalize_recipients(closing.get("mail_prijemci", []), allow_empty=True)
            ),
            "text": str(closing.get("mail_text") or ""),
            "jen_varne_dny": False,
        },
        FUNCTION_SPECIAL: {
            "prijemci": list(
                normalize_recipients(special.get("mail_prijemci", []), allow_empty=True)
            ),
            "text": str(special.get("mail_text") or ""),
            "jen_varne_dny": False,
        },
    }


def apply_function_mails(
    raw: dict[str, Any],
    mails: dict[str, dict[str, Any]],
    *,
    sender: str,
) -> dict[str, Any]:
    """Zapíše maily funkcí do configu; odesílatel zůstává společný."""
    updated = dict(raw)
    daily = mails.get(FUNCTION_DAILY) or empty_mail_state()
    closing_mail = mails.get(FUNCTION_CLOSING) or empty_mail_state()
    special_mail = mails.get(FUNCTION_SPECIAL) or empty_mail_state()
    updated["mail_prijemci"] = list(daily.get("prijemci") or [])
    updated["mail_text"] = str(daily.get("text") or "")
    updated["mail_jen_varne_dny"] = bool(daily.get("jen_varne_dny"))
    updated["mail_odesilatel"] = normalize_recipient(sender)
    closing = _json_object(updated, "uzaverka")
    closing["mail_prijemci"] = list(closing_mail.get("prijemci") or [])
    closing["mail_text"] = str(closing_mail.get("text") or "")
    updated["uzaverka"] = closing
    special = _json_object(updated, "z17")
    special["mail_prijemci"] = list(special_mail.get("prijemci") or [])
    special["mail_text"] = str(special_mail.get("text") or "")
    updated["z17"] = special
    return updated
