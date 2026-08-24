"""Administrace → PDF: vzhled a cíl výstupu společný všem sestavám."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gui_qt.theme import UiMetrics
from gui_qt.widgets.common import (
    field_label,
    hint,
    page_body,
    scroll_area,
    secondary_button,
    section_label,
    size_choice,
    size_input,
)
from services.daily import ORIENTATION_LABELS, ORIENTATIONS
from services.pdf_settings import PdfSettings


LANGUAGE_SUGGESTIONS = ("česky", "anglicky")


class PdfPage(QWidget):
    """Stejné klíče jako Pokročilé nastavení PDF na Denním stavu."""

    settings_changed = Signal()

    def __init__(self, metrics: UiMetrics, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._metrics = metrics
        self._loading = False

        content, layout = page_body(metrics, "PDF", max_width=980)

        layout.addWidget(section_label("Vzhled"))
        layout.addLayout(self._build_appearance())

        layout.addWidget(section_label("Obsah"))
        layout.addLayout(self._build_content())

        layout.addWidget(section_label("Výstup"))
        layout.addLayout(self._build_output())

        layout.addStretch(1)
        layout.addWidget(
            hint(
                "Stejné hodnoty najdete i na obrazovce Denní stav v sekci "
                "Pokročilé nastavení PDF; obě místa píší do jednoho nastavení."
            )
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(scroll_area(content, self, metrics))

    # ------------------------------------------------------------------
    # Stavba rozvržení
    # ------------------------------------------------------------------
    def _grid(self) -> QGridLayout:
        metrics = self._metrics
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(metrics.normal_gap)
        grid.setVerticalSpacing(metrics.small_gap)
        grid.setColumnMinimumWidth(0, metrics.label_column)
        return grid

    def _build_appearance(self) -> QGridLayout:
        grid = self._grid()
        self._orientation = QComboBox()
        for key in ORIENTATIONS:
            self._orientation.addItem(ORIENTATION_LABELS[key], key)
        size_choice(self._orientation, self._metrics, 130)
        self._orientation.currentIndexChanged.connect(self._emit_change)

        self._data_size = self._font_spin()
        self._label_size = self._font_spin()
        self._bold = self._check("Tučná data")

        grid.addWidget(field_label("Orientace", self._orientation), 0, 0)
        grid.addWidget(self._orientation, 0, 1)
        grid.addWidget(field_label("Velikost dat", self._data_size), 0, 2)
        grid.addWidget(self._data_size, 0, 3)
        grid.addWidget(field_label("Velikost popisků", self._label_size), 1, 0)
        grid.addWidget(self._label_size, 1, 1)
        grid.addWidget(self._bold, 1, 3)
        grid.setColumnStretch(4, 1)
        return grid

    def _build_content(self) -> QGridLayout:
        grid = self._grid()
        self._language = QComboBox()
        self._language.setEditable(True)
        self._language.addItems(LANGUAGE_SUGGESTIONS)
        size_choice(self._language, self._metrics, 130)
        self._language.currentTextChanged.connect(lambda _value: self._emit_change())

        self._menu_number = QSpinBox()
        self._menu_number.setRange(1, 99)
        size_input(self._menu_number, self._metrics, 84)
        self._menu_number.valueChanged.connect(self._emit_change)

        self._category_separation = self._check("Oddělit dle kategorií")
        self._show_categories = self._check("Souhrn dle kategorií")
        self._show_norms = self._check("Souhrn dle norem")

        grid.addWidget(field_label("Jazyk", self._language), 0, 0)
        grid.addWidget(self._language, 0, 1)
        grid.addWidget(field_label("Jídelníček", self._menu_number), 0, 2)
        grid.addWidget(self._menu_number, 0, 3)
        grid.addWidget(self._category_separation, 1, 1)
        grid.addWidget(self._show_categories, 1, 3)
        grid.addWidget(self._show_norms, 2, 1)
        grid.setColumnStretch(4, 1)
        return grid

    def _build_output(self) -> QGridLayout:
        grid = self._grid()
        self._output = QLineEdit()
        self._output.setMinimumWidth(self._metrics.px(260))
        self._output.setMaximumWidth(self._metrics.px(460))
        self._output.setToolTip("Lze použít zástupné hodnoty {datum} a {datum_cz}.")
        self._output.editingFinished.connect(self._emit_change)
        browse = secondary_button("Procházet…")
        browse.clicked.connect(self._pick_directory)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(self._metrics.small_gap)
        row.addWidget(self._output, 1)
        row.addWidget(browse)
        grid.addWidget(field_label("Výstupní PDF", self._output), 0, 0)
        grid.addLayout(row, 0, 1, 1, 3)
        grid.setColumnStretch(4, 1)
        return grid

    def _font_spin(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(5.0, 18.0)
        spin.setSingleStep(0.1)
        spin.setDecimals(1)
        size_input(spin, self._metrics, 90)
        spin.valueChanged.connect(self._emit_change)
        return spin

    def _check(self, text: str) -> QCheckBox:
        box = QCheckBox(text)
        box.toggled.connect(self._emit_change)
        return box

    # ------------------------------------------------------------------
    # Rozhraní pro controller
    # ------------------------------------------------------------------
    def set_settings(self, settings: PdfSettings) -> None:
        self._loading = True
        self._language.setCurrentText(settings.language)
        index = self._orientation.findData(settings.orientation)
        self._orientation.setCurrentIndex(max(0, index))
        self._menu_number.setValue(settings.menu_list_number)
        self._data_size.setValue(settings.data_font_size)
        self._label_size.setValue(settings.label_font_size)
        self._output.setText(settings.output)
        self._bold.setChecked(settings.bold)
        self._category_separation.setChecked(settings.category_separation)
        self._show_categories.setChecked(settings.show_by_categories)
        self._show_norms.setChecked(settings.show_by_norms)
        self._loading = False

    def settings(self) -> PdfSettings:
        return PdfSettings(
            language=self._language.currentText().strip(),
            menu_list_number=int(self._menu_number.value()),
            output=self._output.text().strip(),
            orientation=str(self._orientation.currentData()),
            data_font_size=float(self._data_size.value()),
            label_font_size=float(self._label_size.value()),
            bold=self._bold.isChecked(),
            category_separation=self._category_separation.isChecked(),
            show_by_categories=self._show_categories.isChecked(),
            show_by_norms=self._show_norms.isChecked(),
        )

    def focus_default(self) -> None:
        self._orientation.setFocus()

    # ------------------------------------------------------------------
    # Interakce
    # ------------------------------------------------------------------
    def _emit_change(self, *_args) -> None:
        if not self._loading:
            self.settings_changed.emit()

    def _pick_directory(self) -> None:
        current = Path(self._output.text().strip() or "vystup/MailPilot.pdf")
        start = current.parent if current.parent.as_posix() else Path(".")
        chosen = QFileDialog.getExistingDirectory(
            self, "Vyberte složku pro PDF", str(start)
        )
        if not chosen:
            return
        self._output.setText(str(Path(chosen) / current.name))
        self._emit_change()
