"""Dialog pro výběr kategorií strávníků."""

from __future__ import annotations

from typing import Iterable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from gui_qt.theme import UiMetrics
from gui_qt.widgets.common import ghost_button


class CategoryDialog(QDialog):
    """Zaškrtávací seznam s hledáním; zvládne i stovky kategorií."""

    def __init__(
        self,
        options: Sequence[tuple[str, str]],
        selected: Iterable[str],
        metrics: UiMetrics,
        parent: QWidget | None = None,
        *,
        title: str = "Výběr kategorií",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self._metrics = metrics
        self._selected = {str(code) for code in selected}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            metrics.margin, metrics.margin, metrics.margin, metrics.margin
        )
        layout.setSpacing(metrics.normal_gap)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Hledat kód nebo název…")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search)

        tools = QHBoxLayout()
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(metrics.small_gap)
        select_all = ghost_button("Vybrat vše")
        select_all.clicked.connect(lambda: self._set_visible_checked(True))
        clear_all = ghost_button("Zrušit vše")
        clear_all.clicked.connect(lambda: self._set_visible_checked(False))
        invert = ghost_button("Obrátit")
        invert.clicked.connect(self._invert_visible)
        tools.addWidget(select_all)
        tools.addWidget(clear_all)
        tools.addWidget(invert)
        tools.addStretch(1)
        self._summary = QLabel("")
        self._summary.setProperty("role", "hint")
        tools.addWidget(self._summary)
        layout.addLayout(tools)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setUniformItemSizes(True)
        self._list.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self._list, 1)

        self._buttons = QDialogButtonBox()
        apply_button = self._buttons.addButton(
            "Použít", QDialogButtonBox.AcceptRole
        )
        apply_button.setProperty("emphasis", "primary")
        apply_button.setDefault(True)
        self._buttons.addButton("Zrušit", QDialogButtonBox.RejectRole)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        self._fill(options)
        self._refresh_summary()
        self.resize(metrics.px(380), metrics.px(470))
        self._search.setFocus()

    def _fill(self, options: Sequence[tuple[str, str]]) -> None:
        self._list.blockSignals(True)
        for code, name in options:
            label = f"{code} — {name}" if name else code
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, code)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(
                Qt.Checked if code in self._selected else Qt.Unchecked
            )
            self._list.addItem(item)
        self._list.blockSignals(False)

    def _items(self) -> list[QListWidgetItem]:
        return [self._list.item(index) for index in range(self._list.count())]

    def _apply_filter(self, text: str) -> None:
        needle = text.strip().casefold()
        for item in self._items():
            item.setHidden(bool(needle) and needle not in item.text().casefold())
        self._refresh_summary()

    def _set_visible_checked(self, checked: bool) -> None:
        self._list.blockSignals(True)
        for item in self._items():
            if not item.isHidden():
                item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self._list.blockSignals(False)
        self._refresh_summary()

    def _invert_visible(self) -> None:
        self._list.blockSignals(True)
        for item in self._items():
            if item.isHidden():
                continue
            item.setCheckState(
                Qt.Unchecked if item.checkState() == Qt.Checked else Qt.Checked
            )
        self._list.blockSignals(False)
        self._refresh_summary()

    def _on_item_changed(self, _item: QListWidgetItem) -> None:
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        items = self._items()
        checked = sum(1 for item in items if item.checkState() == Qt.Checked)
        text = f"Vybráno: {checked} / {len(items)}"
        hidden = sum(1 for item in items if item.isHidden())
        if hidden:
            text += f" · filtr skrývá {hidden}"
        self._summary.setText(text)

    def selected_codes(self) -> tuple[str, ...]:
        """Vybrané kódy v pořadí, v jakém je zobrazuje seznam."""
        return tuple(
            str(item.data(Qt.UserRole))
            for item in self._items()
            if item.checkState() == Qt.Checked
        )
