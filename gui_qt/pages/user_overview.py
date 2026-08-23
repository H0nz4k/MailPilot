"""User přehled automatického denního mailu."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QPlainTextEdit, QVBoxLayout, QWidget

from gui_qt.theme import UiMetrics
from gui_qt.widgets.common import (
    field_label,
    hint,
    page_body,
    primary_button,
    scroll_area,
    section_label,
)
from services.user_overview import AutoMailOverview


class UserOverviewPage(QWidget):
    resend_requested = Signal()

    def __init__(self, metrics: UiMetrics, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._metrics = metrics
        self._can_resend = False
        content, layout = page_body(metrics, "", max_width=720)
        layout.addWidget(section_label("Automatický denní mail"))
        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(metrics.small_gap)
        self._active = hint("Stav úlohy: —")
        self._jobs = hint("Aktivní úloha/úlohy: —")
        self._last_success = hint("Poslední odeslání: —")
        self._next_send = hint("Další odeslání: —")
        self._next_source = hint("Další odeslání podle úlohy: —")
        for widget in (
            self._active,
            self._jobs,
            self._last_success,
            self._next_send,
            self._next_source,
        ):
            info.addWidget(widget)
        layout.addLayout(info)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(metrics.normal_gap)
        actions.addWidget(field_label("Ruční akce"))
        self._resend = primary_button("Odeslat denní mail znovu")
        self._resend.clicked.connect(self.resend_requested.emit)
        actions.addWidget(self._resend)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addWidget(
            hint(
                "Ruční odeslání používá stejné nastavení jako automatická úloha "
                "(příjemci, varné dny, PDF)."
            )
        )
        layout.addWidget(section_label("Poslední chyby"))
        self._errors = QPlainTextEdit()
        self._errors.setReadOnly(True)
        self._errors.setMinimumHeight(metrics.px(120))
        self._errors.setMaximumHeight(metrics.px(170))
        self._errors.setMaximumWidth(metrics.px(420))
        layout.addWidget(self._errors)
        layout.addStretch(1)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(scroll_area(content, self, metrics))

    def set_overview(self, value: AutoMailOverview) -> None:
        if value.configured:
            state = "nastaveno"
            if value.enabled:
                state += " (aktivní)"
            else:
                state += " (vypnuto)"
        else:
            state = "nenastaveno"
        self._active.setText(f"Stav úlohy: {state}")
        self._jobs.setText(
            "Aktivní úloha/úlohy: " + (", ".join(value.job_names) if value.job_names else "—")
        )
        self._last_success.setText(f"Poslední odeslání: {value.last_success}")
        self._next_send.setText(f"Další odeslání: {value.next_send}")
        self._next_source.setText(
            f"Další odeslání podle úlohy: {value.next_send_from}"
        )
        self._errors.setPlainText("\n".join(value.errors) or "Žádné chyby.")
        self._can_resend = value.configured
        self._resend.setEnabled(value.configured)
        self._resend.setToolTip(
            "" if value.configured else "Nejprve vytvořte úlohu Denní stav v Administraci -> Plánovač."
        )

    def set_busy(self, busy: bool) -> None:
        self._resend.setEnabled(self._can_resend and not busy)
        if busy:
            self._resend.setText("Odesílám…")
        else:
            self._resend.setText("Odeslat denní mail znovu")

    def focus_default(self) -> None:
        self._resend.setFocus(Qt.OtherFocusReason)
