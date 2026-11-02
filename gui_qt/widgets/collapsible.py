"""Sbalitelná sekce pro málo používaná nastavení."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QToolButton, QVBoxLayout, QWidget

from gui_qt.icons import CHEVRON_DOWN, CHEVRON_RIGHT, muted_icon
from gui_qt.theme import Palette, UiMetrics


class CollapsibleSection(QWidget):
    """Řádek s chevronem a skrytým obsahem; bez rámečku a bez animací."""

    toggled = Signal(bool)

    def __init__(
        self,
        title: str,
        metrics: UiMetrics,
        parent: QWidget | None = None,
        *,
        expanded: bool = False,
        palette: Palette | None = None,
    ) -> None:
        super().__init__(parent)
        self._palette = palette
        self._metrics = metrics
        self._toggle = QToolButton(self)
        self._toggle.setObjectName("SectionToggle")
        self._toggle.setText(title)
        self._toggle.setAccessibleName(title)
        self._toggle.setCheckable(True)
        self._toggle.setChecked(expanded)
        self._toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self._toggle.setIconSize(QSize(metrics.icon_size, metrics.icon_size))
        self._toggle.setAutoRaise(True)
        self._toggle.setFocusPolicy(Qt.StrongFocus)
        self._toggle.setCursor(Qt.PointingHandCursor)
        self._apply_arrow(expanded)
        self._set_accessibility_state(expanded)
        self._toggle.toggled.connect(self._on_toggled)

        self._content = QWidget(self)
        self._content.setVisible(expanded)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(metrics.normal_gap)
        layout.addWidget(self._toggle, 0, Qt.AlignLeft)
        layout.addWidget(self._content)

    @property
    def content(self) -> QWidget:
        """Widget, do kterého se vkládá obsah sekce."""
        return self._content

    def is_expanded(self) -> bool:
        return self._toggle.isChecked()

    def set_expanded(self, expanded: bool) -> None:
        self._toggle.setChecked(bool(expanded))

    def _apply_arrow(self, expanded: bool) -> None:
        if self._palette is None:
            self._toggle.setArrowType(
                Qt.DownArrow if expanded else Qt.RightArrow
            )
            return
        name = CHEVRON_DOWN if expanded else CHEVRON_RIGHT
        self._toggle.setIcon(
            muted_icon(name, self._palette, self._metrics.icon_size)
        )

    def _set_accessibility_state(self, expanded: bool) -> None:
        action = "Sbalit" if expanded else "Rozbalit"
        self._toggle.setToolTip(f"{action}: {self._toggle.text()}")
        self._toggle.setAccessibleDescription(
            "Rozbalená sekce. Aktivací sbalíte." if expanded
            else "Sbalená sekce. Aktivací rozbalíte."
        )

    def _on_toggled(self, checked: bool) -> None:
        self._apply_arrow(checked)
        self._set_accessibility_state(checked)
        self._content.setVisible(checked)
        self.toggled.emit(checked)
