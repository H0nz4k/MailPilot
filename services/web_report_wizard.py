"""Four-step daily report creation. Saving config never sends an email."""
from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from uuid import uuid4

from nicegui import run, ui

from services.web_daily_profiles import save_profile
from services.web_mail_task_store import load_tasks, save_tasks, task_file
from services.web_mail_tasks import MailTask, next_send_at, target_date
from services.web_mail_cooking_days import available_cooking_calendars, resolve_task_date
from services.web_recipient_editor import RecipientEditor
from services.web_worker_status import observed_status
from services.web_meal_types import meal_filter_caption
from services.web_task_output import TaskOutputEditor
from services.web_controls import day_stepper

RULES = {"today": "Dnes", "tomorrow": "Zítra", "after_tomorrow": "Pozítří (2 dny dopředu)",
         "next_cooking_day": "Následující varný den", "offset": "Jiný počet dní dopředu"}
STEPS = ("Datum a strava", "Obsah a PDF", "Na který den", "E-mail a uložení")
WEEKDAYS = ("pondělí", "úterý", "středa", "čtvrtek", "pátek", "sobota", "neděle")


def preview_days(config_path, task, sent_on, upcoming):
    resolve = lambda day: resolve_task_date(config_path, task, day)
    current = resolve(sent_on)
    return current, current if upcoming == sent_on else resolve(upcoming)


def readable_day(day):
    return f"{WEEKDAYS[day.weekday()]} {day:%d.%m.%Y}"


