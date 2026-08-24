"""Design tokeny, barevná schémata a UI šablony MailPilotu.

Jen prezentační vrstva: velikosti, rozestupy, barvy a rozvržení. Business
logika (databáze, PDF, maily) sem nepatří. Šablony mění pouze hodnoty tokenů
a strategii rozvržení, nikoli chování aplikace.
"""

from __future__ import annotations

from typing import Any

from nicegui import ui

# ---------------------------------------------------------------------------
# Písmo: tři styly pro celou aplikaci
# ---------------------------------------------------------------------------

UI_TEXT_SIZE_LABELS = {
    "mala": "Malá",
    "stredni": "Střední",
    "velka": "Velká",
    "extra": "Extra velká",
}
UI_TEXT_SIZE_PX = {
    "text": {"mala": 13, "stredni": 14, "velka": 16, "extra": 18},
    "nadpis": {"mala": 15, "stredni": 16, "velka": 19, "extra": 22},
    "popis": {"mala": 11, "stredni": 12, "velka": 14, "extra": 16},
}
DEFAULT_UI_TEXT_SIZE = "stredni"

# ---------------------------------------------------------------------------
# Hustota: rozestupy, řádkování a výška ovládacích prvků
# ---------------------------------------------------------------------------

UI_SPACING_LABELS = {
    "tesne": "Těsné",
    "stredni": "Střední",
    "volne": "Volné",
}
UI_DENSITY_LABELS = {
    "husta": "Hustá pole",
    "bezna": "Běžná pole",
    "volna": "Volná pole",
}
UI_SPACING_PX = {
    "tesne": {
        "gap": 6,
        "stack": 6,
        "panel": 6,
        "section": 4,
        "block": 8,
        "control": 30,
        "header": 34,
    },
    "stredni": {
        "gap": 10,
        "stack": 10,
        "panel": 10,
        "section": 6,
        "block": 12,
        "control": 36,
        "header": 42,
    },
    "volne": {
        "gap": 14,
        "stack": 16,
        "panel": 14,
        "section": 10,
        "block": 16,
        "control": 42,
        "header": 50,
    },
}
UI_LINE_HEIGHT = {
    "tesne": "1.25",
    "stredni": "1.4",
    "volne": "1.55",
}
UI_FIELD_HEIGHT = {
    "husta": 32,
    "bezna": 38,
    "volna": 46,
}

# Šablona hustoty zůstává kvůli starším configům; nově ji předvolí UI šablona.
UI_STYLE_TEMPLATE_LABELS = {
    "kompaktni": "Kompaktní",
    "bezna": "Běžná",
    "pohodlna": "Pohodlná",
}
UI_STYLE_TEMPLATES = {
    "kompaktni": {"rozestupy": "tesne", "radkovani": "tesne", "hustota": "husta"},
    "bezna": {"rozestupy": "stredni", "radkovani": "stredni", "hustota": "bezna"},
    "pohodlna": {"rozestupy": "volne", "radkovani": "volne", "hustota": "volna"},
}
DEFAULT_UI_TEMPLATE = "bezna"

# ---------------------------------------------------------------------------
# UI šablony: rozvržení navigace, karet a hlavních akcí
# ---------------------------------------------------------------------------

NAV_TOP = "top"
NAV_SIDE = "side"

UI_LAYOUT_LABELS = {
    "compact": "Compact Professional",
    "dashboard": "Dashboard",
    "minimal": "Minimal / Dense",
}
UI_LAYOUTS: dict[str, dict[str, Any]] = {
    "compact": {
        "navigace": NAV_TOP,
        "sablona": "bezna",
        "karty": "jemne",
        "radius": "6px",
        "nav_width": "0px",
        "sticky_akce": True,
        "prehled": False,
        "sirka": "1560px",
        "popis": "Vodorovná navigace, jemné rámování, formuláře ve sloupcích.",
        "vhodne": "Každodenní práce na 1920×1080 i 1366×768.",
    },
    "dashboard": {
        "navigace": NAV_SIDE,
        "sablona": "bezna",
        "karty": "vyrazne",
        "radius": "10px",
        "nav_width": "216px",
        "sticky_akce": True,
        "prehled": True,
        "sirka": "1720px",
        "popis": "Levý sidebar, přehledové dlaždice se stavem a rychlé akce.",
        "vhodne": "Širší monitory a uživatele, kteří chtějí stav na první pohled.",
    },
    "minimal": {
        "navigace": NAV_TOP,
        "sablona": "kompaktni",
        "karty": "zadne",
        "radius": "3px",
        "nav_width": "0px",
        "sticky_akce": False,
        "prehled": False,
        "sirka": "100%",
        "popis": "Maximální informační hustota, žádné karty ani dekorace.",
        "vhodne": "Power user, malé rozlišení, práce s klávesnicí.",
    },
}
DEFAULT_UI_LAYOUT = "compact"

# ---------------------------------------------------------------------------
# Přiblížení stránky
# ---------------------------------------------------------------------------

DEFAULT_UI_ZOOM = 100
UI_ZOOM_MIN = 80
UI_ZOOM_MAX = 150
UI_ZOOM_STEP = 5

# ---------------------------------------------------------------------------
# Barevná schémata
# ---------------------------------------------------------------------------

