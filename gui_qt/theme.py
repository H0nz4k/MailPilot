"""Design tokeny a QSS desktopového rozhraní.

Jediné místo s barvami, rozestupy, velikostmi písma i výškami prvků.
Motiv mění pouze barvy, zvětšení rozhraní pouze rozměry; rozvržení
obrazovek zůstává ve všech kombinacích stejné.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from runtime_paths import bundled_path
from services.ui_settings import (
    DEFAULT_UI_SCALE,
    FONT_BOLD_BOTH,
    FONT_BOLD_HEADINGS,
    FONT_BOLD_TEXT,
    THEME_DARK,
    THEME_LIGHT,
    THEME_SYSTEM,
    normalize_font_bold_mode,
    normalize_scale,
    normalize_theme,
)


UI_FONT_FAMILY = "Segoe UI"

# Hodnoty pro 100 % zvětšení; všechno ostatní z nich vzniká násobením.
BASE_CONTROL_HEIGHT = 30
BASE_NAV_ITEM_HEIGHT = 34
BASE_HEADER_HEIGHT = 48
BASE_ROW_HEIGHT = 28
BASE_SMALL_GAP = 4
BASE_NORMAL_GAP = 8
BASE_SECTION_GAP = 16
BASE_MARGIN = 20
BASE_SIDEBAR_WIDTH = 180
BASE_BUTTON_PADDING = 14
BASE_ICON_SIZE = 18
BASE_LABEL_COLUMN = 110
BASE_FORM_WIDTH = 560
BASE_FONT_PT = 10.0
BASE_TITLE_PT = 15.0
BASE_SECTION_PT = 8.5
BASE_HEADING_PT = 11.0


@dataclass(frozen=True)
class UiMetrics:
    """Rozměry v logických pixelech; Qt je dál přepočítá podle DPI.

    Rozestupy drží stupnici 4 / 8 / 16 / 20 px vynásobenou zvětšením,
    aby se v rozhraní neobjevovaly nahodilé hodnoty.
    """

    scale: float
    control_height: int
    nav_item_height: int
    header_height: int
    row_height: int
    small_gap: int
    normal_gap: int
    section_gap: int
    margin: int
    sidebar_width: int
    border_radius: int
    button_padding: int
    icon_size: int
    label_column: int
    form_width: int
    font_pt: float
    title_pt: float
    heading_pt: float
    section_pt: float

    def px(self, value: float) -> int:
        """Libovolný rozměr přepočítaný stejným zvětšením jako zbytek UI."""
        return max(1, round(value * self.scale))

    def field_width(self, value: float) -> int:
        return self.px(value)


def metrics_for(scale: object = DEFAULT_UI_SCALE) -> UiMetrics:
    """Kompletní sada rozměrů pro zvolené zvětšení rozhraní."""
    factor = normalize_scale(scale)

    def size(value: float) -> int:
        return max(1, round(value * factor))

    return UiMetrics(
        scale=factor,
        control_height=size(BASE_CONTROL_HEIGHT),
        nav_item_height=size(BASE_NAV_ITEM_HEIGHT),
        header_height=size(BASE_HEADER_HEIGHT),
        row_height=size(BASE_ROW_HEIGHT),
        small_gap=size(BASE_SMALL_GAP),
        normal_gap=size(BASE_NORMAL_GAP),
        section_gap=size(BASE_SECTION_GAP),
        margin=size(BASE_MARGIN),
        sidebar_width=size(BASE_SIDEBAR_WIDTH),
        border_radius=max(3, size(4)),
        button_padding=size(BASE_BUTTON_PADDING),
        icon_size=size(BASE_ICON_SIZE),
        label_column=size(BASE_LABEL_COLUMN),
        form_width=size(BASE_FORM_WIDTH),
        font_pt=round(BASE_FONT_PT * factor, 1),
        title_pt=round(BASE_TITLE_PT * factor, 1),
        heading_pt=round(BASE_HEADING_PT * factor, 1),
        section_pt=round(BASE_SECTION_PT * factor, 1),
    )


@dataclass(frozen=True)
class Palette:
    """Barevné role rozhraní; obě témata plní stejnou sadu."""

    window: str
    base: str
    alt_base: str
    sidebar: str
    header: str
    status_bar: str
    text: str
    muted: str
    disabled: str
    border: str
    strong_border: str
    accent: str
    accent_hover: str
    accent_text: str
    accent_soft: str
    selection: str
    selection_text: str
    hover: str
    ok: str
    error: str
    warning: str


PALETTES = {
    THEME_LIGHT: Palette(
        window="#f4f6f9",
        base="#ffffff",
        alt_base="#f7f9fb",
        sidebar="#eef1f5",
        header="#ffffff",
        status_bar="#eef1f5",
        text="#1b1f24",
        muted="#5c6672",
        disabled="#9aa2ac",
        border="#d3d9e0",
        strong_border="#b6bec8",
        accent="#1160a8",
        accent_hover="#0d4f8c",
        accent_text="#ffffff",
        accent_soft="#e2edf8",
        selection="#d5e6f6",
        selection_text="#123252",
        hover="#e7ebf0",
        ok="#1f7a45",
        error="#b3261e",
        warning="#9a5b0a",
    ),
    THEME_DARK: Palette(
        window="#1e2126",
        base="#2a2f35",
        alt_base="#30363d",
        sidebar="#181b1f",
        header="#2a2f35",
        status_bar="#181b1f",
        text="#e8ebee",
        muted="#a4aeb8",
        disabled="#727b84",
        border="#3b4147",
        strong_border="#525a62",
        accent="#4a9eea",
        accent_hover="#65b0f2",
        accent_text="#0d1b28",
        accent_soft="#24384c",
        selection="#2d4459",
        selection_text="#eaf3fb",
        hover="#333941",
        ok="#5fc287",
        error="#f0837a",
        warning="#dda54f",
    ),
}


def system_prefers_dark() -> bool:
    """Zjistí motiv Windows; při nejistotě zůstává u světlého."""
    application = QGuiApplication.instance()
    hints = application.styleHints() if application is not None else None
    scheme = getattr(hints, "colorScheme", None)
    if scheme is not None:
        try:
            return scheme() == Qt.ColorScheme.Dark
        except (AttributeError, TypeError):  # pragma: no cover - starší Qt
            pass
    try:  # pragma: no cover - závisí na systému
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        with key:
            value, _type = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return int(value) == 0
    except (ImportError, OSError, ValueError):
        return False


def resolve_theme(theme: object) -> str:
    """Přeloží volbu uživatele na konkrétní světlé nebo tmavé téma."""
    value = normalize_theme(theme)
    if value == THEME_SYSTEM:
        return THEME_DARK if system_prefers_dark() else THEME_LIGHT
    return value


def _mix(first: str, second: str, ratio: float) -> str:
    left = QColor(first)
    right = QColor(second)
    keep = min(1.0, max(0.0, ratio))
    take = 1.0 - keep
    red = round(left.red() * keep + right.red() * take)
    green = round(left.green() * keep + right.green() * take)
    blue = round(left.blue() * keep + right.blue() * take)
    return QColor(red, green, blue).name(QColor.HexRgb).upper()


def palette_for(
    theme: object,
    custom_palette_enabled: bool = False,
    custom_palette: Mapping[str, str] | None = None,
) -> Palette:
    resolved = resolve_theme(theme)
    base = PALETTES[resolved]
    if not custom_palette_enabled:
        return base
    custom = {
        str(key): str(value)
        for key, value in (custom_palette or {}).items()
        if str(value).startswith("#")
    }
    if not custom:
        return base
    colors = replace(
        base,
        window=custom.get("window", base.window),
        base=custom.get("base", base.base),
        sidebar=custom.get("sidebar", base.sidebar),
        header=custom.get("header", base.header),
        text=custom.get("text", base.text),
        accent=custom.get("accent", base.accent),
    )
    accent = colors.accent
    soft = _mix(accent, colors.base, 0.2)
    selection = _mix(accent, colors.base, 0.35)
    hover = _mix(colors.base, colors.window, 0.7)
    return replace(
        colors,
        accent_hover=_mix(accent, "#FFFFFF" if resolved == THEME_DARK else "#000000", 0.85),
        accent_soft=soft,
        selection=selection,
        selection_text=colors.text,
        hover=hover,
        border=_mix(colors.base, colors.text, 0.88),
        strong_border=_mix(colors.base, colors.text, 0.8),
        status_bar=colors.sidebar,
        muted=_mix(colors.text, colors.base, 0.45),
        disabled=_mix(colors.text, colors.base, 0.65),
    )


def check_icon_path() -> str:
    """Fajfka zaškrtávátka; bílá pro obě témata, kreslí se na akcent."""
    return bundled_path("assets", "ui", "check.svg").as_posix()


def build_stylesheet(
    palette: Palette, metrics: UiMetrics, font_bold_mode: str = "none"
) -> str:
    """QSS nad stylem Fusion; hodnoty pocházejí výhradně z tokenů."""
    mode = normalize_font_bold_mode(font_bold_mode)
    heading_bold = mode in {FONT_BOLD_HEADINGS, FONT_BOLD_BOTH}
    heading_weight = 700 if heading_bold else 600
    section_weight = 800 if heading_bold else 700
    primary_button_weight = 700 if heading_bold else 600
    control = metrics.control_height
    radius = metrics.border_radius
    input_radius = max(3, radius - 1)
    indicator = metrics.px(15)
    pad_v = metrics.px(2)
    pad_h = metrics.px(7)
    check_icon = check_icon_path()
    # Import až tady, jinak by vznikl cyklus theme ↔ icons.
    from gui_qt.icons import CHEVRON_DOWN, stylesheet_icon_path

    arrow_size = metrics.px(11)
    arrow_icon = stylesheet_icon_path(CHEVRON_DOWN, palette.muted, arrow_size)
    arrow_icon_disabled = stylesheet_icon_path(
        CHEVRON_DOWN, palette.disabled, arrow_size
    )
    return f"""
