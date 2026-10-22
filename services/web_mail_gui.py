"""NiceGUI editor for independently scheduled MailPilot reports.

This screen edits persistent task definitions; saving never sends mail.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

from nicegui import ui

from services.web_mail_task_store import load_tasks, save_tasks, task_file
from services.web_mail_tasks import MailTask, next_send_at
from services.web_mail_cooking_days import resolve_task_date
from services.web_daily_profiles import load_profiles, profile_file
from services.web_recipient_editor import RecipientEditor

REPORTS = {"daily": "Denní PDF přehled", "meal_summary": "Původní souhrn (nepodporováno)"}
LEGACY_PROFILE_LABEL = "Dosavadní společné nastavení"
DATE_MODES = {
    "today": "Dnes", "tomorrow": "Zítra", "offset": "Posun o X dní",
    "next_cooking_day": "Následující varný den", "fixed": "Konkrétní datum",
}


def build_mail_tasks_panel(
    config_directory: Path, config_path: Path | None = None,
    category_names: Callable[[], dict[str, str]] | None = None,
) -> None:
    """Mount task management as a tab in the existing NiceGUI application."""
    path = task_file(Path(config_directory))
    active_config_path = Path(config_path) if config_path is not None else Path(config_directory) / "config.json"
    ui.label("Pravidelné odesílání").classes("app-heading")
    ui.label(
        "Nastavte, komu a kdy se má přehled posílat."
    ).classes("ui-help")
    def read():
        try:
            return load_tasks(path)
        except (OSError, ValueError) as exc:
            ui.notify(f"Nelze načíst úlohy: {exc}", type="negative")
            return None

    def profile_options():
        return {
            p.id: p.name for p in load_profiles(profile_file(Path(config_directory)))
        }

    @ui.refreshable
    def table():
        tasks = read()
        if tasks is None:
            return
        if not tasks:
            ui.label("Zatím nemáte nastavené žádné odesílání.").classes("ui-help")
        for task in tasks:
            with ui.card().classes("w-full"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(task.name).classes("text-subtitle1")
                    ui.badge("Nelze odeslat" if task.report != "daily" else "Aktivní" if task.enabled else "Vypnutá")
                ui.label(f"{REPORTS[task.report]} · {task.send_time} · {', '.join(task.recipients)}")
                ui.label(f"Datum sestavy: {DATE_MODES[task.date_mode]}")
                if task.profile_id:
                    try:
                        label = profile_options().get(task.profile_id, "Chybějící přehled – upravte úlohu")
                    except (OSError, ValueError) as exc:
                        label = f"Přehled nelze načíst: {exc}"
                    ui.label(f"Odesílaný přehled: {label}")
                elif task.report == "daily":
                    ui.label(f"Odesílaný přehled: {LEGACY_PROFILE_LABEL}")
                upcoming = next_send_at(task, datetime.now())
                if upcoming:
                    try:
                        report_date = resolve_task_date(active_config_path, task, upcoming.date())
                        ui.label(f"Další běh: {upcoming:%d.%m.%Y %H:%M}; sestava za {report_date:%d.%m.%Y}")
                    except Exception as exc:
                        ui.label(
                            f"Další běh: {upcoming:%d.%m.%Y %H:%M}; "
                            f"datum sestavy nelze určit: {exc}"
                        )
                with ui.row().classes("gap-2"):
                    ui.button("Upravit", on_click=lambda t=task: editor(t)).props("outline")
                    ui.button("Kopírovat", on_click=lambda t=task: editor(t, duplicate=True)).props("outline")
                    ui.button(
                        "Vypnout" if task.enabled else "Zapnout",
                        on_click=lambda t=task: set_enabled(t),
                    ).props("outline")
                    ui.button("Smazat", on_click=lambda t=task: confirm_delete(t)).props("outline color=negative")

    def persist(items):
        try:
            save_tasks(path, items)
        except (OSError, ValueError) as exc:
            ui.notify(f"Uložení selhalo: {exc}", type="negative")
            return False
        table.refresh()
        ui.notify("Úlohy byly uloženy.", type="positive")
        return True

    def set_enabled(task):
        if task.report != "daily" and not task.enabled:
            ui.notify("Nejprve úlohu upravte a vyberte přehled k odesílání.", type="warning")
            return
        tasks = read()
        if tasks is None:
            return
        persist([replace(t, enabled=not t.enabled) if t.id == task.id else t for t in tasks])

    def confirm_delete(task):
        with ui.dialog() as dialog, ui.card():
            ui.label(f"Opravdu smazat úlohu „{task.name}“?")
            with ui.row():
                ui.button("Zrušit", on_click=dialog.close).props("flat")
                def remove():
                    tasks = read()
                    if tasks is not None and persist([t for t in tasks if t.id != task.id]):
                        dialog.close()
                ui.button("Smazat", on_click=remove).props("color=negative")
        dialog.open()

    def editor(task=None, duplicate=False):
        try:
            saved_profiles = {p.id: p for p in load_profiles(profile_file(Path(config_directory)))}
        except (OSError, ValueError) as exc:
            ui.notify(f"Přehledy nelze načíst: {exc}", type="negative")
            return
        profiles = {key: p.name for key, p in saved_profiles.items()}
        legacy_common = bool(task and task.report == "daily" and not task.profile_id)
        if legacy_common:
            profiles = {"": LEGACY_PROFILE_LABEL, **profiles}
        if task and task.profile_id and task.profile_id not in profiles:
            profiles[task.profile_id] = "Chybějící přehled – vyberte jiný"
        if not profiles:
            ui.notify(
                "Nejprve v Denní stav → Moje přehledy vyberte kategorie, "
                "přehled pojmenujte a uložte. Potom ho zde vyberete k odesílání.",
                type="info", timeout=8000,
            )
            return
        with ui.dialog() as dialog, ui.card().classes("ds-mail-dialog"):
            ui.label("Kopírovat odesílání" if duplicate else "Upravit odesílání" if task else "Nové odesílání").classes("ds-dialog-title")
            with ui.column().classes("ds-dialog-body w-full"):
                name = ui.input("Název odesílání", placeholder="např. Obědy pro školku", value=(task.name + " – kopie" if duplicate else task.name) if task else "").props("outlined dense").classes("w-full")
                recipients = RecipientEditor(task.recipients if task else ())
                convert = None
                if task and task.report != "daily":
                    ui.label("Tato starší sestava se nedá odesílat. Vyberte uložený denní přehled.").classes("ui-help")
                    convert = ui.checkbox("Převést úlohu na odesílání vybraného přehledu")
                selected = (task.profile_id or "") if task and task.report == "daily" else (
                    next(iter(profiles)) if len(profiles) == 1 else None
                )
                profile = ui.select(profiles, label="Který přehled odesílat?", value=selected).props("outlined dense").classes("w-full")
                with ui.expansion("Co přehled obsahuje?", icon="info_outline").classes("w-full ds-profile-details"):
                    details = ui.label().classes("ui-help w-full")
                    ui.label("Obsah změníte v Denní stav → Moje přehledy.").classes("ui-help")

                def explain_profile():
                    chosen = saved_profiles.get(profile.value)
                    if chosen:
                        names = category_names() if category_names else {}
                        categories = ", ".join(names.get(code, code) for code in chosen.categories)
                        parts = [
                            f"Uložené kategorie: {categories}.",
                            f"Typ stravy: {chosen.meal_type or 'všechny typy'}.",
                            "Se seznamem strávníků." if chosen.show_diner_list else "Bez seznamu strávníků.",
                        ]
                        details.set_text(" ".join(parts))
                    elif profile.value == "" and legacy_common:
                        details.set_text(
                            "Tato starší úloha používá společné nastavení aplikace: "
                            "kategorie, typ stravy a obsah PDF. Žádný uložený přehled nevybírá."
                        )
                    elif profile.value:
                        details.set_text("Tento přehled byl odstraněn. Vyberte jiný uložený přehled.")
                    else:
                        details.set_text("Vyberte jeden z přehledů uložených v Denní stav → Moje přehledy.")

                profile.on_value_change(lambda _event: explain_profile())
                explain_profile()
                with ui.element("div").classes("ds-mail-schedule w-full"):
                    time = ui.input("V kolik hodin?", value=task.send_time if task else "08:00").props("outlined dense type=time").classes("w-full")
                    mode = ui.select(DATE_MODES, label="Za který den?", value=task.date_mode if task else "today").props("outlined dense").classes("w-full")
                offset = ui.number("Posun od dneška (dní)", value=task.day_offset if task else 0, step=1).props("outlined dense").classes("w-full")
                fixed = ui.input("Vybraný den", value=task.fixed_date or "" if task else date.today().isoformat()).props("outlined dense type=date").classes("w-full")
                offset.bind_visibility_from(mode, "value", backward=lambda value: value == "offset")
                fixed.bind_visibility_from(mode, "value", backward=lambda value: value == "fixed")
                enabled = ui.checkbox("Odesílat automaticky", value=task.enabled if task else True)
            with ui.row().classes("ds-dialog-footer w-full justify-end"):
                ui.button("Zrušit", on_click=dialog.close).props("flat")
                def save():
                    tasks = read()
                    if tasks is None:
                        return
                    if not recipients.commit_pending():
                        return
                    try:
                        if convert is not None and not convert.value:
                            raise ValueError("Potvrďte převod na odesílání vybraného přehledu.")
                        if not profile.value and not (legacy_common and profile.value == ""):
                            raise ValueError("Vyberte přehled k odesílání.")
                        new = MailTask.from_dict({
                            "id": str(uuid4()) if duplicate or task is None else task.id,
                            "name": name.value, "recipients": recipients.addresses,
                            "report": "daily", "send_time": time.value,
                            "date_mode": mode.value, "day_offset": offset.value,
                            "fixed_date": fixed.value, "enabled": enabled.value,
                            "profile_id": profile.value or None,
                        })
                        if new.profile_id and new.profile_id not in profile_options():
                            raise ValueError("Vyberte existující uložený přehled.")
                    except (OSError, ValueError, TypeError) as exc:
                        ui.notify(f"Neplatná úloha: {exc}", type="negative")
                        return
                    items = [t for t in tasks if t.id != new.id] + [new]
                    if persist(items):
                        dialog.close()
                ui.button("Uložit", on_click=save).props("color=primary")
        dialog.open()

    with ui.row():
        ui.button("Nové odesílání", icon="add", on_click=lambda: editor()).props("color=primary")
        ui.button("Obnovit", icon="refresh", on_click=table.refresh).props("outline")
    table()

