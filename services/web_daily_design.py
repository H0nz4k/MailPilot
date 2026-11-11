"""DataShip daily workspace presentation, using existing PDF/mail callbacks."""
from __future__ import annotations

from dataclasses import replace
from services.web_meal_types import meal_filter_values, meal_filter_caption
from uuid import uuid4

from nicegui import run, ui

import ui_widgets as w
from services.web_daily_profiles import DailyProfile, load_profiles, profile_file, save_profile
from stravovaci_sestava import AppConfig, fetch_report, available_delivery_types
from services.collection_status import COLLECTION_OPTIONS, validate_report_history


from services.web_report_wizard import ReportWizardMixin, RULES, HISTORY_RULES
from services.web_pdf_designer import PdfDesigner


class DailyDesignMixin(ReportWizardMixin):
    def _build_daily_workspace(self) -> None:
        self.daily_profiles_path = profile_file(self.config_path.parent)
        self.daily_profiles = []
        self.daily_profile_id = None
        self._daily_dirty = False
        self._applying_daily_profile = False
        self._daily_summary_revision = 0
        self._daily_summary_timer = None
        try:
            self.daily_profiles = load_profiles(self.daily_profiles_path)
        except (OSError, ValueError) as exc:
            self.initial_status = f"Přehledy se nepodařilo načíst: {exc}"
            self.set_status(self.initial_status)
        with ui.column().classes("ui-block ds-daily ds-wizard w-full"):
            ui.label("Přehledy").classes("ds-page-title").props('role="heading" aria-level="1"')
            ui.label("Připravte přehled a naplánujte e-mail nebo uložení PDF.").classes("ds-wizard-intro")
            self._build_wizard_header()
            with w.card().classes("w-full") as selection:
                ui.label("Co zobrazit").classes("app-heading")
                self.wizard_name = ui.input("Název sestavy", placeholder="Například Počty pro kuchyni").props("outlined maxlength=80").classes("w-full").mark("wizard-report-name")
                self._build_date_field()
                self.date_input.classes(remove="w-36 shrink-0").classes("w-full").props("outlined")
                self.date_input.props["label"] = "Datum náhledu"
                ui.label("Výchozí je dnešek. Toto datum slouží pro náhled; pravidelné odesílání nastavíte ve třetím kroku. Minulost je dostupná pouze pro speciální sestavu Odebraná / neodebraná strava.").classes("ui-help")
                with ui.element("div").classes("ds-report-filters w-full"):
                    self.meal_type_select = ui.select({}, value=[], multiple=True, label="Typy stravy").classes("hidden")
                    self.meal_types_button = ui.button("Typy stravy: všechny", icon="checklist", on_click=self._open_meal_types_dialog).props("outline no-caps").classes("ds-report-filter")
                    self.meal_type_select.on_value_change(lambda _e: self._meal_types_changed())
                    self._build_category_panel()
                    saved_delivery = self.raw.get("typy_vydeje") or []
                    if not isinstance(saved_delivery, list):
                        saved_delivery = []
                    self.delivery_type_select = ui.select({value: value for value in saved_delivery}, value=saved_delivery, multiple=True, label="Typy výdeje").classes("hidden")
                    caption = f"Typy výdeje ({len(saved_delivery)})" if saved_delivery else "Typy výdeje: všechny"
                    self.delivery_types_button = ui.button(caption, icon="local_shipping", on_click=self._open_delivery_types_dialog).props("outline no-caps").classes("ds-report-filter")
                    self.delivery_type_select.on_value_change(lambda _e: self._delivery_types_changed())
                with ui.expansion("Uložené přehledy (volitelné)", icon="folder_open").classes("w-full"):
                    self.daily_profile_choices = ui.row().classes("ds-profile-choices w-full")
                    self.daily_profile_status = ui.label("").classes("ui-help ds-preview-state").props('role="status" aria-live="polite"')
                    with ui.row().classes("ds-editor-actions"):
                        self.daily_new_button = ui.button("Uložit výběr…", on_click=lambda: self.open_daily_save_dialog(as_new=True)).props("outline no-caps").mark("daily-save-new")
                        self.daily_update_button = ui.button("Uložit změny…", on_click=lambda: self.open_daily_save_dialog(as_new=False)).props("outline no-caps").mark("daily-save-update")
                        self.daily_reset_button = ui.button("Vrátit uložený výběr", on_click=self._restore_daily_profile).props("outline no-caps")
            self._wizard_cards.append(selection)
            with w.card().classes("w-full") as pdf:
                ui.label("Co má být v PDF?").classes("app-heading")
                self.wizard_content = ui.radio({"counts": "Jen součty", "names": "Součty a jmenný seznam", "collection": "Speciální: Odebraná / neodebraná strava"}, value="collection" if self.raw.get("odber_stravy") else "names" if self.raw.get("seznam_stravniku", True) else "counts").props("inline").classes("ds-wizard-content w-full")
                self.collection_status_select = ui.select(COLLECTION_OPTIONS, value=self.raw.get("odber_stravy") or "both", label="Které odběry zobrazit?").props("outlined").classes("w-full").mark("collection-status")
                self.collection_status_select.bind_visibility_from(self.wizard_content, "value", backward=lambda value: value == "collection")
                with ui.column().classes("w-full gap-2") as history:
                    ui.label("Tato sestava umožňuje i historii. Platí datum, typy stravy, kategorie a typy výdeje z prvního kroku.").classes("ui-help")
                    ui.button("Upravit datum a filtry", icon="event", on_click=lambda: self._wizard_show_step(1)).props("outline no-caps")
                history.bind_visibility_from(self.wizard_content, "value", backward=lambda value: value == "collection")
                self.daily_pdf_settings_button = ui.button("Nastavení PDF", icon="tune", on_click=lambda: self.daily_pdf_settings_dialog.open()).props("outline no-caps")
                with ui.row().classes("ds-summary-heading w-full items-center justify-between"):
                    with ui.column().classes("gap-1 min-w-0"):
                        ui.label("Počty porcí").classes("app-heading")
                        self.daily_summary_name = ui.label("Vlastní výběr").classes("ds-summary-name")
                        self.daily_summary_meta = ui.label("").classes("ui-help")
                    with ui.column().classes("gap-0"):
                        self.daily_summary_total = ui.label("—").classes("ds-summary-total").props('aria-label="Počet porcí celkem"')
                        ui.label("porcí celkem").classes("ui-help")
                self._build_pdf_panel()
                self.generate_button.props(remove="unelevated").props("outline")
                with ui.row().classes("ds-next-step w-full") as self.daily_schedule_card:
                    self.daily_schedule_button = ui.button("Nastavit odesílání", icon="schedule_send", on_click=self.schedule_daily_profile).props("outline no-caps")
                self.daily_schedule_card.set_visibility(False)
                self.daily_summary_status = ui.label("Počty se zobrazí po připojení k Jídelně.").classes("ui-help").props('role="status" aria-live="polite"')
            self._wizard_cards.append(pdf)
            with w.card().classes("w-full") as day:
                self._build_wizard_date()
            self._wizard_cards.append(day)
            with w.card().classes("w-full") as email:
                self._build_wizard_email()
                with ui.expansion("Jednorázové odeslání (volitelné)", icon="mail_outline").classes("w-full") as one_off:
                    ui.label("Odešle PDF pro datum náhledu z prvního kroku výše uvedeným příjemcům. Čas a pravidlo dne pro plánovač se nepoužijí.").classes("ui-help")
                    self.send_button.move(one_off)
                    self.mail_status.move(one_off)
                one_off.bind_visibility_from(self.wizard_output.pdf_only, "value", backward=lambda value: not value)
            self._wizard_cards.append(email)
            self._build_wizard_footer()

        self._build_daily_pdf_settings_dialog()
        self.wizard_content.on_value_change(lambda _e: self._content_changed())
        self.collection_status_select.on_value_change(lambda _e: self._daily_filters_changed())
        self.show_diner_list.on_value_change(lambda e: self.wizard_content.set_value("names" if e.value else "counts") if self.wizard_content.value != "collection" else None)
        self._build_daily_summary_dialog()
        self._build_daily_save_dialog()
        self._content_changed()
        self._render_daily_profile_choices()
        if self.daily_profiles:
            self._load_daily_profile(self.daily_profiles[0])
        else:
            self._update_daily_preview_state()

    def _delivery_types_changed(self):
        values = self.delivery_type_select.value or []
        self.delivery_types_button.set_text(f"Typy výdeje ({len(values)})" if values else "Typy výdeje: všechny")
        self._daily_filters_changed()

    def _selected_collection_status(self):
        return self.collection_status_select.value if self.wizard_content.value == "collection" else None

    def _content_changed(self):
        special = self.wizard_content.value == "collection"
        self.show_diner_list.set_value(self.wizard_content.value != "counts")
        self.show_diner_list.set_enabled(not special)
        self.wizard_mode.set_options({**RULES, **HISTORY_RULES} if special else RULES)
        if not special and self.wizard_mode.value in HISTORY_RULES:
            self.wizard_mode.value = "today"
        self._daily_filters_changed()
        self._wizard_queue_preview()
        if hasattr(self, "pdf_designer"):
            self.pdf_designer._render_layout()

    async def _open_delivery_types_dialog(self):
        if not self.connection_ok or not self._connection_password:
            ui.notify("Nejprve proveďte TEST připojení k databázi.", type="warning")
            return
        try:
            database = dict(self._collect_database(), password=self._connection_password)
            values = await run.io_bound(available_delivery_types, database)
        except Exception as exc:
            ui.notify(f"Typy výdeje se nepodařilo načíst: {exc}", type="negative")
            return
        selected = set(self.delivery_type_select.value or [])
        choices_available = sorted(set(values) | selected, key=str.casefold)
        with ui.dialog() as dialog, ui.card().classes("ds-mail-dialog"):
            ui.label("Typy výdeje v přehledu").classes("ds-dialog-title")
            ui.label("Vyberte jeden nebo více typů výdeje. Výběr platí pro celý přehled.").classes("ui-help")
            all_types = ui.checkbox("Všechny typy výdeje", value=not selected)
            choices = {}
            with ui.column().classes("w-full max-h-[50vh] overflow-y-auto"):
                for value in choices_available:
                    label = value if value in values else f"{value} (nenalezeno v databázi)"
                    choices[value] = ui.checkbox(label, value=value in selected)
            all_types.on_value_change(lambda event: [box.set_value(False) for box in choices.values()] if event.value else None)
            for box in choices.values():
                box.on_value_change(lambda event: all_types.set_value(False) if event.value else None)
            error = ui.label("").classes("text-negative").props('role="alert"')
            def apply():
                chosen = [key for key, box in choices.items() if box.value]
                if not all_types.value and not chosen:
                    error.set_text("Vyberte alespoň jeden typ nebo všechny typy výdeje.")
                    return
                self.delivery_type_select.value = [] if all_types.value else chosen
                self._delivery_types_changed()
                dialog.close()
            with ui.row().classes("w-full justify-end"):
                ui.button("Zrušit", on_click=dialog.close).props("flat no-caps")
                ui.button("Použít výběr", on_click=apply).props("no-caps unelevated")
        dialog.open()

    def _update_meal_types_button(self) -> None:
        values = meal_filter_values(self._selected_daily_meal_type())
        self.meal_types_button.set_text(f"Typy stravy ({len(values)})" if values else "Typy stravy: všechny")

    def _meal_types_changed(self) -> None:
        self._update_meal_types_button()
        self._daily_filters_changed()

    def _open_meal_types_dialog(self) -> None:
        selected = set(meal_filter_values(self._selected_daily_meal_type()))
        with ui.dialog() as dialog, ui.card().classes("ds-mail-dialog"):
            ui.label("Typy stravy v přehledu").classes("ds-dialog-title")
            ui.label("Vyberte více typů. Výběr se uloží společně s přehledem a použije se i při odesílání.").classes("ui-help")
            all_types = ui.checkbox("Všechny typy stravy", value=not selected)
            choices = {}
            with ui.column().classes("w-full max-h-[50vh] overflow-y-auto"):
                for value, label in self.meal_type_select.options.items():
                    choices[value] = ui.checkbox(label, value=value in selected)
            def choose_all(event):
                if event.value:
                    for checkbox in choices.values():
                        checkbox.value = False
            all_types.on_value_change(choose_all)
            for checkbox in choices.values():
                checkbox.on_value_change(lambda event: all_types.set_value(False) if event.value else None)
            error = ui.label("").classes("text-negative")
            def apply():
                values = [key for key, checkbox in choices.items() if checkbox.value]
                if not all_types.value and not values:
                    error.set_text("Vyberte alespoň jeden typ nebo Všechny typy stravy.")
                    return
                self.meal_type_select.value = [] if all_types.value else values
                self._meal_types_changed()
                dialog.close()
            with ui.row().classes("w-full justify-end"):
                ui.button("Zrušit", on_click=dialog.close).props("flat no-caps")
                ui.button("Použít výběr", on_click=apply).props("no-caps")
        dialog.open()

    def _update_daily_preview_state(self) -> None:
        profile = next((p for p in self.daily_profiles if p.id == self.daily_profile_id), None)
        if profile and self._daily_dirty:
            status = "Náhled změn"
        elif profile:
            status = "Prohlížení"
        else:
            status = "Prohlížení"
        self.daily_profile_status.set_text(status)
        self._wizard_update_caption()
        title = profile.name if profile else "Vlastní výběr"
        self.daily_summary_name.set_text(title + " – náhled změn" if profile and self._daily_dirty else title)
        self.daily_new_button.set_text("Uložit jako nový…" if profile else "Uložit výběr…")
        self.daily_update_button.set_visibility(profile is not None)
        self.daily_update_button.set_enabled(profile is not None)
        self.daily_update_button.set_text("Uložit změny…" if self._daily_dirty else "Upravit název…")
        self.daily_reset_button.set_visibility(bool(profile and self._daily_dirty))
        self._render_daily_preview_categories()

    def _render_daily_preview_categories(self) -> None:
        """Výběr je na hlavní stránce zastoupen počtem; položky jsou v dialogu."""

    def _build_daily_pdf_settings_dialog(self) -> None:
        with ui.dialog() as self.daily_pdf_settings_dialog, ui.card().classes("ds-mail-dialog ds-pdf-dialog"):
            ui.label("Nastavení PDF").classes("ds-dialog-title")
            with ui.column().classes("ds-dialog-body w-full"):
                with ui.tabs().props("no-caps").classes("w-full") as tabs:
                    appearance = ui.tab("Vzhled a obsah", icon="tune")
                    layout = ui.tab("Rozložení, náhled a šablony", icon="dashboard_customize")
                with ui.tab_panels(tabs, value=appearance).classes("w-full"):
                    with ui.tab_panel(appearance).classes("p-0"):
                        self._build_pdf_settings_section()
                    with ui.tab_panel(layout).classes("p-0"):
                        self.pdf_designer = PdfDesigner(self)
                for field in (self.category_separation, self.show_categories, self.show_norms, self.show_diner_list, self.show_delivery_summary, self.delivery_show_names, self.delivery_page_per_type,
                              self.pdf_orientation, self.pdf_data_size, self.pdf_label_size, self.pdf_bold, self.pdf_compact_rows,
                              self.language_input, self.menu_number):
                    field.on_value_change(lambda _e: self.pdf_designer.changed())
            with ui.row().classes("ds-dialog-footer w-full justify-end"):
                ui.button("Hotovo", on_click=self.daily_pdf_settings_dialog.close).props("no-caps unelevated")

    def _apply_pdf_appearance(self, settings):
        fields = {"pdf_orientation": self.pdf_orientation, "pdf_data_font_size": self.pdf_data_size,
                  "pdf_label_font_size": self.pdf_label_size, "pdf_bold": self.pdf_bold,
                  "pdf_compact_rows": self.pdf_compact_rows, "category_separation": self.category_separation,
                  "show_by_categories": self.show_categories, "show_by_norms": self.show_norms,
                  "show_diner_list": self.show_diner_list, "show_delivery_summary": self.show_delivery_summary,
                  "delivery_show_names": self.delivery_show_names, "delivery_page_per_type": self.delivery_page_per_type}
        for key, field in fields.items():
            field.value = settings[key]

    def _build_daily_summary_dialog(self) -> None:
        with ui.dialog() as self.daily_summary_dialog, ui.card().classes("ds-mail-dialog ds-summary-dialog"):
            ui.label("Porce podle kategorií").classes("ds-dialog-title")
            with ui.column().classes("ds-dialog-body w-full"):
                self.daily_summary_table = ui.table(columns=[
                    {"name": "name", "label": "Kategorie", "field": "name", "align": "left"},
                    {"name": "portions", "label": "Porce", "field": "portions", "align": "right"},
                ], rows=[], row_key="code").props('flat dense hide-bottom wrap-cells tabindex="0" aria-label="Souhrn počtu porcí podle kategorií"').classes("w-full ds-summary-table")
                self.daily_collection_heading = ui.label("Seznam odběrů stravy").classes("app-heading")
                self.daily_collection_table = ui.table(columns=[
                    {"name": "number", "label": "Číslo", "field": "number", "align": "left"},
                    {"name": "name", "label": "Jméno", "field": "name", "align": "left"},
                    {"name": "classroom", "label": "Třída", "field": "classroom", "align": "left"},
                    {"name": "category", "label": "Kategorie", "field": "category", "align": "left"},
                    {"name": "meal", "label": "Strava", "field": "meal", "align": "left"},
                    {"name": "menu", "label": "Menu", "field": "menu", "align": "left"},
                    {"name": "status", "label": "Odběr", "field": "status", "align": "left"},
                ], rows=[], row_key="id", pagination=25).props('flat dense wrap-cells aria-label="Seznam odběrů stravy"').classes("w-full")
                self.daily_collection_heading.set_visibility(False)
                self.daily_collection_table.set_visibility(False)
            with ui.row().classes("ds-dialog-footer w-full justify-end"):
                ui.button("Zavřít", on_click=self.daily_summary_dialog.close).props("no-caps unelevated")

    def _build_daily_save_dialog(self) -> None:
        with ui.dialog() as self.daily_save_dialog, ui.card().classes("ds-mail-dialog"):
            self.daily_save_title = ui.label().classes("ds-dialog-title")
            with ui.column().classes("ds-dialog-body w-full"):
                self.daily_save_help = ui.label().classes("ui-help")
                self.daily_profile_name = ui.input("Název přehledu", value="Nový přehled", placeholder="Například Obědy pro školku").props("outlined dense maxlength=80").classes("w-full")
                self.daily_save_error = ui.label().classes("ui-help").props('role="alert"')
                self.daily_profile_name.on_value_change(lambda _e: self.daily_save_error.set_text(""))
            with ui.row().classes("ds-dialog-footer w-full justify-end"):
                ui.button("Zrušit", on_click=self.daily_save_dialog.close).props("flat no-caps")
                self.daily_save_button = ui.button("Uložit přehled", on_click=self._confirm_daily_profile_save).props("no-caps unelevated").style("color: var(--ds-on-primary) !important").mark("daily-save-confirm")

    def open_daily_save_dialog(self, *, as_new: bool, schedule: bool = False) -> None:
        try:
            self._manual_daily_categories()
        except ValueError as exc:
            ui.notify(str(exc), type="warning")
            return
        self._daily_save_as_new = as_new
        self._daily_save_schedule = schedule
        profile = next((p for p in self.daily_profiles if p.id == self.daily_profile_id), None)
        self.daily_profile_name.value = ((profile.name[:72] + " – kopie") if as_new and profile else profile.name if profile else "Nový přehled")
        self.daily_save_title.set_text("Uložit přehled a pokračovat" if schedule else "Uložit přehled" if as_new else "Uložit změny přehledu" if self._daily_dirty else "Upravit název přehledu")
        self.daily_save_help.set_text(
            "Uloží se kategorie, typ stravy a obsah PDF. Datum se při pravidelném odesílání určí podle zvoleného pravidla."
            if as_new else "Změny se použijí i u pravidelných odesílání, která tento přehled používají. Datum náhledu se neukládá."
        )
        self.daily_save_button.set_text("Uložit a pokračovat" if schedule else "Uložit přehled" if as_new else "Uložit změny")
        self.daily_save_error.set_text("")
        self.daily_save_dialog.open()

    def _confirm_daily_profile_save(self) -> None:
        if not self.save_daily_profile(as_new=self._daily_save_as_new):
            return
        self.daily_save_dialog.close()
        if self._daily_save_schedule:
            self._open_daily_schedule(self.daily_profile_id)

    def schedule_daily_profile(self) -> None:
        try:
            self._wizard_validate(1)
            self._wizard_validate(2)
            self._wizard_show_step(3)
        except (ValueError, TypeError) as exc:
            self.wizard_error.set_text(str(exc))

    def _open_daily_schedule(self, profile_id: str) -> None:
        self.tabs.value = "mail_tasks"
        self.mail_tasks_editor(profile_id=profile_id)

    def _restore_daily_profile(self) -> None:
        profile = next((p for p in self.daily_profiles if p.id == self.daily_profile_id), None)
        if profile:
            self._load_daily_profile(profile)

    def _mark_daily_dirty(self) -> None:
        if not getattr(self, "_applying_daily_profile", False) and hasattr(self, "daily_profile_status"):
            self._daily_dirty = True
            self._update_daily_preview_state()

    def _daily_filters_changed(self) -> None:
        self._mark_daily_dirty()
        self._wizard_update_caption()
        self._queue_daily_summary()
        if hasattr(self, "pdf_designer"):
            self.pdf_designer.changed()

    def _current_daily_profile(self) -> DailyProfile:
        if not self.categories:
            raise ValueError("Jídelna ještě není připojena. Požádejte správce o nastavení připojení.")
        self.pdf_designer.settings()
        return DailyProfile.from_dict({
            "id": self.daily_profile_id or str(uuid4()), "name": self.daily_profile_name.value,
            "categories": self._selected_category_order(),
            "meal_type": self._selected_daily_meal_type(),
            "delivery_types": list(self.delivery_type_select.value or []),
            "collection_status": self._selected_collection_status(),
            "category_separation": bool(self.category_separation.value),
            "show_by_categories": bool(self.show_categories.value),
            "show_by_norms": bool(self.show_norms.value),
            "show_diner_list": bool(self.show_diner_list.value),
            "show_delivery_summary": bool(self.show_delivery_summary.value),
            "delivery_show_names": bool(self.delivery_show_names.value),
            "delivery_page_per_type": bool(self.delivery_page_per_type.value),
            "pdf_orientation": self.pdf_orientation.value,
            "pdf_data_font_size": self.pdf_data_size.value,
            "pdf_label_font_size": self.pdf_label_size.value,
            "pdf_bold": bool(self.pdf_bold.value),
            "pdf_compact_rows": bool(self.pdf_compact_rows.value),
            **self.pdf_designer.layout_values(),
            "language": self.language_input.value,
            "menu_list_number": self.menu_number.value,
        })

    def save_daily_profile(self, *, as_new: bool = False) -> bool:
        try:
            profile = self._current_daily_profile()
            if as_new:
                profile = replace(profile, id=str(uuid4()))
            self.daily_profiles = save_profile(self.daily_profiles_path, profile)
        except (OSError, ValueError) as exc:
            ui.notify(str(exc), type="warning")
            self.daily_save_error.set_text(str(exc))
            self.daily_profile_name.run_method("focus")
            return False
        self.daily_profile_id = profile.id
        self._daily_dirty = False
        self._render_daily_profile_choices()
        self._update_daily_preview_state()
        return True

    def new_daily_profile(self) -> None:
        self.daily_profile_id = None
        self.daily_profile_name.value = "Nový přehled"
        self.selected_categories = set(self.allowed_categories)
        self.meal_type_select.value = []
        self.delivery_type_select.value = []
        self.wizard_content.value = "names"
        self.collection_status_select.value = "both"
        self._render_daily_selection()
        self._mark_daily_dirty()
        self._render_daily_profile_choices()

    def _render_daily_profile_choices(self) -> None:
        self.daily_profile_choices.clear()
        with self.daily_profile_choices:
            options = {"": "Vlastní výběr", **{p.id: p.name for p in self.daily_profiles}}
            def choose(event):
                if event.value:
                    profile = next(p for p in self.daily_profiles if p.id == event.value)
                    self._choose_daily_profile(profile)
                else:
                    self.new_daily_profile()
            ui.select(options, value=self.daily_profile_id or "", label="Uložený přehled", on_change=choose).props("outlined dense").classes("w-full")

    def _choose_daily_profile(self, profile: DailyProfile) -> None:
        if profile.id == self.daily_profile_id:
            return
        profile = next(p for p in self.daily_profiles if p.id == profile.id)
        self._load_daily_profile(profile)

    def _load_daily_profile(self, profile: DailyProfile) -> None:
        self._applying_daily_profile = True
        try:
            self.daily_profile_id = profile.id
            self.daily_profile_name.value = profile.name
            self.selected_categories = set(profile.categories) & self.allowed_categories
            meals = list(meal_filter_values(profile.meal_type))
            self.meal_type_select.options = {**self.meal_type_select.options, **{v: v for v in meals}}
            self.meal_type_select.value = meals
            self._update_meal_types_button()
            self.delivery_type_select.options = {**self.delivery_type_select.options, **{value: value for value in profile.delivery_types}}
            self.delivery_type_select.value = list(profile.delivery_types)
            self._delivery_types_changed()
            self.collection_status_select.value = profile.collection_status or "both"
            self.wizard_content.value = "collection" if profile.collection_status else "names" if profile.show_diner_list else "counts"
            for field, value in ((self.category_separation, profile.category_separation),
                                 (self.show_categories, profile.show_by_categories),
                                 (self.show_norms, profile.show_by_norms),
                                 (self.show_diner_list, profile.show_diner_list),
                                 (self.show_delivery_summary, profile.show_delivery_summary),
                                 (self.delivery_show_names, profile.delivery_show_names),
                                 (self.delivery_page_per_type, profile.delivery_page_per_type)):
                field.value = value
            self.pdf_compact_rows.value = profile.pdf_compact_rows
            self.pdf_designer.set_layout(profile.pdf_layout, profile.pdf_page_breaks)
            for field, key, raw_key, default in (
                (self.pdf_orientation, "pdf_orientation", "pdf_orientace", "na_vysku"),
                (self.pdf_data_size, "pdf_data_font_size", "pdf_velikost_dat", 8.5),
                (self.pdf_label_size, "pdf_label_font_size", "pdf_velikost_popisku", 9.0),
                (self.pdf_bold, "pdf_bold", "pdf_tucne", False),
                (self.language_input, "language", "jazyk_jidelnicku", "česky"),
                (self.menu_number, "menu_list_number", "cislo_jidelnicku", 1),
            ):
                value = getattr(profile, key)
                field.value = value if value is not None else self.raw.get(raw_key, default)
            self._render_daily_selection()
            self._daily_dirty = False
        finally:
            self._applying_daily_profile = False
        self._render_daily_profile_choices()
        self._update_daily_preview_state()
        self._queue_daily_summary()

    def _queue_daily_summary(self) -> None:
        if not hasattr(self, "daily_summary_status"):
            return
        self._daily_summary_revision += 1
        self.daily_summary_total.set_text("—")
        self.daily_summary_table.rows = []
        self.daily_summary_table.update()
        self.daily_collection_table.rows = []
        self.daily_collection_table.update()
        self.daily_collection_heading.set_visibility(False)
        self.daily_collection_table.set_visibility(False)
        if self._daily_summary_timer is not None:
            self._daily_summary_timer.deactivate()
        if not self.connection_ok:
            self.daily_summary_status.set_text("Počty se zobrazí po připojení k Jídelně.")
            return
        self.daily_summary_status.set_text("Aktualizuji souhrn…")
        # Date reloads also call this from a background task without a UI slot.
        with self.daily_summary_status.parent_slot:
            self._daily_summary_timer = ui.timer(0.45, self.refresh_daily_summary, once=True)

    async def refresh_daily_summary(self) -> None:
        if not self.connection_ok or not self._connection_password:
            return
        self._daily_summary_revision += 1
        revision = self._daily_summary_revision
        try:
            categories = self._manual_daily_categories()
            day = self._selected_date()
            status = self._selected_collection_status()
            validate_report_history(day, status)
            meal_type = self._selected_daily_meal_type()
            database = dict(self._collect_database(), password=self._connection_password)
            self.daily_summary_total.set_text("—")
            self.daily_summary_table.rows = []
            self.daily_summary_table.update()
            self.daily_summary_meta.set_text(f"{day:%d.%m.%Y} · {meal_filter_caption(meal_type)}")
            self.daily_summary_status.set_text("Načítám počty porcí…")
            config = AppConfig(database=database, report_date=day, categories=categories,
                meal_type=meal_type, delivery_types=tuple(self.delivery_type_select.value or []), language=str(self.language_input.value or "česky"),
                menu_list_number=int(self.menu_number.value or 1), show_diner_list=False, collection_status=status)
            report = await run.io_bound(self._fetch_daily_summary, config)
        except Exception as exc:
            if revision == self._daily_summary_revision:
                self.daily_summary_status.set_text(f"Souhrn není dostupný: {exc}")
            return
        if revision != self._daily_summary_revision:
            return
        rows = {}
        for item in report.categories:
            row = rows.setdefault(item.code, {"code": item.code, "name": item.name or item.code, "portions": 0})
            row["portions"] += item.applications
        total = sum(item.portions for item in report.menus)
        self.daily_summary_total.set_text(f"{total:,}".replace(",", " "))
        self.daily_summary_table.rows = list(rows.values())
        self.daily_summary_table.update()
        self.daily_collection_table.rows = [
            {"id": i, "number": item.diner_number, "name": item.name or "[bez jména]",
             "classroom": item.classroom or "", "category": item.category_code,
             "meal": item.meal_type, "menu": f"Menu {item.menu}",
             "status": "Odebraná" if item.collected else "Neodebraná"}
            for i, item in enumerate(report.diners)
        ] if status else []
        self.daily_collection_table.update()
        self.daily_collection_heading.set_visibility(status is not None)
        self.daily_collection_table.set_visibility(status is not None)
        self.daily_summary_status.set_text(f"Vybraných kategorií: {len(categories)}")

    @staticmethod
    def _fetch_daily_summary(config):
        # The verified session password is already in the snapshot. Reading the
        # credential store here would fail on a first TEST before PDF saves it.
        return fetch_report(config)