QWidget {{
    color: {palette.text};
    font-size: {metrics.font_pt}pt;
}}
QMainWindow, QDialog, QWidget#PageBody {{
    background: {palette.window};
}}

/* ---------- hlavička ---------- */
QFrame#HeaderBar {{
    background: {palette.header};
    border-bottom: 1px solid {palette.border};
}}
QLabel#HeaderTitle {{
    font-size: {metrics.heading_pt}pt;
    font-weight: {heading_weight};
}}
QPushButton#HeaderHomeButton,
QPushButton#HeaderAdminButton {{
    min-height: {control - metrics.px(8)}px;
    font-weight: {heading_weight};
    border-radius: {radius}px;
}}
QPushButton#HeaderHomeButton {{
    background: transparent;
    border-color: {palette.strong_border};
}}
QPushButton#HeaderAdminButton[adminState="locked"] {{
    background: transparent;
    border-color: {palette.strong_border};
    color: {palette.text};
}}
QPushButton#HeaderAdminButton[adminState="unlocked"] {{
    background: {palette.error};
    border-color: {palette.error};
    color: {palette.accent_text};
    font-weight: 700;
}}
QPushButton#HeaderAdminButton[adminState="unlocked"]:hover {{
    background: {_mix(palette.error, '#000000', 0.8)};
    border-color: {_mix(palette.error, '#000000', 0.8)};
}}
QLabel#HeaderSubject {{
    font-weight: {heading_weight};
}}
QLabel#HeaderMeta {{
    color: {palette.muted};
}}
QFrame#HeaderDivider {{
    background: {palette.border};
    max-width: 1px;
}}
QFrame#HeaderStatusGroup {{
    background: {palette.base};
    border: 1px solid {palette.border};
    border-radius: {radius}px;
}}
QFrame#HeaderStatusGroup[stateRole="statusOk"] {{
    border: 1px solid {palette.ok};
}}
QFrame#HeaderStatusGroup[stateRole="statusError"] {{
    border: 1px solid {palette.error};
}}
QFrame#HeaderStatusGroup[stateRole="statusIdle"] {{
    border: 1px solid {palette.strong_border};
}}
QFrame#StatusDot {{
    background: {palette.muted};
    border-radius: {metrics.px(5)}px;
}}
QFrame#StatusDot[role="statusOk"] {{
    background: {palette.ok};
}}
QFrame#StatusDot[role="statusError"] {{
    background: {palette.error};
}}
QFrame#StatusDot[role="statusWarning"] {{
    background: {palette.warning};
}}
QLabel[role="statusOk"] {{
    color: {palette.ok};
}}
QLabel[role="statusError"] {{
    color: {palette.error};
}}
QLabel[role="statusIdle"] {{
    color: {palette.muted};
}}
QLabel#HeaderState,
QLabel#HeaderSubject,
QLabel#HeaderMeta {{
    font-weight: {heading_weight};
}}
QLabel#HeaderMeta {{
    color: {palette.text};
}}

