"""Horní lišta: identita aplikace, stav databáze, provozovna a období.

Primární informace jsou vidět na první pohled, technické podrobnosti
(server, port, celý název databáze) nese tooltip stavu.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from gui_qt.theme import UiMetrics
from gui_qt.widgets.common import ElidedLabel, StatusDot


STATE_IDLE = "idle"
STATE_OK = "ok"
STATE_ERROR = "error"

_STATE_ROLE = {
    STATE_IDLE: "statusIdle",
    STATE_OK: "statusOk",
    STATE_ERROR: "statusError",
}


class HeaderBar(QFrame):
    """Jedna řádka: Přehled vlevo, DB + Administrace vpravo."""

    database_setup_requested = Signal()
    home_requested = Signal()
    admin_requested = Signal()

    def __init__(
        self,
        metrics: UiMetrics,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("HeaderBar")
        self.setFixedHeight(metrics.header_height)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(metrics.margin, 0, metrics.margin, 0)
        layout.setSpacing(metrics.normal_gap)
        control_height = metrics.control_height - metrics.px(6)

        self._home_button = QPushButton("Přehled")
        self._home_button.setObjectName("HeaderHomeButton")
        self._home_button.setMinimumHeight(control_height)
        self._home_button.setMaximumHeight(control_height)
        self._home_button.clicked.connect(self.home_requested.emit)
        layout.addWidget(self._home_button)

        layout.addSpacing(metrics.small_gap)
        layout.addWidget(self._divider(metrics))
        layout.addSpacing(metrics.small_gap)

        self._status_group = _ClickableFrame(self)
        self._status_group.setObjectName("HeaderStatusGroup")
        self._status_group.setMinimumHeight(control_height)
        self._status_group.setMaximumHeight(control_height)
        group_layout = QHBoxLayout(self._status_group)
        group_layout.setContentsMargins(
            metrics.px(10), 0, metrics.px(10), 0
        )
        group_layout.setSpacing(metrics.px(10))

        self._dot = StatusDot(self, metrics)
        self._state_label = QLabel("Neověřeno")
        self._state_label.setObjectName("HeaderState")
        self._status_widgets = (self._dot, self._state_label)
        group_layout.addWidget(self._dot)
        group_layout.addWidget(self._state_label)
        self._subject = ElidedLabel("")
        self._subject.setObjectName("HeaderSubject")
        self._subject.setMinimumWidth(metrics.px(80))
        group_layout.addWidget(self._subject)

        self._meta = QLabel("")
        self._meta.setObjectName("HeaderMeta")
        group_layout.addWidget(self._meta)
        self._admin_button = QPushButton("Administrace")
        self._admin_button.setObjectName("HeaderAdminButton")
        self._admin_button.setMinimumHeight(control_height)
        self._admin_button.setMaximumHeight(control_height)
        self._admin_button.clicked.connect(self.admin_requested.emit)
        layout.addStretch(1)
        self._right_group = QWidget(self)
        right_layout = QHBoxLayout(self._right_group)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(metrics.normal_gap)
        right_layout.addWidget(self._status_group)
        right_layout.addWidget(self._admin_button)
        layout.addWidget(self._right_group, 0, Qt.AlignRight)
        self._status_group.clicked.connect(self.database_setup_requested.emit)

        self.set_state(STATE_IDLE, "Neověřeno", "Připojení nebylo ověřeno.")
        self.set_connection_meta("", "")
        self.set_setup_hint_enabled(False)
        self.set_admin_unlocked(False)

    def _divider(self, metrics: UiMetrics) -> QFrame:
        line = QFrame(self)
        line.setObjectName("HeaderDivider")
        line.setFixedWidth(1)
        line.setFixedHeight(max(metrics.px(12), metrics.control_height - metrics.px(12)))
        return line

    def set_state(self, state: str, text: str, tooltip: str = "") -> None:
        """Přebarví tečku i text stavu; podrobnosti nese tooltip."""
        role = _STATE_ROLE.get(state, "statusIdle")
        self._dot.set_state(role)
        self._status_group.setProperty("stateRole", role)
        self._status_group.style().unpolish(self._status_group)
        self._status_group.style().polish(self._status_group)
        self._state_label.setProperty("role", role)
        self._state_label.style().unpolish(self._state_label)
        self._state_label.style().polish(self._state_label)
        self._state_label.setText(text)
        for widget in self._status_widgets:
            widget.setToolTip(tooltip or text)

    def set_setup_hint_enabled(self, enabled: bool) -> None:
        self._status_group.setCursor(
            Qt.PointingHandCursor if enabled else Qt.ArrowCursor
        )

    def set_connection_meta(self, subject: str, meta: str, tooltip: str = "") -> None:
        """Provozovna vlevo, databáze a období vpravo, detaily v tooltipu."""
        self._subject.setText(subject)
        self._subject.setToolTip(tooltip or subject)
        self._subject.setVisible(bool(subject))
        clean_meta = str(meta or "").strip()
        if clean_meta and not clean_meta.upper().startswith("DB:"):
            clean_meta = f"DB: {clean_meta}"
        self._meta.setText(clean_meta)
        self._meta.setToolTip(tooltip or meta)
        self._meta.setVisible(bool(clean_meta))

    def state_text(self) -> str:
        return self._state_label.text()

    def set_home_icon(self, icon: QIcon) -> None:
        self._home_button.setIcon(icon)

    def set_admin_icon(self, icon: QIcon) -> None:
        self._admin_button.setIcon(icon)

    def set_admin_unlocked(self, unlocked: bool) -> None:
        self._admin_button.setText("Uzamknout" if unlocked else "Administrace")
        self._admin_button.setProperty(
            "adminState", "unlocked" if unlocked else "locked"
        )
        self._admin_button.style().unpolish(self._admin_button)
        self._admin_button.style().polish(self._admin_button)

    def apply_metrics(self, metrics: UiMetrics) -> None:
        self.setFixedHeight(metrics.header_height)
        layout = self.layout()
        layout.setContentsMargins(metrics.margin, 0, metrics.margin, 0)
        layout.setSpacing(metrics.normal_gap)
        control_height = metrics.control_height - metrics.px(6)
        group_layout = self._status_group.layout()
        group_layout.setContentsMargins(
            metrics.px(10), 0, metrics.px(10), 0
        )
        group_layout.setSpacing(metrics.px(10))
        right_layout = self._right_group.layout()
        right_layout.setSpacing(metrics.normal_gap)
        for widget in (self._home_button, self._status_group, self._admin_button):
            widget.setMinimumHeight(control_height)
            widget.setMaximumHeight(control_height)


class _ClickableFrame(QFrame):
    clicked = Signal()

    def mousePressEvent(self, event) -> None:  # noqa: N802, ANN001 - Qt API
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)
