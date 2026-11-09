"""Saved daily-report filters, shared by the NiceGUI form and mail worker."""
from __future__ import annotations

import json
import os
import tempfile
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from uuid import uuid4
from services.web_meal_types import normalize_meal_filter


@dataclass(frozen=True)
class DailyProfile:
    id: str
    name: str
    categories: tuple[str, ...]
    meal_type: str | tuple[str, ...] | None = None
    delivery_types: tuple[str, ...] = ()
    category_separation: bool = True
    show_by_categories: bool = True
    show_by_norms: bool = True
    show_diner_list: bool = True
    show_delivery_summary: bool = False
    delivery_show_names: bool = False
    # None preserves the global setting for reports saved by older versions.
    pdf_orientation: str | None = None
    pdf_data_font_size: float | None = None
    pdf_label_font_size: float | None = None
    pdf_bold: bool | None = None
    language: str | None = None
    menu_list_number: int | None = None

    @classmethod
    def from_dict(cls, raw: dict) -> "DailyProfile":
        if not isinstance(raw, dict):
            raise ValueError("Přehled musí být objekt.")
        name = str(raw.get("name") or "").strip()
        if not name or len(name) > 80:
            raise ValueError("Název přehledu musí mít 1–80 znaků.")
        values = raw.get("categories")
        if not isinstance(values, (list, tuple)) or not values:
            raise ValueError("Vyberte alespoň jednu kategorii přehledu.")
        if any(not isinstance(c, str) or not c.strip() for c in values):
            raise ValueError("Kódy kategorií musí být neprázdné texty.")
        categories = tuple(dict.fromkeys(c.strip() for c in values))
        meal = normalize_meal_filter(raw.get("meal_type"))
        from stravovaci_sestava import normalize_delivery_filter
        delivery_types = normalize_delivery_filter(raw.get("delivery_types"))
        flags = {}
        for key in ("category_separation", "show_by_categories", "show_by_norms", "show_diner_list"):
            flags[key] = raw.get(key, True)
            if not isinstance(flags[key], bool):
                raise ValueError(f"{key} musí být true nebo false.")
        for key in ("show_delivery_summary", "delivery_show_names"):
            flags[key] = raw.get(key, False)
            if not isinstance(flags[key], bool):
                raise ValueError(f"{key} musí být true nebo false.")
        pdf = {key: raw.get(key) for key in (
            "pdf_orientation", "pdf_data_font_size", "pdf_label_font_size",
            "pdf_bold", "language", "menu_list_number",
        )}
        if pdf["pdf_orientation"] not in (None, "na_vysku", "na_sirku"):
            raise ValueError("Neplatná orientace PDF.")
        for key in ("pdf_data_font_size", "pdf_label_font_size"):
            value = pdf[key]
            if value is not None:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 5 <= value <= 18:
                    raise ValueError("Velikost písma PDF musí být 5–18 bodů.")
        if pdf["pdf_bold"] is not None and not isinstance(pdf["pdf_bold"], bool):
            raise ValueError("Neplatná volba tučného písma.")
        if pdf["language"] is not None and (not isinstance(pdf["language"], str) or not pdf["language"].strip()):
            raise ValueError("Vyplňte jazyk jídelníčku.")
        number = pdf["menu_list_number"]
        if number is not None and (isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or int(number) != number or not 1 <= number <= 99):
            raise ValueError("Číslo jídelníčku musí být 1–99.")
        if number is not None:
            pdf["menu_list_number"] = int(number)
        return cls(str(raw.get("id") or uuid4()), name, categories,
                   meal, delivery_types, **flags, **pdf)

    def to_dict(self) -> dict:
        raw = asdict(self)
        raw["categories"] = list(self.categories)
        raw["delivery_types"] = list(self.delivery_types)
        if isinstance(self.meal_type, tuple):
            raw["meal_type"] = list(self.meal_type)
        return raw


def profile_file(directory: Path) -> Path:
    return Path(directory) / "daily_reports.json"


def load_profiles(path: Path) -> list[DailyProfile]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    if not isinstance(raw, dict) or raw.get("version") != 1 or not isinstance(raw.get("profiles"), list):
        raise ValueError("Neplatný soubor daily_reports.json (očekáváno profiles: pole, version: 1).")
    profiles = [DailyProfile.from_dict(item) for item in raw["profiles"]]
    if len({p.id for p in profiles}) != len(profiles):
        raise ValueError("Duplicitní ID denního přehledu.")
    return profiles


def save_profile(path: Path, profile: DailyProfile) -> list[DailyProfile]:
    """Read the current store before updating one profile; replace atomically."""
    profile = DailyProfile.from_dict(profile.to_dict())
    profiles = load_profiles(path)
    found = any(p.id == profile.id for p in profiles)
    profiles = [profile if p.id == profile.id else p for p in profiles]
    if not found:
        profiles.append(profile)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".daily-reports-", delete=False) as file:
            temporary = Path(file.name)
            json.dump({"version": 1, "profiles": [p.to_dict() for p in profiles]},
                      file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return profiles


def apply_profile(config, profile: DailyProfile, raw: dict):
    """Recheck current administrator permissions; never widen a saved filter."""
    from pocty_nastaveni import all_client_categories, peek_client_categories
    categories = profile.categories
    if not all_client_categories(raw):
        allowed = set(peek_client_categories(raw))
        categories = tuple(code for code in categories if code in allowed)
    if not categories:
        raise ValueError("Žádná kategorie uloženého přehledu již není povolena správcem.")
    pdf = {key: getattr(profile, key) for key in (
        "pdf_orientation", "pdf_data_font_size", "pdf_label_font_size",
        "pdf_bold", "language", "menu_list_number",
    ) if getattr(profile, key) is not None}
    return replace(config, categories=categories, meal_type=profile.meal_type, delivery_types=profile.delivery_types,
                   category_separation=profile.category_separation,
                   show_by_categories=profile.show_by_categories,
                   show_by_norms=profile.show_by_norms,
                   show_diner_list=profile.show_diner_list,
                   show_delivery_summary=profile.show_delivery_summary,
                   delivery_show_names=profile.delivery_show_names, **pdf)


def task_report_config(config, raw: dict, task, directory: Path):
    """Existing tasks retain their global settings; missing profiles fail closed."""
    profile_id = getattr(task, "profile_id", None)
    if not profile_id:
        return config
    profile = next((p for p in load_profiles(profile_file(directory)) if p.id == profile_id), None)
    if profile is None:
        raise ValueError("Uložený přehled této úlohy neexistuje; zvolte jej znovu.")
    return apply_profile(config, profile, raw)