/* ---------- typografie ---------- */
QLabel#PageTitle {{
    font-size: {metrics.title_pt}pt;
    font-weight: {heading_weight};
}}
QLabel#SectionLabel {{
    color: {palette.muted};
    font-size: {metrics.section_pt}pt;
    font-weight: {section_weight};
}}
QLabel#SectionTitle {{
    font-size: {metrics.heading_pt}pt;
    font-weight: {heading_weight};
}}
QLabel#EmptyStateTitle {{
    color: {palette.text};
    font-size: {metrics.heading_pt}pt;
    font-weight: {heading_weight};
}}
QLabel#EmptyStateHint {{
    color: {palette.muted};
}}
QLabel[role="hint"] {{
    color: {palette.muted};
}}
QLabel[role="error"] {{
    color: {palette.error};
}}
QLabel[role="fieldLabel"] {{
    color: {palette.text};
}}
QFrame[role="separator"] {{
    background: {palette.border};
    max-height: 1px;
    border: none;
}}

/* ---------- navigace ---------- */
QListWidget#NavSidebar {{
    background: {palette.sidebar};
    border: none;
    border-right: 1px solid {palette.border};
    outline: 0;
    padding-top: {metrics.normal_gap}px;
}}
QListWidget#NavSidebar::item {{
    min-height: {metrics.nav_item_height}px;
    padding-left: {metrics.normal_gap}px;
    border-left: {metrics.px(3)}px solid transparent;
    color: {palette.text};
}}
QListWidget#NavSidebar::item:hover {{
    background: {palette.hover};
}}
QListWidget#NavSidebar::item:selected {{
    background: {palette.accent_soft};
    border-left: {metrics.px(3)}px solid {palette.accent};
    color: {palette.text};
    font-weight: 600;
}}
QListWidget#NavSidebar::item:disabled {{
    background: transparent;
    border-left: {metrics.px(3)}px solid transparent;
}}

