"""Visible, validated recipients shared by customer-facing mail forms."""
from __future__ import annotations

import re
from collections.abc import Sequence

from nicegui import ui

from mail_service import normalize_recipients


class RecipientEditor:
    def __init__(self, addresses: Sequence[str] = ()) -> None:
        self.addresses = list(addresses)
        with ui.column().classes("ds-recipient-editor w-full gap-2"):
            ui.label("Komu posílat?").classes("app-label")
            self.chips = ui.row().classes("ds-recipient-chips w-full gap-2").props('role="list" aria-label="Přidaní příjemci"')
            with ui.row().classes("ds-recipient-entry w-full items-start gap-2 no-wrap"):
                self.input = ui.input(placeholder="např. vedouci@jidelna.cz").props('outlined dense type=email aria-label="E-mail příjemce"').classes("flex-grow min-w-0")
                self.input.on("keydown.enter", self.commit_pending)
                ui.button("Přidat", icon="add", on_click=self.commit_pending).props("outline no-caps")
            self.status = ui.label("").classes("ui-help").props('role="status" aria-live="polite"')
        self.render()

    def commit_pending(self) -> bool:
        text = str(self.input.value or "").strip()
        if not text:
            return True
        try:
            addresses = normalize_recipients([a for a in re.split(r"[\s,;]+", text) if a])
        except ValueError:
            self.input.props["error"] = True
            self.input.props["error-message"] = "Zkontrolujte e-mailovou adresu."
            self.input.update()
            self.status.set_text("Adresa nebyla přidána. Opravte ji a zvolte Přidat.")
            return False
        existing = {a.casefold() for a in self.addresses}
        added = [a for a in addresses if a.casefold() not in existing]
        self.addresses.extend(added)
        self.input.value = ""
        self.input.props(remove="error error-message")
        self.input.update()
        self.status.set_text("Příjemce přidán." if added else "Tento příjemce už je přidaný.")
        self.render()
        return True

    def remove(self, address: str) -> None:
        if address not in self.addresses:
            return
        self.addresses.remove(address)
        self.status.set_text("Příjemce odebrán.")
        self.render()

    def render(self) -> None:
        self.chips.clear()
        self.chips.set_visibility(bool(self.addresses))
        with self.chips:
            for address in self.addresses:
                with ui.row().classes("ds-recipient-chip items-center no-wrap").props('role="listitem"'):
                    ui.icon("check_circle").props('aria-hidden="true"')
                    ui.label(address).classes("min-w-0")
                    ui.button(icon="close", on_click=lambda _e, a=address: self.remove(a)).props("flat round").props(f'aria-label="Odebrat příjemce {address}"')