class ReportWizardMixin:
    def _build_wizard_header(self):
        self._wizard_step = 1
        self._wizard_task_id = str(uuid4())
        self._wizard_profile_id = str(uuid4())
        self._wizard_saved = False
        self._wizard_revision = 0
        self._wizard_timer = None
        self._wizard_cards = []
        self._wizard_indicators = []
        with ui.element("div").classes("ds-wizard-progress w-full").props('aria-label="Postup vytvoření přehledu"'):
            for index, title in enumerate(STEPS, 1):
                with ui.row().classes("ds-wizard-indicator items-center no-wrap") as indicator:
                    ui.label(str(index)).classes("ds-wizard-number").props('aria-hidden="true"')
                    ui.label(title).classes("ds-wizard-step-title")
                self._wizard_indicators.append(indicator)
        self.wizard_heading = ui.label().classes("app-heading").props('role="heading" aria-level="2"')
        self.wizard_selection_caption = ui.label("").classes("ds-wizard-context")
        self.wizard_error = ui.label("").classes("text-negative").props('role="alert"')

    def _build_wizard_date(self):
        ui.label("Každý den připravit přehled na:").classes("app-heading")
        self.wizard_mode = ui.select(RULES, value="today", label="Den přehledu").props("outlined").classes("w-full")
        self.wizard_offset = day_stepper("Počet kalendářních dní dopředu", 2)
        self.wizard_offset.stepper_row.bind_visibility_from(self.wizard_mode, "value", backward=lambda mode: mode == "offset")
        self.wizard_offset.bind_visibility_from(self.wizard_mode, "value", backward=lambda mode: mode == "offset")
        ui.label("Dva dny dopředu znamená dva kalendářní dny. Následující varný den se určí podle kalendáře Jídelny.").classes("ui-help")
        self.wizard_only_cooking = ui.checkbox("Spustit jen tehdy, když se v den přehledu vaří", value=True)
        with ui.expansion("Jiný kalendář varných dnů (volitelné)", icon="event").classes("w-full"):
            ui.label("Kalendář určuje, kdy se vaří. Obsah PDF se tím nemění. Běžně použijeme stravu z prvního kroku; u více kalendářů stačí, aby se vařilo alespoň podle jednoho z nich.").classes("ui-help")
            self.wizard_calendar_mode = ui.select({"report": "Stejné typy stravy jako v přehledu", "all": "Kterýkoli kalendář Jídelny", "selected": "Jen kalendáře, které zvolím"}, value="report", label="Které varné dny použít?").props("outlined").classes("w-full")
            self.wizard_calendars = ui.select([], multiple=True, value=[], label="Kalendáře z Jídelny").props("outlined use-chips").classes("w-full")
            self.wizard_calendars.bind_visibility_from(self.wizard_calendar_mode, "value", backward=lambda mode: mode == "selected")
            self.wizard_calendar_status = ui.label("").classes("ui-help")
            ui.button("Načíst kalendáře", icon="refresh", on_click=self._wizard_load_calendars).props("outline no-caps")
        self.wizard_date_preview = ui.label("").classes("ds-wizard-preview").props('role="status" aria-live="polite"')
        for field in (self.wizard_mode, self.wizard_offset, self.wizard_only_cooking,
                      self.wizard_calendar_mode, self.wizard_calendars):
            field.on_value_change(lambda _e: self._wizard_queue_preview())

    def _build_wizard_email(self):
        self.wizard_name = ui.input("Název úlohy", value="Nový přehled").props("outlined maxlength=80").classes("w-full")
        self.wizard_output = TaskOutputEditor(self.config_path.parent)
        self.wizard_recipients = self.wizard_output.recipients
        self.wizard_time = ui.input("Každý den odeslat v", value="08:00").props("outlined type=time").classes("w-full")
        self.wizard_enabled = ui.checkbox("Zapnout automatické odesílání", value=True)
        self.wizard_time.on_value_change(lambda _e: self._wizard_queue_preview())
        self.wizard_final_preview = ui.label("").classes("ds-wizard-preview").props('role="status" aria-live="polite"')
        self.wizard_save_help = ui.label("").classes("ui-help")
        self.wizard_output.pdf_only.on_value_change(lambda _event: self._wizard_output_changed())
        for field in (self.wizard_output.directory, self.wizard_output.filename):
            field.on_value_change(lambda _event: self._wizard_queue_preview())
        self._wizard_output_changed()

    def _wizard_output_changed(self):
        pdf = self.wizard_output.pdf_only.value
        self.wizard_time.props['label'] = "Každý den vytvořit v" if pdf else "Každý den odeslat v"
        self.wizard_time.update()
        self.wizard_enabled.text = "Zapnout automatické vytváření PDF" if pdf else "Zapnout automatické odesílání"
        self.wizard_enabled.update()
        self.wizard_save_help.set_text(
            "V zadaný čas se pouze vytvoří PDF ve zvolené složce. E-mail se neposílá."
            if pdf else "Uložením se úloha zařadí do plánovače. E-mail se odešle až v naplánovaný čas."
        )
        self._wizard_queue_preview()

    def _build_wizard_footer(self):
        with ui.row().classes("ds-wizard-actions w-full items-center justify-between") as self.wizard_navigation:
            self.wizard_back = ui.button("Zpět", icon="arrow_back", on_click=lambda: self._wizard_show_step(self._wizard_step - 1)).props("outline no-caps")
            self.wizard_next = ui.button("Pokračovat", icon="arrow_forward", on_click=self._wizard_next_step).props("no-caps unelevated").mark("wizard-next")
        with ui.column().classes("ds-wizard-receipt w-full gap-3") as self.wizard_receipt:
            with ui.row().classes("items-center gap-3"):
                ui.icon("check_circle", color="positive", size="32px").props('aria-hidden="true"')
                ui.label("Úloha byla uložena do plánovače").classes("app-heading")
            self.wizard_receipt_summary = ui.label("").classes("ds-wizard-preview")
            self.wizard_receipt_status = ui.label("").props('role="status" aria-live="polite"')
            with ui.row().classes("gap-3"):
                ui.button("Otevřít plánovač", icon="schedule", on_click=lambda: self.tabs.set_value("mail_tasks")).props("outline no-caps")
                ui.button("Vytvořit další úlohu", icon="add", on_click=self._wizard_new).props("no-caps unelevated")
        self.wizard_receipt.set_visibility(False)
        ui.timer(10, self._wizard_refresh_status)
        self._wizard_show_step(1)

    def _wizard_show_step(self, number):
        self._wizard_step = max(1, min(4, number))
        self.wizard_error.set_text("")
        for index, card in enumerate(self._wizard_cards, 1):
            card.set_visibility(index == self._wizard_step and not self._wizard_saved)
        for index, label in enumerate(self._wizard_indicators, 1):
            label.classes(remove="ds-wizard-current ds-wizard-done")
            if index == self._wizard_step:
                label.classes("ds-wizard-current").props('aria-current="step"')
            else:
                label.props(remove="aria-current")
                if index < self._wizard_step:
                    label.classes("ds-wizard-done")
        self.wizard_heading.set_text(f"Krok {self._wizard_step} ze 4 · {STEPS[self._wizard_step - 1]}")
        self._wizard_update_caption()
        self.wizard_back.set_visibility(self._wizard_step > 1)
        self.wizard_next.set_text("Uložit do plánovače" if self._wizard_step == 4 else "Pokračovat")
        self.wizard_next.set_visibility(self._wizard_step < 3 or self.mail_tasks_tab.visible)
        if self._wizard_step >= 3:
            self._wizard_queue_preview()

    def _wizard_update_caption(self):
        if not hasattr(self, "show_diner_list"):
            return
        try:
            day = self._selected_date()
            meals = meal_filter_caption(self._selected_daily_meal_type())
            count = len(self._selected_category_order())
            content = "součty a jména" if self.show_diner_list.value else "jen součty"
            self.wizard_selection_caption.set_text(f"Náhled {day:%d.%m.%Y} · {meals} · kategorií: {count} · {content}")
        except ValueError:
            self.wizard_selection_caption.set_text("Zkontrolujte datum náhledu.")

    def _wizard_validate(self, number):
        if number == 1:
            self._selected_date()
            self._manual_daily_categories()
        if number == 2:
            self._current_daily_profile()
        if number >= 3:
            self._wizard_task(validate_recipients=False)
        if number == 4:
            if not self.wizard_output.commit():
                raise ValueError("Opravte e-mailovou adresu příjemce.")
            self._wizard_task()

    def _wizard_next_step(self):
        try:
            self._wizard_validate(self._wizard_step)
            if self._wizard_step == 4:
                self._wizard_save()
            else:
                self._wizard_show_step(self._wizard_step + 1)
        except (ValueError, OSError, TypeError) as exc:
            self.wizard_error.set_text(str(exc))

    def _wizard_task(self, *, validate_recipients=True):
        mode = self.wizard_mode.value
        offset = 2 if mode == "after_tomorrow" else self.wizard_offset.value
        if mode == "offset" and (offset is None or int(offset) != offset or not 0 <= offset <= 370):
            raise ValueError("Zadejte celý počet dní od 0 do 370.")
        calendar = self.wizard_calendar_mode.value
        selected = list(self.wizard_calendars.value or [])
        if calendar == "selected" and not selected:
            raise ValueError("Vyberte alespoň jeden skutečný kalendář z Jídelny.")
        return MailTask.from_dict({
            "id": self._wizard_task_id, "profile_id": self._wizard_profile_id,
            **self.wizard_output.values(preview=not validate_recipients),
            "name": self.wizard_name.value, "report": "daily",
            "recipients": self.wizard_recipients.addresses if validate_recipients else ["preview@example.invalid"],
            "send_time": self.wizard_time.value, "enabled": self.wizard_enabled.value,
            "date_mode": "offset" if mode == "after_tomorrow" else mode,
            "day_offset": int(offset or 0), "only_cooking_days": self.wizard_only_cooking.value,
            "cooking_meal_type": "*" if calendar == "all" else selected if calendar == "selected" else None,
        })

    def _wizard_queue_preview(self):
        self._wizard_revision += 1
        if not hasattr(self, "wizard_final_preview"):
            return
        self.wizard_date_preview.set_text("Počítám konkrétní datum…")
        self.wizard_final_preview.set_text("Počítám konkrétní datum…")
        if self._wizard_timer:
            self._wizard_timer.deactivate()
        with self.wizard_date_preview.parent_slot:
            self._wizard_timer = ui.timer(0.25, self._wizard_preview, once=True)

    async def _wizard_preview(self):
        revision = self._wizard_revision
        try:
            task = self._wizard_task(validate_recipients=False)
            upcoming = next_send_at(replace(task, enabled=True), datetime.now())
            profile = self._current_daily_profile()
            # Use current unsaved meal filters, never write a preview profile to disk.
            if task.date_mode == "next_cooking_day":
                task = replace(task, profile_id=None, cooking_meal_type=task.cooking_meal_type or profile.meal_type or "*")
                current, day = await run.io_bound(preview_days, self.config_path, task, date.today(), upcoming.date())
            else:
                current = target_date(task, date.today())
                day = target_date(task, upcoming.date())
            message = (f"Dnes tato volba znamená přehled za {readable_day(current)}. "
                       f"Příští plánované spuštění: {upcoming:%d.%m.%Y v %H:%M}; "
                       f"PDF bude za {readable_day(day)}.")
            if task.only_cooking_days and task.date_mode != "next_cooking_day":
                message += " Pokud se v tento den nevaří, spuštění se přeskočí."
            if task.output_mode == "pdf":
                message += " PDF se pouze uloží na disk, e-mail se neposílá."
        except Exception as exc:
            message = f"Konkrétní datum nelze ověřit: {exc}. Zkontrolujte připojení a kalendář Jídelny."
        if revision == self._wizard_revision:
            self.wizard_date_preview.set_text(message)
            self.wizard_final_preview.set_text(message)

    async def _wizard_load_calendars(self):
        try:
            names = await run.io_bound(available_cooking_calendars, self.config_path)
            self.wizard_calendars.set_options(list(names), value=[n for n in self.wizard_calendars.value if n in names])
            self.wizard_calendar_status.set_text(f"Načteno kalendářů: {len(names)}.")
        except Exception as exc:
            self.wizard_calendar_status.set_text(f"Kalendáře nelze načíst: {exc}")

    def _wizard_save(self):
        if self._wizard_saved:
            return
        for number in range(1, 5):
            try:
                self._wizard_validate(number)
            except (ValueError, TypeError):
                self._wizard_show_step(number)
                raise
        task = self._wizard_task()
        # A separate immutable snapshot protects other schedules sharing the source.
        profile = replace(self._current_daily_profile(), id=self._wizard_profile_id, name=task.name)
        upcoming = next_send_at(task, datetime.now())
        task = replace(task, first_send_date=upcoming.date().isoformat() if upcoming else None)
        path = task_file(self.config_path.parent)
        tasks = load_tasks(path)
        self.wizard_next.disable()
        try:
            profiles = save_profile(self.daily_profiles_path, profile)
            save_tasks(path, [t for t in tasks if t.id != task.id] + [task])
        finally:
            self.wizard_next.enable()
        self.daily_profiles = profiles
        self._wizard_saved = True
        self._wizard_saved_task = task
        for card in self._wizard_cards:
            card.set_visibility(False)
        self.wizard_navigation.set_visibility(False)
        destination = (f"PDF: {task.output_directory} · {task.output_filename}"
                       if task.output_mode == "pdf" else ', '.join(task.recipients))
        self.wizard_receipt_summary.set_text(f"{task.name} · každý den v {task.send_time} · {destination}. " + (f"Příští spuštění {upcoming:%d.%m.%Y v %H:%M}." if upcoming else "Automatické spouštění je vypnuté."))
        self.wizard_receipt.set_visibility(True)
        self._wizard_refresh_status()
        if hasattr(self, "mail_tasks_refresh"):
            self.mail_tasks_refresh()

    def _wizard_refresh_status(self):
        if self._wizard_saved:
            self.wizard_receipt_status.set_text(observed_status(self.config_path.parent, self._wizard_saved_task))

    def _wizard_new(self):
        self._wizard_saved = False
        self._wizard_task_id = str(uuid4())
        self._wizard_profile_id = str(uuid4())
        self.new_daily_profile()
        self.date_input.value = date.today().strftime("%d.%m.%Y")
        self.date_picker.value = date.today().isoformat()
        self.wizard_name.value = "Nový přehled"
        self.wizard_mode.value = "today"
        self.wizard_calendar_mode.value = "report"
        self.wizard_calendars.value = []
        self.wizard_enabled.value = True
        self.wizard_output.pdf_only.value = False
        self.wizard_output.directory.value = self.wizard_output.default_directory
        self.wizard_output.filename.value = "Prehled_{date}.pdf"
        self.wizard_recipients.addresses.clear()
        self.wizard_recipients.input.value = ""
        self.wizard_recipients.render()
        self.wizard_receipt.set_visibility(False)
        self.wizard_navigation.set_visibility(True)
        self._wizard_show_step(1)