DEFAULT_UI_THEME = "svetle"
UI_THEME_LABELS = {
    "svetle": "Světlé",
    "tmave": "Tmavé",
    "ocean": "Oceán",
    "les": "Les",
    "pisek": "Písek",
    "burgund": "Burgund",
}
UI_THEMES: dict[str, dict[str, Any]] = {
    "svetle": {
        "dark": False,
        "primary": "#1769aa",
        "secondary": "#455a64",
        "accent": "#00897b",
        "vars": {
            "--app-ink": "#17243d",
            "--app-muted": "#5b6b80",
            "--app-border": "#cfd8e3",
            "--app-surface": "#ffffff",
            "--app-page-from": "#eef2f7",
            "--app-page-mid": "#f3f6fa",
            "--app-page-to": "#f7f9fc",
            "--app-primary": "#1769aa",
            "--app-primary-soft": "#eaf4ff",
            "--app-tab": "#5b6b80",
            "--app-tab-active-bg": "#eaf4ff",
            "--app-tab-active": "#0b63ad",
            "--app-brand": "#0b4f86",
            "--app-brand-shadow": "rgba(11, 79, 134, 0.22)",
            "--app-shell-border": "#d3dce7",
            "--app-shell-shadow": "rgba(22, 42, 66, 0.10)",
            "--app-status-border": "#bcd7ef",
            "--app-status-accent": "#1769aa",
            "--app-status-bg": "#f2f8ff",
            "--app-status-ink": "#17243d",
            "--app-field": "#101828",
            "--app-field-label": "#5b6b80",
            "--app-block": "#f7f9fc",
            "--app-note": "#f4f7fb",
            "--app-table-head": "#e7edf4",
            "--app-hover": "#f0f6fd",
            "--app-separator": "#e2e8f0",
            "--app-ok": "#0f7b3d",
            "--app-ok-bg": "#eaf7ef",
            "--app-warn": "#a15c00",
            "--app-warn-bg": "#fdf4e6",
            "--app-bad": "#b42318",
            "--app-bad-bg": "#fdf0ef",
        },
    },
    "tmave": {
        "dark": True,
        "primary": "#5eb0e8",
        "secondary": "#90a4ae",
        "accent": "#26a69a",
        "vars": {
            "--app-ink": "#e8eef6",
            "--app-muted": "#9aa8b8",
            "--app-border": "#3d4a5c",
            "--app-surface": "#1e2733",
            "--app-page-from": "#141a22",
            "--app-page-mid": "#161d26",
            "--app-page-to": "#1a222c",
            "--app-primary": "#5eb0e8",
            "--app-primary-soft": "#243140",
            "--app-tab": "#9aa8b8",
            "--app-tab-active-bg": "#243140",
            "--app-tab-active": "#8ec9f0",
            "--app-brand": "#1a4f7a",
            "--app-brand-shadow": "rgba(0, 0, 0, 0.45)",
            "--app-shell-border": "#3d4a5c",
            "--app-shell-shadow": "rgba(0, 0, 0, 0.45)",
            "--app-status-border": "#3d6a94",
            "--app-status-accent": "#5eb0e8",
            "--app-status-bg": "#243140",
            "--app-status-ink": "#d7e7f6",
            "--app-field": "#f0f4f8",
            "--app-field-label": "#a8b6c6",
            "--app-block": "#232d3a",
            "--app-note": "#243040",
            "--app-table-head": "#2a3646",
            "--app-hover": "#2c3a4c",
            "--app-separator": "#3d4a5c",
            "--app-ok": "#5fd08a",
            "--app-ok-bg": "#1d3327",
            "--app-warn": "#e0a860",
            "--app-warn-bg": "#33291a",
            "--app-bad": "#f18a80",
            "--app-bad-bg": "#3a2422",
        },
    },
    "ocean": {
        "dark": False,
        "primary": "#0e7490",
        "secondary": "#155e75",
        "accent": "#0f766e",
        "vars": {
            "--app-ink": "#134e4a",
            "--app-muted": "#42737a",
            "--app-border": "#bcdfe3",
            "--app-surface": "#fbfeff",
            "--app-page-from": "#e6f4f6",
            "--app-page-mid": "#eef8f9",
            "--app-page-to": "#f4fbfc",
            "--app-primary": "#0e7490",
            "--app-primary-soft": "#e0f7fa",
            "--app-tab": "#42737a",
            "--app-tab-active-bg": "#e0f7fa",
            "--app-tab-active": "#155e75",
            "--app-brand": "#115e75",
            "--app-brand-shadow": "rgba(14, 116, 144, 0.22)",
            "--app-shell-border": "#c2e2e6",
            "--app-shell-shadow": "rgba(15, 70, 80, 0.10)",
            "--app-status-border": "#a5e4ee",
            "--app-status-accent": "#0e7490",
            "--app-status-bg": "#f0fcfd",
            "--app-status-ink": "#134e4a",
            "--app-field": "#134e4a",
            "--app-field-label": "#42737a",
            "--app-block": "#f2fbfb",
            "--app-note": "#f0fbfb",
            "--app-table-head": "#dcf1f3",
            "--app-hover": "#e6f9fb",
            "--app-separator": "#d3e9ec",
            "--app-ok": "#0f7b57",
            "--app-ok-bg": "#e8f7f1",
            "--app-warn": "#a15c00",
            "--app-warn-bg": "#fdf4e6",
            "--app-bad": "#b42318",
            "--app-bad-bg": "#fdf0ef",
        },
    },
    "les": {
        "dark": False,
        "primary": "#3f7a3a",
        "secondary": "#3f6212",
        "accent": "#4d7c0f",
        "vars": {
            "--app-ink": "#1a3318",
            "--app-muted": "#4f6a48",
            "--app-border": "#c9dcbc",
            "--app-surface": "#fcfefa",
            "--app-page-from": "#eaf2e3",
            "--app-page-mid": "#f1f7ec",
            "--app-page-to": "#f6faf2",
            "--app-primary": "#3f7a3a",
            "--app-primary-soft": "#edf8e6",
            "--app-tab": "#4f6a48",
            "--app-tab-active-bg": "#edf8e6",
            "--app-tab-active": "#2d5a28",
            "--app-brand": "#2d5a28",
            "--app-brand-shadow": "rgba(45, 90, 40, 0.22)",
            "--app-shell-border": "#cadcbd",
            "--app-shell-shadow": "rgba(40, 70, 30, 0.10)",
            "--app-status-border": "#c4e6c9",
            "--app-status-accent": "#3f7a3a",
            "--app-status-bg": "#f3fbf4",
            "--app-status-ink": "#1a3318",
            "--app-field": "#1a3318",
            "--app-field-label": "#4f6a48",
            "--app-block": "#f4faf0",
            "--app-note": "#f4faf0",
            "--app-table-head": "#e2eeda",
            "--app-hover": "#edf8e6",
            "--app-separator": "#dbe8d2",
            "--app-ok": "#2f6d33",
            "--app-ok-bg": "#eaf6ea",
            "--app-warn": "#8f5a05",
            "--app-warn-bg": "#fbf3e4",
            "--app-bad": "#a8261c",
            "--app-bad-bg": "#fbeeec",
        },
    },
    "pisek": {
        "dark": False,
        "primary": "#b45309",
        "secondary": "#92400e",
        "accent": "#c2410c",
        "vars": {
            "--app-ink": "#432310",
            "--app-muted": "#7c5334",
            "--app-border": "#e8d5bb",
            "--app-surface": "#fffdfa",
            "--app-page-from": "#f6eee1",
            "--app-page-mid": "#faf4ea",
            "--app-page-to": "#fdf9f3",
            "--app-primary": "#b45309",
            "--app-primary-soft": "#fdf0dd",
            "--app-tab": "#7c5334",
            "--app-tab-active-bg": "#fdf0dd",
            "--app-tab-active": "#9a3412",
            "--app-brand": "#9a3412",
            "--app-brand-shadow": "rgba(154, 52, 18, 0.22)",
            "--app-shell-border": "#e6d3b7",
            "--app-shell-shadow": "rgba(90, 50, 20, 0.10)",
            "--app-status-border": "#f2ce9d",
            "--app-status-accent": "#b45309",
            "--app-status-bg": "#fff8ef",
            "--app-status-ink": "#432310",
            "--app-field": "#432310",
            "--app-field-label": "#7c5334",
            "--app-block": "#fbf5ec",
            "--app-note": "#fbf6ee",
            "--app-table-head": "#f2e6d3",
            "--app-hover": "#fdf0dd",
            "--app-separator": "#eaddc8",
            "--app-ok": "#2f6d33",
            "--app-ok-bg": "#edf6ea",
            "--app-warn": "#96540a",
            "--app-warn-bg": "#fdf2e2",
            "--app-bad": "#b42318",
            "--app-bad-bg": "#fdefed",
        },
    },
    "burgund": {
        "dark": False,
        "primary": "#9f1239",
        "secondary": "#9f1239",
        "accent": "#be123c",
        "vars": {
            "--app-ink": "#4c0519",
            "--app-muted": "#84334b",
            "--app-border": "#ecc9d2",
            "--app-surface": "#fffcfd",
            "--app-page-from": "#f5e8ec",
            "--app-page-mid": "#faf0f2",
            "--app-page-to": "#fdf7f8",
            "--app-primary": "#9f1239",
            "--app-primary-soft": "#fdeaee",
            "--app-tab": "#84334b",
            "--app-tab-active-bg": "#fdeaee",
            "--app-tab-active": "#881337",
            "--app-brand": "#881337",
            "--app-brand-shadow": "rgba(136, 19, 55, 0.22)",
            "--app-shell-border": "#e9c4ce",
            "--app-shell-shadow": "rgba(80, 20, 40, 0.10)",
            "--app-status-border": "#f3c0ca",
            "--app-status-accent": "#9f1239",
            "--app-status-bg": "#fff5f7",
            "--app-status-ink": "#4c0519",
            "--app-field": "#4c0519",
            "--app-field-label": "#84334b",
            "--app-block": "#fdf4f6",
            "--app-note": "#fdf4f6",
            "--app-table-head": "#f4e2e7",
            "--app-hover": "#fdeaee",
            "--app-separator": "#f0dbe1",
            "--app-ok": "#2f6d47",
            "--app-ok-bg": "#eaf6ef",
            "--app-warn": "#96540a",
            "--app-warn-bg": "#fdf2e2",
            "--app-bad": "#b42318",
            "--app-bad-bg": "#fdefed",
        },
    },
}


