"""Vzhled a čitelnost: motiv, velikost, tučný font, vlastní barvy."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from gui_qt.theme import UiMetrics
from gui_qt.widgets.common import (
    field_label,
    hint,
    page_body,
    primary_button,
    scroll_area,
    secondary_button,
    section_label,
    section_title,
)
from services.ui_settings import (
    CUSTOM_COLOR_KEYS,
    FONT_BOLD_LABELS,
    FONT_BOLD_MODES,
    THEME_LABELS,
    THEMES,
    normalize_font_bold_mode,
    UI_SCALES,
    normalize_color,
    scale_label,
)


class AppearancePage(QWidget):
    """Motiv mění barvy, zvětšení celé rozhraní; rozvržení zůstává stejné."""

    theme_selected = Signal(str)
    scale_selected = Signal(float)
    bold_mode_selected = Signal(str)
    custom_palette_enabled_toggled = Signal(bool)
    custom_palette_changed = Signal(dict)

    COLOR_LABELS = {
        "window": "Pozadí okna",
        "base": "Pozadí polí",
        "sidebar": "Postranní panel",
        "header": "Horní lišta",
        "accent": "Akcent (hlavní tlačítka)",
        "text": "Barva textu",
    }

    def __init__(
        self,
        metrics: UiMetrics,
        parent: QWidget | None = None,
        *,
        title: str = "Vzhled a čitelnost",
    ) -> None:
        super().__init__(parent)
        self._metrics = metrics
        self._custom_palette: dict[str, str] = {}
        content, layout = page_body(metrics, title, max_width=980)

        self._theme_buttons: dict[str, QRadioButton] = {}
        self._scale_buttons: dict[float, QRadioButton] = {}
        self._color_buttons: dict[str, QPushButton] = {}
        self._bold_mode_buttons: dict[str, QRadioButton] = {}

        layout.addLayout(self._build_theme_group(metrics))
        layout.addLayout(self._build_scale_group(metrics))
        layout.addLayout(self._build_font_group(metrics))
        layout.addLayout(self._build_custom_palette_group(metrics))
        layout.addWidget(self._build_preview(metrics))
        layout.addWidget(
            hint(
                "Změna se projeví okamžitě a uloží se do bloku „ui“ v "
                "config.json. Velikost rozhraní lze měnit i klávesami "
                "Ctrl + a Ctrl −, Ctrl 0 vrátí 100 %."
            )
        )
        layout.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(scroll_area(content, self, metrics))

    # ------------------------------------------------------------------
    # Stavba
    # ------------------------------------------------------------------
    def _build_theme_group(self, metrics: UiMetrics) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(metrics.small_gap)
        box.addWidget(section_label("Motiv"))
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(metrics.section_gap)
        group = QButtonGroup(self)
        group.setExclusive(True)
        for key in THEMES:
            button = QRadioButton(THEME_LABELS[key])
            button.toggled.connect(
                lambda checked, value=key: checked and self.theme_selected.emit(value)
            )
            group.addButton(button)
            row.addWidget(button)
            self._theme_buttons[key] = button
        row.addStretch(1)
        box.addLayout(row)
        box.addWidget(
            hint("Systémový motiv se řídí nastavením Windows (světlý/tmavý).")
        )
        return box

    def _build_font_group(self, metrics: UiMetrics) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(metrics.small_gap)
        box.addWidget(section_label("Písmo"))
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(metrics.section_gap)
        group = QButtonGroup(self)
        group.setExclusive(True)
        for mode in FONT_BOLD_MODES:
            button = QRadioButton(FONT_BOLD_LABELS[mode])
            button.toggled.connect(
                lambda checked, value=mode: checked
                and self.bold_mode_selected.emit(value)
            )
            group.addButton(button)
            row.addWidget(button)
            self._bold_mode_buttons[mode] = button
        row.addStretch(1)
        box.addLayout(row)
        box.addWidget(
            hint(
                "Můžete zvýraznit jen nadpisy, jen běžný text, nebo oboje."
            )
        )
        return box

    def _build_custom_palette_group(self, metrics: UiMetrics) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(metrics.small_gap)
        box.addWidget(section_label("Vlastní barevné schéma"))
        self._custom_enabled = QCheckBox("Zapnout vlastní barvy")
        self._custom_enabled.toggled.connect(
            self.custom_palette_enabled_toggled.emit
        )
        self._custom_enabled.toggled.connect(self._toggle_custom_controls)
        box.addWidget(self._custom_enabled)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(metrics.normal_gap)
        grid.setVerticalSpacing(metrics.small_gap)
        for row, key in enumerate(CUSTOM_COLOR_KEYS):
            button = secondary_button("#—")
            button.clicked.connect(
                lambda _checked=False, role=key: self._pick_color(role)
            )
            grid.addWidget(field_label(self.COLOR_LABELS[key]), row, 0)
            grid.addWidget(button, row, 1)
            self._color_buttons[key] = button
        reset = secondary_button("Obnovit výchozí barvy")
        reset.clicked.connect(self._reset_custom_palette)
        grid.addWidget(reset, len(CUSTOM_COLOR_KEYS), 1)
        box.addLayout(grid)
        box.addWidget(
            hint(
                "Změny se aplikují hned. Při nečitelném výsledku vypněte vlastní "
                "barvy nebo použijte Obnovit výchozí."
            )
        )
        self._toggle_custom_controls(False)
        return box

    def _build_scale_group(self, metrics: UiMetrics) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(metrics.small_gap)
        box.addWidget(section_label("Velikost rozhraní"))
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(metrics.section_gap)
        group = QButtonGroup(self)
        group.setExclusive(True)
        for scale in UI_SCALES:
            button = QRadioButton(scale_label(scale))
            button.setToolTip(
                "Zvětší celé rozhraní: písmo, tlačítka, pole, tabulky i navigaci."
            )
            button.toggled.connect(
                lambda checked, value=scale: checked
                and self.scale_selected.emit(value)
            )
            group.addButton(button)
            row.addWidget(button)
            self._scale_buttons[scale] = button
        row.addStretch(1)
        box.addLayout(row)
        return box

    def _build_preview(self, metrics: UiMetrics) -> QWidget:
        frame = QFrame()
        frame.setFrameShape(QFrame.NoFrame)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(metrics.small_gap)
        layout.addWidget(section_label("Ukázka"))

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(metrics.normal_gap)
        grid.setVerticalSpacing(metrics.small_gap)

        self._sample_title = section_title("AutoReport · ZŠ Kozinova")
        grid.addWidget(self._sample_title, 0, 0, 1, 3)

        sample_input = QLineEdit("vystup/AutoReport_{datum}.pdf")
        sample_input.setMinimumWidth(metrics.px(240))
        sample_input.setMaximumWidth(metrics.px(340))
        grid.addWidget(field_label("Ukázka pole", sample_input), 1, 0)
        grid.addWidget(sample_input, 1, 1)

        sample_check = QCheckBox("Odesílat pouze ve varné dny")
        sample_check.setChecked(True)
        grid.addWidget(sample_check, 2, 1)

        buttons = QHBoxLayout()
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(metrics.normal_gap)
        buttons.addWidget(secondary_button("Vytvořit PDF"))
        buttons.addWidget(primary_button("Vytvořit PDF a odeslat"))
        buttons.addStretch(1)
        grid.addLayout(buttons, 3, 1, 1, 2)
        grid.setColumnStretch(2, 1)
        layout.addLayout(grid)
        return frame

    # ------------------------------------------------------------------
    # Rozhraní pro controller
    # ------------------------------------------------------------------
    def set_values(
        self,
        theme: str,
        scale: float,
        *,
        font_bold_mode: str = "none",
        custom_palette_enabled: bool = False,
        custom_palette: dict[str, str] | None = None,
    ) -> None:
        for key, button in self._theme_buttons.items():
            button.blockSignals(True)
            button.setChecked(key == theme)
            button.blockSignals(False)
        for value, button in self._scale_buttons.items():
            button.blockSignals(True)
            button.setChecked(abs(value - float(scale)) < 0.001)
            button.blockSignals(False)
        current_mode = normalize_font_bold_mode(font_bold_mode)
        for mode, button in self._bold_mode_buttons.items():
            button.blockSignals(True)
            button.setChecked(mode == current_mode)
            button.blockSignals(False)
        self._custom_palette = dict(custom_palette or {})
        self._custom_enabled.blockSignals(True)
        self._custom_enabled.setChecked(bool(custom_palette_enabled))
        self._custom_enabled.blockSignals(False)
        self._toggle_custom_controls(bool(custom_palette_enabled))
        self._refresh_color_buttons()

    def focus_default(self) -> None:
        for button in self._theme_buttons.values():
            if button.isChecked():
                button.setFocus(Qt.OtherFocusReason)
                return

    def _toggle_custom_controls(self, enabled: bool) -> None:
        for button in self._color_buttons.values():
            button.setEnabled(bool(enabled))

    def _pick_color(self, key: str) -> None:
        initial = QColor(self._custom_palette.get(key, "#000000"))
        picked = QColorDialog.getColor(initial, self, self.COLOR_LABELS[key])
        if not picked.isValid():
            return
        color = picked.name(QColor.HexRgb).upper()
        self._custom_palette[key] = color
        self._refresh_color_buttons()
        self.custom_palette_changed.emit(dict(self._custom_palette))

    def _refresh_color_buttons(self) -> None:
        for key, button in self._color_buttons.items():
            color = normalize_color(self._custom_palette.get(key)) or "#—"
            button.setText(color)
            if color == "#—":
                button.setStyleSheet("")
            else:
                button.setStyleSheet(f"QPushButton {{ background: {color}; }}")

    def _reset_custom_palette(self) -> None:
        self._custom_palette = {}
        self._refresh_color_buttons()
        self.custom_palette_changed.emit({})
