"""Detekce cenového režimu JídelnaSQL (PouzivatCenik=0/1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


PRICING_MODE_SAZBY = 0
PRICING_MODE_CENIK = 1

_FALLBACK_QUERY = """
SELECT hodnota
FROM public.parametry
WHERE LOWER(BTRIM(sekce)) = LOWER('BACKUP')
  AND LOWER(BTRIM(parametr)) = LOWER('PouzivatCenik')
LIMIT 1
"""


@dataclass(frozen=True)
class PricingModeInfo:
    mode: int | None
    source: str
    raw_value: str

    @property
    def label(self) -> str:
        return pricing_mode_label(self.mode)


def normalize_pricing_mode(value: Any) -> int | None:
    if isinstance(value, bool):
        return PRICING_MODE_CENIK if value else PRICING_MODE_SAZBY
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = int(value)
        if number in (0, 1):
            return number
        return None
    text = str(value or "").strip().casefold()
    if text in {"0", "false", "f", "no", "ne"}:
        return PRICING_MODE_SAZBY
    if text in {"1", "true", "t", "yes", "ano"}:
        return PRICING_MODE_CENIK
    return None


def pricing_mode_label(mode: int | None) -> str:
    if mode == PRICING_MODE_CENIK:
        return "Ceník"
    if mode == PRICING_MODE_SAZBY:
        return "Sazby"
    return "nelze určit"


def detect_pricing_mode(cursor: Any) -> int | None:
    return detect_pricing_mode_info(cursor).mode


def detect_pricing_mode_info(cursor: Any) -> PricingModeInfo:
    try:
        cursor.execute("SELECT public.pouzivatcenik()")
        row = cursor.fetchone() or (None,)
        raw = row[0]
        return PricingModeInfo(
            mode=normalize_pricing_mode(raw),
            source="public.pouzivatcenik()",
            raw_value=str(raw),
        )
    except Exception:
        _rollback_cursor(cursor)
    try:
        cursor.execute(_FALLBACK_QUERY)
        row = cursor.fetchone() or (None,)
        raw = row[0]
        return PricingModeInfo(
            mode=normalize_pricing_mode(raw),
            source="public.parametry(BACKUP/PouzivatCenik)",
            raw_value=str(raw),
        )
    except Exception:
        _rollback_cursor(cursor)
    return PricingModeInfo(mode=None, source="unknown", raw_value="")


def _rollback_cursor(cursor: Any) -> None:
    connection = getattr(cursor, "connection", None)
    if connection is None:
        return
    rollback = getattr(connection, "rollback", None)
    if callable(rollback):
        rollback()