/* ---------- lokální navigace v obsahu ---------- */
QWidget#SegmentedBar {{
    background: transparent;
}}
QPushButton[segment="true"] {{
    background: transparent;
    border: none;
    border-bottom: {metrics.px(2)}px solid transparent;
    border-radius: 0px;
    color: {palette.muted};
    padding: {metrics.px(4)}px {metrics.px(10)}px;
    min-height: {control}px;
}}
QPushButton[segment="true"]:hover {{
    color: {palette.text};
    background: {palette.hover};
}}
QPushButton[segment="true"]:focus {{
    border-bottom-color: {palette.strong_border};
}}
QPushButton[segment="true"][active="true"] {{
    color: {palette.accent};
    border-bottom: {metrics.px(2)}px solid {palette.accent};
    font-weight: 600;
}}

/* ---------- vstupní prvky ---------- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit, QPlainTextEdit,
QTextEdit {{
    background: {palette.base};
    border: 1px solid {palette.border};
    border-radius: {input_radius}px;
    padding: {pad_v}px {pad_h}px;
    selection-background-color: {palette.accent};
    selection-color: {palette.accent_text};
}}
QComboBox {{
    combobox-popup: 1;
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit {{
    min-height: {control - metrics.px(8)}px;
}}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover,
QDateEdit:hover {{
    border-color: {palette.strong_border};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
QDateEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: {metrics.px(2)}px solid {palette.accent};
    padding: {max(0, pad_v - 1)}px {max(1, pad_h - 1)}px;
}}
QLineEdit[invalid="true"] {{
    border-color: {palette.error};
    background: {_mix(palette.error, palette.base, 0.1)};
}}
QLineEdit[invalid="true"]:focus {{
    border: {metrics.px(2)}px solid {palette.error};
    padding: {max(0, pad_v - 1)}px {max(1, pad_h - 1)}px;
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
QComboBox:disabled, QDateEdit:disabled {{
    background: {palette.alt_base};
    color: {palette.disabled};
}}
QComboBox::drop-down, QDateEdit::drop-down {{
    width: {metrics.px(18)}px;
    border: none;
}}
QComboBox::down-arrow, QDateEdit::down-arrow {{
    image: url("{arrow_icon}");
    width: {arrow_size}px;
    height: {arrow_size}px;
}}
QComboBox::down-arrow:disabled, QDateEdit::down-arrow:disabled {{
    image: url("{arrow_icon_disabled}");
}}
QComboBox QAbstractItemView {{
    background: {palette.base};
    border: 1px solid {palette.border};
    selection-background-color: {palette.selection};
    selection-color: {palette.selection_text};
    outline: 0;
}}
QComboBox QAbstractItemView::item {{
    min-height: {control - metrics.px(8)}px;
    padding: {pad_v}px {pad_h}px;
}}
QCalendarWidget QWidget {{
    alternate-background-color: {palette.alt_base};
}}
QCalendarWidget QToolButton {{
    min-height: {metrics.px(24)}px;
    padding: {metrics.px(2)}px {metrics.px(6)}px;
    border: 1px solid transparent;
}}
QCalendarWidget QToolButton:hover {{
    background: {palette.hover};
    border-color: {palette.border};
}}
QCalendarWidget QMenu {{
    background: {palette.base};
    border: 1px solid {palette.border};
}}
QCalendarWidget QSpinBox {{
    min-height: {metrics.px(22)}px;
}}
QCalendarWidget QTableView {{
    border: 1px solid {palette.border};
    background: {palette.base};
    alternate-background-color: {palette.alt_base};
    selection-background-color: {palette.selection};
    selection-color: {palette.selection_text};
}}
QCalendarWidget QTableView::item {{
    padding: {metrics.px(1)}px;
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: {metrics.px(16)}px;
}}

/* ---------- tlačítka ---------- */
QPushButton {{
    background: {palette.base};
    border: 1px solid {palette.strong_border};
    border-radius: {radius}px;
    padding: {pad_v}px {metrics.button_padding}px;
    min-height: {control - metrics.px(8)}px;
}}
QPushButton:hover {{
    background: {palette.hover};
}}
QPushButton:pressed {{
    background: {palette.selection};
}}
QPushButton:focus {{
    border: {metrics.px(2)}px solid {palette.accent};
}}
QPushButton:disabled {{
    color: {palette.disabled};
    background: {palette.base};
    border-color: {palette.border};
}}
QPushButton[emphasis="primary"] {{
    background: {palette.accent};
    border-color: {palette.accent};
    color: {palette.accent_text};
    font-weight: {primary_button_weight};
}}
QPushButton[emphasis="primary"]:hover {{
    background: {palette.accent_hover};
    border-color: {palette.accent_hover};
}}
QPushButton[emphasis="primary"]:disabled {{
    background: {palette.alt_base};
    border-color: {palette.border};
    color: {palette.disabled};
}}
QPushButton[emphasis="ghost"] {{
    background: transparent;
    border: 1px solid transparent;
    color: {palette.muted};
}}
QPushButton[emphasis="ghost"]:hover {{
    background: {palette.hover};
    color: {palette.text};
}}
QPushButton[emphasis="ghost"]:focus {{
    border: {metrics.px(2)}px solid {palette.accent};
}}
QPushButton[emphasis="ghost"]:disabled {{
    background: transparent;
    border-color: transparent;
    color: {palette.disabled};
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {radius}px;
    padding: {pad_v}px {pad_h}px;
    min-height: {control - metrics.px(10)}px;
}}
QToolButton:hover {{
    background: {palette.hover};
}}
QToolButton:focus {{
    border-color: {palette.accent};
}}
QToolButton#SectionToggle {{
    color: {palette.text};
    padding-left: {metrics.px(2)}px;
    font-weight: 600;
}}
QToolButton#SectionToggle:hover {{
    background: transparent;
    color: {palette.accent};
}}

