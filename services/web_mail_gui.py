"""NiceGUI editor for independently scheduled MailPilot reports.

This screen only edits persistent task definitions. Actual delivery is delegated
to the upcoming Windows scheduler service; saving never sends mail.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from nicegui import ui

from services.web_mail_task_store import load_tasks, save_tasks, task_file
from services.web_mail_tasks import MailTask, next_send_at
from services.web_mail_cooking_days import resolve_task_date
from services.web_daily_profiles import load_profiles, profile_file

REPORTS = {"daily": "Denní stav / počty", "meal_summary": "Souhrn počtu jídel"}
DATE_MODES = {
    "today": "Dnes", "tomorrow": "Zítra", "offset": "Posun o X dní",
    "next_cooking_day": "Následující varný den", "fixed": "Konkrétní datum",
}


def build_mail_tasks_panel(config_directory: Path, config_path: Path | None = None) -> None:
    """Mount task management as a tab in the existing NiceGUI application."""
    path = task_file(Path(config_directory))
    active_config_path = Path(config_path) if config_path is not None else Path(config_directory) / "config.json"
    ui.label("E-mailové úlohy").classes("text-h6")
    ui.label(
        "Každá úloha má vlastní příjemce, sestavu, čas a cílové datum. "
        "Automatické odesílání začne fungovat až po instalaci plánovací služby."
    ).classes("text-caption")
    with ui.row().classes("items-center gap-2"):
        ui.label(f"Konfigurace: {path}").classes("text-caption")
    def read():
        try:
            return load_tasks(path)
        except (OSError, ValueError) as exc:
            ui.notify(f"Nelze načíst úlohy: {exc}", type="negative")
            return None

    def profile_options():
        return {"": "Výchozí nastavení (všechny povolené kategorie)", **{
            p.id: p.name for p in load_profiles(profile_file(Path(config_directory)))
        }}

    @ui.refreshable
    def table():
        tasks = read()
        if tasks is None:
            return
        if not tasks:
            ui.label("Zatím nejsou vytvořeny žádné úlohy.")
        for task in tasks:
            with ui.card().classes("w-full"):
                with ui.row().classes("w-full items-center justify-between"):
                    ui.label(task.name).classes("text-subtitle1")
                    ui.badge("Aktivní" if task.enabled else "Vypnutá")
                ui.label(f"{REPORTS[task.report]} · {task.send_time} · {', '.join(task.recipients)}")
                ui.label(f"Datum sestavy: {DATE_MODES[task.date_mode]}")
                if task.profile_id:
                    try:
                        label = profile_options().get(task.profile_id, "Chybějící přehled – upravte úlohu")
                    except (OSError, ValueError) as exc:
                        label = f"Přehled nelze načíst: {exc}"
                    ui.label(f"Uložený přehled: {label}")
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
            profiles = profile_options()
        except (OSError, ValueError) as exc:
            ui.notify(f"Přehledy nelze načíst: {exc}", type="negative")
            return
        if task and task.profile_id and task.profile_id not in profiles:
            profiles[task.profile_id] = "Chybějící přehled – vyberte jiný"
        with ui.dialog() as dialog, ui.card().classes("w-full").style("min-width: min(90vw, 520px)"):
            ui.label("Kopírovat úlohu" if duplicate else "Upravit úlohu" if task else "Nová úloha").classes("text-h6")
            name = ui.input("Název", value=(task.name + " – kopie" if duplicate else task.name) if task else "").classes("w-full")
            recipients = ui.textarea("E-mailové adresy (čárka nebo nový řádek)", value=", ".join(task.recipients) if task else "").classes("w-full")
            report = ui.select(REPORTS, label="Sestava", value=task.report if task else "daily").classes("w-full")
            profile = ui.select(profiles, label="Uložený denní přehled", value=(task.profile_id or "") if task else "").classes("w-full")
            profile.bind_visibility_from(report, "value", backward=lambda value: value == "daily")
            time = ui.input("Čas odeslání (HH:MM)", value=task.send_time if task else "08:00").classes("w-full")
            mode = ui.select(DATE_MODES, label="Datum sestavy", value=task.date_mode if task else "today").classes("w-full")
            offset = ui.number("Posun (dní)", value=task.day_offset if task else 0, step=1).classes("w-full")
            fixed = ui.input("Konkrétní datum (YYYY-MM-DD)", value=task.fixed_date or "" if task else date.today().isoformat()).classes("w-full")
            enabled = ui.checkbox("Úloha aktivní", value=task.enabled if task else True)
            with ui.row():
                ui.button("Zrušit", on_click=dialog.close).props("flat")
                def save():
                    tasks = read()
                    if tasks is None:
                        return
                    try:
                        new = MailTask.from_dict({
                            "id": str(uuid4()) if duplicate or task is None else task.id,
                            "name": name.value, "recipients": [address.strip() for address in recipients.value.replace("\n", ",").split(",") if address.strip()],
                            "report": report.value, "send_time": time.value,
                            "date_mode": mode.value, "day_offset": offset.value,
                            "fixed_date": fixed.value, "enabled": enabled.value,
                            "profile_id": (profile.value or None) if report.value == "daily" else None,
                        })
                        if new.profile_id and new.profile_id not in profile_options():
                            raise ValueError("Vyberte existující uložený přehled.")
                    except (ValueError, TypeError) as exc:
                        ui.notify(f"Neplatná úloha: {exc}", type="negative")
                        return
                    items = [t for t in tasks if t.id != new.id] + [new]
                    if persist(items):
                        dialog.close()
                ui.button("Uložit", on_click=save).props("color=primary")
        dialog.open()

    with ui.row():
        ui.button("Nová úloha", icon="add", on_click=lambda: editor()).props("color=primary")
        ui.button("Obnovit", icon="refresh", on_click=table.refresh).props("outline")
    table()

