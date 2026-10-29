"""Web settings for NSSM, JídelnaSQL warning and outgoing mail."""
from __future__ import annotations

from pathlib import Path
from typing import Callable
from nicegui import ui
from env_store import DEFAULT_ENV_PATH, EnvStoreError, get_resend_api_key, set_resend_api_key
from services.web_mail_settings import load_settings, save_settings, settings_path
from services.web_mail_nssm import service_command, windows_admin_state, ADMIN_HELP
from services.web_path_picker import pick_local_file
from nicegui import run
from services.jidelnasql_warning import (
    JidelnaWarningSettings, show_jidelnasql_mail_warning,
    clear_jidelnasql_mail_warning, is_jidelnasql_mail_warning_active,
)


def build_web_settings_panel(
    directory: Path, *, require_admin: Callable[[], bool] | None = None,
    before_lock: list[Callable[[], None]] | None = None,
    on_api_key_saved: Callable[[str], None] | None = None,
) -> None:
    path = settings_path(directory)
    try:
        values = load_settings(path)
    except (OSError, ValueError) as exc:
        ui.label(f"Nastavení nelze načíst: {exc}").classes("text-negative")
        return

    def allowed() -> bool:
        return require_admin is None or require_admin()

    async def browse(field, kind: str):
        if not allowed():
            return
        try:
            selected = await run.io_bound(pick_local_file, str(field.value or ""), kind=kind)
            if selected and allowed():
                if not Path(selected).is_file():
                    raise ValueError("Vybraný soubor nebyl nalezen.")
                if kind == "nssm" and Path(selected).name.casefold() != "nssm.exe":
                    raise ValueError("Vyberte soubor nssm.exe.")
                field.value = selected
        except (OSError, ValueError) as exc:
            ui.notify(str(exc), type="negative")

    ui.label("Služba a odesílání").classes("ds-page-title").props('role="heading" aria-level="1"')
    ui.label("Služba odesílá přehledy i při zavřeném okně DataShipu. Instalace vyžaduje oprávnění správce Windows.").classes("ui-help")
    with ui.element("div").classes("ds-settings-grid"):
        with ui.column().classes("ds-settings-column w-full"):
            with ui.card().classes("ds-settings-card"):
                ui.label("Windows služba NSSM").classes("app-heading")
                elevated = windows_admin_state()
                ui.label("Oprávnění Windows: správce" if elevated else "Oprávnění Windows: běžný uživatel" if elevated is False else "Správa služby je dostupná ve Windows.").classes("ui-help ds-service-rights")
                if elevated is False:
                    ui.label(ADMIN_HELP).classes("ui-help")
                with ui.row().classes("ds-path-entry w-full items-center no-wrap"):
                    nssm = ui.input("Cesta k nssm.exe", value=values["nssm_path"]).props("outlined dense").classes("grow min-w-0")
                    ui.button("Procházet…", icon="folder_open", on_click=lambda: browse(nssm, "nssm")).props('outline no-caps aria-label="Vybrat nssm.exe"').mark("browse-nssm")
                name = ui.input("Název služby", value=values["service_name"]).props("outlined dense").classes("w-full")
                ui.label("1. Spusťte DataShip.exe jako správce Windows. 2. Ověřte databázi a e-mail. 3. Instalujte službu. 4. Klikněte na Spustit.").classes("ui-help")
                ui.label("Služba zajistí odesílání, i když je okno DataShipu zavřené. Používá DataShip-Worker.exe ze stejné složky.").classes("ui-help")
                service_status = ui.label("Stav služby zatím nebyl ověřen. Klikněte na Ověřit stav.").classes("ui-help ds-service-status").props('role="status" aria-live="polite"')
                busy = {"value": False}
                service_buttons = []
                async def control(action: str):
                    if busy["value"] or not allowed() or not save():
                        return
                    busy["value"] = True
                    for button, _action in service_buttons:
                        button.disable()
                    service_status.set_text("Provádím operaci služby…")
                    try:
                        result = await run.io_bound(service_command, directory, action)
                        service_status.set_text(result)
                        ui.notify(result, type="positive", timeout=8000)
                    except Exception as exc:
                        message = ("Nastavení služby nelze uložit. Ověřte právo zápisu do složky aplikace."
                                   if isinstance(exc, OSError) and exc.errno else str(exc))
                        service_status.set_text(message)
                        ui.notify(message, type="negative", timeout=15000)
                    finally:
                        busy["value"] = False
                        for button, operation in service_buttons:
                            button.set_enabled(elevated is not False or operation == "status")
                with ui.row().classes("gap-2"):
                    for action, caption in (
                        ("install", "Instalovat službu"), ("start", "Spustit službu"),
                        ("stop", "Zastavit službu"), ("restart", "Restartovat"),
                        ("status", "Ověřit stav"), ("repair", "Opravit cesty služby")
                    ):
                        button = ui.button(caption, on_click=lambda op=action: control(op)).props("outline no-caps")
                        button.set_enabled(elevated is not False or action == "status")
                        service_buttons.append((button, action))
                removal_target = {"name": ""}
                with ui.dialog() as removal_dialog, ui.card().classes("w-full max-w-lg gap-3"):
                    ui.label("Odstranit službu?").classes("app-heading")
                    removal_name = ui.label("")
                    ui.label("Běžící služba se nejprve zastaví a potom odstraní z Windows. Automatické odesílání touto službou přestane fungovat. Uložené úlohy, API klíč i ostatní nastavení zůstanou zachované.").classes("ui-help")
                    async def confirm_removal():
                        removal_dialog.close()
                        if str(name.value or "").strip() != removal_target["name"]:
                            ui.notify("Název služby se změnil. Potvrďte odstranění znovu.", type="warning")
                            return
                        await control("remove")
                    with ui.row().classes("w-full justify-end gap-2"):
                        ui.button("Zrušit", on_click=removal_dialog.close).props("outline no-caps").mark("cancel-service-removal")
                        ui.button("Ano, odstranit službu", color="negative", on_click=confirm_removal).props("no-caps").mark("confirm-service-removal")

                def request_removal():
                    if busy["value"] or not allowed() or elevated is False:
                        return
                    removal_target["name"] = str(name.value or "").strip()
                    removal_name.set_text(f'Služba: {removal_target["name"]}')
                    removal_dialog.open()

                remove_button = ui.button("Odstranit službu", icon="delete_outline", color="negative", on_click=request_removal).props("outline no-caps").mark("remove-service")
                remove_button.set_enabled(elevated is not False)
                service_buttons.append((remove_button, "remove"))
                ui.label("Po přesunu DataShipu zastavené službě opravte cesty. Oprava zachová stejnou službu a sama ji nespustí.").classes("ui-help")

            with ui.card().classes("ds-settings-card"):
                ui.label("Upozornění v dashboardu Jídelny").classes("app-heading")
                warning_on = ui.checkbox("Povolit upozornění při chybě", value=values["dashboard_enabled"])
                with ui.row().classes("ds-path-entry w-full items-center no-wrap"):
                    template = ui.input("Cesta k dashboard.template.html", value=values["dashboard_path"]).props("outlined dense").classes("grow min-w-0")
                    ui.button("Procházet…", icon="folder_open", on_click=lambda: browse(template, "dashboard")).props('outline no-caps aria-label="Vybrat šablonu dashboardu"').mark("browse-dashboard")
                state = ui.label("")
                def warning_settings():
                    return JidelnaWarningSettings(
                        enabled=True, template_path=Path(template.value).expanduser()
                    )
                def test_show():
                    if not allowed():
                        return
                    if not warning_on.value:
                        ui.notify("Nejdřív povolte upozornění.", type="warning")
                        return
                    result = show_jidelnasql_mail_warning(
                        warning_settings(), message="TEST MailPilot: upozornění funguje."
                    )
                    ui.notify(result or "Testovací upozornění vloženo.", type="negative" if result else "positive")
                    refresh_state()
                def test_clear():
                    if not allowed():
                        return
                    result = clear_jidelnasql_mail_warning(warning_settings())
                    ui.notify(result or "Testovací upozornění odstraněno.", type="negative" if result else "positive")
                    refresh_state()
                def refresh_state():
                    active = is_jidelnasql_mail_warning_active(warning_settings())
                    state.set_text("Upozornění je v HTML aktivní." if active else "Upozornění v HTML není aktivní.")
                with ui.row().classes("gap-2"):
                    ui.button("Zobrazit test", on_click=test_show).props("outline")
                    ui.button("Odstranit upozornění", on_click=test_clear).props("outline")
                    ui.button("Ověřit stav", on_click=refresh_state).props("flat")
                refresh_state()
                ui.label("Pozor: odstranění smaže i případné aktuální produkční upozornění.").classes("text-caption")

        with ui.column().classes("ds-settings-column w-full"):
            with ui.card().classes("ds-settings-card"):
                ui.label("Odchozí e-mail").classes("app-heading")
                transport = ui.select({"resend": "Resend API", "smtp": "SMTP server"},
                                      label="Způsob odesílání", value=values["transport"]).props("outlined dense").classes("w-full")
                with ui.column().classes("w-full gap-3") as smtp_fields:
                    host = ui.input("SMTP server", value=values["smtp_host"]).props("outlined dense").classes("w-full")
                    port = ui.number("Port SMTP", value=values["smtp_port"], min=1, max=65535, step=1)
                    security = ui.select({"starttls": "STARTTLS", "ssl": "SSL/TLS", "none": "Bez TLS"},
                                         value=values["smtp_security"], label="Zabezpečení SMTP")
                    username = ui.input("SMTP přihlašovací jméno", value=values["smtp_username"]).props("outlined dense").classes("w-full")
                    ui.label("Heslo SMTP ukládejte do prostředí služby jako MAILPILOT_SMTP_PASSWORD, ne do JSON souboru.").classes("text-caption")
                smtp_fields.bind_visibility_from(transport, "value", backward=lambda value: value == "smtp")
                with ui.column().classes("w-full gap-2") as resend_fields:
                    api_key = ui.input(
                        "Resend API klíč", password=True, password_toggle_button=True,
                    ).props("outlined dense autocomplete=off").classes("w-full").mark("resend-api-key")
                    ui.label("Pole slouží pro zadání nového klíče. Po uložení se vyprázdní; uložený klíč zůstává k dispozici.").classes("ui-help")
                    with ui.row().classes("ds-api-key-state w-full items-center no-wrap").props('role="status" aria-live="polite" aria-atomic="true"').mark("resend-key-state") as key_state:
                        key_icon = ui.icon("info", size="24px").props('aria-hidden="true"').mark("resend-key-icon")
                        key_status = ui.label("").classes("ds-api-key-status-text").mark("resend-key-status")
                    ui.label(f"Soubor s klíčem: {DEFAULT_ENV_PATH}").classes("ui-help break-all").mark("resend-key-location")

                    def show_key_status(kind: str, message: str, icon: str):
                        key_state.classes(
                            remove="ds-api-key-state--positive ds-api-key-state--warning ds-api-key-state--negative",
                            add=f"ds-api-key-state--{kind}",
                        )
                        key_icon.props(f'name={icon}')
                        key_status.set_text(message)

                    def refresh_key_status():
                        try:
                            loaded = get_resend_api_key()
                        except (EnvStoreError, OSError):
                            show_key_status("negative", "Uložený API klíč se nepodařilo načíst.", "error_outline")
                            return
                        if loaded:
                            show_key_status("positive", "API klíč je uložený a načtený.", "check_circle")
                        else:
                            show_key_status("warning", "API klíč zatím není nastaven.", "key_off")

                    def key_changed():
                        if str(api_key.value or "").strip():
                            show_key_status("warning", "Nový API klíč ještě není uložený.", "edit_note")
                        else:
                            refresh_key_status()

                    refresh_key_status()
                    api_key.on_value_change(lambda _event: key_changed())

                    def save_api_key():
                        if not allowed():
                            return
                        value = str(api_key.value or "").strip()
                        if not value:
                            refresh_key_status()
                            return
                        try:
                            set_resend_api_key(value)
                        except (EnvStoreError, OSError):
                            show_key_status("negative", "API klíč se nepodařilo uložit. Ověřte právo zápisu do složky aplikace.", "error_outline")
                            return
                        try:
                            loaded = get_resend_api_key()
                        except (EnvStoreError, OSError):
                            loaded = None
                        if loaded != value:
                            show_key_status("negative", "API klíč byl zapsán, ale jeho načtení se nepodařilo ověřit. Zkuste jej uložit znovu.", "error_outline")
                            return
                        if on_api_key_saved is not None:
                            on_api_key_saved(value)
                        api_key.value = ""
                        show_key_status("positive", "API klíč je uložený a načtený.", "check_circle")

                    api_key.on("keydown.enter.prevent", save_api_key)
                    ui.button("Uložit API klíč", icon="save", on_click=save_api_key).props("outline no-caps")
                resend_fields.bind_visibility_from(transport, "value", backward=lambda value: value == "resend")
                from_email = ui.input("E-mail odesílatele", value=values["from_email"]).props("outlined dense").classes("w-full")
                from_name = ui.input("Zobrazované jméno odesílatele", value=values["from_name"]).props("outlined dense").classes("w-full")
                subject = ui.input("Výchozí předmět", value=values["subject_template"]).props("outlined dense").classes("w-full")
                body = ui.textarea("Výchozí text e-mailu", value=values["body_template"]).props("outlined dense").classes("w-full")
                ui.label("Dostupné proměnné: {report}, {date}.").classes("text-caption")

    with ui.expansion("Kalendář starších odesílání", icon="history").classes("w-full app-note"):
        ui.label("Platí pouze pro starší odesílání bez vlastního kalendáře. U každého nového odesílání vyberete kalendář přímo v jeho úpravě.").classes("ui-help")
        cooking_meal_type = ui.input(
            "Dosavadní kalendář varných dnů",
            value=values["cooking_meal_type"],
        ).props("outlined dense").classes("w-full")
        ui.label("Po uložení vlastního kalendáře u odesílání se toto společné nastavení pro něj už nepoužije.").classes("ui-help")

    autosave = {"timer": None, "dirty": False}
    save_status = ui.label("Změny se ukládají automaticky.").classes("ui-help ds-settings-save").props('role="status" aria-live="polite"').mark("settings-autosave-status")

    def save() -> bool:
        if autosave["timer"] is not None:
            autosave["timer"].deactivate()
        if not allowed():
            return False
        try:
            if port.value is None or not float(port.value).is_integer():
                raise ValueError("Zadejte celé číslo portu SMTP od 1 do 65535.")
            data = dict(
                nssm_path=nssm.value.strip(), service_name=name.value.strip(),
                cooking_meal_type=cooking_meal_type.value.strip(),
                dashboard_enabled=warning_on.value, dashboard_path=template.value.strip(),
                transport=transport.value, smtp_host=host.value.strip(),
                smtp_port=int(port.value), smtp_security=security.value,
                smtp_username=username.value.strip(), from_email=from_email.value.strip(),
                from_name=from_name.value.strip(), subject_template=subject.value,
                body_template=body.value,
            )
            save_settings(path, data)
        except (OSError, ValueError, TypeError) as exc:
            save_status.set_text(f"Změny nejsou uložené: {exc}")
            save_status.classes(add="text-negative")
            return False
        else:
            autosave["dirty"] = False
            save_status.set_text("Uloženo.")
            save_status.classes(remove="text-negative")
            return True

    def queue_save():
        if not allowed():
            return
        autosave["dirty"] = True
        if autosave["timer"] is not None:
            autosave["timer"].deactivate()
        save_status.set_text("Ukládám…")
        save_status.classes(remove="text-negative")
        autosave["timer"] = ui.timer(0.7, save, once=True, immediate=False)

    def flush():
        if autosave["dirty"]:
            save()

    for field in (nssm, name, warning_on, template, transport, host, port, security,
                  username, from_email, from_name, subject, body, cooking_meal_type):
        field.on_value_change(lambda _event: queue_save())
        field.on("blur", flush)
    if before_lock is not None:
        before_lock.append(flush)