# ---------------------------------------------------------------------------
# Čtení nastavení z configu (starší klíče zůstávají funkční)
# ---------------------------------------------------------------------------


def _valid_choice(value: object, allowed: dict[str, Any]) -> str | None:
    text = str(value or "").strip()
    return text if text in allowed else None


def peek_ui_size(raw: dict[str, Any] | None, key: str) -> str:
    if isinstance(raw, dict):
        current = _valid_choice(raw.get(key), UI_TEXT_SIZE_LABELS)
        if current:
            return current
        legacy = _valid_choice(raw.get("ui_velikost_textu"), UI_TEXT_SIZE_LABELS)
        if legacy:
            return legacy
    return DEFAULT_UI_TEXT_SIZE


def peek_ui_text_size(raw: dict[str, Any] | None) -> str:
    return peek_ui_size(raw, "ui_velikost_textu")


def peek_ui_theme(raw: dict[str, Any] | None) -> str:
    value = raw.get("ui_barevne_schema") if isinstance(raw, dict) else None
    return str(value) if value in UI_THEMES else DEFAULT_UI_THEME


def peek_ui_layout(raw: dict[str, Any] | None) -> str:
    """UI šablona: compact, dashboard nebo minimal."""
    if isinstance(raw, dict):
        current = _valid_choice(
            raw.get("layout", raw.get("ui_layout")), UI_LAYOUT_LABELS
        )
        if current:
            return current
    return DEFAULT_UI_LAYOUT


