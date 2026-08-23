"""Levý navigační panel hlavního okna."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QWidget

from gui_qt.icons import nav_icon
from gui_qt.theme import Palette, UiMetrics


SEPARATOR = "-"


@dataclass(frozen=True)
class NavItem:
    key: str
    label: str
    shortcut_hint: str = ""
    icon: str = ""


class NavigationSidebar(QListWidget):
    """Jednoúrovňová navigace; oddělovač odděluje administraci."""

    page_selected = Signal(str)

    def __init__(
        self,
        items: Sequence[NavItem],
        metrics: UiMetrics,
        parent: QWidget | None = None,
        *,
        object_name: str = "NavSidebar",
        palette: Palette | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setFrameShape(QListWidget.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setUniformItemSizes(False)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setIconSize(QSize(metrics.icon_size, metrics.icon_size))
        self.apply_metrics(metrics)
        self._populate(items, metrics, palette)
        self.currentItemChanged.connect(self._on_current_changed)

    def _populate(
        self,
        items: Sequence[NavItem],
        metrics: UiMetrics,
        palette: Palette | None,
    ) -> None:
        for item in items:
            if item.key == "help":
                spacer = QListWidgetItem("")
                spacer.setFlags(Qt.NoItemFlags)
                spacer.setSizeHint(QSize(0, metrics.normal_gap + 12))
                self.addItem(spacer)
            if item.key == SEPARATOR:
                widget_item = QListWidgetItem("")
                widget_item.setFlags(Qt.NoItemFlags)
                widget_item.setSizeHint(QSize(0, metrics.normal_gap + 4))
                self.addItem(widget_item)
                continue
            widget_item = QListWidgetItem(item.label)
            widget_item.setData(Qt.UserRole, item.key)
            if item.icon and palette is not None:
                widget_item.setIcon(
                    nav_icon(item.icon, palette, metrics.icon_size)
                )
            if item.shortcut_hint:
                widget_item.setToolTip(item.shortcut_hint)
            widget_item.setSizeHint(QSize(0, metrics.nav_item_height))
            self.addItem(widget_item)

    def apply_metrics(self, metrics: UiMetrics) -> None:
        self.setFixedWidth(metrics.sidebar_width)
        self.setIconSize(QSize(metrics.icon_size, metrics.icon_size))
        for index in range(self.count()):
            item = self.item(index)
            if item.flags() == Qt.NoItemFlags:
                item.setSizeHint(QSize(0, metrics.normal_gap + 4))
            else:
                item.setSizeHint(QSize(0, metrics.nav_item_height))

    def select(self, key: str) -> None:
        for index in range(self.count()):
            item = self.item(index)
            if item.data(Qt.UserRole) == key:
                self.setCurrentItem(item)
                return

    def current_key(self) -> str:
        item = self.currentItem()
        return "" if item is None else str(item.data(Qt.UserRole) or "")

    def _on_current_changed(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            return
        key = str(current.data(Qt.UserRole) or "")
        if key:
            self.page_selected.emit(key)
