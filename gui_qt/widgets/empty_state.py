"""Prázdný stav uvnitř tabulky, aby nezůstávala jen bílá plocha."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from gui_qt.icons import TABLE_EMPTY, muted_icon
from gui_qt.theme import Palette, UiMetrics
from gui_qt.widgets.common import allow_wrapping


class TableEmptyState(QWidget):
    """Vysvětlivka vykreslená přes výřez tabulky, dokud nejsou data."""

    def __init__(
        self,
        view: QAbstractItemView,
        metrics: UiMetrics,
        palette: Palette,
        title: str,
        hint_text: str,
    ) -> None:
        super().__init__(view.viewport())
        self._viewport = view.viewport()
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            metrics.normal_gap, metrics.small_gap, metrics.normal_gap, metrics.small_gap
        )
        layout.setSpacing(metrics.small_gap)
        layout.addStretch(1)

        icon_size = metrics.px(24)
        self._icon = QLabel(self)
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon.setPixmap(
            muted_icon(TABLE_EMPTY, palette, icon_size).pixmap(icon_size, icon_size)
        )
        layout.addWidget(self._icon)

        self._title = allow_wrapping(QLabel(title, self))
        self._title.setObjectName("EmptyStateTitle")
        self._title.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._title)

        self._hint = allow_wrapping(QLabel(hint_text, self))
        self._hint.setObjectName("EmptyStateHint")
        self._hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._hint)
        layout.addStretch(1)

        self._has_hint = bool(hint_text)
        self._viewport.installEventFilter(self)
        self.setGeometry(self._viewport.rect())
        self._fit()

    def set_message(self, title: str, hint_text: str = "") -> None:
        self._title.setText(title)
        self._hint.setText(hint_text)
        self._has_hint = bool(hint_text)
        self._fit()

    def _fit(self) -> None:
        """V nízké tabulce raději ubereme ozdoby, než abychom text ořízli."""
        available = self.height()
        if available <= 0:
            return
        self._icon.setVisible(True)
        self._hint.setVisible(self._has_hint)
        if self._needed() > available:
            self._icon.setVisible(False)
        if self._hint.isVisible() and self._needed() > available:
            self._hint.setVisible(False)

    def _needed(self) -> int:
        layout = self.layout()
        layout.invalidate()
        layout.activate()
        return layout.minimumSize().height()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        if watched is self._viewport and event.type() == QEvent.Resize:
            self.setGeometry(self._viewport.rect())
            self._fit()
        return super().eventFilter(watched, event)
