"""DataShip daily workspace presentation, using existing PDF/mail callbacks."""
from __future__ import annotations

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
        self.daily_checkboxes = {}
        self._daily_category_options = None
        try:
            self.daily_profiles = load_profiles(self.daily_profiles_path)
        except (OSError, ValueError) as exc:
            self.initial_status = f"Přehledy se nepodařilo načíst: {exc}"
            self.set_status(self.initial_status)
        with ui.column().classes("ui-block ds-daily w-full"):
            with ui.row().classes("ds-page-heading w-full items-center justify-between"):
                with ui.column().classes("gap-1"):
                    ui.label("Denní stav").classes("ds-page-title").props('role="heading" aria-level="1"')
            self._build_daily_overview()
            with ui.element("div").classes("ds-daily-grid ds-daily-single"):
                with w.card().classes("ds-editor"):
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label("Moje přehledy").classes("app-heading")
                        self.daily_profile_status = ui.label("").classes("ui-help").props('role="status" aria-live="polite"')
                    self.daily_profile_choices = ui.row().classes("ds-profile-choices w-full")
                    self.daily_profile_name = ui.input("Název přehledu", value="Denní přehled").props("outlined dense maxlength=80").classes("w-full")
                    self.daily_profile_name.on_value_change(lambda _e: self._mark_daily_dirty())
                    with ui.element("div").classes("ds-daily-fields"):
                        self._build_date_field()
                        self.date_input.classes(remove="w-36 shrink-0").classes("w-full").props("outlined")
                        self.meal_type_select = ui.select({"__all__": "Všechny typy stravy"}, value="__all__", label="Typ stravy").props("outlined dense options-dense").classes("w-full")
                        self.meal_type_select.on_value_change(lambda _e: self._daily_filters_changed())
                    self._build_category_panel()
                    ui.label("Skupiny strávníků").classes("ds-section-title")
                    self.daily_category_grid = ui.element("div").classes("ds-category-grid")
                    with ui.row().classes("ds-total-line w-full items-center justify-between no-wrap"):
                        with ui.row().classes("items-baseline gap-2 no-wrap"):
                            ui.label("Celkem").classes("ds-total-caption")
                            self.daily_summary_total = ui.label("—").classes("ds-summary-total").props('aria-label="Počet porcí celkem" aria-live="polite"')
                            ui.label("porcí").classes("ds-total-caption")
                        self._daily_show_counts = False
                        self.daily_detail_toggle = ui.button("Zobrazit detail", on_click=self._toggle_daily_detail).props("flat no-caps dense").classes("ds-detail-toggle")
                    self.daily_summary_status = ui.label("Souhrn se načte po úspěšném TESTu připojení.").classes("ui-help").props('role="status" aria-live="polite" aria-atomic="true"')
                    with ui.expansion("Pokročilé nastavení PDF", icon="tune").classes("w-full app-note ds-advanced"):
                        self._build_pdf_settings_section()
                    for field in (self.category_separation, self.show_categories, self.show_norms, self.show_diner_list):
                        field.on_value_change(lambda _e: self._mark_daily_dirty())
                    with ui.row().classes("ds-editor-actions w-full justify-between"):
                        ui.button("Nový přehled", icon="add", on_click=self.new_daily_profile).props("flat no-caps")
                        ui.button("Uložit přehled", icon="bookmark_border", on_click=self.save_daily_profile).props("outline no-caps")
                # Souhrnná karta byla odstraněna; prvky zůstávají kvůli stávající logice.
                with ui.column().classes("ds-summary-hidden") as summary_box:
                    self.daily_summary_name = ui.label("Denní přehled").classes("ds-summary-name")
                    self.daily_summary_meta = ui.label("").classes("ui-help")
                    self.daily_summary_table = ui.table(columns=[
                        {"name": "name", "label": "Kategorie", "field": "name", "align": "left"},
                        {"name": "portions", "label": "Porce", "field": "portions", "align": "right"},
                    ], rows=[], row_key="code").props("flat dense hide-bottom").classes("w-full ds-summary-table")
                summary_box.set_visibility(False)
            self._build_pdf_panel()
        self._render_daily_profile_choices()
        self._render_daily_category_grid()
        if self.daily_profiles:
            self._load_daily_profile(self.daily_profiles[0])

    def _mark_daily_dirty(self) -> None:
        if not getattr(self, "_applying_daily_profile", False) and hasattr(self, "daily_profile_status"):
            self._daily_dirty = True
            self.daily_profile_status.set_text("Neuložené změny")
        if hasattr(self, "daily_summary_name"):
            self.daily_summary_name.set_text(str(self.daily_profile_name.value or "Nový přehled"))

    def _daily_filters_changed(self) -> None:
        self._mark_daily_dirty()
        self._queue_daily_summary()

    def _current_daily_profile(self) -> DailyProfile:
        if not self.categories:
            raise ValueError("Nejprve proveďte TEST připojení k databázi.")
        return DailyProfile.from_dict({
            "id": self.daily_profile_id or str(uuid4()), "name": self.daily_profile_name.value,
            "categories": self._selected_category_order(),
            "meal_type": self._selected_daily_meal_type(),
            "category_separation": bool(self.category_separation.value),
            "show_by_categories": bool(self.show_categories.value),
            "show_by_norms": bool(self.show_norms.value),
            "show_diner_list": bool(self.show_diner_list.value),
        })

    def save_daily_profile(self) -> bool:
        try:
            profile = self._current_daily_profile()
            self.daily_profiles = save_profile(self.daily_profiles_path, profile)
        except (OSError, ValueError) as exc:
            ui.notify(str(exc), type="warning")
            return False
        self.daily_profile_id = profile.id
        self._daily_dirty = False
        self.daily_profile_status.set_text("Uloženo")
        self._render_daily_profile_choices()
        return True

    def new_daily_profile(self) -> None:
        if self._daily_dirty and not self.save_daily_profile():
            return
        self.daily_profile_id = None
        self.daily_profile_name.value = "Nový přehled"
        self.selected_categories = set()
        self.meal_type_select.value = "__all__"
        self._render_daily_selection()
        self._mark_daily_dirty()
        self._render_daily_profile_choices()

    def _render_daily_profile_choices(self) -> None:
        self.daily_profile_choices.clear()
        with self.daily_profile_choices:
            if not self.daily_profiles:
                ui.label("Vyberte kategorie a uložte svůj první přehled.").classes("ui-help")
            for profile in self.daily_profiles:
                count = len(set(profile.categories) & self.allowed_categories) if self.categories else len(profile.categories)
                button = ui.button(f"{profile.name} · {count} kat.", on_click=lambda _e, p=profile: self._choose_daily_profile(p)).props("no-caps outline").classes("ds-profile")
                button.props(f'aria-pressed="{str(profile.id == self.daily_profile_id).lower()}"')
                if profile.id == self.daily_profile_id:
                    button.classes(add="ds-profile-active")
                    # Quasar's layered !important outline background outranks
                    # unlayered custom CSS; keep the selected surface explicit.
                    button.style("background-color: var(--app-primary-soft) !important; "
                                 "box-shadow: inset 0 0 0 1px var(--app-primary) !important")

    def _choose_daily_profile(self, profile: DailyProfile) -> None:
        if self._daily_dirty and not self.save_daily_profile():
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
            self.daily_profile_status.set_text("Uloženo")
        finally:
            self._applying_daily_profile = False
        self._render_daily_profile_choices()
        self._queue_daily_summary()

    def _render_daily_category_grid(self) -> None:
        if not hasattr(self, "daily_category_grid"):
            return
        options = tuple((code, name) for code, name in self.categories if code in self.allowed_categories)
        self._syncing_daily_checks = True
        try:
            if options != self._daily_category_options:
                self.daily_category_grid.clear()
                self.daily_checkboxes = {}
                self._daily_category_options = options
                with self.daily_category_grid:
                    if not options:
                        ui.label("Kategorie se zobrazí po TESTu připojení.").classes("ui-help")
                    for code, name in options:
                        self.daily_checkboxes[code] = ui.checkbox(name or code, value=code in self.selected_categories,
                            on_change=lambda e, c=code: self._toggle_daily_category(c, bool(e.value))).props("dense").classes("ds-category")
            else:
                for code, checkbox in self.daily_checkboxes.items():
                    checkbox.value = code in self.selected_categories
            self._daily_category_names = {code: name or code for code, name in options}
            self._apply_daily_count_badges()
        finally:
            self._syncing_daily_checks = False

    def _toggle_daily_detail(self) -> None:
        self._daily_show_counts = not getattr(self, "_daily_show_counts", False)
        self.daily_detail_toggle.set_text("Skrýt detail" if self._daily_show_counts else "Zobrazit detail")
        self._apply_daily_count_badges()

    def _apply_daily_count_badges(self) -> None:
        """Volitelně ukáže počet porcí přímo ve štítku skupiny (nulové ztlumeně)."""
        names = getattr(self, "_daily_category_names", {})
        counts = getattr(self, "_daily_counts", {})
        show = getattr(self, "_daily_show_counts", False)
        for code, checkbox in getattr(self, "daily_checkboxes", {}).items():
            name = names.get(code, code)
            count = counts.get(code) if show else None
            checkbox.set_text(name if count is None else f"{name} · {count}")
            checkbox.classes(remove="ds-zero")
            if count == 0:
                checkbox.classes(add="ds-zero")

    def _toggle_daily_category(self, code: str, checked: bool) -> None:
        if self._syncing_daily_checks:
            return
        if checked and code in self.allowed_categories:
            self.selected_categories.add(code)
        else:
            self.selected_categories.discard(code)
        self._render_daily_selection()
        self._daily_filters_changed()

    def _queue_daily_summary(self) -> None:
        if not hasattr(self, "daily_summary_status"):
            return
        self._daily_summary_revision += 1
        self.daily_summary_total.set_text("—")
        self._daily_counts = {}
        self._apply_daily_count_badges()
        self.daily_summary_table.rows = []
        self.daily_summary_table.update()
        if self._daily_summary_timer is not None:
            self._daily_summary_timer.deactivate()
        if not self.connection_ok:
            self.daily_summary_status.set_text("Souhrn se načte po úspěšném TESTu připojení.")
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
            self.daily_summary_status.set_text("Načítám aktuální počty z databáze…")
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
        self._daily_counts = {code: row["portions"] for code, row in rows.items()}
        self._apply_daily_count_badges()
        self.daily_summary_table.rows = list(rows.values())
        self.daily_summary_table.update()
        self.daily_summary_status.set_text(f"Aktuální data · {len(categories)} kategorií · {total} porcí")

    @staticmethod
    def _fetch_daily_summary(config):
        # The verified session password is already in the snapshot. Reading the
        # credential store here would fail on a first TEST before PDF saves it.
        return fetch_report(config)
