"""Named reusable PDF appearance; never stores date, DB access or report filters."""
from dataclasses import dataclass, asdict
import json
import math
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from services.pdf_layout import normalize_layout, normalize_page_breaks

DEFAULT_SETTINGS = {
    "pdf_orientation": "na_vysku", "pdf_data_font_size": 8.5,
    "pdf_label_font_size": 9.0, "pdf_bold": False, "pdf_compact_rows": False,
    "category_separation": True, "show_by_categories": True, "show_by_norms": True,
    "show_diner_list": True, "show_delivery_summary": False,
    "delivery_show_names": False, "delivery_page_per_type": False,
    "pdf_layout": (), "pdf_page_breaks": ("diners",),
}


def normalize_template_settings(value):
    if not isinstance(value, dict) or set(value) - set(DEFAULT_SETTINGS):
        raise ValueError("Šablona smí obsahovat pouze nastavení vzhledu PDF.")
    settings = {**DEFAULT_SETTINGS, **value}
    for key, default in DEFAULT_SETTINGS.items():
        if isinstance(default, bool) and not isinstance(settings[key], bool):
            raise ValueError("Přepínače šablony musí být true nebo false.")
    if settings["pdf_orientation"] not in ("na_vysku", "na_sirku"):
        raise ValueError("Neplatná orientace šablony PDF.")
    for key in ("pdf_data_font_size", "pdf_label_font_size"):
        number = settings[key]
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or not 5 <= number <= 18:
            raise ValueError("Velikost písma PDF musí být 5–18 bodů.")
    settings["pdf_layout"] = normalize_layout(settings["pdf_layout"])
    settings["pdf_page_breaks"] = normalize_page_breaks(settings["pdf_page_breaks"])
    if settings["delivery_page_per_type"] and any("delivery" in row and len(row) == 2 for row in settings["pdf_layout"]):
        raise ValueError("Pro samostatné stránky typů výdeje umístěte tento blok na vlastní řádek.")
    return settings


@dataclass(frozen=True)
class PdfTemplate:
    id: str
    name: str
    settings: dict

    @classmethod
    def from_dict(cls, value):
        if not isinstance(value, dict):
            raise ValueError("Neplatná šablona PDF.")
        name = str(value.get("name") or "").strip()
        if not 1 <= len(name) <= 80:
            raise ValueError("Název šablony musí mít 1–80 znaků.")
        return cls(str(value.get("id") or uuid4()), name,
                   normalize_template_settings(value.get("settings")))

    def to_dict(self):
        return asdict(self)


def template_file(directory):
    return Path(directory) / "pdf_templates.json"


def load_templates(path):
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    if not isinstance(raw, dict) or raw.get("version") != 1 or not isinstance(raw.get("templates"), list):
        raise ValueError("Soubor šablon PDF má neplatný formát.")
    templates = [PdfTemplate.from_dict(item) for item in raw["templates"]]
    if len({item.id for item in templates}) != len(templates):
        raise ValueError("Soubor obsahuje duplicitní šablony PDF.")
    return templates


def save_template(path, template):
    template = PdfTemplate.from_dict(template.to_dict())
    items = load_templates(path)
    if any(item.name.casefold() == template.name.casefold() and item.id != template.id for item in items):
        raise ValueError("Šablona s tímto názvem již existuje. Zvolte jiný název nebo uložte změny.")
    found = any(item.id == template.id for item in items)
    items = [template if item.id == template.id else item for item in items]
    if not found:
        items.append(template)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".pdf-templates-", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({"version": 1, "templates": [item.to_dict() for item in items]},
                      stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return items