/* ---------- volby ---------- */
QCheckBox, QRadioButton {{
    spacing: {metrics.px(7)}px;
    min-height: {control - metrics.px(8)}px;
}}
QCheckBox:disabled, QRadioButton:disabled {{
    color: {palette.disabled};
}}
QCheckBox::indicator, QRadioButton::indicator, QListWidget::indicator {{
    width: {indicator}px;
    height: {indicator}px;
    background: {palette.base};
    border: 1px solid {palette.strong_border};
    border-radius: {max(2, metrics.px(3))}px;
}}
QRadioButton::indicator {{
    border-radius: {max(3, indicator // 2 + 1)}px;
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover,
QListWidget::indicator:hover {{
    border-color: {palette.accent};
}}
QCheckBox::indicator:focus, QRadioButton::indicator:focus {{
    border-color: {palette.accent};
}}
QCheckBox::indicator:checked, QListWidget::indicator:checked {{
    background: {palette.accent};
    border-color: {palette.accent};
    image: url("{check_icon}");
}}
QRadioButton::indicator:checked {{
    border-color: {palette.accent};
    background: qradialgradient(cx: 0.5, cy: 0.5, radius: 0.5, fx: 0.5, fy: 0.5,
        stop: 0 {palette.accent}, stop: 0.45 {palette.accent},
        stop: 0.5 {palette.base}, stop: 1 {palette.base});
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled,
QListWidget::indicator:disabled {{
    background: {palette.alt_base};
    border-color: {palette.border};
}}
QCheckBox::indicator:checked:disabled, QListWidget::indicator:checked:disabled {{
    background: {palette.disabled};
    border-color: {palette.disabled};
}}

/* ---------- tabulky a seznamy ---------- */
QTableView {{
    background: {palette.base};
    alternate-background-color: {palette.alt_base};
    border: 1px solid {palette.border};
    border-radius: {input_radius}px;
    selection-background-color: {palette.selection};
    selection-color: {palette.selection_text};
}}
QTableView::item {{
    padding: 0px {pad_h}px;
    border: none;
}}
QHeaderView::section {{
    background: {palette.base};
    color: {palette.muted};
    border: none;
    border-bottom: 1px solid {palette.border};
    padding: {metrics.px(4)}px {pad_h}px;
    font-weight: 600;
}}
QHeaderView::section:first {{
    padding-left: {metrics.px(9)}px;
}}
QListWidget {{
    background: {palette.base};
    border: 1px solid {palette.border};
    border-radius: {input_radius}px;
    outline: 0;
}}
QListWidget::item {{
    padding: {metrics.px(3)}px {metrics.px(5)}px;
    min-height: {metrics.px(20)}px;
}}
QListWidget::item:selected {{
    background: {palette.selection};
    color: {palette.selection_text};
}}
QProgressBar {{
    background: {palette.alt_base};
    border: 1px solid {palette.border};
    border-radius: {input_radius}px;
    height: {metrics.px(10)}px;
    text-align: center;
    color: {palette.muted};
}}
QProgressBar::chunk {{
    background: {palette.accent};
    border-radius: {max(2, input_radius - 1)}px;
}}

/* ---------- nabídka, stavový řádek, doplňky ---------- */
QMenuBar {{
    background: {palette.header};
    color: {palette.text};
    padding: {metrics.px(2)}px {metrics.px(4)}px;
}}
QMenuBar::item {{
    padding: {metrics.px(4)}px {metrics.px(10)}px;
    border-radius: {input_radius}px;
    background: transparent;
}}
QMenuBar::item:selected {{
    background: {palette.hover};
}}
QStatusBar {{
    background: {palette.status_bar};
    border-top: 1px solid {palette.border};
    color: {palette.muted};
}}
QStatusBar::item {{
    border: none;
}}
QStatusBar QLabel {{
    color: {palette.muted};
}}
QScrollBar:vertical {{
    background: transparent;
    width: {metrics.px(12)}px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: {palette.strong_border};
    border-radius: {metrics.px(3)}px;
    min-height: {metrics.px(28)}px;
    margin: {metrics.px(2)}px;
}}
QScrollBar::handle:vertical:hover {{
    background: {palette.muted};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: {metrics.px(12)}px;
    margin: 0px;
}}
QScrollBar::handle:horizontal {{
    background: {palette.strong_border};
    border-radius: {metrics.px(3)}px;
    min-width: {metrics.px(28)}px;
    margin: {metrics.px(2)}px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0px;
    height: 0px;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}
QMenu {{
    background: {palette.base};
    border: 1px solid {palette.border};
    padding: {metrics.px(4)}px;
}}
QMenu::item {{
    padding: {metrics.px(5)}px {metrics.px(22)}px {metrics.px(5)}px {metrics.px(12)}px;
    border-radius: {input_radius}px;
}}
QMenu::item:selected {{
    background: {palette.accent_soft};
}}
QMenu::separator {{
    height: 1px;
    background: {palette.border};
    margin: {metrics.px(4)}px {metrics.px(6)}px;
}}
QToolTip {{
    background: {palette.base};
    color: {palette.text};
    border: 1px solid {palette.border};
    padding: {metrics.px(4)}px {pad_h}px;
}}
"""


def qt_palette(palette: Palette) -> QPalette:
    """QPalette pro standardní widgety a systémové dialogy."""
    result = QPalette()
    window = QColor(palette.window)
    base = QColor(palette.base)
    text = QColor(palette.text)
    result.setColor(QPalette.Window, window)
    result.setColor(QPalette.WindowText, text)
    result.setColor(QPalette.Base, base)
    result.setColor(QPalette.AlternateBase, QColor(palette.alt_base))
    result.setColor(QPalette.Text, text)
    result.setColor(QPalette.Button, window)
    result.setColor(QPalette.ButtonText, text)
    result.setColor(QPalette.ToolTipBase, base)
    result.setColor(QPalette.ToolTipText, text)
    result.setColor(QPalette.Highlight, QColor(palette.accent))
    result.setColor(QPalette.HighlightedText, QColor(palette.accent_text))
    result.setColor(QPalette.Link, QColor(palette.accent))
    result.setColor(QPalette.PlaceholderText, QColor(palette.muted))
    disabled = QColor(palette.disabled)
    for group in (QPalette.Disabled,):
        result.setColor(group, QPalette.WindowText, disabled)
        result.setColor(group, QPalette.Text, disabled)
        result.setColor(group, QPalette.ButtonText, disabled)
    return result


def ui_font() -> QFont:
    """Systémové písmo Windows; jinde padne na výchozí písmo Qt."""
    families = QFontDatabase.families()
    if UI_FONT_FAMILY in families:
        return QFont(UI_FONT_FAMILY)
    return QFontDatabase.systemFont(QFontDatabase.GeneralFont)


def apply_theme(
    application: QApplication,
    theme: str,
    scale: object = DEFAULT_UI_SCALE,
    *,
    font_bold_mode: str = "none",
    custom_palette_enabled: bool = False,
    custom_palette: Mapping[str, str] | None = None,
) -> UiMetrics:
    """Nastaví písmo, paletu i QSS a vrátí použité metriky."""
    mode = normalize_font_bold_mode(font_bold_mode)
    colors = palette_for(
        theme,
        custom_palette_enabled=custom_palette_enabled,
        custom_palette=custom_palette,
    )
    metrics = metrics_for(scale)
    font = ui_font()
    font.setPointSizeF(metrics.font_pt)
    font.setBold(mode in {FONT_BOLD_TEXT, FONT_BOLD_BOTH})
    application.setFont(font)
    application.setPalette(qt_palette(colors))
    application.setStyleSheet(build_stylesheet(colors, metrics, mode))
    return metrics