def peek_ui_zoom(raw: dict[str, Any] | None) -> int:
    """Přiblížení stránky v procentech."""
    if not isinstance(raw, dict):
        return DEFAULT_UI_ZOOM
    value = raw.get("zoom", raw.get("ui_zoom"))
    if value in (None, ""):
        return DEFAULT_UI_ZOOM
    try:
        zoom = int(round(float(value)))
    except (TypeError, ValueError):
        return DEFAULT_UI_ZOOM
    zoom = max(UI_ZOOM_MIN, min(UI_ZOOM_MAX, zoom))
    return int(round(zoom / UI_ZOOM_STEP) * UI_ZOOM_STEP)


def peek_ui_blocks(raw: dict[str, Any] | None) -> bool:
    """Zvýraznit rámování bloků."""
    if not isinstance(raw, dict):
        return False
    value = raw.get("zvyrazneni", raw.get("ui_zvyrazneni_bloku"))
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().casefold() in {"1", "true", "ano", "on"}


def peek_ui_template(raw: dict[str, Any] | None) -> str:
    """Šablona hustoty; bez uloženého výběru ji předvolí UI šablona."""
    if isinstance(raw, dict):
        current = _valid_choice(
            raw.get("sablona", raw.get("ui_sablona")), UI_STYLE_TEMPLATE_LABELS
        )
        if current:
            return current
    return str(UI_LAYOUTS[peek_ui_layout(raw)]["sablona"])


def _peek_preset(
    raw: dict[str, Any] | None,
    *,
    keys: tuple[str, ...],
    allowed: dict[str, Any],
    preset_key: str,
) -> str:
    if isinstance(raw, dict):
        for key in keys:
            current = _valid_choice(raw.get(key), allowed)
            if current:
                return current
    return str(UI_STYLE_TEMPLATES[peek_ui_template(raw)][preset_key])


def peek_ui_spacing(raw: dict[str, Any] | None) -> str:
    return _peek_preset(
        raw,
        keys=("rozestupy", "ui_rozestupy"),
        allowed=UI_SPACING_LABELS,
        preset_key="rozestupy",
    )


def peek_ui_line(raw: dict[str, Any] | None) -> str:
    return _peek_preset(
        raw,
        keys=("radkovani", "ui_radkovani"),
        allowed=UI_SPACING_LABELS,
        preset_key="radkovani",
    )


def peek_ui_density(raw: dict[str, Any] | None) -> str:
    return _peek_preset(
        raw,
        keys=("hustota", "ui_hustota_poli"),
        allowed=UI_DENSITY_LABELS,
        preset_key="hustota",
    )


