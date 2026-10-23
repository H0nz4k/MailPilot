"""Readable monthly export UI over the existing closing engine."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import NamedTemporaryFile

from nicegui import run, ui

import ui_widgets as w
from services.closing import MONTH_NAMES, previous_period, run_closing
from uzaverka_nastaveni import (
    SESTAVA_ARCH, SESTAVA_FKSP, SESTAVA_REKAPITULACE, peek_closing_ui,
)


def export_closing_preview(config_path: Path, *, year: int, month: int):
    """Snapshot in the same directory preserves relative output paths.

    A manual export must never inherit the scheduled email flag. The original
    configuration and its automatic delivery preference remain untouched.
    """
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    raw["uzaverka"] = dict(raw.get("uzaverka") or {}, odeslat_mail=False)
    with NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".json",
                            prefix=".dataship-closing-", dir=config_path.parent,
                            delete=False) as temporary:
        snapshot = Path(temporary.name)
        json.dump(raw, temporary, ensure_ascii=False)
    try:
        return run_closing(snapshot, year=year, month=month)
    finally:
        snapshot.unlink(missing_ok=True)


class ClosingDesignMixin:
    def _build_closing_workspace(self) -> None:
        closing = peek_closing_ui(self.raw)
        year, month = previous_period()
        self._closing_running = False
        with ui.column().classes("ds-closing w-full gap-4"):
            with ui.column().classes("ds-page-heading gap-1"):
                ui.label("Měsíční uzávěrka").classes("ds-page-title").props('role="heading" aria-level="1"')
                ui.label("Vyberte měsíc a sestavy. Vytvořené soubory si stáhnete do počítače.").classes("ui-help")
            with w.card().classes("ds-closing-card"):
                with ui.row().classes("ds-closing-period w-full items-center"):
                    self.closing_month = ui.select(
                        {i + 1: label.capitalize() for i, label in enumerate(MONTH_NAMES)},
                        value=month, label="Měsíc",
                    ).props("outlined dense").classes("grow")
                    self.closing_year = ui.number("Rok", value=year, min=2000, max=2100, step=1).props("outlined dense").classes("w-36")
                ui.label("Které sestavy vytvořit?").classes("app-heading")
                selected = set(closing["sestavy"])
                with ui.element("div").classes("ds-closing-options w-full"):
                    self._build_closing_report_options(selected)
                self.closing_zip = ui.checkbox("Přidat balíček ZIP se všemi sestavami", value=bool(closing["zip"]))
                with ui.expansion("Uložení a automatické odesílání", icon="settings").classes("w-full app-note"):
                    self.closing_output = self._output_path_field(
                        "Složka pro uložení", str(closing["vystup"]),
                        "Soubory se ukládají podle roku a měsíce.",
                        on_change=self.save_closing_settings,
                    )
                    self.closing_mail = ui.checkbox("Odesílat při automatické uzávěrce z plánovače", value=bool(closing["odeslat_mail"]))
                    ui.label("Tlačítko Vytvořit sestavy pouze připraví soubory. Příjemce automatické uzávěrky nastavíte v Nastavení → E-maily.").classes("ui-help")
                with ui.row().classes("w-full items-center gap-3"):
                    self.closing_generate_button = ui.button("Vytvořit sestavy", icon="description", on_click=self.generate_closing).props("unelevated no-caps").style("color: var(--ds-on-primary) !important").mark("closing-generate")
                    self.closing_status = ui.label("Vyberte období a alespoň jednu sestavu.").classes("ui-help").props('role="status" aria-live="polite"')
            self.closing_results = ui.column().classes("ds-closing-results w-full")
            self.closing_results.set_visibility(False)
        for element in (self.closing_arch, self.closing_fksp, self.closing_recap, self.closing_zip, self.closing_mail):
            element.on("update:model-value", lambda: self.save_closing_settings())

    def _build_closing_report_options(self, selected: set[str]) -> None:
        for attr, key, title, hint in (
            ("closing_arch", SESTAVA_ARCH, "Stravovací arch", "Přehled strávníků a stravy po dnech."),
            ("closing_fksp", SESTAVA_FKSP, "Podklady FKSP", "Podklady pro příspěvek zaměstnavatele na stravování."),
            ("closing_recap", SESTAVA_REKAPITULACE, "Rekapitulace", "Souhrn plateb a odebraných jídel."),
        ):
            with ui.column().classes("ds-report-option w-full gap-0"):
                field = ui.checkbox(title, value=key in selected)
                setattr(self, attr, field)
                ui.label(hint).classes("ui-help ds-option-help")

    async def generate_closing(self) -> None:
        if self._closing_running:
            return
        if not self.connection_ok:
            ui.notify("Nejprve připojte Jídelnu v Nastavení → Databáze.", type="warning")
            return
        self.closing_results.clear()
        self.closing_results.set_visibility(False)
        try:
            year = int(self.closing_year.value or 0)
            month = int(self.closing_month.value or 0)
            if not 2000 <= year <= 2100 or not 1 <= month <= 12:
                raise ValueError("Vyberte platný měsíc a rok.")
            if not self._selected_closing_reports():
                raise ValueError("Vyberte alespoň jednu sestavu.")
            # Lock before yielding so a second click cannot start another run.
            self._closing_running = True
            self.closing_generate_button.disable()
            self.closing_status.set_text("Načítám data a vytvářím sestavy…")
            await self._persist_settings()
            result = await run.io_bound(export_closing_preview, self.config_path, year=year, month=month)
        except Exception as exc:
            self.closing_status.set_text(f"Sestavy se nepodařilo vytvořit: {exc}")
            ui.notify(str(exc), type="negative")
        else:
            with self.closing_results:
                with w.card().classes("w-full"):
                    ui.label(f"Sestavy za {MONTH_NAMES[month - 1]} {year} jsou připravené").classes("app-heading")
                    ui.label("Soubory byly vytvořeny. E-mail se neodesílal.").classes("ui-help")
                    files = list(dict.fromkeys((*result.attachments, *result.files)))
                    for path in files:
                        with ui.row().classes("ds-output-file w-full items-center justify-between"):
                            ui.label(path.name).classes("app-text")
                            ui.button("Stáhnout ZIP" if path.suffix.lower() == ".zip" else "Stáhnout PDF", icon="download", on_click=lambda p=path: ui.download.file(p)).props("outline no-caps")
            self.closing_results.set_visibility(True)
            self.closing_status.set_text(f"Hotovo. Vytvořeno sestav: {len(result.files)}.")
        finally:
            self._closing_running = False
            self.closing_generate_button.enable()
