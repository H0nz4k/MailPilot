"""PDF layout controls, real paged preview and named reusable templates."""
from base64 import b64encode
from uuid import uuid4

from nicegui import run, ui

from services.pdf_layout import DEFAULT_LAYOUT, SECTIONS, normalize_layout, normalize_page_breaks
from services.pdf_templates import PdfTemplate, load_templates, save_template, template_file, normalize_template_settings
from services.pdf_preview import generate_preview, render_preview_page
from services.collection_status import validate_report_history


class PdfDesigner:
    def __init__(self, owner):
        self.owner = owner
        self.rows = [list(row) for row in normalize_layout(owner.raw.get("pdf_rozlozeni")) or DEFAULT_LAYOUT]
        self.breaks = set(normalize_page_breaks(owner.raw.get("pdf_nove_stranky")))
        self.custom = bool(owner.raw.get("pdf_rozlozeni"))
        self.path = template_file(owner.config_path.parent)
        self.templates = []
        self._pdf = None
        self._revision = 0
        self._render_revision = 0
        self._suspend = False
        self._stale = True
        with ui.column().classes("w-full gap-3"):
            ui.label("Šablona PDF").classes("app-heading")
            self.template_choice = ui.select({"": "Vlastní nastavení"}, value="", label="Uložená šablona", on_change=lambda e: self.apply_template(e.value)).props("outlined").classes("w-full")
            with ui.row().classes("w-full items-end gap-3"):
                self.template_name = ui.input("Název šablony", placeholder="Například Přehled pro kuchyni").props("outlined maxlength=80").classes("grow min-w-0")
                ui.button("Uložit jako novou", icon="add", on_click=lambda: self.save(as_new=True)).props("outline no-caps")
                self.update_button = ui.button("Uložit změny šablony", icon="save", on_click=lambda: self.save(as_new=False)).props("outline no-caps")
            self.notice = ui.label("").classes("ui-help").props('role="status" aria-live="polite"')
            try:
                self.templates = load_templates(self.path)
                self._template_options()
            except (OSError, ValueError) as exc:
                self.notice.set_text(f"Šablony nelze načíst: {exc}")
            with ui.element("div").classes("ds-pdf-designer w-full"):
                with ui.column().classes("min-w-0 w-full gap-3"):
                    ui.label("Pořadí a umístění bloků").classes("app-heading")
                    ui.label("Přesouvejte celé řádky. Dva bloky můžete spojit vedle sebe; uvnitř řádku lze prohodit levou a pravou pozici. Viditelnost bloků nastavíte v záložce Vzhled.").classes("ui-help")
                    self.layout_container = ui.column().classes("w-full gap-3")
                    ui.button("Obnovit výchozí rozložení", on_click=self.reset_layout).props("flat no-caps")
                with ui.column().classes("min-w-0 w-full gap-3"):
                    ui.label("Náhled skutečného PDF").classes("app-heading")
                    self.source = ui.select({"example": "Ukázková data", "database": "Vybraná data z Jídelny"}, value="database" if owner.connection_ok else "example", label="Data náhledu").props("outlined").classes("w-full")
                    self.source.on_value_change(lambda _e: self.changed())
                    self.preview_button = ui.button("Aktualizovat náhled", icon="preview", on_click=self.refresh_preview).props("no-caps unelevated").mark("pdf-preview-refresh")
                    self.preview_status = ui.label("Náhled zatím nebyl vytvořen.").classes("ui-help").props('role="status" aria-live="polite"')
                    with ui.row().classes("w-full items-center gap-2"):
                        self.previous = ui.button(icon="chevron_left", on_click=lambda: self.page.set_value(self.page.value - 1)).props('outline round aria-label="Předchozí stránka PDF"')
                        self.page = ui.number("Stránka", min=1, max=1, value=1, step=1, on_change=self.change_page).props("outlined dense").classes("w-28")
                        self.next = ui.button(icon="chevron_right", on_click=lambda: self.page.set_value(self.page.value + 1)).props('outline round aria-label="Další stránka PDF"')
                        self.page_count = ui.label("/ 0").classes("ui-help")
                    self.preview_image = ui.image().props('fit=contain alt="Náhled stránky PDF"').classes("w-full ds-pdf-preview-image")
                    self.preview_image.set_visibility(False)
                    self.previous.disable()
                    self.next.disable()
        self._render_layout()
        self.update_button.disable()

    def layout_values(self):
        return {"pdf_layout": normalize_layout(self.rows) if self.custom else (),
                "pdf_page_breaks": normalize_page_breaks([key for key in SECTIONS if key in self.breaks])}

    def settings(self):
        owner = self.owner
        return normalize_template_settings({
            "pdf_orientation": owner.pdf_orientation.value,
            "pdf_data_font_size": owner.pdf_data_size.value, "pdf_label_font_size": owner.pdf_label_size.value,
            "pdf_bold": owner.pdf_bold.value, "pdf_compact_rows": owner.pdf_compact_rows.value,
            "category_separation": owner.category_separation.value,
            "show_by_categories": owner.show_categories.value, "show_by_norms": owner.show_norms.value,
            "show_diner_list": owner.show_diner_list.value, "show_delivery_summary": owner.show_delivery_summary.value,
            "delivery_show_names": owner.delivery_show_names.value, "delivery_page_per_type": owner.delivery_page_per_type.value,
            **self.layout_values(),
        })

    def changed(self):
        if self._suspend:
            return
        self._revision += 1
        self._render_revision += 1
        self._stale = True
        self.owner._mark_daily_dirty()
        self.preview_status.set_text("Nastavení se změnilo. Aktualizujte náhled.")

    def set_layout(self, layout, breaks):
        self.rows = [list(row) for row in normalize_layout(layout) or DEFAULT_LAYOUT]
        self.breaks = set(normalize_page_breaks(breaks))
        self.custom = bool(layout)
        self._render_layout()
        self.changed()

    def reset_layout(self):
        self.set_layout((), ("diners",))

    def move(self, index, direction):
        visible = self._visible_indexes()
        position = visible.index(index)
        if 0 <= position + direction < len(visible):
            target = visible[position + direction]
            self.rows[index], self.rows[target] = self.rows[target], self.rows[index]
            self._layout_changed()

    def join(self, index):
        indexes = self._visible_indexes()
        position = indexes.index(index)
        previous = indexes[position - 1] if position > 0 else None
        if previous is not None and len(self.rows[previous]) == len(self.rows[index]) == 1:
            self.rows[previous].extend(self.rows.pop(index))
            self._layout_changed()

    def separate(self, index):
        if len(self.rows[index]) == 2:
            left, right = self.rows[index]
            self.rows[index:index + 1] = [[left], [right]]
            self._layout_changed()

    def swap(self, index):
        self.rows[index].reverse()
        self._layout_changed()

    def set_break(self, index, enabled):
        row = self.rows[index]
        self.breaks.difference_update(row)
        if enabled:
            self.breaks.add(row[0])
        self.custom = True
        self.changed()

    def _layout_changed(self):
        self.custom = True
        self._render_layout()
        self.changed()

    def _render_layout(self):
        self.layout_container.clear()
        indexes = self._visible_indexes()
        with self.layout_container:
            for position, i in enumerate(indexes):
                row = self.rows[i]
                with ui.column().classes("ds-pdf-layout-row w-full gap-2"):
                    ui.label(f"Řádek {position + 1}").classes("ui-help")
                    with ui.row().classes("w-full gap-2 no-wrap"):
                        for key in row:
                            ui.label(SECTIONS[key]).classes("ds-pdf-block flex-1 min-w-0")
                    with ui.row().classes("w-full items-center gap-2"):
                        ui.button(icon="arrow_upward", on_click=lambda index=i: self.move(index, -1)).props(f'outline round aria-label="Posunout řádek {position + 1} nahoru"').set_enabled(position > 0)
                        ui.button(icon="arrow_downward", on_click=lambda index=i: self.move(index, 1)).props(f'outline round aria-label="Posunout řádek {position + 1} dolů"').set_enabled(position < len(indexes) - 1)
                        if len(row) == 2:
                            ui.button("Prohodit", icon="swap_horiz", on_click=lambda index=i: self.swap(index)).props("outline no-caps")
                            ui.button("Pod sebe", on_click=lambda index=i: self.separate(index)).props("outline no-caps")
                        elif position > 0 and len(self.rows[indexes[position - 1]]) == 1:
                            ui.button("Vedle předchozího", on_click=lambda index=i: self.join(index)).props("outline no-caps")
                    ui.checkbox("Začít na nové stránce", value=bool(self.breaks.intersection(row)), on_change=lambda e, index=i: self.set_break(index, e.value))

    def _visible_indexes(self):
        special = self.owner._selected_collection_status() is not None
        return [i for i, row in enumerate(self.rows)
                if any((key == "collection") == special for key in row)]

    def _template_options(self):
        self.template_choice.set_options({"": "Vlastní nastavení", **{t.id: t.name for t in self.templates}})

    def apply_template(self, identity):
        self.update_button.set_enabled(bool(identity))
        if not identity:
            return
        template = next((t for t in self.templates if t.id == identity), None)
        if template is None:
            self.notice.set_text("Šablona už není dostupná.")
            return
        settings = template.settings
        self.template_name.value = template.name
        self._suspend = True
        try:
            self.owner._apply_pdf_appearance(settings)
            self.set_layout(settings["pdf_layout"], settings["pdf_page_breaks"])
        finally:
            self._suspend = False
        self.changed()
        self.notice.set_text(f"Použita šablona {template.name}. Datum a filtry zůstávají podle přehledu.")

    def save(self, *, as_new):
        try:
            identity = str(uuid4()) if as_new else self.template_choice.value
            if not identity:
                raise ValueError("Nejprve vyberte šablonu nebo uložte novou.")
            template = PdfTemplate.from_dict({"id": identity, "name": self.template_name.value, "settings": self.settings()})
            self.templates = save_template(self.path, template)
            self._template_options()
            self.template_choice.value = template.id
            self.notice.set_text(f"Šablona {template.name} byla uložena.")
        except (OSError, ValueError) as exc:
            self.notice.set_text(str(exc))

    def _preview_config(self):
        from stravovaci_sestava import AppConfig
        owner = self.owner
        example = self.source.value == "example"
        if not example and (not owner.connection_ok or not owner._connection_password):
            raise ValueError("Pro skutečná data nejprve připojte Jídelnu nebo vyberte ukázková data.")
        day = owner._selected_date()
        status = owner._selected_collection_status()
        validate_report_history(day, status)
        categories = ("UK",) if example and not owner.categories else owner._manual_daily_categories()
        return AppConfig(database={**owner._collect_database(), "password": owner._connection_password} if not example else {},
                         report_date=day, categories=categories, meal_type=owner._selected_daily_meal_type(),
                         delivery_types=tuple(owner.delivery_type_select.value or ()), collection_status=status,
                         language=str(owner.language_input.value or "česky"), menu_list_number=int(owner.menu_number.value or 1),
                         **self.settings())

    async def refresh_preview(self):
        self._revision += 1
        revision = self._revision
        self.preview_button.disable()
        self.preview_status.set_text("Vytvářím náhled PDF…")
        try:
            config = self._preview_config()
            example = self.source.value == "example"
            data = await run.io_bound(generate_preview, config, example=example)
            png, count = await run.io_bound(render_preview_page, data, 0)
            if revision != self._revision:
                return
            self._pdf = data
            self._example = example
            self._stale = False
            self._render_revision += 1
            self.page.max = count
            self.page.value = 1
            self.page_count.set_text(f"/ {count}")
            self._show_page(png, 1, count)
        except Exception as exc:
            if revision == self._revision:
                self.preview_status.set_text(f"Náhled se nepodařilo vytvořit: {exc}")
        finally:
            self.preview_button.enable()

    def _show_page(self, png, number, count):
        self.preview_image.set_source("data:image/png;base64," + b64encode(png).decode("ascii"))
        self.preview_image.set_visibility(True)
        self.previous.set_enabled(number > 1)
        self.next.set_enabled(number < count)
        source = "Ukázková data – smyšlené údaje" if self._example else "Vybraná data z Jídelny"
        self.preview_status.set_text(("Nastavení se změnilo. Aktualizujte náhled. " if self._stale else "") + f"{source} · stránka {number} z {count}.")

    async def change_page(self):
        if not self._pdf:
            return
        self._render_revision += 1
        revision = self._render_revision
        try:
            number = self.page.value
            if number is None or int(number) != number:
                raise ValueError("Zadejte celé číslo stránky.")
            png, count = await run.io_bound(render_preview_page, self._pdf, int(number) - 1)
            if revision == self._render_revision:
                self._show_page(png, int(number), count)
        except Exception as exc:
            if revision == self._render_revision:
                self.preview_status.set_text(f"Stránku nelze zobrazit: {exc}")
