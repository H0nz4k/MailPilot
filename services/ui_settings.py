"""Nastavení desktopového rozhraní v bloku ``ui`` konfigurace."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


THEME_SYSTEM = "system"
THEME_LIGHT = "light"
THEME_DARK = "dark"
THEMES = (THEME_SYSTEM, THEME_LIGHT, THEME_DARK)
THEME_LABELS = {
    THEME_SYSTEM: "Systémový",
    THEME_LIGHT: "Světlý",
    THEME_DARK: "Tmavý",
}

# Zvětšení celého rozhraní, ne jen písma.
UI_SCALES = (0.9, 1.0, 1.1, 1.25, 1.4, 1.6)
DEFAULT_UI_SCALE = 1.0
MIN_UI_SCALE = UI_SCALES[0]
MAX_UI_SCALE = UI_SCALES[-1]

DEFAULT_WINDOW_WIDTH = 1180
DEFAULT_WINDOW_HEIGHT = 800
MIN_WINDOW_WIDTH = 940
MIN_WINDOW_HEIGHT = 600

# Barevná schémata staré NiceGUI verze; do desktopu se přenáší jen světlo/tma.
_LEGACY_DARK_THEMES = frozenset({"tmave", "les", "burgund"})
# v11 nabízel místo zvětšení jen hustotu polí.
_LEGACY_DENSITY_SCALES = {
    "compact": 1.0,
    "husta": 1.0,
    "tesne": 1.0,
    "normal": 1.1,
    "volna": 1.1,
    "volne": 1.1,
    "bezna": 1.1,
    "comfortable": 1.25,
    "pohodlna": 1.25,
}
CUSTOM_COLOR_KEYS = ("window", "base", "sidebar", "header", "accent", "text")

FONT_BOLD_NONE = "none"
FONT_BOLD_HEADINGS = "headings"
FONT_BOLD_TEXT = "text"
FONT_BOLD_BOTH = "both"
FONT_BOLD_MODES = (
    FONT_BOLD_NONE,
    FONT_BOLD_HEADINGS,
    FONT_BOLD_TEXT,
    FONT_BOLD_BOTH,
)
FONT_BOLD_LABELS = {
    FONT_BOLD_NONE: "Bez tučného",
    FONT_BOLD_HEADINGS: "Tučné nadpisy",
    FONT_BOLD_TEXT: "Tučné texty",
    FONT_BOLD_BOTH: "Tučné nadpisy i texty",
}


@dataclass(frozen=True)
class UiSettings:
    """Hodnoty, které si desktopové UI pamatuje mezi spuštěními."""

    theme: str = THEME_LIGHT
    ui_scale: float = DEFAULT_UI_SCALE
    font_bold_mode: str = FONT_BOLD_NONE
    custom_palette_enabled: bool = False
    custom_palette: dict[str, str] = field(default_factory=dict)
    window_width: int = DEFAULT_WINDOW_WIDTH
    window_height: int = DEFAULT_WINDOW_HEIGHT
    window_x: int | None = None
    window_y: int | None = None
    maximized: bool = False

    def with_theme(self, theme: str) -> "UiSettings":
        return replace(self, theme=normalize_theme(theme))

    def with_scale(self, scale: float) -> "UiSettings":
        return replace(self, ui_scale=normalize_scale(scale))

    def with_font_bold_mode(self, mode: str) -> "UiSettings":
        return replace(self, font_bold_mode=normalize_font_bold_mode(mode))

    def with_custom_palette(
        self, enabled: bool, colors: dict[str, str] | None = None
    ) -> "UiSettings":
        return replace(
            self,
            custom_palette_enabled=bool(enabled),
            custom_palette=normalize_custom_palette(colors or self.custom_palette),
        )

    def zoomed(self, step: int) -> "UiSettings":
        """Posun o ``step`` kroků v nabídce zvětšení."""
        return replace(self, ui_scale=shift_scale(self.ui_scale, step))

    def with_geometry(
        self,
        *,
        width: int,
        height: int,
        x: int | None,
        y: int | None,
        maximized: bool,
    ) -> "UiSettings":
        return replace(
            self,
            window_width=max(MIN_WINDOW_WIDTH, int(width)),
            window_height=max(MIN_WINDOW_HEIGHT, int(height)),
            window_x=None if x is None else int(x),
            window_y=None if y is None else int(y),
            maximized=bool(maximized),
        )


def normalize_theme(value: object) -> str:
    text = str(value or "").strip().casefold()
    if text in THEMES:
        return text
    if text in _LEGACY_DARK_THEMES:
        return THEME_DARK
    return THEME_LIGHT


def normalize_scale(value: object) -> float:
    """Zaokrouhlí na nejbližší nabízené zvětšení."""
    try:
        scale = float(value)
    except (TypeError, ValueError):
        return DEFAULT_UI_SCALE
    if scale > 10:  # hodnoty uložené v procentech
        scale = scale / 100.0
    scale = min(MAX_UI_SCALE, max(MIN_UI_SCALE, scale))
    return min(UI_SCALES, key=lambda step: abs(step - scale))


def shift_scale(current: object, step: int) -> float:
    """Sousední hodnota zvětšení; na krajích zůstane na místě."""
    scale = normalize_scale(current)
    index = UI_SCALES.index(scale) + int(step)
    index = min(len(UI_SCALES) - 1, max(0, index))
    return UI_SCALES[index]


def scale_label(scale: float) -> str:
    return f"{round(normalize_scale(scale) * 100)} %"


def _optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _positive_int(value: object, default: int, minimum: int) -> int:
    parsed = _optional_int(value)
    if parsed is None:
        return default
    return max(minimum, parsed)


def _scale_from_legacy_density(value: object) -> float | None:
    text = str(value or "").strip().casefold()
    return _LEGACY_DENSITY_SCALES.get(text)


def normalize_color(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if not text.startswith("#"):
        text = f"#{text}"
    if len(text) != 7:
        return None
    digits = text[1:]
    if not all(ch in "0123456789abcdefABCDEF" for ch in digits):
        return None
    return f"#{digits.upper()}"


def normalize_custom_palette(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, str] = {}
    for key in CUSTOM_COLOR_KEYS:
        color = normalize_color(value.get(key))
        if color is not None:
            normalized[key] = color
    return normalized


def normalize_font_bold_mode(value: object) -> str:
    text = str(value or "").strip().casefold()
    if text in FONT_BOLD_MODES:
        return text
    return FONT_BOLD_NONE


def peek_ui_settings(raw: dict[str, Any] | None) -> UiSettings:
    """Načte blok ``ui``; config z v11 zůstává čitelný beze změny."""
    source = raw if isinstance(raw, dict) else {}
    block = source.get("ui")
    if not isinstance(block, dict):
        block = {}
    # Starší konfigurace znají jen NiceGUI klíč ui_barevne_schema.
    theme_value = block.get("theme", source.get("ui_barevne_schema"))
    scale_value = block.get("ui_scale")
    if scale_value is None:
        legacy = _scale_from_legacy_density(
            block.get("density", source.get("ui_hustota_poli"))
        )
        scale_value = legacy if legacy is not None else DEFAULT_UI_SCALE
    legacy_bold = block.get("font_bold") is True
    mode_value = block.get("font_bold_mode")
    if mode_value is None and legacy_bold:
        mode_value = FONT_BOLD_BOTH
    return UiSettings(
        theme=normalize_theme(theme_value),
        ui_scale=normalize_scale(scale_value),
        font_bold_mode=normalize_font_bold_mode(mode_value),
        custom_palette_enabled=block.get("custom_palette_enabled") is True,
        custom_palette=normalize_custom_palette(block.get("custom_palette")),
        window_width=_positive_int(
            block.get("window_width"), DEFAULT_WINDOW_WIDTH, MIN_WINDOW_WIDTH
        ),
        window_height=_positive_int(
            block.get("window_height"), DEFAULT_WINDOW_HEIGHT, MIN_WINDOW_HEIGHT
        ),
        window_x=_optional_int(block.get("window_x")),
        window_y=_optional_int(block.get("window_y")),
        maximized=block.get("maximized") is True,
    )


def apply_ui_settings(
    raw: dict[str, Any], settings: UiSettings
) -> dict[str, Any]:
    """Zapíše blok ``ui`` a ostatní klíče ponechá nedotčené."""
    updated = dict(raw)
    block = updated.get("ui")
    block = dict(block) if isinstance(block, dict) else {}
    block.update(
        {
            "theme": normalize_theme(settings.theme),
            "ui_scale": normalize_scale(settings.ui_scale),
            "font_bold_mode": normalize_font_bold_mode(settings.font_bold_mode),
            "font_bold": normalize_font_bold_mode(settings.font_bold_mode)
            == FONT_BOLD_BOTH,
            "custom_palette_enabled": bool(settings.custom_palette_enabled),
            "window_width": int(settings.window_width),
            "window_height": int(settings.window_height),
            "maximized": bool(settings.maximized),
        }
    )
    custom = normalize_custom_palette(settings.custom_palette)
    if custom:
        block["custom_palette"] = custom
    else:
        block.pop("custom_palette", None)
    # Hustota polí z v11 už nemá ve v12 význam, zvětšení ji nahradilo.
    block.pop("density", None)
    if settings.window_x is None:
        block.pop("window_x", None)
    else:
        block["window_x"] = int(settings.window_x)
    if settings.window_y is None:
        block.pop("window_y", None)
    else:
        block["window_y"] = int(settings.window_y)
    updated["ui"] = block
    return updated
