"""One-off collection report; no scheduler tasks are created."""
from datetime import date
from pathlib import Path
import json

from nicegui import run, ui

from services.collection_status import COLLECTION_OPTIONS, COLLECTION_TITLES
from services.config_io import parse_czech_date, open_document
from services.web_date_ui import CZECH_DATE_LOCALE
from services.web_recipient_editor import RecipientEditor
from stravovaci_sestava import AppConfig, fetch_report, create_pdf, available_meal_types, available_delivery_types


def build_collection_panel(owner):
    from mail_service import normalize_recipients, normalize_recipient
    from env_store import get_resend_api_key
    from services.web_mail_smtp import smtp_send
    from mail_service import send_pdf_via_mailsender

    with ui.column().classes("ui-block ds-daily w-full"):
        ui.label("Odběry").classes("ds-page-title").props('role="heading" aria-level="1"')
        ui.label("Jednorázový přehled odebrané a neodebrané stravy za zvolené období.").classes("ui-help")
        with ui.card().classes("w-full"):
            ui.label("Období a obsah").classes("app-heading")
            with ui.row().classes("w-full gap-3"):
                def date_field(label):
                    today = date.today()
                    with ui.input(label, value=today.strftime("%d.%m.%Y")).props('outlined mask="##.##.####" placeholder="DD.MM.RRRR"').classes("grow min-w-0") as field:
                        with ui.menu().props("no-parent-event") as menu:
                            def selected(event):
                                field.value = date.fromisoformat(event.value).strftime("%d.%m.%Y")
                                menu.close()
                            picker = ui.date(value=today.isoformat(), on_change=selected).props("first-day-of-week=1")
                            picker.props[":locale"] = json.dumps(CZECH_DATE_LOCALE, ensure_ascii=False)
                        with field.add_slot("append"):
                            ui.button(icon="event", on_click=menu.open).props(f'flat round aria-label="Vybrat {label}"')
                    return field
                start = date_field("Datum od")
                end = date_field("Datum do")
            status = ui.select(COLLECTION_OPTIONS, value="both", label="Které odběry zobrazit?").props("outlined").classes("w-full")
            owner.collection_categories = ui.select({}, value=[], multiple=True, label="Kategorie").props("outlined").classes("w-full").mark("collection-categories")
            def category_caption(event):
                owner.collection_categories.props["display-value"] = f"Vybráno: {len(event.value or [])}"
                owner.collection_categories.update()
            owner.collection_categories.on_value_change(category_caption)
            meals = ui.select({}, value=[], multiple=True, label="Typy stravy (prázdné = všechny)").props("outlined").classes("w-full")
            deliveries = ui.select({}, value=[], multiple=True, label="Typy výdeje (prázdné = všechny)").props("outlined").classes("w-full")
            filter_status = ui.label("Pro výběr jednotlivých typů načtěte nabídku z Jídelny.").classes("ui-help")
            async def load_filters():
                try:
                    if not owner.connection_ok or not owner._connection_password:
                        raise ValueError("Nejprve proveďte TEST připojení k Jídelně.")
                    first, last = parse_czech_date(start.value), parse_czech_date(end.value)
                    if first > last or (last - first).days > 365:
                        raise ValueError("Zadejte správné období nejvýše 366 dnů.")
                    database = {**owner._collect_database(), "password": owner._connection_password}
                    def fetch_types():
                        types = set()
                        for year in range(first.year, last.year + 1):
                            types.update(available_meal_types(database, date(year, 1, 1)))
                        return sorted(types, key=str.casefold), available_delivery_types(database)
                    meal_options, delivery_options = await run.io_bound(fetch_types)
                    meals.set_options(meal_options, value=[v for v in meals.value if v in meal_options])
                    deliveries.set_options(list(delivery_options), value=[v for v in deliveries.value if v in delivery_options])
                    filter_status.set_text("Typy načteny. Prázdný výběr znamená všechny typy.")
                except Exception as exc:
                    filter_status.set_text(f"Typy se nepodařilo načíst: {exc}")
            ui.button("Načíst typy stravy a výdeje", icon="refresh", on_click=load_filters).props("outline no-caps")
            ui.label("Po připojení k Jídelně se vyberou všechny povolené kategorie. Hromadné přihlášky se v odběrech jednotlivců nevykazují.").classes("ui-help")
            by_category = ui.checkbox("Počty podle kategorií", value=True)
            separate = ui.checkbox("Oddělit jmenný seznam podle kategorií", value=True)
            ui.label("Přehled obsahuje jednotlivé objednávky za každý den; jedna osoba může být uvedena vícekrát.").classes("ui-help")
        with ui.card().classes("w-full"):
            ui.label("PDF a odeslání").classes("app-heading")
            output = ui.input("Soubor PDF", value=str(owner.config_path.parent / "vystup" / "Odbery.pdf")).props("outlined").classes("w-full")
            recipients = RecipientEditor(directory=owner.config_path.parent)
            status_line = ui.label("").classes("ui-help").props('role="status" aria-live="polite"')
            with ui.row().classes("w-full gap-3"):
                create_button = ui.button("Vytvořit PDF", icon="picture_as_pdf").props("no-caps unelevated").mark("collection-create")
                send_button = ui.button("Vytvořit a odeslat", icon="send").props("outline no-caps").mark("collection-send")

    def snapshot():
        if not owner.connection_ok or not owner._connection_password:
            raise ValueError("Nejprve proveďte TEST připojení k Jídelně.")
        first, last = parse_czech_date(start.value), parse_czech_date(end.value)
        if first > last or (last - first).days > 365:
            raise ValueError("Zadejte správné období nejvýše 366 dnů.")
        selected = tuple(owner.collection_categories.value or ())
        allowed = set(owner._allowed_category_order())
        if not selected or not set(selected).issubset(allowed):
            raise ValueError("Vyberte alespoň jednu povolenou kategorii.")
        target = Path(str(output.value or "").strip())
        if not str(output.value or "").strip() or target.suffix.lower() != ".pdf":
            raise ValueError("Zadejte cestu k souboru PDF s příponou .pdf.")
        config = AppConfig(database={**owner._collect_database(), "password": owner._connection_password},
            report_date=first, report_end_date=last, categories=selected,
            language=str(owner.language_input.value or "česky"), menu_list_number=int(owner.menu_number.value or 1),
            collection_status=status.value, show_by_categories=bool(by_category.value),
            meal_type=tuple(meals.value or ()), delivery_types=tuple(deliveries.value or ()),
            category_separation=bool(separate.value), pdf_output=target,
            pdf_orientation=str(owner.pdf_orientation.value), pdf_data_font_size=float(owner.pdf_data_size.value),
            pdf_label_font_size=float(owner.pdf_label_size.value), pdf_bold=bool(owner.pdf_bold.value))
        return config

    def build_pdf(config):
        config.pdf_output.parent.mkdir(parents=True, exist_ok=True)
        return create_pdf(config, fetch_report(config))

    async def create():
        try:
            config = snapshot()
            create_button.disable(); send_button.disable()
            status_line.set_text("Načítám odběry a vytvářím PDF…")
            path = await run.io_bound(build_pdf, config)
            status_line.set_text(f"PDF vytvořeno: {path}")
            owner.last_pdf = path
            try:
                open_document(path)
            except Exception:
                ui.notify("PDF bylo vytvořeno, ale nepodařilo se ho otevřít.", type="warning")
        except Exception as exc:
            status_line.set_text(f"PDF se nepodařilo vytvořit: {exc}")
        finally:
            create_button.enable(); send_button.enable()

    async def send():
        create_button.disable(); send_button.disable()
        try:
            config = snapshot()
            if not recipients.commit_pending():
                return
            addresses = normalize_recipients(recipients.addresses)
            if not addresses:
                raise ValueError("Přidejte alespoň jednoho příjemce.")
            settings = owner._outgoing_mail_settings()
            sender = normalize_recipient(owner._outgoing_sender()) if settings["transport"] == "resend" else None
            api_key = await run.io_bound(get_resend_api_key) if settings["transport"] == "resend" else None
            if settings["transport"] == "resend" and not api_key:
                raise ValueError("Chybí Resend API klíč v nastavení odesílání.")
            period = f"{config.report_date:%d.%m.%Y} – {config.report_end_date:%d.%m.%Y}"
            values = {"report": COLLECTION_TITLES[config.collection_status], "date": period}
            subject = settings["subject_template"].format(**values)
            body = settings["body_template"].format(**values)
            if not await owner._confirm_send(len(addresses), subject, extra=f"Období: {period}"):
                return
            status_line.set_text("Vytvářím PDF a odesílám…")
            def deliver():
                path = build_pdf(config)
                if settings["transport"] == "smtp":
                    smtp_send(settings, addresses, subject, body, path)
                else:
                    send_pdf_via_mailsender(addresses, subject, body, path, api_key=api_key, sender_email=sender)
                return path
            path = await run.io_bound(deliver)
            owner.last_pdf = path
            status_line.set_text(f"Odesláno {len(addresses)} příjemcům. PDF: {path}")
        except Exception as exc:
            status_line.set_text(f"Odeslání se nepodařilo: {exc}")
        finally:
            create_button.enable(); send_button.enable()

    create_button.on_click(create)
    send_button.on_click(send)