def peek_ui_appearance(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Kompletní vzhled: šablona, hustota, písmo, barvy a přiblížení."""
    data = raw if isinstance(raw, dict) else {}
    mapped = {
        "ui_velikost_textu": data.get("text", data.get("ui_velikost_textu")),
        "ui_velikost_nadpisu": data.get("nadpis", data.get("ui_velikost_nadpisu")),
        "ui_velikost_popisu": data.get("popis", data.get("ui_velikost_popisu")),
        "ui_barevne_schema": data.get("schema", data.get("ui_barevne_schema")),
        "ui_zvyrazneni_bloku": data.get(
            "zvyrazneni", data.get("ui_zvyrazneni_bloku")
        ),
        "ui_zoom": data.get("zoom", data.get("ui_zoom")),
        "ui_layout": data.get("layout", data.get("ui_layout")),
        "ui_sablona": data.get("sablona", data.get("ui_sablona")),
        "ui_rozestupy": data.get("rozestupy", data.get("ui_rozestupy")),
        "ui_radkovani": data.get("radkovani", data.get("ui_radkovani")),
        "ui_hustota_poli": data.get("hustota", data.get("ui_hustota_poli")),
    }
    return {
        "layout": peek_ui_layout(mapped),
        "text": peek_ui_size(mapped, "ui_velikost_textu"),
        "nadpis": peek_ui_size(mapped, "ui_velikost_nadpisu"),
        "popis": peek_ui_size(mapped, "ui_velikost_popisu"),
        "schema": peek_ui_theme(mapped),
        "zvyrazneni": peek_ui_blocks(mapped),
        "zoom": peek_ui_zoom(mapped),
        "sablona": peek_ui_template(mapped),
        "rozestupy": peek_ui_spacing(mapped),
        "radkovani": peek_ui_line(mapped),
        "hustota": peek_ui_density(mapped),
    }


def appearance_config(appearance: dict[str, Any]) -> dict[str, Any]:
    """Převede vzhled na klíče do config.json."""
    peeked = peek_ui_appearance(appearance)
    return {
        "ui_layout": peeked["layout"],
        "ui_velikost_textu": peeked["text"],
        "ui_velikost_nadpisu": peeked["nadpis"],
        "ui_velikost_popisu": peeked["popis"],
        "ui_barevne_schema": peeked["schema"],
        "ui_zvyrazneni_bloku": bool(peeked["zvyrazneni"]),
        "ui_zoom": int(peeked["zoom"]),
        "ui_sablona": peeked["sablona"],
        "ui_rozestupy": peeked["rozestupy"],
        "ui_radkovani": peeked["radkovani"],
        "ui_hustota_poli": peeked["hustota"],
    }


def layout_tokens(appearance: dict[str, Any]) -> dict[str, Any]:
    """Rozvržení zvolené šablony: navigace, karty, šířka obsahu."""
    return dict(UI_LAYOUTS[peek_ui_appearance(appearance)["layout"]])


def appearance_css_vars(appearance: dict[str, Any]) -> dict[str, str]:
    """Design tokeny pro CSS z uloženého vzhledu."""
    peeked = peek_ui_appearance(appearance)
    theme = UI_THEMES[peeked["schema"]]
    layout = UI_LAYOUTS[peeked["layout"]]
    space = UI_SPACING_PX[peeked["rozestupy"]]
    variables = dict(theme["vars"])
    variables.update(
        {
            "--app-text": f"{UI_TEXT_SIZE_PX['text'][peeked['text']]}px",
            "--app-heading": f"{UI_TEXT_SIZE_PX['nadpis'][peeked['nadpis']]}px",
            "--app-help": f"{UI_TEXT_SIZE_PX['popis'][peeked['popis']]}px",
            "--app-line": UI_LINE_HEIGHT[peeked["radkovani"]],
            "--app-zoom": f"{peeked['zoom'] / 100:.2f}",
            "--app-gap": f"{space['gap']}px",
            "--app-stack": f"{space['stack']}px",
            "--app-panel-pad": f"{space['panel']}px",
            "--app-section-gap": f"{space['section']}px",
            "--app-block-pad": f"{space['block']}px",
            "--app-control-min": f"{space['control']}px",
            "--app-header-min": f"{space['header']}px",
            "--app-field-min": f"{UI_FIELD_HEIGHT[peeked['hustota']]}px",
            "--app-radius": str(layout["radius"]),
            "--app-nav-width": str(layout["nav_width"]),
            "--app-content-max": str(layout["sirka"]),
        }
    )
    return variables


def appearance_html_classes(appearance: dict[str, Any]) -> str:
    """Třídy na <html>, kterými se přepíná šablona a hustota."""
    peeked = peek_ui_appearance(appearance)
    layout = UI_LAYOUTS[peeked["layout"]]
    names = [
        f"theme-{peeked['schema']}",
        f"layout-{peeked['layout']}",
        f"cards-{layout['karty']}",
        f"nav-{layout['navigace']}",
        f"fields-{peeked['hustota']}",
    ]
    if layout["prehled"]:
        names.append("overview-on")
    if peeked["zvyrazneni"]:
        names.append("blocks-emphasized")
    return " ".join(names)


def _removable_html_classes() -> str:
    names = [f"theme-{name}" for name in UI_THEMES]
    names += [f"layout-{name}" for name in UI_LAYOUTS]
    names += [f"cards-{name}" for name in ("jemne", "vyrazne", "zadne")]
    names += [f"nav-{name}" for name in (NAV_TOP, NAV_SIDE)]
    names += [f"fields-{name}" for name in UI_DENSITY_LABELS]
    names.append("overview-on")
    names.append("blocks-emphasized")
    return " ".join(names)


def apply_ui_appearance(
    appearance: dict[str, Any],
    *,
    dark_mode: Any | None = None,
) -> None:
    """Nastaví design tokeny a šablonu v běžícím okně."""
    peeked = peek_ui_appearance(appearance)
    theme = UI_THEMES[peeked["schema"]]
    variables = appearance_css_vars(peeked)
    inline = "; ".join(f"{key}: {value}" for key, value in variables.items())
    ui.query(":root").style(inline)
    ui.query("html").style(
        f"font-size: {variables['--app-text']}; zoom: {variables['--app-zoom']}; {inline}"
    )
    ui.query("html").classes(
        remove=_removable_html_classes(),
        add=appearance_html_classes(peeked),
    )
    ui.colors(
        primary=str(theme["primary"]),
        secondary=str(theme["secondary"]),
        accent=str(theme["accent"]),
    )
    if dark_mode is not None:
        if theme["dark"]:
            dark_mode.enable()
        else:
            dark_mode.disable()


# ---------------------------------------------------------------------------
# CSS: rozdělené po vrstvách, spojené do UI_CSS
# ---------------------------------------------------------------------------

_CSS_TOKENS = """
:root {
    --app-ink: #17243d;
    --app-muted: #5b6b80;
    --app-border: #cfd8e3;
    --app-surface: #ffffff;
    --app-page-from: #eef2f7;
    --app-page-mid: #f3f6fa;
    --app-page-to: #f7f9fc;
    --app-primary: #1769aa;
    --app-primary-soft: #eaf4ff;
    --app-tab: #5b6b80;
    --app-tab-active-bg: #eaf4ff;
    --app-tab-active: #0b63ad;
    --app-brand: #0b4f86;
    --app-brand-shadow: rgba(11, 79, 134, 0.22);
    --app-shell-border: #d3dce7;
    --app-shell-shadow: rgba(22, 42, 66, 0.10);
    --app-status-border: #bcd7ef;
    --app-status-accent: #1769aa;
    --app-status-bg: #f2f8ff;
    --app-status-ink: #17243d;
    --app-field: #101828;
    --app-field-label: #5b6b80;
    --app-block: #f7f9fc;
    --app-note: #f4f7fb;
    --app-table-head: #e7edf4;
    --app-hover: #f0f6fd;
    --app-separator: #e2e8f0;
    --app-ok: #0f7b3d;
    --app-ok-bg: #eaf7ef;
    --app-warn: #a15c00;
    --app-warn-bg: #fdf4e6;
    --app-bad: #b42318;
    --app-bad-bg: #fdf0ef;
    --app-text: 14px;
    --app-heading: 16px;
    --app-help: 12px;
    --app-line: 1.4;
    --app-zoom: 1.00;
    --app-weight-heading: 650;
    --app-weight-text: 400;
    --app-gap: 10px;
    --app-stack: 10px;
    --app-panel-pad: 10px;
    --app-section-gap: 6px;
    --app-block-pad: 12px;
    --app-control-min: 36px;
    --app-header-min: 42px;
    --app-field-min: 38px;
    --app-radius: 6px;
    --app-nav-width: 0px;
    --app-content-max: 1560px;
}
"""

_CSS_BASE = """
html {
    font-size: var(--app-text);
    zoom: var(--app-zoom);
}

body,
body.body--dark,
.body--dark {
    background: var(--app-page-to) !important;
    color: var(--app-ink);
    font-family: "Segoe UI", Inter, Roboto, Arial, sans-serif;
    font-size: var(--app-text);
    font-weight: var(--app-weight-text);
    line-height: var(--app-line);
}

.app-page {
    width: 100%;
    max-width: var(--app-content-max);
    margin: 0 auto;
}

.q-separator {
    background: var(--app-separator) !important;
}
"""

_CSS_TYPOGRAPHY = """
.app-title {
    color: var(--app-ink);
    font-size: calc(var(--app-heading) * 1.05);
    font-weight: 700;
    line-height: 1.1;
    letter-spacing: -0.01em;
}

.app-heading,
.app-subheading {
    color: var(--app-ink);
    font-size: var(--app-heading);
    font-weight: var(--app-weight-heading);
    line-height: 1.25;
}

.app-label {
    color: var(--app-ink);
    font-size: var(--app-text);
    font-weight: var(--app-weight-heading);
    line-height: var(--app-line);
}

.app-text {
    color: var(--app-ink);
    font-size: var(--app-text);
    font-weight: var(--app-weight-text);
    line-height: var(--app-line);
}

.section-help,
.ui-help,
.inline-status,
.app-footer,
.connection-details,
.connection-caption {
    color: var(--app-muted);
    font-size: var(--app-help);
    font-weight: var(--app-weight-text);
    line-height: var(--app-line);
}

.app-mono {
    font-family: "Cascadia Mono", Consolas, "Courier New", monospace;
    font-size: var(--app-text);
}

.text-ok { color: var(--app-ok); }
.text-warn { color: var(--app-warn); }
.text-bad { color: var(--app-bad); }
"""

_CSS_FORMS = """
.q-field,
.q-field__native,
.q-field__input,
.q-field__prefix,
.q-field__suffix {
    color: var(--app-field);
    font-size: var(--app-text);
    font-weight: var(--app-weight-text);
}

.q-field__label {
    color: var(--app-field-label);
    font-size: var(--app-help);
    font-weight: var(--app-weight-text);
}

.q-field--dense .q-field__control,
.q-field__control {
    min-height: var(--app-field-min);
}

.q-field--outlined .q-field__control:before {
    border-color: var(--app-border);
}

.q-field--standard .q-field__control::before {
    border-bottom: 1px solid var(--app-border);
}

.q-field--standard:hover .q-field__control::before {
    border-bottom-color: var(--app-primary);
}

.q-checkbox__label,
.q-toggle__label,
.q-radio__label {
    color: var(--app-ink);
    font-size: var(--app-text);
    font-weight: var(--app-weight-text);
}

.q-item__label,
.q-expansion-item .q-item__section--main,
.q-notification__message {
    font-size: var(--app-text);
    font-weight: var(--app-weight-text);
}

.nicegui-code,
pre, code {
    font-size: var(--app-text);
    font-weight: var(--app-weight-text);
}

.form-grid {
    display: grid;
    width: 100%;
    column-gap: calc(var(--app-gap) * 1.4);
    row-gap: var(--app-gap);
    align-items: end;
}

.form-grid-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.form-grid-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.form-grid-4 { grid-template-columns: repeat(4, minmax(0, 1fr)); }

@media (max-width: 1500px) {
    .form-grid-4 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

@media (max-width: 1180px) {
    .form-grid-3,
    .form-grid-4 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 820px) {
    .form-grid-2,
    .form-grid-3,
    .form-grid-4 { grid-template-columns: minmax(0, 1fr); }
}

.field-hint {
    color: var(--app-muted);
    font-size: var(--app-help);
    cursor: help;
}
"""

_CSS_BUTTONS = """
.q-btn {
    min-height: var(--app-control-min);
    border-radius: var(--app-radius);
    font-size: var(--app-text);
    font-weight: var(--app-weight-heading);
    letter-spacing: 0;
    text-transform: none;
}

.q-btn .q-icon {
    font-size: calc(var(--app-text) * 1.25);
}

.q-btn--dense {
    min-height: calc(var(--app-control-min) - 4px);
}

.btn-tertiary {
    color: var(--app-muted) !important;
}

.q-btn.disabled,
.q-btn[disabled] {
    opacity: 0.45 !important;
}
"""

_CSS_NAV = """
.app-topbar {
    display: flex;
    align-items: center;
    gap: var(--app-gap);
    width: 100%;
    min-height: var(--app-header-min);
    padding: 4px 10px;
    background: var(--app-surface);
    border: 1px solid var(--app-shell-border);
    border-radius: var(--app-radius);
}

.brand-mark {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 2px 10px 2px 4px;
    color: var(--app-brand);
    border-right: 1px solid var(--app-separator);
}

.brand-chip {
    background: var(--app-brand);
    color: #ffffff;
    border-radius: var(--app-radius);
}

.brand-chip .app-title,
.brand-chip .ui-help {
    color: #ffffff;
}

.q-tab {
    min-height: var(--app-control-min);
    color: var(--app-tab);
    padding: 0 12px;
    border-radius: var(--app-radius);
}

.q-tab__label {
    font-size: var(--app-text);
    font-weight: var(--app-weight-heading);
    letter-spacing: 0;
}

.q-tab__icon {
    font-size: calc(var(--app-text) * 1.2);
    margin-bottom: 0;
}

.q-tab--active {
    background: var(--app-tab-active-bg);
    color: var(--app-tab-active);
}

.q-tab__indicator {
    height: 2px;
}

.q-tabs,
.q-tab-panels,
.app-surface {
    background: var(--app-surface) !important;
    color: var(--app-ink);
}

.q-tab-panel {
    padding: var(--app-panel-pad);
}

/* Workspace: navigace nahoře, nebo jako levý sidebar. Rozhoduje třída na <html>. */
.workspace {
    display: flex;
    flex-direction: column;
    align-items: stretch;
}

.app-nav {
    width: 100%;
    border-bottom: 1px solid var(--app-separator);
}

html.nav-side .workspace {
    flex-direction: row;
}

html.nav-side .app-nav {
    width: var(--app-nav-width);
    min-width: var(--app-nav-width);
    flex-shrink: 0;
    height: auto;
    padding: 6px;
    border-bottom: none;
    border-right: 1px solid var(--app-separator);
}

html.nav-side .app-nav .q-tabs__content {
    flex-direction: column;
    align-items: stretch;
    justify-content: flex-start;
    flex: 0 0 auto;
}

html.nav-side .app-nav.q-tabs {
    align-items: flex-start;
}

html.nav-side .app-nav .q-tabs__arrow {
    display: none;
}

/* Sidebar navigace (hlavní i administrace) */
html.nav-side .app-nav .q-tab,
.side-nav .q-tab {
    width: 100%;
    flex: 0 0 auto;
    min-height: var(--app-control-min);
    justify-content: flex-start;
    margin-bottom: 2px;
}

html.nav-side .app-nav .q-tab__content,
.side-nav .q-tab__content {
    flex-direction: row;
    justify-content: flex-start;
    gap: 8px;
}

html.nav-side .app-nav .q-tab__indicator,
.side-nav .q-tab__indicator {
    display: none;
}

html.nav-side .app-nav .q-tab--active,
.side-nav .q-tab--active {
    box-shadow: inset 3px 0 0 var(--app-primary);
}

.admin-nav {
    width: 172px;
    min-width: 172px;
    padding: 6px;
    border-right: 1px solid var(--app-separator);
}

@media (max-width: 1240px) {
    .admin-nav {
        width: 52px;
        min-width: 52px;
    }

    .admin-nav .q-tab__label {
        display: none;
    }
}
"""

_CSS_COMPONENTS = """
.app-shell {
    background: var(--app-surface);
    border: 1px solid var(--app-shell-border);
    border-radius: var(--app-radius);
    overflow: hidden;
}

.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: var(--app-help);
    font-weight: 650;
    white-space: nowrap;
    border: 1px solid transparent;
}

.status-pill-ok {
    color: var(--app-ok);
    background: var(--app-ok-bg);
    border-color: var(--app-ok);
}

.status-pill-bad {
    color: var(--app-bad);
    background: var(--app-bad-bg);
    border-color: var(--app-bad);
}

.status-dot {
    width: 8px;
    height: 8px;
    border-radius: 999px;
    background: currentColor;
    flex-shrink: 0;
}

.db-chip {
    cursor: pointer;
    user-select: none;
    border-radius: var(--app-radius);
    min-width: 0;
}

.db-chip:hover {
    background: var(--app-hover);
}

.connection-name {
    color: var(--app-ink);
    font-size: var(--app-text);
    font-weight: 650;
    line-height: 1.2;
}

.status-strip {
    border: 1px solid var(--app-status-border);
    border-left: 3px solid var(--app-status-accent);
    background: var(--app-status-bg);
    color: var(--app-status-ink);
    border-radius: var(--app-radius);
}

.section-header {
    width: 100%;
    margin-bottom: var(--app-section-gap);
}

.section-icon {
    background: var(--app-primary-soft);
    color: var(--app-primary);
    border-radius: var(--app-radius);
}

.app-note {
    background: var(--app-note);
    border: 1px solid var(--app-border);
    border-radius: var(--app-radius);
}

.app-table-head {
    background: var(--app-table-head);
    color: var(--app-ink);
    font-size: var(--app-text);
    font-weight: var(--app-weight-heading);
}

.app-list {
    border-color: var(--app-border) !important;
    background: var(--app-surface);
    border-radius: var(--app-radius);
}

.app-row:hover {
    background: var(--app-hover);
}

/* Přehledové dlaždice patří jen do šablony s přehledem. */
.overview-row {
    display: none;
}

html.overview-on .overview-row {
    display: flex;
    margin-bottom: var(--app-gap);
}

.overview-row > .stat-card {
    flex: 1 1 0;
}

.stat-card {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
    padding: 4px 10px;
    background: var(--app-note);
    border: 1px solid var(--app-border);
    border-radius: var(--app-radius);
}

.stat-card-label {
    color: var(--app-muted);
    font-size: var(--app-help);
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

.stat-card-value {
    color: var(--app-ink);
    font-size: var(--app-text);
    font-weight: 650;
    line-height: 1.2;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.action-bar {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--app-gap);
    width: 100%;
    padding: var(--app-gap);
    background: var(--app-surface);
    border-top: 1px solid var(--app-separator);
}

html.layout-compact .action-bar,
html.layout-dashboard .action-bar {
    position: sticky;
    bottom: 0;
    z-index: 3;
    box-shadow: 0 -4px 12px var(--app-shell-shadow);
}

.summary-line {
    display: flex;
    align-items: center;
    gap: var(--app-gap);
    flex-wrap: wrap;
    width: 100%;
}

.count-badge {
    display: inline-flex;
    align-items: center;
    padding: 1px 8px;
    border-radius: 999px;
    background: var(--app-primary-soft);
    color: var(--app-tab-active);
    font-size: var(--app-help);
    font-weight: 650;
}

.chip-row {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
    max-height: 5.6em;
    overflow-y: auto;
    scrollbar-width: thin;
}

.chip-row:empty {
    display: none;
}

/* Dashboard má navíc přehledové dlaždice, seznam chipů proto drží nižší strop. */
html.layout-dashboard .chip-row {
    max-height: 4.2em;
}

.selection-chip {
    display: inline-flex;
    align-items: center;
    width: auto;
    border: 1px solid var(--app-border);
    background: var(--app-note);
    color: var(--app-ink);
    border-radius: 999px;
    padding: 1px 8px;
    font-size: var(--app-help);
    font-weight: var(--app-weight-text);
    line-height: 1.4;
}

.selection-chip > * {
    width: auto !important;
    margin: 0;
}

.selection-chip-warn {
    background: var(--app-bad-bg);
    border-color: var(--app-bad);
    color: var(--app-bad);
    cursor: pointer;
}

.picker-dialog-list {
    max-height: 46vh;
    overflow-y: auto;
    border: 1px solid var(--app-border);
    border-radius: var(--app-radius);
}

.picker-row {
    cursor: pointer;
    user-select: none;
}

.picker-row .q-checkbox {
    pointer-events: none;
}

.scheduler-help {
    border: 1px solid var(--app-status-border);
    border-left: 3px solid var(--app-status-accent);
    background: var(--app-status-bg);
    color: var(--app-status-ink);
    border-radius: var(--app-radius);
}

.template-card {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px 10px;
    cursor: pointer;
    background: var(--app-surface);
    border: 1px solid var(--app-border);
    border-radius: var(--app-radius);
}

.template-card:hover {
    background: var(--app-hover);
}

.template-card-active {
    border-color: var(--app-primary);
    box-shadow: inset 0 0 0 1px var(--app-primary);
    background: var(--app-primary-soft);
}

.template-preview {
    display: flex;
    gap: 3px;
    height: 34px;
    padding: 3px;
    background: var(--app-block);
    border: 1px solid var(--app-separator);
    border-radius: 3px;
}

.template-preview i {
    display: block;
    background: var(--app-primary);
    opacity: 0.35;
    border-radius: 2px;
}

.template-preview .pv-side { width: 18%; opacity: 0.55; }
.template-preview .pv-main { flex: 1; }
.template-preview .pv-col { display: flex; flex-direction: column; gap: 3px; flex: 1; }
.template-preview .pv-bar { height: 5px; }
.template-preview .pv-fill { flex: 1; opacity: 0.18; }
"""

_CSS_LAYOUTS = """
.ui-block {
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: var(--app-stack) !important;
}

.app-card {
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: var(--app-stack);
    padding: var(--app-block-pad);
    background: var(--app-surface);
    border: 1px solid var(--app-border);
    border-radius: var(--app-radius);
}

html.cards-vyrazne .app-card {
    box-shadow: 0 1px 3px var(--app-shell-shadow);
}

html.cards-zadne .app-card {
    padding: 0 0 var(--app-gap) 0;
    border: none;
    border-bottom: 1px solid var(--app-separator);
    border-radius: 0;
    background: transparent;
    box-shadow: none;
}

html.cards-zadne .app-note,
html.cards-zadne .stat-card {
    background: transparent;
}

html.blocks-emphasized .app-card,
html.blocks-emphasized .ui-block {
    border-left: 3px solid var(--app-primary);
}

html.blocks-emphasized .section-header {
    background: var(--app-primary-soft);
    border-radius: var(--app-radius);
    padding: 4px 8px;
}

html.layout-minimal .q-tab {
    padding: 0 8px;
}

html.layout-minimal .section-icon {
    display: none;
}

html.layout-minimal .app-topbar {
    border-radius: 0;
    border-left: none;
    border-right: none;
}

html.fields-husta .q-btn {
    min-height: calc(var(--app-control-min) - 2px);
}
"""

UI_CSS = "\n".join(
    (
        _CSS_TOKENS,
        _CSS_BASE,
        _CSS_TYPOGRAPHY,
        _CSS_FORMS,
        _CSS_BUTTONS,
        _CSS_NAV,
        _CSS_COMPONENTS,
        _CSS_LAYOUTS,
    )
)
