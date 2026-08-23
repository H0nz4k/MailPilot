"""Malé stavební prvky formulářů: nadpisy, oddělovače, nápovědy."""

from __future__ import annotations

from typing import Sequence

from PySide6.QtCore import QSize, Qt, QTime, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gui_qt.theme import UiMetrics


class ElidedLabel(QLabel):
    """Text, který se při nedostatku místa zkrátí výpustkou."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._full_text = text
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API
        self._full_text = text
        super().setText(text)
        self.updateGeometry()

    def full_text(self) -> str:
        return self._full_text

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API
        metrics = self.fontMetrics()
        return QSize(metrics.horizontalAdvance("…"), metrics.height())

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API
        metrics = self.fontMetrics()
        return QSize(
            metrics.horizontalAdvance(self._full_text), metrics.height()
        )

    def paintEvent(self, event) -> None:  # noqa: N802, ANN001 - Qt API
        painter = QPainter(self)
        painter.setPen(self.palette().color(self.foregroundRole()))
        metrics = painter.fontMetrics()
        text = metrics.elidedText(self._full_text, Qt.ElideRight, self.width())
        painter.drawText(
            self.rect(), int(self.alignment() | Qt.AlignVCenter), text
        )


class StatusDot(QFrame):
    """Malá barevná tečka; barvu určuje QSS podle vlastnosti ``role``."""

    SIZE = 10

    def __init__(
        self, parent: QWidget | None = None, metrics: UiMetrics | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("StatusDot")
        size = self.SIZE if metrics is None else metrics.px(self.SIZE)
        self.setFixedSize(size, size)

    def set_state(self, role: str) -> None:
        """``statusOk``, ``statusError`` nebo prázdná hodnota pro neutrální."""
        self.setProperty("role", role)
        self.style().unpolish(self)
        self.style().polish(self)


class SegmentedNav(QWidget):
    """Vodorovná lokální navigace uvnitř obsahu.

    Nahrazuje druhý trvalý sidebar: položky jsou tlačítka s podtrženou
    aktivní volbou, takže i při 160 % zůstane obsah co nejširší.
    """

    section_selected = Signal(str)

    def __init__(
        self,
        items: Sequence[tuple[str, str]],
        metrics: UiMetrics,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SegmentedBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(metrics.small_gap)
        self._buttons: dict[str, QPushButton] = {}
        self._current = ""
        for key, label in items:
            button = QPushButton(label, self)
            button.setProperty("segment", "true")
            button.setProperty("active", "false")
            button.setCheckable(False)
            button.setCursor(Qt.PointingHandCursor)
            button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            button.clicked.connect(
                lambda _checked=False, value=key: self.select(value)
            )
            layout.addWidget(button)
            self._buttons[key] = button
        layout.addStretch(1)

    def select(self, key: str, *, notify: bool = True) -> None:
        if key not in self._buttons:
            return
        self._current = key
        for name, button in self._buttons.items():
            button.setProperty("active", "true" if name == key else "false")
            button.style().unpolish(button)
            button.style().polish(button)
        if notify:
            self.section_selected.emit(key)

    def current_key(self) -> str:
        return self._current

    def keys(self) -> tuple[str, ...]:
        return tuple(self._buttons)


class SmartTimeEdit(QLineEdit):
    """Textové pole času (např. 800 -> 8:00), výchozí stav je prázdný."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._time = QTime(0, 0)
        self.setPlaceholderText("hh:mm")
        self.editingFinished.connect(self._normalize_short_time)

    def focusInEvent(self, event) -> None:  # noqa: N802, ANN001 - Qt API
        super().focusInEvent(event)
        self.selectAll()

    def _set_empty(self) -> None:
        self._time = QTime(0, 0)
        self.clear()

    def _normalize_short_time(self) -> None:
        text = self.text().strip().replace(" ", "")
        if not text:
            self._set_empty()
            return
        parsed = QTime.fromString(text, "H:mm")
        if not parsed.isValid():
            parsed = QTime.fromString(text, "H:m")
        if not parsed.isValid() and text.isdigit():
            digits = text.lstrip("0") or "0"
            if len(digits) <= 2:
                hour = int(digits)
                minute = 0
            elif len(digits) == 3:
                hour = int(digits[0])
                minute = int(digits[1:])
            else:
                hour = int(digits[:-2])
                minute = int(digits[-2:])
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                parsed = QTime(hour, minute)
        if parsed.isValid():
            self._time = parsed
            self.setText(parsed.toString("H:mm"))

    def time(self) -> QTime:
        return QTime(self._time.hour(), self._time.minute())

    def setTime(self, value: QTime) -> None:  # noqa: N802 - Qt API
        if not value.isValid():
            self._set_empty()
            return
        self._time = QTime(value.hour(), value.minute())
        self.setText(self._time.toString("H:mm"))


def page_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("PageTitle")
    return label


def section_label(text: str) -> QLabel:
    """Tichý nadpis sekce verzálkami; odděluje bloky bez rámečků."""
    label = QLabel(text.upper())
    label.setObjectName("SectionLabel")
    return label


