"""User sekce: přehled automailu pro běžného uživatele."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from gui_qt.pages.user_overview import UserOverviewPage
from gui_qt.theme import UiMetrics
from services.user_overview import AutoMailOverview


class UserSettingsPage(QWidget):
    """Rychlá sekce pro běžného uživatele."""

    resend_requested = Signal()

    def __init__(self, metrics: UiMetrics, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(metrics.margin, metrics.normal_gap, metrics.margin, 0)
        layout.setSpacing(metrics.small_gap)

        self.overview_page = UserOverviewPage(metrics, self)
        layout.addWidget(self.overview_page, 1)
        self.overview_page.resend_requested.connect(self.resend_requested.emit)

    def set_overview(self, value: AutoMailOverview) -> None:
        self.overview_page.set_overview(value)

    def set_overview_busy(self, busy: bool) -> None:
        self.overview_page.set_busy(busy)

    def focus_default(self) -> None:
        self.overview_page.focus_default()
