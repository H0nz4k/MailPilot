"""NiceGUI editor for independently scheduled MailPilot reports.

This screen edits persistent task definitions; saving never sends mail.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import Callable
from uuid import uuid4

from nicegui import run, ui

from services.web_mail_task_store import load_tasks, save_tasks, task_file
from services.web_mail_tasks import MailTask, next_send_at
from services.web_mail_cooking_days import (
    resolve_task_date, task_calendar_type, report_is_cooking_day,
)
from services.web_daily_profiles import load_profiles, profile_file
from services.web_recipient_editor import RecipientEditor

REPORTS = {"daily": "Denní PDF přehled", "meal_summary": "Původní souhrn (nepodporováno)"}
LEGACY_PROFILE_LABEL = "Dosavadní společné nastavení"
DATE_MODES = {
    "today": "Dnes", "tomorrow": "Zítra", "offset": "Za několik dní (např. pozítří)",
    "next_cooking_day": "Následující varný den", "fixed": "Konkrétní datum",
}


def build_mail_tasks_panel(
    config_directory: Path, config_path: Path | None = None,
    category_names: Callable[[], dict[str, str]] | None = None,
    on_open_reports: Callable[[], None] | None = None,
) -> Callable:
    """Mount task management as a tab in the existing NiceGUI application."""
    path = task_file(Path(config_directory))
    active_config_path = Path(config_path) if config_path is not None else Path(config_directory) / "config.json"
    ui.label("Odesílání přehledů").classes("ds-page-title").props('role="heading" aria-level="1"')
    ui.label(
        "1. Vyberte uložený přehled (typ stravy a vzhled PDF). "
        "2. Zadejte příjemce. 3. Nastavte čas a den přehledu, například 2 dny dopředu."
    ).classes("ui-help")
    def read():
        try:
            return load_tasks(path)
        except (OSError, ValueError) as exc:
            ui.notify(f"Nelze načíst odesílání: {exc}", type="negative")
            return None

    def profile_options():
        return {
            p.id: p.name for p in load_profiles(profile_file(Path(config_directory)))
        }

    from services.web_activity import activity_rows

    @ui.refreshable
    def table():
        tasks = read()
        if tasks is None:
            return
        if not tasks:
            ui.label("Zatím nemáte nastavené žádné odesílání.").classes("ui-help")
        latest = {}
        for event in activity_rows(config_directory):
            if event["task_id"]:
                latest.setdefault(event["task_id"], event)
        for task in tasks:
            with ui.card().classes("ds-mail-task w-full"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(task.name).classes("ds-task-title")
                    ui.badge("Nelze odeslat" if task.report != "daily" else "Aktivní" if task.enabled else "Vypnutá", color=None).classes("ds-task-badge")
                ui.label(f"Každý den v {task.send_time}").classes("ds-task-line")
                ui.label(f"Příjemci: {', '.join(task.recipients)}").classes("ds-task-line")
                date_label = f"Den přehledu: {DATE_MODES[task.date_mode]}"
                if task.date_mode == "offset":
                    date_label += f" · posun {task.day_offset:+d} dní od dneška"
                if task.date_mode == "fixed":
                    date_label += f" · {task.fixed_date}"
                if task.date_mode == "next_cooking_day":
                    try:
                        calendar_name = task_calendar_type(active_config_path, task)
                        date_label += f" · varné dny: {calendar_name or 'alespoň jeden typ stravy'}"
                        if not task.profile_id and task.cooking_meal_type is None:
                            date_label += " (dosavadní nastavení)"
                    except (OSError, ValueError):
                        date_label += " · vyberte kalendář v úpravě odesílání"
                ui.label(date_label)
                if task.only_cooking_days:
                    ui.label("Odeslat pouze, pokud je den přehledu varný; jinak přeskočit.").classes("ui-help")
                if task.profile_id:
                    try:
                        label = profile_options().get(task.profile_id, "Chybějící přehled – upravte odesílání")
                    except (OSError, ValueError) as exc:
                        label = f"Přehled nelze načíst: {exc}"
                    ui.label(f"Odesílaný přehled: {label}")
                elif task.report == "daily":
                    ui.label(f"Odesílaný přehled: {LEGACY_PROFILE_LABEL}")
                upcoming = next_send_at(task, datetime.now())
                if upcoming:
                    try:
                        report_date = resolve_task_date(active_config_path, task, upcoming.date())
                        cooking = report_is_cooking_day(active_config_path, task, report_date)
                        ui.label(f"Příští kontrola: {upcoming:%d.%m.%Y %H:%M}; přehled za {report_date:%d.%m.%Y}"
                                 + (" · přeskočí se: nevarný den" if not cooking else ""))
                    except Exception as exc:
                        ui.label(
                            f"Příští odeslání: {upcoming:%d.%m.%Y %H:%M}; "
                            f"den přehledu nelze určit: {exc}"
                        )
                event = latest.get(task.id)
                if event:
                    with ui.row().classes("w-full items-center gap-2").props('role="status"'):
                        ui.icon('error_outline' if event['kind'] == 'error' else 'skip_next' if event['kind'] == 'skipped' else 'check_circle', color='negative' if event['kind'] == 'error' else 'grey' if event['kind'] == 'skipped' else 'positive')
                        ui.label(f"{event['time'].replace('T', ' ')} · {event['message']}").style('overflow-wrap:anywhere')
                    if event['report_date']:
                        ui.label(f"Poslední přehled za {event['report_date']}").classes('ui-help')
                else:
                    ui.label('Poslední výsledek zatím není zaznamenán.').classes('ui-help')
                with ui.row().classes("ds-task-actions gap-2"):
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
        ui.notify("Odesílání bylo uloženo.", type="positive")
        return True

    def set_enabled(task):
        if task.report != "daily" and not task.enabled:
            ui.notify("Nejprve odesílání upravte a vyberte přehled k odesílání.", type="warning")
            return
        tasks = read()
        if tasks is None:
            return
        persist([replace(t, enabled=not t.enabled) if t.id == task.id else t for t in tasks])

    def confirm_delete(task):
        with ui.dialog() as dialog, ui.card():
            ui.label(f"Opravdu smazat odesílání „{task.name}“?")
            with ui.row():
                ui.button("Zrušit", on_click=dialog.close).props("flat")
                def remove():
                    tasks = read()
                    if tasks is not None and persist([t for t in tasks if t.id != task.id]):
                        dialog.close()
                ui.button("Smazat", on_click=remove).props("color=negative")
        dialog.open()

    def editor(task=None, duplicate=False, *, profile_id=None):
        try:
            saved_profiles = {p.id: p for p in load_profiles(profile_file(Path(config_directory)))}
        except (OSError, ValueError) as exc:
            ui.notify(f"Přehledy nelze načíst: {exc}", type="negative")
            return
        profiles = {key: p.name for key, p in saved_profiles.items()}
        if profile_id is not None and profile_id not in profiles:
            ui.notify("Tento přehled už není uložený. Vraťte se do Přehledů a uložte ho znovu.", type="warning")
            return
        legacy_common = bool(task and task.report == "daily" and not task.profile_id)
        if legacy_common:
            profiles = {"": LEGACY_PROFILE_LABEL, **profiles}
        if task and task.profile_id and task.profile_id not in profiles:
            profiles[task.profile_id] = "Chybějící přehled – vyberte jiný"
        if not profiles:
            with ui.dialog() as first_profile, ui.card().classes("ds-mail-dialog"):
                ui.label("Nejprve připravte přehled").classes("ds-dialog-title")
                with ui.column().classes("ds-dialog-body"):
                    ui.label("V Přehledech vyberte požadované počty a klikněte na Nastavit odesílání. Výběr se uloží a přenese sem.").classes("ui-help")
                with ui.row().classes("ds-dialog-footer w-full justify-end"):
                    ui.button("Zrušit", on_click=first_profile.close).props("flat no-caps")
                    if on_open_reports:
                        def prepare():
                            first_profile.close()
                            on_open_reports()
                        ui.button("Připravit přehled", on_click=prepare).props("no-caps unelevated").style("color: var(--ds-on-primary) !important")
            first_profile.open()
            return
        calendar_value = task.cooking_meal_type if task else None
        with ui.dialog() as dialog, ui.card().classes("ds-mail-dialog"):
            ui.label("Kopírovat odesílání" if duplicate else "Upravit odesílání" if task else "Nové odesílání").classes("ds-dialog-title")
            with ui.column().classes("ds-dialog-body w-full"):
                convert = None
                if task and task.report != "daily":
                    ui.label("Tato starší sestava se nedá odesílat. Vyberte uložený denní přehled.").classes("ui-help")
                    convert = ui.checkbox("Převést úlohu na odesílání vybraného přehledu")
                selected = (task.profile_id or "") if task and task.report == "daily" else (
                    profile_id if profile_id is not None else next(iter(profiles)) if len(profiles) == 1 else None
                )
                profile = ui.select(profiles, label="Uložený přehled", value=selected).props("outlined dense").classes("w-full")
                with ui.expansion("Typ stravy a obsah PDF", icon="info_outline", value=True).classes("w-full ds-profile-details"):
                    details = ui.label().classes("ui-help w-full")
                    ui.label("Stejný přehled najdete v Přehledech. Tam můžete upravit jeho obsah.").classes("ui-help")

                recipients = RecipientEditor(task.recipients if task else ())

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
                            "Toto starší odesílání používá společné nastavení aplikace: "
                            "kategorie, typ stravy a obsah PDF. Žádný uložený přehled nevybírá."
                        )
                    elif profile.value:
                        details.set_text("Tento přehled byl odstraněn. Vyberte jiný uložený přehled.")
                    else:
                        details.set_text("Vyberte jeden z přehledů uložených v Přehledech.")
                    if not task and (not name.value or name.value == automatic_name[0]):
                        automatic_name[0] = (chosen.name + " – odesílání") if chosen else ""
                        name.value = automatic_name[0]

                automatic_name = [""]
                with ui.expansion("Název odesílání", icon="edit").classes("w-full ds-profile-details"):
                    name = ui.input("Název odesílání", placeholder="např. Obědy pro školku", value=(task.name + " – kopie" if duplicate else task.name) if task else "").props("outlined dense").classes("w-full")
                profile.on_value_change(lambda _event: explain_profile())
                explain_profile()
                with ui.element("div").classes("ds-mail-schedule w-full"):
                    time = ui.input("V kolik hodin?", value=task.send_time if task else "08:00").props("outlined dense type=time").classes("w-full")
                    mode = ui.select(DATE_MODES, label="Za který den posílat?", value=task.date_mode if task else "today").props("outlined dense").classes("w-full")
                ui.label("Datum se při každém odeslání určí podle této volby. Datum náhledu z Přehledů se nepřebírá.").classes("ui-help")
                with ui.column().classes("w-full gap-1").bind_visibility_from(
                    mode, "value", backward=lambda value: value == "next_cooking_day"
                ):
                    ui.label("Varný den určíme podle typu stravy uloženého přehledu. Pro všechny typy použijeme nejbližší den, kdy se vaří alespoň jeden z nich.").classes("ui-help")
                offset = ui.number("Kolik dní dopředu? (2 = pozítří)", value=task.day_offset if task else 0, step=1).props("outlined dense").classes("w-full")
                ui.label("Například 2 znamená: dnes odešleme přehled na pozítří. Jde o kalendářní dny.").classes("ui-help").bind_visibility_from(mode, "value", backward=lambda value: value == "offset")
                fixed = ui.input("Vybraný den", value=task.fixed_date or "" if task else date.today().isoformat()).props("outlined dense type=date").classes("w-full")
                offset.bind_visibility_from(mode, "value", backward=lambda value: value == "offset")
                fixed.bind_visibility_from(mode, "value", backward=lambda value: value == "fixed")
                only_cooking = ui.checkbox("Odeslat jen tehdy, když se v den přehledu vaří", value=task.only_cooking_days if task else True)
                ui.label("Kontroluje cílové datum PDF, nikoli dnešek. Pro konkrétní stravu její kalendář; pro všechny typy alespoň jeden. Nevarný den se přeskočí, datum se neposouvá.").classes("ui-help")
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
                            "only_cooking_days": only_cooking.value,
                            "profile_id": profile.value or None,
                            "cooking_meal_type": calendar_value if legacy_common and not profile.value else None,
                        })
                        if new.profile_id and new.profile_id not in profile_options():
                            raise ValueError("Vyberte existující uložený přehled.")
                    except (OSError, ValueError, TypeError) as exc:
                        ui.notify(f"Odesílání nelze uložit: {exc}", type="negative")
                        return
                    items = [t for t in tasks if t.id != new.id] + [new]
                    if persist(items):
                        dialog.close()
                ui.button("Uložit", on_click=save).props("color=primary").style("color: var(--ds-on-primary) !important").mark("mail-task-save")
        dialog.open()

    with ui.row():
        ui.button("Nové odesílání", icon="add", on_click=lambda: editor()).props("color=primary").style("color: var(--ds-on-primary) !important")
        ui.button("Obnovit", icon="refresh", on_click=table.refresh).props("outline")
        if on_open_reports:
            ui.button("Přejít do Přehledů", icon="today", on_click=on_open_reports).props("flat no-caps")
    table()
    return editor


