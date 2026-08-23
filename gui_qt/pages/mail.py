"""Administrace → E-maily: příjemci a text zvlášť pro každou funkci."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from gui_qt.theme import UiMetrics
from gui_qt.widgets.common import (
    field_label,
    ghost_button,
    hint,
    page_body,
    scroll_area,
    secondary_button,
    section_label,
    size_choice,
    size_input,
)
from services.mail_settings import (
    COOKING_DAY_FUNCTIONS,
    DEFAULT_SENDER,
    FUNCTION_IDS,
    FUNCTION_LABELS,
    FunctionMail,
    MailSettings,
    add_recipient,
)
from stravovaci_sestava import ConfigError


class _BodyEdit(QPlainTextEdit):
    """Víceřádkový text, který se ukládá až při odchodu z pole."""

    editing_finished = Signal()

    def focusOutEvent(self, event) -> None:  # noqa: N802, ANN001 - Qt API
        super().focusOutEvent(event)
        self.editing_finished.emit()


class MailPage(QWidget):
    """Pohled bez business logiky; ukládání řeší controller."""

    settings_changed = Signal()
    api_key_save_requested = Signal(str)
    failed = Signal(str)

    def __init__(self, metrics: UiMetrics, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._metrics = metrics
        self._settings = MailSettings()
        self._current = FUNCTION_IDS[0]
        self._loading = False

        content, layout = page_body(metrics, "E-maily", max_width=980)

        layout.addWidget(section_label("Odesílání"))
        layout.addLayout(self._build_sender_form())

        layout.addWidget(section_label("Funkce"))
        layout.addLayout(self._build_function_form(), 1)

        layout.addWidget(
            hint(
                "Změny se ukládají průběžně. Resend API klíč se zapisuje do "
                "souboru .env, nikdy do config.json."
            )
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(scroll_area(content, self, metrics))

    # ------------------------------------------------------------------
    # Stavba rozvržení
    # ------------------------------------------------------------------
    def _build_sender_form(self) -> QGridLayout:
        metrics = self._metrics
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(metrics.normal_gap)
        grid.setVerticalSpacing(metrics.small_gap)
        grid.setColumnMinimumWidth(0, metrics.label_column)

        self._sender = size_input(QLineEdit(), metrics, 260)
        self._sender.setPlaceholderText(DEFAULT_SENDER)
        self._sender.editingFinished.connect(self._commit_sender)

        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.Password)
        size_input(self._api_key, metrics, 260)
        self._api_key.setPlaceholderText("Klíč z resend.com")
        self._api_key.returnPressed.connect(self._save_api_key)
        save_key = secondary_button("Uložit klíč")
        save_key.clicked.connect(self._save_api_key)

        grid.addWidget(field_label("Odesílatel", self._sender), 0, 0)
        grid.addWidget(self._sender, 0, 1)
        grid.addWidget(field_label("Resend API klíč", self._api_key), 1, 0)
        grid.addWidget(self._api_key, 1, 1)
        grid.addWidget(save_key, 1, 2)
        grid.setColumnStretch(3, 1)
        return grid

    def _build_function_form(self) -> QGridLayout:
        metrics = self._metrics
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(metrics.normal_gap)
        grid.setVerticalSpacing(metrics.small_gap)
        grid.setColumnMinimumWidth(0, metrics.label_column)

        self._function = QComboBox()
        for key in FUNCTION_IDS:
            self._function.addItem(FUNCTION_LABELS[key], key)
        size_choice(self._function, metrics, 280)
        self._function.setMaxVisibleItems(max(12, len(FUNCTION_IDS)))
        self._function.currentIndexChanged.connect(self._switch_function)
        grid.addWidget(field_label("Funkce", self._function), 0, 0)
        grid.addWidget(self._function, 0, 1)

        self._recipients = QListWidget()
        size_input(self._recipients, metrics, 300)
        self._recipients.setMinimumHeight(metrics.px(96))
        self._recipients.setAlternatingRowColors(True)
        self._recipients.setSelectionMode(QListWidget.SingleSelection)
        grid.addWidget(field_label("Příjemci", self._recipients), 1, 0, Qt.AlignTop)
        grid.addWidget(self._recipients, 1, 1, 1, 2)

        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 0, 0, 0)
        add_row.setSpacing(metrics.small_gap)
        self._new_recipient = size_input(QLineEdit(), metrics, 220)
        self._new_recipient.setPlaceholderText("adresa@skola.cz")
        self._new_recipient.returnPressed.connect(self._add_recipient)
        add_button = secondary_button("Přidat")
        add_button.clicked.connect(self._add_recipient)
        self._remove = ghost_button("Odebrat vybraného")
        self._remove.clicked.connect(self._remove_recipient)
        add_row.addWidget(self._new_recipient)
        add_row.addWidget(add_button)
        add_row.addWidget(self._remove)
        add_row.addStretch(1)
        grid.addLayout(add_row, 2, 1, 1, 3)

        self._body = _BodyEdit()
        self._body.setMinimumHeight(metrics.control_height * 3)
        self._body.setMinimumWidth(metrics.px(300))
        self._body.setMaximumWidth(metrics.px(560))
        self._body.setTabChangesFocus(True)
        self._body.editing_finished.connect(self._commit_body)
        grid.addWidget(field_label("Text zprávy", self._body), 3, 0, Qt.AlignTop)
        grid.addWidget(self._body, 3, 1, 1, 3)

        self._cooking_days = QCheckBox("Odesílat jen ve varných dnech")
        self._cooking_days.toggled.connect(self._commit_cooking_days)
        grid.addWidget(self._cooking_days, 4, 1, 1, 3)

        grid.setColumnStretch(4, 1)
        grid.setRowStretch(5, 1)
        return grid

    # ------------------------------------------------------------------
    # Rozhraní pro controller
    # ------------------------------------------------------------------
    def set_settings(self, settings: MailSettings) -> None:
        self._settings = settings
        self._loading = True
        self._sender.setText(settings.sender)
        self._loading = False
        self._show_function(self._current)

    def settings(self) -> MailSettings:
        return self._settings

    def set_api_key(self, api_key: str) -> None:
        self._api_key.setText(api_key)

    def api_key(self) -> str:
        return self._api_key.text().strip()

    def focus_default(self) -> None:
        self._function.setFocus()

    # ------------------------------------------------------------------
    # Interakce
    # ------------------------------------------------------------------
    def _show_function(self, key: str) -> None:
        mail = self._settings.function(key)
        self._loading = True
        self._recipients.clear()
        self._recipients.addItems(list(mail.recipients))
        self._body.setPlainText(mail.body)
        self._cooking_days.setChecked(mail.only_cooking_days)
        self._loading = False
        supports_cooking = key in COOKING_DAY_FUNCTIONS
        self._cooking_days.setVisible(supports_cooking)

    def _switch_function(self, _index: int) -> None:
        self._commit_body()
        self._current = str(self._function.currentData())
        self._show_function(self._current)

    def _current_mail(self) -> FunctionMail:
        return self._settings.function(self._current)

    def _update_current(self, mail: FunctionMail) -> None:
        self._settings = self._settings.with_function(self._current, mail)
        self.settings_changed.emit()

    def _commit_sender(self) -> None:
        if self._loading:
            return
        sender = self._sender.text().strip()
        if sender == self._settings.sender:
            return
        self._settings = self._settings.with_sender(sender)
        self.settings_changed.emit()

    def _commit_body(self) -> None:
        if self._loading:
            return
        body = self._body.toPlainText()
        mail = self._current_mail()
        if body == mail.body:
            return
        self._update_current(
            FunctionMail(
                recipients=mail.recipients,
                body=body,
                only_cooking_days=mail.only_cooking_days,
            )
        )

    def _commit_cooking_days(self, checked: bool) -> None:
        if self._loading:
            return
        mail = self._current_mail()
        self._update_current(
            FunctionMail(
                recipients=mail.recipients,
                body=mail.body,
                only_cooking_days=bool(checked),
            )
        )

    def _add_recipient(self) -> None:
        mail = self._current_mail()
        try:
            recipients = add_recipient(mail.recipients, self._new_recipient.text())
        except ConfigError as exc:
            self.failed.emit(str(exc))
            return
        self._new_recipient.clear()
        self._update_current(
            FunctionMail(
                recipients=recipients,
                body=self._body.toPlainText(),
                only_cooking_days=mail.only_cooking_days,
            )
        )
        self._show_function(self._current)

    def _remove_recipient(self) -> None:
        item = self._recipients.currentItem()
        if item is None:
            self.failed.emit("Nejdřív vyberte adresu v seznamu.")
            return
        address = item.text()
        mail = self._current_mail()
        self._update_current(
            FunctionMail(
                recipients=tuple(
                    value for value in mail.recipients if value != address
                ),
                body=self._body.toPlainText(),
                only_cooking_days=mail.only_cooking_days,
            )
        )
        self._show_function(self._current)

    def _save_api_key(self) -> None:
        key = self.api_key()
        if not key:
            self.failed.emit("Resend API klíč nesmí být prázdný.")
            return
        self.api_key_save_requested.emit(key)