def section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionTitle")
    return label


def field_label(text: str, buddy: QWidget | None = None) -> QLabel:
    """Popisek formulářového pole; bez mnemoniky, aby nebyl podtržený."""
    label = QLabel(text)
    label.setProperty("role", "fieldLabel")
    label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    if buddy is not None:
        label.setBuddy(buddy)
    return label


def allow_wrapping(label: QLabel) -> QLabel:
    """Zalamovaný popisek si v layoutu vynutí výšku podle šířky.

    Bez zapnutého ``heightForWidth`` počítá layout výšku jen na jeden
    řádek a delší text se ořízne.
    """
    label.setWordWrap(True)
    policy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
    policy.setHeightForWidth(True)
    label.setSizePolicy(policy)
    return label


def hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "hint")
    return allow_wrapping(label)


def elided_hint(text: str = "") -> ElidedLabel:
    """Jednořádková poznámka, která se raději zkrátí, než by roztáhla okno."""
    label = ElidedLabel(text)
    label.setProperty("role", "hint")
    return label


def error_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "error")
    return allow_wrapping(label)


def wrapped_label(text: str, width: int) -> QLabel:
    """Odstavec pevné šířky, který se v layoutu nikdy neořízne."""
    label = QLabel(text)
    allow_wrapping(label)
    label.setFixedWidth(width)
    label.setMinimumHeight(label.heightForWidth(width))
    return label


def separator() -> QFrame:
    line = QFrame()
    line.setProperty("role", "separator")
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Plain)
    line.setFixedHeight(1)
    return line


def form_layout(metrics: UiMetrics) -> QFormLayout:
    layout = QFormLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setHorizontalSpacing(metrics.section_gap)
    layout.setVerticalSpacing(metrics.small_gap)
    layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
    layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
    layout.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
    return layout


def row(metrics: UiMetrics, *widgets: QWidget, stretch_last: bool = False) -> QWidget:
    """Vodorovná skupina prvků pro jeden řádek formuláře."""
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(metrics.normal_gap)
    for index, widget in enumerate(widgets):
        last = index == len(widgets) - 1
        layout.addWidget(widget, 1 if last and stretch_last else 0)
    if not stretch_last:
        layout.addStretch(1)
    return container


def size_input(widget: QWidget, metrics: UiMetrics, width: int) -> QWidget:
    """Pole s předvídatelnou šířkou, která roste se zvětšením rozhraní."""
    widget.setMinimumWidth(metrics.px(width))
    widget.setMaximumWidth(metrics.px(width))
    return widget


def size_choice(widget: QWidget, metrics: UiMetrics, width: int) -> QWidget:
    """Rozbalovací seznam: minimální šířka, delší text si prostor vezme."""
    widget.setMinimumWidth(metrics.px(width))
    if hasattr(widget, "setMaxVisibleItems"):
        widget.setMaxVisibleItems(32)
    return widget


def scroll_area(
    content: QWidget,
    parent: QWidget | None = None,
    metrics: UiMetrics | None = None,
) -> QScrollArea:
    """Posuvná oblast bez rámečku; pojistka pro malá rozlišení a 160 %."""
    scroll = QScrollArea(parent)
    scroll.setWidget(content)
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    # Bez výslovného minima si oblast vynutí celou minimální velikost
    # obsahu a okno by pak při 160 % nešlo zmenšit na 1366×768.
    if metrics is None:
        scroll.setMinimumSize(240, 140)
    else:
        scroll.setMinimumSize(metrics.px(240), metrics.px(140))
    return scroll


def page_body(
    metrics: UiMetrics, title: str = "", *, max_width: int = 0
) -> tuple[QWidget, QVBoxLayout]:
    """Obsah stránky s jednotnými okraji a volitelným nadpisem.

    ``max_width`` drží formuláře v čitelné šířce i na širokém monitoru;
    hodnota se uvádí pro 100 % a přepočítá se podle zvětšení.
    """
    content = QWidget()
    content.setObjectName("PageBody")
    if max_width:
        content.setMaximumWidth(metrics.px(max_width))
    layout = QVBoxLayout(content)
    layout.setContentsMargins(
        metrics.margin, metrics.normal_gap, metrics.margin, metrics.normal_gap
    )
    layout.setSpacing(metrics.section_gap)
    if title:
        layout.addWidget(page_title(title))
    return content, layout


def limited(widget: QWidget, width: int) -> QWidget:
    """Formulář v přirozené šířce; zbytek plochy zůstane volný."""
    widget.setMaximumWidth(width)
    return widget


def secondary_button(text: str) -> QPushButton:
    button = QPushButton(text)
    button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    return button


def primary_button(text: str) -> QPushButton:
    button = secondary_button(text)
    button.setProperty("emphasis", "primary")
    button.setDefault(True)
    return button


def ghost_button(text: str) -> QPushButton:
    """Nejnižší úroveň akce: bez rámečku, jen text."""
    button = secondary_button(text)
    button.setProperty("emphasis", "ghost")
    return button
