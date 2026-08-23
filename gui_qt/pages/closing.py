"""Obrazovka Uzávěrka: měsíční sestavy, ZIP a odeslání."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gui_qt.theme import Palette, UiMetrics
from gui_qt.widgets.collapsible import CollapsibleSection
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
from services.closing import (
    ARCH_LABELS,
    MONTH_NAMES,
    RECAP_LABELS,
    REPORT_HINTS,
    REPORT_LABELS,
    ClosingForm,
)
from uzaverka_nastaveni import ARCH_VARIANTS, REKAPITULACE_VARIANTS, SUPPORTED_REPORTS


class ClosingPage(QWidget):
    """Pohled bez business logiky; běh spouští controller."""

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
        self._recipients: tuple[str, ...] = ()
        self._last_file: Path | None = None

        content, layout = page_body(metrics, "Uzávěrka", max_width=980)
        layout.addLayout(self._build_period(metrics))
        layout.addLayout(self._build_reports(metrics))
        layout.addLayout(self._build_output(metrics))
        layout.addWidget(self._build_advanced(metrics))
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
    def _build_period(self, metrics: UiMetrics) -> QGridLayout:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(metrics.normal_gap)
        grid.setVerticalSpacing(metrics.small_gap)
        grid.setColumnMinimumWidth(0, metrics.label_column)

        self._month = QComboBox()
        for index, name in enumerate(MONTH_NAMES, start=1):
            self._month.addItem(name, index)
        self._month.setMinimumWidth(metrics.px(130))
        self._month.currentIndexChanged.connect(
            lambda _value: self._on_period_changed()
        )

        self._year = QSpinBox()
        self._year.setRange(2000, 2100)
        self._year.setMinimumWidth(metrics.px(84))
        self._year.valueChanged.connect(lambda _value: self._on_period_changed())

        period_row = QHBoxLayout()
        period_row.setContentsMargins(0, 0, 0, 0)
        period_row.setSpacing(metrics.small_gap)
        period_row.addWidget(self._month)
        period_row.addWidget(self._year)
        period_row.addStretch(1)

        self._current_period = QCheckBox("Použít aktuální měsíc z Jídelny")
        self._current_period.setToolTip(
            "Období se načte z databáze (parametry TentoMesic a TentoRok) "
            "stejně jako u příkazu --zaverka_am."
        )
        self._current_period.toggled.connect(self._on_current_toggled)

        grid.addWidget(field_label("Období", self._month), 0, 0)
        grid.addLayout(period_row, 0, 1)
        grid.addWidget(self._current_period, 1, 1)
        grid.setColumnStretch(2, 1)
        return grid

    def _build_reports(self, metrics: UiMetrics) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(metrics.small_gap)
        box.addWidget(section_label("Sestavy"))
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(metrics.section_gap)
        self._reports: dict[str, QCheckBox] = {}
        for key in SUPPORTED_REPORTS:
            box_item = QCheckBox(REPORT_LABELS.get(key, key))
            box_item.setToolTip(REPORT_HINTS.get(key, ""))
            box_item.toggled.connect(lambda _value: self.settings_changed.emit())
            row.addWidget(box_item)
            self._reports[key] = box_item
        row.addStretch(1)
        box.addLayout(row)
        return box

    def _build_output(self, metrics: UiMetrics) -> QGridLayout:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(metrics.normal_gap)
        grid.setVerticalSpacing(metrics.small_gap)
        grid.setColumnMinimumWidth(0, metrics.label_column)

        self._output = QLineEdit()
        self._output.setMinimumWidth(metrics.px(260))
        self._output.setMaximumWidth(metrics.px(460))
        self._output.setToolTip(
            "Lze použít zástupné hodnoty {rok} a {mesic}, například "
            "vystup/uzaverka/{rok}-{mesic}."
        )
        self._output.editingFinished.connect(self.settings_changed.emit)
        browse = secondary_button("Procházet…")
        browse.clicked.connect(self._pick_output)

        output_row = QHBoxLayout()
        output_row.setContentsMargins(0, 0, 0, 0)
        output_row.setSpacing(metrics.small_gap)
        output_row.addWidget(self._output, 1)
        output_row.addWidget(browse)
        output_row.addStretch(1)

        grid.addWidget(field_label("Výstup", self._output), 0, 0)
        grid.addLayout(output_row, 0, 1, 1, 2)

        self._resolved = elided_hint("")
        grid.addWidget(self._resolved, 1, 1, 1, 2)

        self._pack_zip = QCheckBox("Zabalit sestavy do jednoho ZIP")
        self._pack_zip.toggled.connect(lambda _value: self.settings_changed.emit())
        self._send_mail = QCheckBox("Odeslat e-mailem po vytvoření")
        self._send_mail.toggled.connect(self._on_send_toggled)
        grid.addWidget(self._pack_zip, 2, 1, 1, 2)
        grid.addWidget(self._send_mail, 3, 1, 1, 2)

        self._recipients_label = hint("")
        grid.addWidget(self._recipients_label, 4, 1, 1, 2)
        grid.setColumnStretch(2, 1)
        return grid

    def _build_advanced(self, metrics: UiMetrics) -> QWidget:
        self._advanced = CollapsibleSection(
            "Pokročilé nastavení uzávěrky", metrics, self, palette=self._palette
        )
        grid = QGridLayout(self._advanced.content)
        grid.setContentsMargins(metrics.section_gap, 0, 0, 0)
        grid.setHorizontalSpacing(metrics.normal_gap)
        grid.setVerticalSpacing(metrics.small_gap)
        grid.setColumnMinimumWidth(0, metrics.label_column)

        self._arch_variant = QComboBox()
        for key in ARCH_VARIANTS:
            self._arch_variant.addItem(ARCH_LABELS.get(key, key), key)
        self._arch_variant.setMinimumWidth(metrics.px(200))
        self._arch_variant.currentIndexChanged.connect(
            lambda _value: self.settings_changed.emit()
        )

        self._recap_variant = QComboBox()
        for key in REKAPITULACE_VARIANTS:
            self._recap_variant.addItem(RECAP_LABELS.get(key, key), key)
        self._recap_variant.setMinimumWidth(metrics.px(200))
        self._recap_variant.currentIndexChanged.connect(
            lambda _value: self.settings_changed.emit()
        )

        self._include_bulk = QCheckBox("Zahrnout hromadné strávníky do archu")
        self._include_bulk.toggled.connect(
            lambda _value: self.settings_changed.emit()
        )
        self._all_categories = QCheckBox("Použít všechny kategorie z databáze")
        self._all_categories.setToolTip(
            "Vypnuto se použije seznam povolených kategorií z konfigurace."
        )
        self._all_categories.toggled.connect(
            lambda _value: self.settings_changed.emit()
        )

        grid.addWidget(field_label("Stravovací arch", self._arch_variant), 0, 0)
        grid.addWidget(self._arch_variant, 0, 1)
        grid.addWidget(field_label("Rekapitulace", self._recap_variant), 1, 0)
        grid.addWidget(self._recap_variant, 1, 1)
        grid.addWidget(self._include_bulk, 2, 1)
        grid.addWidget(self._all_categories, 3, 1)
        grid.setColumnStretch(2, 1)
        return self._advanced

    def _build_progress(self, metrics: UiMetrics) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(metrics.small_gap)
        box.addWidget(section_label("Průběh"))

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setVisible(False)
        box.addWidget(self._progress)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(metrics.small_gap)
        self._state_dot = StatusDot(self, metrics)
        self._state_label = QLabel("Uzávěrka zatím nebyla spuštěna.")
        self._state_label.setProperty("role", "hint")
        row.addWidget(self._state_dot)
        row.addWidget(self._state_label, 1)
        box.addLayout(row)
        return box

    def _build_footer(self, metrics: UiMetrics) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(metrics.normal_gap)

        self._last_label = elided_hint("Poslední výstup: —")
        footer.addWidget(self._last_label, 1)

        self._open_folder = ghost_button("Otevřít složku")
        self._open_folder.clicked.connect(self.open_folder_requested.emit)
        self._open_last = secondary_button("Otevřít poslední")
        self._open_last.setEnabled(False)
        self._open_last.clicked.connect(self._emit_open_last)
        self._run = primary_button("Vytvořit uzávěrku")
        self._run.clicked.connect(self.run_requested.emit)

        footer.addWidget(self._open_folder)
        footer.addWidget(self._open_last)
        footer.addWidget(self._run)
        return footer

    # ------------------------------------------------------------------
    # Rozhraní pro controller
    # ------------------------------------------------------------------
    def set_form(self, form: ClosingForm) -> None:
        widgets = (
            self._month,
            self._year,
            self._current_period,
            self._output,
            self._pack_zip,
            self._send_mail,
            self._arch_variant,
            self._recap_variant,
            self._include_bulk,
            self._all_categories,
            *self._reports.values(),
        )
        for widget in widgets:
            widget.blockSignals(True)
        self._month.setCurrentIndex(max(0, self._month.findData(form.month)))
        self._year.setValue(int(form.year))
        self._current_period.setChecked(form.use_current_period)
        for key, box in self._reports.items():
            box.setChecked(key in form.reports)
        self._output.setText(form.output)
        self._pack_zip.setChecked(form.pack_zip)
        self._send_mail.setChecked(form.send_mail)
        self._arch_variant.setCurrentIndex(
            max(0, self._arch_variant.findData(form.arch_variant))
        )
        self._recap_variant.setCurrentIndex(
            max(0, self._recap_variant.findData(form.recap_variant))
        )
        self._include_bulk.setChecked(form.include_bulk_arch)
        self._all_categories.setChecked(form.use_all_categories)
        for widget in widgets:
            widget.blockSignals(False)
        self._recipients = tuple(form.recipients)
        self._month.setEnabled(not form.use_current_period)
        self._year.setEnabled(not form.use_current_period)
        self._refresh_recipients()

    def form(self) -> ClosingForm:
        return ClosingForm(
            year=int(self._year.value()),
            month=int(self._month.currentData()),
            use_current_period=self._current_period.isChecked(),
            reports=tuple(
                key for key, box in self._reports.items() if box.isChecked()
            ),
            output=self._output.text().strip(),
            pack_zip=self._pack_zip.isChecked(),
            send_mail=self._send_mail.isChecked(),
            arch_variant=str(self._arch_variant.currentData()),
            include_bulk_arch=self._include_bulk.isChecked(),
            recap_variant=str(self._recap_variant.currentData()),
            use_all_categories=self._all_categories.isChecked(),
            recipients=self._recipients,
        )

    def set_resolved_output(self, text: str) -> None:
        self._resolved.setText(text)
        self._resolved.setToolTip(text)

    def set_recipients(self, recipients: tuple[str, ...]) -> None:
        self._recipients = tuple(recipients)
        self._refresh_recipients()

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

    def set_last_output(self, path: Path | None, note: str = "") -> None:
        self._last_file = path
        if path is None:
            self._last_label.setText(f"Poslední výstup: {note or '—'}")
            self._last_label.setToolTip("")
            self._open_last.setEnabled(False)
            return
        self._last_label.setText(f"Poslední výstup: {note or path.name}")
        self._last_label.setToolTip(str(path))
        self._open_last.setEnabled(path.is_file())

    def set_busy(self, busy: bool) -> None:
        self._run.setEnabled(not busy)
        self._run.setText("Pracuji…" if busy else "Vytvořit uzávěrku")

    def set_run_enabled(self, enabled: bool, reason: str = "") -> None:
        self._run.setEnabled(enabled)
        self._run.setToolTip(
            reason or "Vytvoří vybrané sestavy za zvolené období"
        )

    def focus_default(self) -> None:
        if self._month.isEnabled():
            self._month.setFocus(Qt.OtherFocusReason)
        else:
            self._current_period.setFocus(Qt.OtherFocusReason)

    # ------------------------------------------------------------------
    # Interakce
    # ------------------------------------------------------------------
    def _emit_open_last(self) -> None:
        if self._last_file is not None:
            self.open_file_requested.emit(self._last_file)

    def _on_period_changed(self) -> None:
        self.settings_changed.emit()

    def _on_current_toggled(self, checked: bool) -> None:
        self._month.setEnabled(not checked)
        self._year.setEnabled(not checked)
        self.settings_changed.emit()

    def _on_send_toggled(self, _checked: bool) -> None:
        self._refresh_recipients()
        self.settings_changed.emit()

    def _refresh_recipients(self) -> None:
        if not self._send_mail.isChecked():
            self._recipients_label.setText(
                "Sestavy se jen uloží do výstupní složky."
            )
            self._recipients_label.setProperty("role", "hint")
        elif self._recipients:
            people = ", ".join(self._recipients)
            self._recipients_label.setText(
                f"Příjemci uzávěrky: {len(self._recipients)} · {people}"
            )
            self._recipients_label.setProperty("role", "hint")
        else:
            self._recipients_label.setText(
                "Doplňte příjemce v Administraci → E-maily → Uzávěrka."
            )
            self._recipients_label.setProperty("role", "error")
        self._recipients_label.style().unpolish(self._recipients_label)
        self._recipients_label.style().polish(self._recipients_label)

    def _pick_output(self) -> None:
        current = self._output.text().strip()
        chosen = QFileDialog.getExistingDirectory(
            self, "Vyberte složku pro sestavy uzávěrky", current or "."
        )
        if not chosen:
            return
        self._output.setText(join_picked_directory(current, chosen))
        self.settings_changed.emit()
