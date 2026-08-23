"""Obrazovka Denní stav: nejčastější denní operace na jedné ploše."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QCalendarWidget,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from gui_qt.dialogs.categories import CategoryDialog
from gui_qt.models import OverviewModel
from gui_qt.theme import Palette, UiMetrics
from gui_qt.widgets.collapsible import CollapsibleSection
from gui_qt.widgets.common import (
    StatusDot,
    field_label,
    ghost_button,
    hint,
    page_title,
    primary_button,
    scroll_area,
    secondary_button,
    section_label,
    separator,
    size_choice,
    size_input,
)
from gui_qt.widgets.empty_state import TableEmptyState
from services.daily import (
    ORIENTATION_LABELS,
    ORIENTATIONS,
    ActionState,
    DailyOverview,
    DailySettings,
    describe_moment,
    selection_preview,
    selection_summary,
)


LANGUAGE_SUGGESTIONS = ("česky", "anglicky")

EMPTY_TITLE = "Přehled zatím nebyl načten"
EMPTY_HINT = "Stiskněte F9 nebo klikněte na Načíst"


class DailyPage(QWidget):
    """Pohled bez business logiky; akce jen ohlásí signálem."""

    create_requested = Signal()
    send_requested = Signal()
    open_last_requested = Signal()
    overview_requested = Signal()
    settings_changed = Signal()

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

        # Obsah je v posuvné oblasti jen jako záloha pro malá rozlišení
        # a vysoké DPI; při 1366×768 a 100 % se nikdy neposouvá.
        content = QWidget()
        inner = QVBoxLayout(content)
        inner.setContentsMargins(
            metrics.margin, metrics.normal_gap, metrics.margin, metrics.normal_gap
        )
        inner.setSpacing(metrics.section_gap)
        inner.addWidget(page_title("Denní stav"))
        inner.addLayout(self._build_primary_form())
        inner.addWidget(self._build_advanced_section())
        inner.addWidget(self._build_overview(), 1)

        self._scroll = scroll = scroll_area(content, self, metrics)

        footer = QWidget(self)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(
            metrics.margin, metrics.normal_gap, metrics.margin, metrics.normal_gap
        )
        footer_layout.setSpacing(metrics.normal_gap)
        footer_layout.addLayout(self._build_footer())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(scroll, 1)
        layout.addWidget(separator())
        layout.addWidget(footer)

        self.setTabOrder(self._date, self._change_categories)

    # ------------------------------------------------------------------
    # Stavba rozvržení
    # ------------------------------------------------------------------
    def _build_primary_form(self) -> QGridLayout:
        metrics = self._metrics
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(metrics.normal_gap)
        grid.setVerticalSpacing(metrics.small_gap)
        grid.setColumnMinimumWidth(0, metrics.label_column)

        self._date = QDateEdit()
        self._date.setDisplayFormat("dd.MM.yyyy")
        self._date.setCalendarPopup(True)
        calendar = self._date.calendarWidget()
        calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        calendar.setNavigationBarVisible(True)
        calendar.setGridVisible(False)
        calendar.setMinimumSize(metrics.px(320), metrics.px(260))
        self._date.setDate(QDate.currentDate())
        size_input(self._date, metrics, 124)
        self._date.setAccessibleName("Datum sestavy")
        self._date.dateChanged.connect(self._on_date_changed)

        today = secondary_button("Dnes")
        today.setToolTip("Nastaví dnešní datum")
        today.clicked.connect(
            lambda: self._date.setDate(QDate.currentDate())
        )

        grid.addWidget(field_label("Datum", self._date), 0, 0)
        grid.addWidget(self._date, 0, 1)
        grid.addWidget(today, 0, 2)

        self._selection_label = QLabel("0 vybráno")
        self._change_categories = secondary_button("Změnit…")
        self._change_categories.setToolTip(
            "Otevře dialog s hledáním a hromadným výběrem kategorií"
        )
        self._change_categories.clicked.connect(self._open_category_dialog)

        grid.addWidget(field_label("Kategorie", self._change_categories), 1, 0)
        grid.addWidget(self._selection_label, 1, 1)
        grid.addWidget(self._change_categories, 1, 2)
        grid.setColumnStretch(3, 1)
        return grid

    def _build_advanced_section(self) -> QWidget:
        metrics = self._metrics
        self._advanced = CollapsibleSection(
            "Pokročilé nastavení PDF", metrics, self, palette=self._palette
        )
        grid = QGridLayout(self._advanced.content)
        grid.setContentsMargins(metrics.section_gap, 0, 0, 0)
        grid.setHorizontalSpacing(metrics.normal_gap)
        grid.setVerticalSpacing(metrics.small_gap)
        grid.setColumnMinimumWidth(0, metrics.label_column)

        self._language = QComboBox()
        self._language.setEditable(True)
        self._language.addItems(LANGUAGE_SUGGESTIONS)
        size_choice(self._language, metrics, 130)
        self._language.currentTextChanged.connect(
            lambda _value: self.settings_changed.emit()
        )

        self._orientation = QComboBox()
        for key in ORIENTATIONS:
            self._orientation.addItem(ORIENTATION_LABELS[key], key)
        size_choice(self._orientation, metrics, 130)
        self._orientation.currentIndexChanged.connect(
            lambda _value: self.settings_changed.emit()
        )

        self._menu_number = QSpinBox()
        self._menu_number.setRange(1, 99)
        size_input(self._menu_number, metrics, 84)
        self._menu_number.valueChanged.connect(
            lambda _value: self.settings_changed.emit()
        )

        self._data_size = self._font_spin()
        self._label_size = self._font_spin()

        self._output = QLineEdit()
        self._output.setMinimumWidth(metrics.px(240))
        self._output.setMaximumWidth(metrics.px(440))
        self._output.setToolTip(
            "Lze použít zástupné hodnoty {datum} a {datum_cz}."
        )
        self._output.editingFinished.connect(self.settings_changed.emit)
        browse = secondary_button("Procházet…")
        browse.clicked.connect(self._pick_output_directory)

        self._category_separation = self._check("Oddělit dle kategorií")
        self._show_categories = self._check("Souhrn dle kategorií")
        self._show_norms = self._check("Souhrn dle norem")
        self._bold = self._check("Tučná data")

        grid.addWidget(field_label("Jazyk", self._language), 0, 0)
        grid.addWidget(self._language, 0, 1)
        grid.addWidget(field_label("Orientace", self._orientation), 0, 2)
        grid.addWidget(self._orientation, 0, 3)

        grid.addWidget(field_label("Jídelníček", self._menu_number), 1, 0)
        grid.addWidget(self._menu_number, 1, 1)
        grid.addWidget(field_label("Velikost dat", self._data_size), 1, 2)
        grid.addWidget(self._data_size, 1, 3)

        grid.addWidget(field_label("Velikost popisků", self._label_size), 2, 0)
        grid.addWidget(self._label_size, 2, 1)

        grid.addWidget(self._category_separation, 3, 1)
        grid.addWidget(self._show_categories, 3, 2, 1, 2)
        grid.addWidget(self._show_norms, 4, 1)
        grid.addWidget(self._bold, 4, 2, 1, 2)

        output_row = QHBoxLayout()
        output_row.setContentsMargins(0, 0, 0, 0)
        output_row.setSpacing(self._metrics.small_gap)
        output_row.addWidget(self._output, 1)
        output_row.addWidget(browse)
        output_row.addStretch(1)
        grid.addWidget(field_label("Výstupní PDF", self._output), 5, 0)
        grid.addLayout(output_row, 5, 1, 1, 3)
        grid.setColumnStretch(4, 1)
        return self._advanced

    def _font_spin(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(5.0, 18.0)
        spin.setSingleStep(0.1)
        spin.setDecimals(1)
        size_input(spin, self._metrics, 90)
        spin.valueChanged.connect(lambda _value: self.settings_changed.emit())
        return spin

    def _check(self, text: str) -> QCheckBox:
        box = QCheckBox(text)
        box.toggled.connect(lambda _value: self.settings_changed.emit())
        return box

    def _build_overview(self) -> QWidget:
        metrics = self._metrics
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(metrics.small_gap)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(metrics.normal_gap)
        head.addWidget(section_label("Přehled porcí"))
        self._overview_summary = QLabel("")
        self._overview_summary.setProperty("role", "hint")
        head.addWidget(self._overview_summary)
        head.addStretch(1)
        self._refresh_overview = secondary_button("Načíst")
        self._refresh_overview.setShortcut("F9")
        self._refresh_overview.setToolTip(
            "Načte souhrn porcí z databáze bez tvorby PDF (F9)"
        )
        self._refresh_overview.clicked.connect(self.overview_requested.emit)
        head.addWidget(self._refresh_overview)
        layout.addLayout(head)

        self._overview_model = OverviewModel()
        self._overview = QTableView()
        self._overview.setModel(self._overview_model)
        self._overview.setAlternatingRowColors(True)
        self._overview.setShowGrid(False)
        self._overview.setSelectionBehavior(QTableView.SelectRows)
        self._overview.setSelectionMode(QTableView.SingleSelection)
        self._overview.setEditTriggers(QTableView.NoEditTriggers)
        self._overview.setWordWrap(False)
        self._overview.verticalHeader().setVisible(False)
        self._overview.verticalHeader().setDefaultSectionSize(metrics.row_height)
        header = self._overview.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setHighlightSections(False)
        header.setFixedHeight(metrics.control_height - metrics.px(4))
        self._overview.setMinimumHeight(metrics.px(96))
        layout.addWidget(self._overview, 1)

        self._empty_state = TableEmptyState(
            self._overview, metrics, self._palette, EMPTY_TITLE, EMPTY_HINT
        )
        return container

    def _build_footer(self) -> QHBoxLayout:
        metrics = self._metrics
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(metrics.normal_gap)

        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(2)
        self._last_pdf_label = hint("Poslední PDF: —")
        self._last_pdf_label.setWordWrap(False)
        mail_row = QHBoxLayout()
        mail_row.setContentsMargins(0, 0, 0, 0)
        mail_row.setSpacing(metrics.small_gap)
        self._mail_dot = StatusDot(self)
        self._last_mail_label = hint("E-mail: —")
        self._last_mail_label.setWordWrap(False)
        mail_row.addWidget(self._mail_dot)
        mail_row.addWidget(self._last_mail_label)
        mail_row.addStretch(1)
        info.addWidget(self._last_pdf_label)
        info.addLayout(mail_row)
        footer.addLayout(info, 1)

        self._open_last = ghost_button("Otevřít po&slední")
        self._open_last.clicked.connect(self.open_last_requested.emit)
        self._create = secondary_button("&Vytvořit PDF")
        self._create.setShortcut("F5")
        self._create.clicked.connect(self.create_requested.emit)
        self._send = primary_button("Vytvořit a &odeslat")
        self._send.clicked.connect(self.send_requested.emit)

        footer.addWidget(self._open_last)
        footer.addWidget(self._create)
        footer.addWidget(self._send)
        return footer

    # ------------------------------------------------------------------
    # Rozhraní pro controller
    # ------------------------------------------------------------------
    def set_settings(self, settings: DailySettings) -> None:
        widgets = (
            self._date,
            self._language,
            self._orientation,
            self._menu_number,
            self._data_size,
            self._label_size,
            self._output,
            self._category_separation,
            self._show_categories,
            self._show_norms,
            self._bold,
        )
        for widget in widgets:
            widget.blockSignals(True)
        self._date.setDate(
            QDate(
                settings.report_date.year,
                settings.report_date.month,
                settings.report_date.day,
            )
        )
        self._language.setCurrentText(settings.language)
        index = self._orientation.findData(settings.pdf_orientation)
        self._orientation.setCurrentIndex(max(0, index))
        self._menu_number.setValue(settings.menu_list_number)
        self._data_size.setValue(settings.pdf_data_font_size)
        self._label_size.setValue(settings.pdf_label_font_size)
        self._output.setText(settings.pdf_output)
        self._category_separation.setChecked(settings.category_separation)
        self._show_categories.setChecked(settings.show_by_categories)
        self._show_norms.setChecked(settings.show_by_norms)
        self._bold.setChecked(settings.pdf_bold)
        for widget in widgets:
            widget.blockSignals(False)
        self._selected = tuple(settings.categories)
        self._refresh_selection()

    def settings(self) -> DailySettings:
        qdate = self._date.date()
        return DailySettings(
            report_date=date(qdate.year(), qdate.month(), qdate.day()),
            categories=tuple(self._selected),
            language=self._language.currentText().strip(),
            menu_list_number=int(self._menu_number.value()),
            pdf_output=self._output.text().strip(),
            pdf_orientation=str(self._orientation.currentData()),
            pdf_data_font_size=float(self._data_size.value()),
            pdf_label_font_size=float(self._label_size.value()),
            pdf_bold=self._bold.isChecked(),
            category_separation=self._category_separation.isChecked(),
            show_by_categories=self._show_categories.isChecked(),
            show_by_norms=self._show_norms.isChecked(),
        )

    def set_category_options(
        self, options: Sequence[tuple[str, str]], *, keep_selection: bool = True
    ) -> None:
        self._options = tuple(options)
        known = {code for code, _name in self._options}
        if keep_selection:
            self._selected = tuple(
                code for code in self._selected if code in known
            )
        self._refresh_selection()

    def selected_categories(self) -> tuple[str, ...]:
        return tuple(self._selected)

    def category_options(self) -> tuple[tuple[str, str], ...]:
        return tuple(self._options)

    def overview_rows(self) -> int:
        return self._overview_model.rowCount()

    def set_selected_categories(self, codes: Sequence[str]) -> None:
        self._selected = tuple(codes)
        self._refresh_selection()

    def set_action_state(self, state: ActionState) -> None:
        self._create.setEnabled(state.can_create)
        self._send.setEnabled(state.can_send)
        self._open_last.setEnabled(state.can_open_last)
        tooltip = state.reason
        self._create.setToolTip(tooltip or "Vytvoří PDF denní sestavy (F5)")
        self._send.setToolTip(tooltip or "Vytvoří PDF a odešle je příjemcům")

    def set_overview(self, overview: DailyOverview) -> None:
        self._overview_model.set_rows(overview.rows)
        if overview.rows:
            self._overview_summary.setText(
                f"· {overview.total_portions} porcí · "
                f"{overview.diners} strávníků · "
                f"{overview.categories} kategorií"
            )
            self._empty_state.setVisible(False)
        else:
            self._overview_summary.setText("· bez objednávek")
            self._empty_state.set_message(
                "Pro vybraný den nejsou žádné objednané porce",
                "Zkontrolujte datum nebo výběr kategorií.",
            )
            self._empty_state.setVisible(True)

    def clear_overview(self, note: str = "", detail: str = "") -> None:
        self._overview_model.set_rows(())
        self._overview_summary.setText("")
        self._empty_state.set_message(note or EMPTY_TITLE, detail or EMPTY_HINT)
        self._empty_state.setVisible(True)

    def set_overview_enabled(self, enabled: bool) -> None:
        self._refresh_overview.setEnabled(enabled)

    def set_last_pdf(self, path: Path | None, note: str = "") -> None:
        if path is None:
            self._last_pdf_label.setText(f"Poslední PDF: {note or '—'}")
            self._last_pdf_label.setToolTip("")
            return
        try:
            moment = datetime.fromtimestamp(path.stat().st_mtime)
            stamp = describe_moment(moment)
        except OSError:
            stamp = path.name
        self._last_pdf_label.setText(f"Poslední PDF: {stamp}")
        self._last_pdf_label.setToolTip(str(path))

    def set_last_mail(self, note: str, state: str = "") -> None:
        """``state`` je ``statusOk``, ``statusError`` nebo prázdný text."""
        self._last_mail_label.setText(f"E-mail: {note or '—'}")
        self._last_mail_label.setToolTip(note)
        self._mail_dot.set_state(state)

    def focus_default(self) -> None:
        self._date.setFocus()

    def needs_scroll(self) -> bool:
        """True, pokud se obsah nevejde a je potřeba posuvník."""
        content = self._scroll.widget()
        needed = content.minimumSizeHint().height()
        return needed > self._scroll.viewport().height()

    # ------------------------------------------------------------------
    # Interakce
    # ------------------------------------------------------------------
    def _on_date_changed(self, _value: QDate) -> None:
        if self._overview_model.rowCount() > 0:
            self.clear_overview("Datum se změnilo, přehled načtěte znovu")
        self.settings_changed.emit()

    def _open_category_dialog(self) -> None:
        options = self._options or tuple((code, "") for code in self._selected)
        dialog = CategoryDialog(options, self._selected, self._metrics, self)
        if dialog.exec() != CategoryDialog.Accepted:
            return
        self._selected = dialog.selected_codes()
        self._refresh_selection()
        self.settings_changed.emit()

    def _refresh_selection(self) -> None:
        total = len(self._options) or len(self._selected)
        self._selection_label.setText(
            selection_summary(len(self._selected), total)
        )
        preview = selection_preview(self._selected, limit=24)
        self._selection_label.setToolTip(preview)
        self._change_categories.setToolTip(
            "Otevře dialog s hledáním a hromadným výběrem kategorií"
        )

    def _pick_output_directory(self) -> None:
        current = Path(self._output.text().strip() or "vystup/AutoReport.pdf")
        start = current.parent if current.parent.as_posix() else Path(".")
        chosen = QFileDialog.getExistingDirectory(
            self, "Vyberte složku pro PDF", str(start)
        )
        if not chosen:
            return
        self._output.setText(str(Path(chosen) / current.name))
        self.settings_changed.emit()
