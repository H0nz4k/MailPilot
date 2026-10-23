"""DataShip daily workspace presentation, using existing PDF/mail callbacks."""
from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from nicegui import run, ui

import ui_widgets as w
from services.web_daily_profiles import DailyProfile, load_profiles, profile_file, save_profile
from stravovaci_sestava import AppConfig, fetch_report


class DailyDesignMixin:
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
        with ui.column().classes("ui-block ds-daily w-full"):
            with ui.row().classes("ds-page-heading w-full items-center justify-between"):
                with ui.column().classes("gap-1"):
                    ui.label("Přehledy").classes("ds-page-title").props('role="heading" aria-level="1"')
                    ui.label("Prohlédněte si počty nebo vytvořte PDF. Uložený výběr pak můžete pravidelně odesílat.").classes("ui-help")
            with w.card().classes("ds-report-toolbar"):
                self.daily_profile_choices = ui.row().classes("ds-profile-choices")
                self.daily_profile_status = ui.label("").classes("ui-help ds-preview-state").props('role="status" aria-live="polite"')
                with ui.row().classes("ds-editor-actions"):
                    self.daily_new_button = ui.button("Uložit výběr…", on_click=lambda: self.open_daily_save_dialog(as_new=True)).props("outline no-caps").style("width: 240px; min-height: 44px; max-width: 100%").mark("daily-save-new")
                    self.daily_update_button = ui.button("Uložit změny…", on_click=lambda: self.open_daily_save_dialog(as_new=False)).props("outline no-caps").style("width: 240px; min-height: 44px; max-width: 100%").mark("daily-save-update")
                    self.daily_reset_button = ui.button("Vrátit uložený výběr", on_click=self._restore_daily_profile).props("outline no-caps").style("width: 240px; min-height: 44px; max-width: 100%")
            with ui.element("div").classes("ds-daily-grid"):
                with w.card().classes("ds-editor"):
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label("Co zobrazit").classes("app-heading")
                    self.daily_preview_note = ui.label("").classes("ui-help").props('role="status" aria-live="polite"')
                    with ui.element("div").classes("ds-daily-fields"):
                        self._build_date_field()
                        self.date_input.classes(remove="w-36 shrink-0").classes("w-full").props("outlined")
                        self.date_input.props["label"] = "Datum náhledu"
                        self.meal_type_select = ui.select({"__all__": "Všechny typy stravy"}, value="__all__", label="Typ stravy").props("outlined dense options-dense").classes("w-full")
                        self.meal_type_select.on_value_change(lambda _e: self._daily_filters_changed())
                    self._build_category_panel()
                    self.daily_preview_categories = ui.row().classes("ds-selected-categories w-full")
                    self.daily_edit_expansion = ui.expansion("Vzhled a obsah PDF", icon="tune").classes("w-full app-note")
                    with self.daily_edit_expansion:
                        self._build_pdf_settings_section()
                    for field in (self.category_separation, self.show_categories, self.show_norms, self.show_diner_list):
                        field.on_value_change(lambda _e: self._mark_daily_dirty())
                with ui.column().classes("w-full gap-4 min-w-0"):
                    with w.card().classes("ds-summary"):
                        with ui.row().classes("ds-summary-heading w-full items-center justify-between"):
                            with ui.column().classes("gap-1 min-w-0"):
                                ui.label("Počty porcí").classes("app-heading")
                                self.daily_summary_name = ui.label("Vlastní výběr").classes("ds-summary-name")
                                self.daily_summary_meta = ui.label("").classes("ui-help")
                            with ui.row().classes("items-center gap-3"):
                                with ui.column().classes("gap-0"):
                                    self.daily_summary_total = ui.label("—").classes("ds-summary-total").props('aria-label="Počet porcí celkem"')
                                    ui.label("porcí celkem").classes("ui-help")
                                ui.button(icon="refresh", on_click=self.refresh_daily_summary).props('flat round aria-label="Obnovit souhrn"')
                        self._build_pdf_panel()
                        with ui.row().classes("ds-next-step w-full items-center justify-between") as self.daily_schedule_card:
                            ui.label("Stejný výběr můžete pravidelně odesílat.").classes("ui-help")
                            self.daily_schedule_button = ui.button("Nastavit odesílání", icon="schedule_send", on_click=self.schedule_daily_profile).props("no-caps unelevated").style("color: var(--ds-on-primary) !important")
                        self.daily_schedule_card.set_visibility(self.mail_tasks_tab.visible)
                        self.daily_summary_table = ui.table(columns=[
                            {"name": "name", "label": "Kategorie", "field": "name", "align": "left"},
                            {"name": "portions", "label": "Porce", "field": "portions", "align": "right"},
                        ], rows=[], row_key="code").props('flat dense hide-bottom wrap-cells tabindex="0" aria-label="Souhrn počtu porcí podle kategorií"').classes("w-full ds-summary-table")
                        self.daily_summary_status = ui.label("Počty se zobrazí po připojení k Jídelně.").classes("ui-help").props('role="status" aria-live="polite" aria-atomic="true"')

        self._build_daily_save_dialog()
        self._render_daily_profile_choices()
        if self.daily_profiles:
            self._load_daily_profile(self.daily_profiles[0])
        else:
            self._update_daily_preview_state()

    def _update_daily_preview_state(self) -> None:
        profile = next((p for p in self.daily_profiles if p.id == self.daily_profile_id), None)
        if profile and self._daily_dirty:
            status = "Náhled změn"
            note = "Měníte jen náhled. Uložený přehled i jeho odesílání zůstanou stejné, dokud neuložíte změny."
        elif profile:
            status = "Prohlížení"
            note = "Prohlížíte uložený přehled. Datum náhledu platí jen pro zobrazení a ruční PDF."
        else:
            status = "Prohlížení"
            note = "Prohlížíte vlastní výběr. Pro další použití nebo odesílání ho uložte jako přehled."
        self.daily_profile_status.set_text(status)
        self.daily_preview_note.set_text(note)
        title = profile.name if profile else "Vlastní výběr"
        self.daily_summary_name.set_text(title + " – náhled změn" if profile and self._daily_dirty else title)
        self.daily_new_button.set_text("Uložit jako nový…" if profile else "Uložit výběr…")
        self.daily_update_button.set_visibility(profile is not None)
        self.daily_update_button.set_enabled(profile is not None)
        self.daily_update_button.set_text("Uložit změny…" if self._daily_dirty else "Upravit název…")
        self.daily_reset_button.set_visibility(bool(profile and self._daily_dirty))
        self._render_daily_preview_categories()

    def _render_daily_preview_categories(self) -> None:
        if not hasattr(self, "daily_preview_categories"):
            return
        self.daily_preview_categories.clear()
        with self.daily_preview_categories:
            for code, name in self.categories:
                if code in self.selected_categories:
                    with ui.row().classes("ds-selected-category items-center no-wrap"):
                        ui.icon("check", size="1rem").props('aria-hidden="true"')
                        ui.label(name or code)

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
        if self.daily_profile_id and not self._daily_dirty:
            self._open_daily_schedule(self.daily_profile_id)
        else:
            self.open_daily_save_dialog(as_new=True, schedule=True)

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
        self._queue_daily_summary()

    def _current_daily_profile(self) -> DailyProfile:
        if not self.categories:
            raise ValueError("Jídelna ještě není připojena. Požádejte správce o nastavení připojení.")
        return DailyProfile.from_dict({
            "id": self.daily_profile_id or str(uuid4()), "name": self.daily_profile_name.value,
            "categories": self._selected_category_order(),
            "meal_type": self._selected_daily_meal_type(),
            "category_separation": bool(self.category_separation.value),
            "show_by_categories": bool(self.show_categories.value),
            "show_by_norms": bool(self.show_norms.value),
            "show_diner_list": bool(self.show_diner_list.value),
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
        self.meal_type_select.value = "__all__"
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
            if profile.meal_type:
                self.meal_type_select.options = {**self.meal_type_select.options, profile.meal_type: profile.meal_type}
            self.meal_type_select.value = profile.meal_type or "__all__"
            for field, value in ((self.category_separation, profile.category_separation),
                                 (self.show_categories, profile.show_by_categories),
                                 (self.show_norms, profile.show_by_norms),
                                 (self.show_diner_list, profile.show_diner_list)):
                field.value = value
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
        if self._daily_summary_timer is not None:
            self._daily_summary_timer.deactivate()
        if not self.connection_ok:
            self.daily_summary_status.set_text("Počty se zobrazí po připojení k Jídelně.")
            return
        self.daily_summary_status.set_text("Aktualizuji souhrn…")
        self._daily_summary_timer = ui.timer(0.45, self.refresh_daily_summary, once=True)

    async def refresh_daily_summary(self) -> None:
        if not self.connection_ok or not self._connection_password:
            return
        self._daily_summary_revision += 1
        revision = self._daily_summary_revision
        try:
            categories = self._manual_daily_categories()
            day = self._selected_date()
            meal_type = self._selected_daily_meal_type()
            database = dict(self._collect_database(), password=self._connection_password)
            self.daily_summary_total.set_text("—")
            self.daily_summary_table.rows = []
            self.daily_summary_table.update()
            self.daily_summary_meta.set_text(f"{day:%d.%m.%Y} · {self.meal_type_select.options.get(meal_type or '__all__', meal_type)}")
            self.daily_summary_status.set_text("Načítám počty porcí…")
            config = AppConfig(database=database, report_date=day, categories=categories,
                meal_type=meal_type, language=str(self.language_input.value or "česky"),
                menu_list_number=int(self.menu_number.value or 1), show_diner_list=False)
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
        self.daily_summary_status.set_text(f"Vybraných kategorií: {len(categories)}")

    @staticmethod
    def _fetch_daily_summary(config):
        # The verified session password is already in the snapshot. Reading the
        # credential store here would fail on a first TEST before PDF saves it.
        return fetch_report(config)

