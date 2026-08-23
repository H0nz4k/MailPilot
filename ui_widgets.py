"""Znovupoužitelné UI komponenty AutoReportu.

Modul obsahuje jen prezentační stavební prvky: hlavičky sekcí, formulářové
mřížky, stavové odznaky, dialogy a lišty akcí. Nezná databázi ani PDF, vše
podstatné dostane parametrem nebo callbackem.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence

from nicegui import ui

# ---------------------------------------------------------------------------
# Sekce a rozvržení
# ---------------------------------------------------------------------------


def card(*, gap: bool = True) -> Any:
    """Obal jedné logické sekce; vzhled řídí šablona (jemná / karta / bez)."""
    element = ui.element("div").classes("app-card")
    if not gap:
        element.style("gap: 0")
    return element


def section_header(title: str, help_text: str = "", icon: str = "") -> None:
    """Kompaktní hlavička sekce: ikona, název a jednořádková nápověda."""
    with ui.row().classes("section-header items-center gap-2 no-wrap"):
        if icon:
            with ui.element("div").classes(
                "section-icon flex items-center justify-center w-7 h-7 shrink-0"
            ):
                ui.icon(icon, size="1.15rem")
        with ui.column().classes("gap-0 min-w-0"):
            ui.label(title).classes("app-heading")
            if help_text:
                ui.label(help_text).classes("section-help truncate")
                if len(help_text) > 90:
                    ui.tooltip(help_text)


def form_grid(columns: int = 3) -> Any:
    """Formulářová mřížka, která se na menších šířkách sama zúží."""
    return ui.element("div").classes(f"form-grid form-grid-{max(1, min(4, columns))}")


def action_bar() -> Any:
    """Lišta hlavních akcí; v šablonách Compact a Dashboard je přilepená."""
    return ui.row().classes("action-bar")


def toolbar() -> Any:
    """Vodorovná řada ovládacích prvků s jednotnými rozestupy."""
    return ui.row().classes("summary-line items-center")


# ---------------------------------------------------------------------------
# Stav a nápověda
# ---------------------------------------------------------------------------


def status_pill(text: str, *, ok: bool = True) -> Any:
    """Barevný odznak stavu s tečkou; vrací popisek pro pozdější změnu textu."""
    modifier = "status-pill-ok" if ok else "status-pill-bad"
    with ui.element("span").classes(f"status-pill {modifier}"):
        ui.element("span").classes("status-dot")
        return ui.label(text)


def stat_card(label: str, value: str) -> Any:
    """Dlaždice se stavovou hodnotou; vrací popisek hodnoty."""
    with ui.element("div").classes("stat-card"):
        ui.label(label).classes("stat-card-label")
        return ui.label(value).classes("stat-card-value")


def hint(text: str) -> None:
    """Info ikona s nápovědou místo dlouhého odstavce pod prvkem."""
    if not text:
        return
    ui.icon("info_outline").classes("field-hint").tooltip(text)


def field_label(text: str, help_text: str = "") -> None:
    """Popisek nad skupinou prvků, volitelně s nápovědou."""
    with ui.row().classes("items-center gap-1 no-wrap"):
        ui.label(text).classes("app-label")
        hint(help_text)


# ---------------------------------------------------------------------------
# Formulářové prvky s jednotnou hustotou
# ---------------------------------------------------------------------------


def setting_switch(label: str, value: bool, help_text: str = "") -> Any:
    element = ui.switch(label, value=value).props("dense")
    if help_text:
        element.tooltip(help_text)
    return element


def setting_input(label: str, value: str, help_text: str = "", **kwargs: Any) -> Any:
    element = ui.input(label, value=value, **kwargs).props("dense").classes("w-full")
    if help_text:
        element.tooltip(help_text)
    return element


def setting_number(
    label: str,
    value: float,
    minimum: float,
    maximum: float,
    step: float,
    help_text: str = "",
) -> Any:
    element = (
        ui.number(label, value=value, min=minimum, max=maximum, step=step)
        .props("dense")
        .classes("w-full")
    )
    if help_text:
        element.tooltip(help_text)
    return element


def setting_select(
    label: str, options: dict[str, str], value: str, help_text: str = ""
) -> Any:
    element = (
        ui.select(options, label=label, value=value)
        .props("dense options-dense")
        .classes("w-full")
    )
    if help_text:
        element.tooltip(help_text)
    return element


def path_field(
    label: str,
    value: str,
    help_text: str,
    *,
    on_browse: Callable[[Any], None],
    grow: bool = True,
) -> Any:
    """Cesta k výstupu: pole, tlačítko Procházet a nápověda v tooltipu."""
    wrap = "flex-grow min-w-[260px]" if grow else "w-full"
    with ui.row().classes(f"{wrap} items-end gap-1 no-wrap"):
        element = ui.input(label, value=value).props("dense").classes("flex-grow")
        if help_text:
            element.tooltip(help_text)
        ui.button(
            icon="folder_open",
            on_click=lambda: on_browse(element),
        ).props("outline dense no-caps").tooltip("Procházet složky v počítači")
    return element


# ---------------------------------------------------------------------------
# Dialogy
# ---------------------------------------------------------------------------


def bind_dialog_enter(dialog: Any, on_enter: Callable[[], None]) -> None:
    """Enter potvrdí nebo zavře otevřený dialog."""

    def handle_key(event: Any) -> None:
        if not getattr(dialog, "value", False):
            return
        if not getattr(event.action, "keydown", False):
            return
        if getattr(event.modifiers, "shift", False):
            return
        key = event.key
        is_enter = bool(getattr(key, "enter", False)) or str(key) in {"Enter", "enter"}
        if is_enter:
            on_enter()

    keyboard = ui.keyboard(on_key=handle_key, ignore=[])
    dialog.on("hide", lambda: keyboard.delete())


def dialog_header(title: str, dialog: Any) -> None:
    with ui.row().classes("w-full items-center no-wrap"):
        ui.label(title).classes("app-heading")
        ui.space()
        ui.button(icon="close", on_click=dialog.close).props("flat round dense")


def open_info_dialog(title: str, lines: Sequence[str]) -> None:
    """Jednoduché kontextové okno; zavře se křížkem, OK i Enterem."""
    with ui.dialog() as dialog, ui.card().classes("w-[520px] max-w-[95vw] gap-2"):
        dialog_header(title, dialog)
        if lines:
            with ui.column().classes("w-full gap-0 max-h-[50vh] overflow-y-auto"):
                for line in lines:
                    ui.label(line).classes("app-text")
        else:
            ui.label("Seznam je prázdný.").classes("ui-help")
        with ui.row().classes("w-full justify-end"):
            ui.button("OK", on_click=dialog.close).props("no-caps unelevated")
    bind_dialog_enter(dialog, dialog.close)
    dialog.open()


def open_picker_dialog(
    *,
    title: str,
    options: Sequence[tuple[str, str]],
    selected: Sequence[str],
    label_for: Callable[[str, str], str],
    on_confirm: Callable[[list[str]], None],
    missing_by_code: dict[str, int] | None = None,
    empty_hint: str = "Nejdřív otestujte připojení k databázi.",
) -> None:
    """Zaškrtávací výběr s hledáním. Enter a OK uloží, křížek zruší."""
    pending = set(selected)
    checkboxes: dict[str, Any] = {}
    with ui.dialog() as dialog, ui.card().classes("w-[640px] max-w-[95vw] gap-2"):
        dialog_header(title, dialog)
        search = (
            ui.input(placeholder="Hledat označení nebo název")
            .props("clearable dense outlined")
            .classes("w-full")
        )
        with ui.row().classes("w-full items-center gap-2 no-wrap"):
            ui.button("Vybrat vše", on_click=lambda: apply_all(True)).props(
                "flat dense no-caps"
            )
            ui.button("Zrušit vše", on_click=lambda: apply_all(False)).props(
                "flat dense no-caps"
            )
            ui.space()
            count_label = ui.label("").classes("count-badge")
        list_box = ui.column().classes("w-full picker-dialog-list gap-0")

        def visible_options() -> list[tuple[str, str]]:
            query = str(search.value or "").casefold()
            rows: list[tuple[str, str]] = []
            for code, extra in options:
                label = label_for(code, extra)
                if (
                    query
                    and query not in code.casefold()
                    and query not in label.casefold()
                ):
                    continue
                rows.append((code, label))
            return rows

        def refresh_count() -> None:
            count_label.set_text(f"{len(pending)} / {len(options)}")

        def toggle(code: str, checked: bool) -> None:
            if checked:
                pending.add(code)
            else:
                pending.discard(code)
            refresh_count()

        def flip(code: str) -> None:
            checked = code not in pending
            toggle(code, checked)
            box = checkboxes.get(code)
            if box is not None:
                box.value = checked

        def apply_all(checked: bool) -> None:
            codes = [code for code, _label in visible_options()]
            if checked:
                pending.update(codes)
            else:
                pending.difference_update(codes)
            render_rows()

        def render_rows() -> None:
            checkboxes.clear()
            list_box.clear()
            rows = visible_options()
            with list_box:
                if not options:
                    ui.label(empty_hint).classes("p-3 ui-help")
                elif not rows:
                    ui.label("Nic neodpovídá hledání.").classes("p-3 ui-help")
                for code, label in rows:
                    missing = (
                        missing_by_code.get(code, 0)
                        if missing_by_code is not None
                        else None
                    )
                    with ui.row().classes(
                        "w-full items-center gap-2 px-2 py-0 app-row picker-row no-wrap"
                    ) as row:
                        row.on("click", lambda _event=None, item=code: flip(item))
                        box = ui.checkbox(value=code in pending).props("dense")
                        checkboxes[code] = box
                        ui.label(label).classes("flex-grow app-text truncate")
                        if missing is not None:
                            warn = missing > 0
                            ui.label(f"bez e-mailu: {missing}").classes(
                                "ui-help text-bad" if warn else "ui-help"
                            )
            refresh_count()

        def confirm() -> None:
            ordered = [code for code, _extra in options if code in pending]
            on_confirm(ordered)
            dialog.close()

        search.on("update:model-value", lambda: render_rows())
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Zrušit", on_click=dialog.close).props("flat no-caps")
            ui.button("Použít výběr", on_click=confirm).props("no-caps unelevated")
        render_rows()
    bind_dialog_enter(dialog, confirm)
    dialog.open()


async def confirm_dialog(
    *,
    title: str,
    message: str,
    detail: str = "",
    note: str = "",
    confirm_label: str = "Potvrdit",
    icon: str = "send",
) -> bool:
    """Potvrzení nebezpečné nebo nevratné operace."""
    with ui.dialog() as dialog, ui.card().classes("w-[480px] max-w-[95vw] gap-2"):
        ui.label(title).classes("app-heading")
        ui.label(message).classes("app-text")
        if detail:
            ui.label(detail).classes("ui-help")
        if note:
            ui.label(note).classes("ui-help")
        with ui.row().classes("w-full justify-end gap-2"):
            ui.button("Zrušit", on_click=lambda: dialog.submit(False)).props(
                "flat no-caps"
            )
            ui.button(
                confirm_label, icon=icon, on_click=lambda: dialog.submit(True)
            ).props("no-caps unelevated")
    return bool(await dialog)
