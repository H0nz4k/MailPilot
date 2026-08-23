"""Administrace: jeden hlavní sidebar a lokální navigace uvnitř obsahu."""

from __future__ import annotations

from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from gui_qt.pages.advanced import AdvancedPage
from gui_qt.pages.appearance import AppearancePage
from gui_qt.pages.database import DatabasePage
from gui_qt.pages.headless import HeadlessPage
from gui_qt.pages.mail import MailPage
from gui_qt.pages.pdf import PdfPage
from gui_qt.pages.scheduler import SchedulerPage
from gui_qt.theme import Palette, UiMetrics
from gui_qt.widgets.common import SegmentedNav, separator


SECTION_DATABASE = "db"
SECTION_MAIL = "mail"
SECTION_SCHEDULER = "scheduler"
SECTION_PDF = "pdf"
SECTION_APPEARANCE = "appearance"
SECTION_HEADLESS = "headless"
SECTION_ADVANCED = "advanced"

SECTIONS = (
    (SECTION_DATABASE, "Databáze"),
    (SECTION_MAIL, "E-maily"),
    (SECTION_SCHEDULER, "Plánovač"),
    (SECTION_PDF, "PDF"),
    (SECTION_APPEARANCE, "Vzhled"),
    (SECTION_HEADLESS, "Bez GUI"),
    (SECTION_ADVANCED, "Pokročilé"),
)


class AdminPage(QWidget):
    """Řádek sekcí nahoře, pod ním jedna obrazovka na sekci."""

    def __init__(
        self,
        metrics: UiMetrics,
        parent: QWidget | None = None,
        *,
        palette: Palette,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(metrics.margin, metrics.normal_gap, metrics.margin, 0)
        layout.setSpacing(0)

        self.nav = SegmentedNav(SECTIONS, metrics, self)
        layout.addWidget(self.nav)
        layout.addWidget(separator())

        self.stack = QStackedWidget(self)
        layout.addWidget(self.stack, 1)

        self.database_page = DatabasePage(metrics, self)
        self.mail_page = MailPage(metrics, self)
        self.scheduler_page = SchedulerPage(metrics, self, palette=palette)
        self.pdf_page = PdfPage(metrics, self)
        self.appearance_page = AppearancePage(metrics, self)
        self.headless_page = HeadlessPage(metrics, self)
        self.advanced_page = AdvancedPage(metrics, self)
        self._pages = {
            SECTION_DATABASE: self.database_page,
            SECTION_MAIL: self.mail_page,
            SECTION_SCHEDULER: self.scheduler_page,
            SECTION_PDF: self.pdf_page,
            SECTION_APPEARANCE: self.appearance_page,
            SECTION_HEADLESS: self.headless_page,
            SECTION_ADVANCED: self.advanced_page,
        }
        self._indexes: dict[str, int] = {}
        for key, page in self._pages.items():
            self._indexes[key] = self.stack.addWidget(page)

        self.nav.section_selected.connect(self.show_section)
        self.nav.select(SECTION_DATABASE, notify=False)
        self.stack.setCurrentIndex(self._indexes[SECTION_DATABASE])

    def show_section(self, key: str) -> None:
        index = self._indexes.get(key)
        if index is None:
            return
        self.stack.setCurrentIndex(index)
        if self.nav.current_key() != key:
            self.nav.select(key, notify=False)

    def current_section(self) -> str:
        return self.nav.current_key()

    def current_widget(self) -> QWidget | None:
        return self.stack.currentWidget()

    def sections(self) -> tuple[str, ...]:
        return tuple(self._pages)

    def focus_section(self, key: str) -> None:
        page = self._pages.get(key)
        if page is not None and hasattr(page, "focus_default"):
            page.focus_default()
