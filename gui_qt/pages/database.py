"""Administrace → Databáze: kompaktní formulář a test připojení."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from gui_qt.theme import UiMetrics
from gui_qt.widgets.common import (
    StatusDot,
    field_label,
    hint,
    page_body,
    scroll_area,
    secondary_button,
    section_label,
    size_input,
)


class DatabasePage(QWidget):
    """Formulář připojení; samotný test provádí controller ve vlákně."""

    test_requested = Signal(dict, str)

    def __init__(self, metrics: UiMetrics, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        content, layout = page_body(metrics, "Databáze", max_width=980)

        layout.addWidget(section_label("Připojení"))
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(metrics.normal_gap)
        grid.setVerticalSpacing(metrics.small_gap)
        grid.setColumnMinimumWidth(0, metrics.label_column)

        self._host = size_input(QLineEdit(), metrics, 220)
        self._port = QSpinBox()
        self._port.setRange(1, 65535)
        size_input(self._port, metrics, 96)
        self._dbname = size_input(QLineEdit(), metrics, 220)
        self._user = size_input(QLineEdit(), metrics, 220)
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.Password)
        size_input(self._password, metrics, 220)
        self._password.setPlaceholderText("Uloženo v systémovém trezoru")
        self._password.returnPressed.connect(self._emit_test)

        fields = (
            ("Server", self._host),
            ("Port", self._port),
            ("Databáze", self._dbname),
            ("Uživatel", self._user),
            ("Heslo", self._password),
        )
        for row, (text, widget) in enumerate(fields):
            grid.addWidget(field_label(text, widget), row, 0)
            grid.addWidget(widget, row, 1)
        grid.setColumnStretch(2, 1)
        layout.addLayout(grid)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(metrics.normal_gap)
        self._test = secondary_button("Test připojení")
        self._test.setProperty("emphasis", "primary")
        self._test.clicked.connect(self._emit_test)
        actions.addWidget(self._test)
        actions.addStretch(1)
        layout.addLayout(actions)

        layout.addWidget(section_label("Stav"))
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(metrics.small_gap)
        self._dot = StatusDot(self, metrics)
        self._status = QLabel("Připojení nebylo v této session ověřeno.")
        self._status.setWordWrap(True)
        status_row.addWidget(self._dot)
        status_row.addWidget(self._status, 1)
        layout.addLayout(status_row)
        self._detail = hint("")
        layout.addWidget(self._detail)

        layout.addStretch(1)
        layout.addWidget(
            hint(
                "Heslo se nikdy neukládá do config.json, ale do systémového "
                "úložiště přihlašovacích údajů Windows."
            )
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(scroll_area(content, self, metrics))

    def set_values(self, database: dict[str, Any]) -> None:
        self._host.setText(str(database.get("host", "")))
        try:
            self._port.setValue(int(database.get("port", 5432)))
        except (TypeError, ValueError):
            self._port.setValue(5432)
        self._dbname.setText(str(database.get("dbname", "")))
        self._user.setText(str(database.get("user", "")))

    def values(self) -> dict[str, Any]:
        return {
            "host": self._host.text(),
            "port": self._port.value(),
            "dbname": self._dbname.text(),
            "user": self._user.text(),
            "sslmode": "prefer",
            "connect_timeout": 10,
        }

    def password(self) -> str:
        return self._password.text()

    def clear_password_field(self) -> None:
        self._password.clear()

    def set_busy(self, busy: bool) -> None:
        self._test.setEnabled(not busy)
        if busy:
            self.set_status("Testuji připojení…", "")

    def set_status(self, text: str, detail: str = "", *, error: bool = False) -> None:
        self._status.setText(text)
        self._status.setProperty("role", "error" if error else "")
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)
        self._detail.setText(detail)
        if error:
            self._dot.set_state("statusError")
        elif detail:
            self._dot.set_state("statusOk")
        else:
            self._dot.set_state("")

    def focus_default(self) -> None:
        if not self._host.text().strip():
            self._host.setFocus()
        else:
            self._password.setFocus()

    def _emit_test(self) -> None:
        self.test_requested.emit(self.values(), self._password.text())
