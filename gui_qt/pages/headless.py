"""Administrace → Bez GUI: příkazy pro běh bez okna."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGridLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from gui_qt.theme import UiMetrics
from gui_qt.widgets.common import (
    ghost_button,
    hint,
    page_body,
    scroll_area,
    section_label,
    section_title,
)
from services.environment import cli_commands


class HeadlessPage(QWidget):
    """Přehled příkazů; kopírování zajišťuje controller přes schránku."""

    copy_requested = Signal(str)

    def __init__(self, metrics: UiMetrics, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        content, layout = page_body(metrics, "Bez GUI", max_width=980)
        layout.addWidget(
            hint(
                "Stejná aplikace umí běžet bez okna, takže ji lze spouštět z "
                "plánovače úloh Windows nebo z dávkového souboru. Příkazy "
                "používají stejné nastavení i databázi jako okno."
            )
        )
        layout.addWidget(section_label("Příkazy"))

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(metrics.normal_gap)
        grid.setVerticalSpacing(metrics.small_gap)
        row = 0
        for command in cli_commands():
            grid.addWidget(section_title(command.label), row, 0, 1, 2)
            row += 1

            field = QLineEdit(command.command)
            field.setReadOnly(True)
            field.setMinimumWidth(metrics.px(320))
            field.setMaximumWidth(metrics.px(440))
            field.setCursorPosition(0)
            copy = ghost_button("Kopírovat")
            copy.clicked.connect(
                lambda _checked=False, text=command.command: self.copy_requested.emit(
                    text
                )
            )
            grid.addWidget(field, row, 0)
            grid.addWidget(copy, row, 1)
            row += 1

            grid.addWidget(hint(command.description), row, 0, 1, 2)
            row += 1
            grid.addWidget(hint(f"Log: {command.log}"), row, 0, 1, 2)
            row += 1
        grid.setColumnStretch(2, 1)
        layout.addLayout(grid)

        layout.addStretch(1)
        layout.addWidget(
            hint(
                "Denní stav si v režimu bez GUI vždy bere dnešní datum, ne "
                "datum uložené v nastavení."
            )
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(scroll_area(content, self, metrics))
