"""Validated custom colors and derived UI tokens; no UI or database dependency."""
from __future__ import annotations

import re


CUSTOM_COLOR_LABELS = {
    "primary": "Tlačítka a zvýraznění",
    "page": "Pozadí stránky",
    "surface": "Pozadí bloků",
    "text": "Hlavní text",
    "muted": "Doplňkové texty",
    "border": "Rámečky a oddělovače",
    "soft": "Pozadí vybraných prvků",
}
DEFAULT_CUSTOM_PALETTE = {
    "primary": "#255bdd", "page": "#f7f9fc", "surface": "#ffffff",
    "text": "#18243b", "muted": "#5b6980", "border": "#7d8ba2", "soft": "#edf3ff",
}


def hex_color(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    color = value.strip().lower()
    if re.fullmatch(r"#[0-9a-f]{3}", color):
        color = "#" + "".join(c * 2 for c in color[1:])
    return color if re.fullmatch(r"#[0-9a-f]{6}", color) else None


def normalize_palette(value: object) -> dict[str, str]:
    raw = value if isinstance(value, dict) else {}
    return {key: hex_color(raw.get(key)) or default
            for key, default in DEFAULT_CUSTOM_PALETTE.items()}


def luminance(color: str) -> float:
    rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    return sum(v * w for v, w in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast(first: str, second: str) -> float:
    bright, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (bright + 0.05) / (dark + 0.05)


def palette_tokens(palette: dict[str, str]) -> dict[str, str]:
    values = normalize_palette(palette)
    tokens: dict[str, str] = {}
    roles = {
        "primary": ("primary", "tab-active", "status-accent", "brand"),
        "page": ("page-from", "page-mid", "page-to"),
        "surface": ("surface", "block", "note"),
        "text": ("ink", "field", "status-ink"),
        "muted": ("muted", "field-label", "tab"),
        "border": ("border", "shell-border", "status-border", "separator", "field-border"),
        "soft": ("primary-soft", "tab-active-bg", "status-bg", "table-head", "hover"),
    }
    for key, names in roles.items():
        tokens.update({f"--app-{name}": values[key] for name in names})
    foreground = max(("#000000", "#ffffff"), key=lambda c: contrast(c, values["primary"]))
    tokens["--custom-on-primary"] = foreground
    tokens["--ds-on-primary"] = foreground
    return tokens
