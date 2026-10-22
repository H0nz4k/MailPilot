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
    available_cooking_calendars, resolve_task_date, task_calendar_type,
)
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
    on_open_reports: Callable[[], None] | None = None,
) -> Callable:
    """Mount task management as a tab in the existing NiceGUI application."""
    path = task_file(Path(config_directory))
    active_config_path = Path(config_path) if config_path is not None else Path(config_directory) / "config.json"
    ui.label("Odesílání přehledů").classes("ds-page-title").props('role="heading" aria-level="1"')
    ui.label(
        "Použijte uložený přehled z Přehledů. Zde nastavíte, komu, kdy a za který den se má posílat."
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
                date_label = f"Den přehledu: {DATE_MODES[task.date_mode]}"
                if task.date_mode == "next_cooking_day":
                    try:
                        calendar_name = task_calendar_type(active_config_path, task)
                        date_label += f" · kalendář: {calendar_name}"
                        if task.cooking_meal_type is None:
                            date_label += " (dosavadní nastavení)"
                    except (OSError, ValueError):
                        date_label += " · vyberte kalendář v úpravě odesílání"
                ui.label(date_label)
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
                        ui.label(f"Příští odeslání: {upcoming:%d.%m.%Y %H:%M}; přehled za {report_date:%d.%m.%Y}")
                    except Exception as exc:
                        ui.label(
                            f"Příští odeslání: {upcoming:%d.%m.%Y %H:%M}; "
                            f"den přehledu nelze určit: {exc}"
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
        if task and task.date_mode == "next_cooking_day" and calendar_value is None:
            try:
                calendar_value = task_calendar_type(active_config_path, task)
            except (OSError, ValueError) as exc:
                ui.notify(f"Dosavadní kalendář nelze načíst: {exc}", type="negative")
                return
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
                with ui.expansion("Co přehled obsahuje?", icon="info_outline").classes("w-full ds-profile-details"):
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
                catalog = {"names": None, "busy": False}
                with ui.column().classes("w-full gap-1").bind_visibility_from(
                    mode, "value", backward=lambda value: value == "next_cooking_day"
                ):
                    calendar = ui.select(
                        {calendar_value: calendar_value} if calendar_value else {},
                        label="Kalendář varných dnů", value=calendar_value,
                    ).props("outlined dense").classes("w-full")
                    ui.label("Podle této stravy určíme další varný den. Obsah vybraného přehledu se tím nemění.").classes("ui-help")
                    calendar_status = ui.label("").classes("ui-help").props('role="status" aria-live="polite"')

                    async def load_calendars():
                        if catalog["busy"] or not dialog.value:
                            return
                        catalog["busy"] = True
                        reload_calendars.disable()
                        calendar_status.set_text("Načítám kalendáře z Jídelny…")
                        try:
                            names = await run.io_bound(available_cooking_calendars, active_config_path)
                            if not dialog.value:
                                return
                            catalog["names"] = {name.casefold() for name in names}
                            current = calendar.value
                            canonical = next((name for name in names if current and name.casefold() == current.casefold()), current)
                            options = {name: name for name in names}
                            if canonical and canonical not in options:
                                options[canonical] = f"{canonical} – kalendář nenalezen"
                            calendar.set_options(options, value=canonical)
                            calendar_status.set_text("" if names else "V Jídelně nejsou pro letošní ani příští rok nastavené varné dny. Doplňte je v Jídelně a načtěte nabídku znovu.")
                        except Exception:
                            if dialog.value:
                                calendar_status.set_text("Kalendáře se nepodařilo načíst. Ověřte připojení k Jídelně a zkuste načtení znovu.")
                        finally:
                            catalog["busy"] = False
                            reload_calendars.enable()

                    reload_calendars = ui.button("Načíst kalendáře", icon="refresh", on_click=load_calendars).props("flat no-caps dense")
                    def clear_calendar_error(_event):
                        if calendar.props.get("error"):
                            calendar.props(remove="error error-message")
                            calendar_status.set_text("")

                    calendar.on_value_change(clear_calendar_error)

                def request_calendars(_event=None):
                    if mode.value == "next_cooking_day" and catalog["names"] is None:
                        ui.timer(0.01, load_calendars, once=True)

                mode.on_value_change(request_calendars)
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
                        if mode.value == "next_cooking_day":
                            problem = ""
                            if not calendar.value:
                                problem = "Vyberte kalendář varných dnů pro toto odesílání."
                            elif catalog["names"] is not None and calendar.value.casefold() not in catalog["names"]:
                                problem = "Pro vybranou stravu není v Jídelně nastavený kalendář. Vyberte jiný nebo ho doplňte v Jídelně."
                            if problem:
                                calendar.props["error"] = True
                                calendar.props["error-message"] = problem
                                calendar_status.set_text(problem)
                                calendar.run_method("focus")
                                return
                        new = MailTask.from_dict({
                            "id": str(uuid4()) if duplicate or task is None else task.id,
                            "name": name.value, "recipients": recipients.addresses,
                            "report": "daily", "send_time": time.value,
                            "date_mode": mode.value, "day_offset": offset.value,
                            "fixed_date": fixed.value, "enabled": enabled.value,
                            "profile_id": profile.value or None,
                            "cooking_meal_type": calendar.value or None,
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
        request_calendars()

    with ui.row():
        ui.button("Nové odesílání", icon="add", on_click=lambda: editor()).props("color=primary")
        ui.button("Obnovit", icon="refresh", on_click=table.refresh).props("outline")
        if on_open_reports:
            ui.button("Přejít do Přehledů", icon="today", on_click=on_open_reports).props("flat no-caps")
    table()
    return editor

