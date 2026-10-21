"""Unique predictable PDF paths for one-off DataShip category selections.

Scheduled/CLI exports continue to use the configured filename unchanged.
Only manually generated filtered reports get a suffix, avoiding loss of a
previous report for the same date with different categories/meal types.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Sequence
import re
import unicodedata


def _slug(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value)
    text = folded.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9-]+", "-", text).strip("-").lower() or "typ"


def manual_pdf_path(
    configured_path: Path,
    selected_categories: Sequence[str],
    allowed_categories: Sequence[str],
    meal_type: str | None = None,
) -> Path:
    """Return distinct paths for category subsets without touching config.

    The canonical configured path stays unchanged if the operator chooses
    *all* allowed categories and all meal types.
    """
    selected = {str(code).strip() for code in selected_categories}
    allowed = {str(code).strip() for code in allowed_categories}
    if not selected or not selected <= allowed:
        raise ValueError("Pro PDF vyberte alespoň jednu povolenou kategorii.")
    if selected == allowed and not meal_type:
        return Path(configured_path)

    ordered = sorted(selected, key=lambda code: (code.casefold(), code))
    readable = "-".join(_slug(code) for code in ordered)
    readable = readable[:48].rstrip("-")
    # The hash also distinguishes codes that normalize to the same ASCII.
    signature = "\\0".join(ordered) + "\\0" + (meal_type or "")
    digest = sha256(signature.encode("utf-8")).hexdigest()[:8]
    suffix = f"kat-{len(ordered)}-{readable}-{digest}"
    if meal_type:
        suffix += f"_typ-{_slug(meal_type)[:24]}"
    path = Path(configured_path)
    return path.with_name(f"{path.stem}_{suffix}{path.suffix}")
