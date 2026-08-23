"""Obrazovka Hromadná zpráva: filtr příjemců, text a odeslání."""

from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QRadioButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from gui_qt.dialogs.categories import CategoryDialog
from gui_qt.models import RecipientModel
from gui_qt.theme import Palette, UiMetrics
from gui_qt.widgets.common import (
    StatusDot,
    field_label,
    ghost_button,
    hint,
    page_title,
    primary_button,
    secondary_button,
    section_label,
    separator,
)
from gui_qt.widgets.empty_state import TableEmptyState
from services.bulk import (
    FILTER_LABELS,
    FILTER_TYPES,
    BulkForm,
)


EMPTY_TITLE = "Zatím není vybraná žádná třída ani kategorie"
EMPTY_HINT = "Vyberte filtr tlačítkem Změnit výběr"


class _BodyEdit(QPlainTextEdit):
    """Textové pole, které po opuštění ohlásí dokončenou úpravu."""

    editing_finished = Signal()

    def focusOutEvent(self, event) -> None:  # noqa: N802, ANN001 - Qt API
        super().focusOutEvent(event)
        self.editing_finished.emit()


class BulkPage(QWidget):
    """Filtry nahoře, tabulka příjemců a editor zprávy."""

    settings_changed = Signal()
    filter_changed = Signal()
    send_requested = Signal()
    reload_requested = Signal()

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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            metrics.margin, metrics.normal_gap, metrics.margin, metrics.normal_gap
        )
        layout.setSpacing(metrics.normal_gap)
        layout.addWidget(page_title("Hromadná zpráva"))
        layout.addLayout(self._build_filters(metrics))

        splitter = QSplitter(Qt.Vertical, self)
        splitter.setChildrenCollapsible(False)
        recipients = self._build_recipients(metrics)
        message = self._build_message(metrics)
        # Bez výslovného minima by se okno při 160 % nedalo zmenšit
        # na 1366×768; posuvník uvnitř obou částí zůstává.
        recipients.setMinimumHeight(metrics.px(110))
        message.setMinimumHeight(metrics.px(110))
        splitter.addWidget(recipients)
        splitter.addWidget(message)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setMinimumHeight(metrics.px(230))
        layout.addWidget(splitter, 1)

        layout.addWidget(separator())
        layout.addLayout(self._build_footer(metrics))

    # ------------------------------------------------------------------
    # Stavba
    # ------------------------------------------------------------------
    def _build_filters(self, metrics: UiMetrics) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(metrics.normal_gap)

        self._filter_buttons: dict[str, QRadioButton] = {}
        self._selection_label = QLabel("0 vybráno")
        group = QButtonGroup(self)
        group.setExclusive(True)
        row.addWidget(field_label("Filtrovat podle"))
        for key in FILTER_TYPES:
            button = QRadioButton(FILTER_LABELS[key])
            group.addButton(button)
            row.addWidget(button)
            self._filter_buttons[key] = button
        self._filter_buttons[FILTER_TYPES[0]].setChecked(True)
        # Signály se připojují až po vytvoření všech ovládaných prvků.
        for key, button in self._filter_buttons.items():
            button.toggled.connect(
                lambda checked, value=key: checked and self._on_filter_type(value)
            )

        row.addSpacing(metrics.normal_gap)
        row.addWidget(self._selection_label)
        self._change = secondary_button("Změnit výběr…")
        self._change.clicked.connect(self._open_picker)
        row.addWidget(self._change)
        self._reload = ghost_button("Načíst znovu")
        self._reload.setToolTip("Znovu načte strávníky z databáze")
        self._reload.clicked.connect(self.reload_requested.emit)
        row.addWidget(self._reload)
        row.addStretch(1)
        return row

    def _build_recipients(self, metrics: UiMetrics) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(metrics.small_gap)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(metrics.normal_gap)
        head.addWidget(section_label("Příjemci"))
        self._summary = QLabel("")
        self._summary.setProperty("role", "hint")
        head.addWidget(self._summary, 1)
        layout.addLayout(head)

        self._model = RecipientModel()
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        self._table.setSelectionBehavior(QTableView.SelectRows)
        self._table.setEditTriggers(QTableView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(metrics.row_height)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setHighlightSections(False)
        header.setFixedHeight(metrics.control_height - metrics.px(4))
        self._table.setMinimumHeight(metrics.px(120))
        layout.addWidget(self._table, 1)

        self._empty_state = TableEmptyState(
            self._table, metrics, self._palette, EMPTY_TITLE, EMPTY_HINT
        )
        return container

    def _build_message(self, metrics: UiMetrics) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, metrics.small_gap, 0, 0)
        layout.setSpacing(metrics.small_gap)
        layout.addWidget(section_label("Zpráva"))

        subject_row = QHBoxLayout()
        subject_row.setContentsMargins(0, 0, 0, 0)
        subject_row.setSpacing(metrics.normal_gap)
        self._subject = QLineEdit()
        self._subject.setPlaceholderText("Předmět zprávy")
        self._subject.editingFinished.connect(self.settings_changed.emit)
        subject_row.addWidget(field_label("Předmět", self._subject))
        subject_row.addWidget(self._subject, 1)
        layout.addLayout(subject_row)

        self._body = _BodyEdit()
        self._body.setPlaceholderText(
            "Text zprávy. Všem příjemcům se odešle stejné znění."
        )
        self._body.setMinimumHeight(metrics.px(90))
        self._body.editing_finished.connect(self.settings_changed.emit)
        layout.addWidget(self._body, 1)
        layout.addWidget(
            hint(
                "Každý příjemce dostane samostatnou zprávu, adresy ostatních "
                "nevidí. Předmět i text se ukládají do konfigurace."
            )
        )
        return container

    def _build_footer(self, metrics: UiMetrics) -> QHBoxLayout:
        footer = QHBoxLayout()
        footer.setContentsMargins(0, metrics.small_gap, 0, 0)
        footer.setSpacing(metrics.normal_gap)
        self._state_dot = StatusDot(self, metrics)
        self._status = QLabel("Zpráva zatím nebyla odeslána.")
        self._status.setProperty("role", "hint")
        footer.addWidget(self._state_dot)
        footer.addWidget(self._status, 1)
        self._send = primary_button("Odeslat hromadnou zprávu")
        self._send.setEnabled(False)
        self._send.clicked.connect(self.send_requested.emit)
        footer.addWidget(self._send)
        return footer

    # ------------------------------------------------------------------
    # Rozhraní pro controller
    # ------------------------------------------------------------------
    def set_form(self, form: BulkForm) -> None:
        self._subject.blockSignals(True)
        self._body.blockSignals(True)
        self._subject.setText(form.subject)
        self._body.setPlainText(form.body)
        self._subject.blockSignals(False)
        self._body.blockSignals(False)

    def form(self) -> BulkForm:
        return BulkForm(
            subject=self._subject.text().strip(),
            body=self._body.toPlainText(),
        )

    def filter_type(self) -> str:
        for key, button in self._filter_buttons.items():
            if button.isChecked():
                return key
        return FILTER_TYPES[0]

    def selected_values(self) -> tuple[str, ...]:
        return tuple(self._selected)

    def set_filter_options(self, options: Sequence[tuple[str, str]]) -> None:
        self._options = tuple(options)
        known = {code for code, _note in self._options}
        self._selected = tuple(code for code in self._selected if code in known)
        self._refresh_selection()

    def set_recipients(
        self,
        rows: Sequence[tuple[str, str, str, str]],
        summary: str,
        *,
        can_send: bool,
    ) -> None:
        self._model.set_rows(tuple(rows))
        self._summary.setText(summary)
        self._send.setEnabled(can_send)
        if rows:
            self._empty_state.setVisible(False)
        else:
            self._empty_state.set_message(EMPTY_TITLE, EMPTY_HINT)
            self._empty_state.setVisible(True)

    def set_empty_message(self, title: str, detail: str) -> None:
        self._model.set_rows(())
        self._empty_state.set_message(title, detail)
        self._empty_state.setVisible(True)

    def set_send_enabled(self, enabled: bool, reason: str = "") -> None:
        self._send.setEnabled(enabled)
        self._send.setToolTip(reason or "Odešle zprávu všem vybraným příjemcům")

    def set_picker_enabled(self, enabled: bool) -> None:
        self._change.setEnabled(enabled)
        self._reload.setEnabled(enabled)

    def set_status(self, message: str, *, state: str = "") -> None:
        self._status.setText(message)
        self._status.setToolTip(message)
        self._state_dot.set_state(state)

    def set_busy(self, busy: bool) -> None:
        self._send.setEnabled(not busy)
        self._send.setText("Odesílám…" if busy else "Odeslat hromadnou zprávu")

    def focus_default(self) -> None:
        self._change.setFocus(Qt.OtherFocusReason)

    # ------------------------------------------------------------------
    # Interakce
    # ------------------------------------------------------------------
    def _on_filter_type(self, _value: str) -> None:
        self._selected = ()
        self._refresh_selection()
        self.filter_changed.emit()

    def _open_picker(self) -> None:
        if not self._options:
            self.set_status(
                "Nejprve ověřte připojení k databázi v Administraci → Databáze.",
                state="statusError",
            )
            return
        label = FILTER_LABELS[self.filter_type()]
        dialog = CategoryDialog(
            self._options,
            self._selected,
            self._metrics,
            self,
            title=f"Výběr – {label.lower()}",
        )
        if dialog.exec() != CategoryDialog.Accepted:
            return
        self._selected = dialog.selected_codes()
        self._refresh_selection()
        self.filter_changed.emit()

    def _refresh_selection(self) -> None:
        total = len(self._options)
        count = len(self._selected)
        self._selection_label.setText(
            f"{count} z {total} vybráno" if total else f"{count} vybráno"
        )
        self._selection_label.setToolTip(", ".join(self._selected))
