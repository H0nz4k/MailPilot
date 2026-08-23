"""Obrazovka Speciál · Z 17-01: roční výkaz o činnosti zařízení."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gui_qt.dialogs.categories import CategoryDialog
from gui_qt.theme import Palette, UiMetrics
from gui_qt.widgets.common import (
    StatusDot,
    elided_hint,
    field_label,
    ghost_button,
    hint,
    page_body,
    primary_button,
    scroll_area,
    secondary_button,
    section_label,
    separator,
)
from services.config_io import join_picked_directory
from services.special import MAX_YEAR, MIN_YEAR, SpecialForm, category_summary


MODE_ALL = "all"
MODE_SELECTED = "selected"


class SpecialPage(QWidget):
    """Rok, rozsah kategorií, cesta a vytvoření podkladu Z 17-01."""

    settings_changed = Signal()
    run_requested = Signal()
    open_folder_requested = Signal()
    open_file_requested = Signal(Path)

    def __init__(
        self,
        metrics: UiMetrics,
        parent: QWidget | None = None,
        *,
        palette: Palette,
    ) -> None:
        super().__init__(parent)
        self._metrics = metrics
        self._palette = palette
        self._options: tuple[tuple[str, str], ...] = ()
        self._selected: tuple[str, ...] = ()
        self._last_file: Path | None = None

        content, layout = page_body(metrics, "Speciál · Z 17-01", max_width=980)
        layout.addWidget(
            hint(
                "Roční výkaz o činnosti zařízení školního stravování. "
                "Počty strávníků se berou ke stavu k 31. 10. zvoleného roku, "
                "počty jídel za právě skončený školní rok (1. 9. – 31. 8.)."
            )
        )
        layout.addLayout(self._build_form(metrics))
        layout.addLayout(self._build_progress(metrics))
        layout.addStretch(1)

        footer = QWidget(self)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(
            metrics.margin, metrics.normal_gap, metrics.margin, metrics.normal_gap
        )
        footer_layout.setSpacing(metrics.normal_gap)
        footer_layout.addLayout(self._build_footer(metrics))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(scroll_area(content, self, metrics), 1)
        outer.addWidget(separator())
        outer.addWidget(footer)

    # ------------------------------------------------------------------
    # Stavba
    # ------------------------------------------------------------------
    def _build_form(self, metrics: UiMetrics) -> QGridLayout:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(metrics.normal_gap)
        grid.setVerticalSpacing(metrics.small_gap)
        grid.setColumnMinimumWidth(0, metrics.label_column)

        self._year = QSpinBox()
        self._year.setRange(MIN_YEAR, MAX_YEAR)
        self._year.setMinimumWidth(metrics.px(96))
        self._year.valueChanged.connect(self._on_year_changed)
        grid.addWidget(field_label("Rok výkazu", self._year), 0, 0)
        grid.addWidget(self._year, 0, 1)
        self._school_year = hint("")
        grid.addWidget(self._school_year, 0, 2)

        modes = QHBoxLayout()
        modes.setContentsMargins(0, 0, 0, 0)
        modes.setSpacing(metrics.section_gap)
        self._mode_group = QButtonGroup(self)
        self._mode_all = QRadioButton("Všechny kategorie")
        self._mode_selected = QRadioButton("Jen zvolené kategorie")
        for button in (self._mode_all, self._mode_selected):
            self._mode_group.addButton(button)
            modes.addWidget(button)
        modes.addStretch(1)
        self._mode_all.toggled.connect(self._on_mode_changed)
        grid.addWidget(field_label("Kategorie", self._mode_all), 1, 0)
        grid.addLayout(modes, 1, 1, 1, 2)

        selection = QHBoxLayout()
        selection.setContentsMargins(0, 0, 0, 0)
        selection.setSpacing(metrics.normal_gap)
        self._selection_label = QLabel("")
        self._change_categories = secondary_button("Změnit…")
        self._change_categories.clicked.connect(self._open_category_dialog)
        selection.addWidget(self._selection_label)
        selection.addWidget(self._change_categories)
        selection.addStretch(1)
        grid.addLayout(selection, 2, 1, 1, 2)
        grid.addWidget(
            hint(
                "Výběr je nezávislý na kategoriích denní sestavy; ukládá se "
                "do bloku z17 v konfiguraci."
            ),
            3,
            1,
            1,
            2,
        )

        self._output = QLineEdit()
        self._output.setMinimumWidth(metrics.px(260))
        self._output.setMaximumWidth(metrics.px(460))
        self._output.setToolTip("Lze použít zástupnou hodnotu {rok}.")
        self._output.editingFinished.connect(self.settings_changed.emit)
        browse = secondary_button("Procházet…")
        browse.clicked.connect(self._pick_output)
        output_row = QHBoxLayout()
        output_row.setContentsMargins(0, 0, 0, 0)
        output_row.setSpacing(metrics.small_gap)
        output_row.addWidget(self._output, 1)
        output_row.addWidget(browse)
        output_row.addStretch(1)
        grid.addWidget(field_label("Uložit do", self._output), 4, 0)
        grid.addLayout(output_row, 4, 1, 1, 2)

        self._resolved = elided_hint("")
        grid.addWidget(self._resolved, 5, 1, 1, 2)
        grid.setColumnStretch(2, 1)
        return grid

    def _build_progress(self, metrics: UiMetrics) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(metrics.small_gap)
        box.addWidget(section_label("Průběh"))
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setTextVisible(False)
        self._progress.setVisible(False)
        box.addWidget(self._progress)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(metrics.small_gap)
        self._state_dot = StatusDot(self, metrics)
        self._state_label = QLabel("Podklad Z 17-01 zatím nebyl vytvořen.")
        self._state_label.setProperty("role", "hint")
        row.addWidget(self._state_dot)
        row.addWidget(self._state_label, 1)
        box.addLayout(row)
        return box

    def _build_footer(self, metrics: UiMetrics) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(metrics.normal_gap)
        self._last_label = elided_hint("Poslední PDF: —")
        footer.addWidget(self._last_label, 1)

        self._open_folder = ghost_button("Otevřít složku")
        self._open_folder.clicked.connect(self.open_folder_requested.emit)
        self._open_last = secondary_button("Otevřít poslední PDF")
        self._open_last.setEnabled(False)
        self._open_last.clicked.connect(self._emit_open_last)
        self._run = primary_button("Vytvořit podklad")
        self._run.clicked.connect(self.run_requested.emit)
        footer.addWidget(self._open_folder)
        footer.addWidget(self._open_last)
        footer.addWidget(self._run)
        return footer

    # ------------------------------------------------------------------
    # Rozhraní pro controller
    # ------------------------------------------------------------------
    def set_form(self, form: SpecialForm) -> None:
        widgets = (self._year, self._output, self._mode_all, self._mode_selected)
        for widget in widgets:
            widget.blockSignals(True)
        self._year.setValue(int(form.year))
        self._output.setText(form.output)
        self._mode_all.setChecked(form.use_all_categories)
        self._mode_selected.setChecked(not form.use_all_categories)
        for widget in widgets:
            widget.blockSignals(False)
        self._selected = tuple(form.categories)
        self._refresh_selection()
        self._refresh_school_year()

    def form(self) -> SpecialForm:
        return SpecialForm(
            year=int(self._year.value()),
            output=self._output.text().strip(),
            use_all_categories=self._mode_all.isChecked(),
            categories=tuple(self._selected),
        )

    def set_category_options(self, options: Sequence[tuple[str, str]]) -> None:
        self._options = tuple(options)
        self._refresh_selection()

    def set_resolved_output(self, text: str) -> None:
        self._resolved.setText(text)
        self._resolved.setToolTip(text)

    def set_progress(self, percent: int, message: str) -> None:
        self._progress.setVisible(True)
        self._progress.setValue(max(0, min(100, int(percent))))
        self._state_label.setText(message)
        self._state_dot.set_state("")

    def set_result(self, message: str, *, state: str = "statusOk") -> None:
        self._progress.setVisible(False)
        self._progress.setValue(0)
        self._state_label.setText(message)
        self._state_label.setToolTip(message)
        self._state_dot.set_state(state)

    def last_output(self) -> Path | None:
        return self._last_file

    def set_last_pdf(self, path: Path | None) -> None:
        self._last_file = path
        if path is None:
            self._last_label.setText("Poslední PDF: —")
            self._last_label.setToolTip("")
            self._open_last.setEnabled(False)
            return
        self._last_label.setText(f"Poslední PDF: {path.name}")
        self._last_label.setToolTip(str(path))
        self._open_last.setEnabled(path.is_file())

    def set_busy(self, busy: bool) -> None:
        self._run.setEnabled(not busy)
        self._run.setText("Pracuji…" if busy else "Vytvořit podklad")

    def set_run_enabled(self, enabled: bool, reason: str = "") -> None:
        self._run.setEnabled(enabled)
        self._run.setToolTip(reason or "Vytvoří PDF podkladu Z 17-01")

    def focus_default(self) -> None:
        self._year.setFocus(Qt.OtherFocusReason)

    # ------------------------------------------------------------------
    # Interakce
    # ------------------------------------------------------------------
    def _emit_open_last(self) -> None:
        if self._last_file is not None:
            self.open_file_requested.emit(self._last_file)

    def _on_year_changed(self, _value: int) -> None:
        self._refresh_school_year()
        self.settings_changed.emit()

    def _on_mode_changed(self, _checked: bool) -> None:
        self._refresh_selection()
        self.settings_changed.emit()

    def _refresh_school_year(self) -> None:
        form = self.form()
        self._school_year.setText(
            f"stav k {form.snapshot_label} · školní rok {form.school_year_label}"
        )

    def _refresh_selection(self) -> None:
        use_all = self._mode_all.isChecked()
        total = len(self._options)
        self._selection_label.setText(
            category_summary(use_all=use_all, selected=self._selected, total=total)
        )
        self._selection_label.setToolTip(
            ", ".join(self._selected) if self._selected else ""
        )
        self._change_categories.setEnabled(not use_all)
        self._selection_label.setEnabled(not use_all)

    def _open_category_dialog(self) -> None:
        options = self._options or tuple((code, "") for code in self._selected)
        dialog = CategoryDialog(
            options,
            self._selected,
            self._metrics,
            self,
            title="Kategorie pro Z 17-01",
        )
        if dialog.exec() != CategoryDialog.Accepted:
            return
        self._selected = dialog.selected_codes()
        self._refresh_selection()
        self.settings_changed.emit()

    def _pick_output(self) -> None:
        current = self._output.text().strip()
        chosen = QFileDialog.getExistingDirectory(
            self, "Vyberte složku pro podklad Z 17-01", current or "."
        )
        if not chosen:
            return
        self._output.setText(join_picked_directory(current, chosen))
        self.settings_changed.emit()
