"""Web settings for NSSM, JídelnaSQL warning and outgoing mail."""
from __future__ import annotations

from pathlib import Path
from nicegui import ui
from services.web_mail_settings import load_settings, save_settings, settings_path
from services.web_mail_nssm import service_command
from nicegui import run
from services.jidelnasql_warning import (
    JidelnaWarningSettings, show_jidelnasql_mail_warning,
    clear_jidelnasql_mail_warning, is_jidelnasql_mail_warning_active,
)


def build_web_settings_panel(directory: Path) -> None:
    path = settings_path(directory)
    try:
        values = load_settings(path)
    except (OSError, ValueError) as exc:
        ui.label(f"Nastavení nelze načíst: {exc}").classes("text-negative")
        return

    ui.label("Služba a odesílání").classes("text-h6")
    ui.label("Nastavení se ukládá pro centrální plánovač. Instalace služby vyžaduje oprávnění správce.")
    with ui.card().classes("w-full"):
        ui.label("Windows služba NSSM").classes("text-subtitle1")
        nssm = ui.input("Cesta k nssm.exe", value=values["nssm_path"]).classes("w-full")
        name = ui.input("Název služby", value=values["service_name"]).classes("w-full")
        ui.label("Správa služby vyžaduje na Windows oprávnění správce.").classes("text-caption")
        async def control(action: str):
            try:
                # Save current service paths before invoking NSSM.
                current = load_settings(path)
                current.update(nssm_path=nssm.value.strip(), service_name=name.value.strip())
                save_settings(path, current)
                result = await run.io_bound(service_command, directory, action)
                ui.notify(result or "Operace dokončena.", type="positive")
            except Exception as exc:
                ui.notify(f"NSSM: {exc}", type="negative")
        with ui.row().classes("gap-2"):
            for action, caption in (
                ("install", "Instalovat"), ("start", "Spustit"),
                ("stop", "Zastavit"), ("restart", "Restart"),
                ("status", "Stav")
            ):
                ui.button(caption, on_click=lambda op=action: control(op)).props("outline")

    with ui.card().classes("w-full"):
        ui.label("Upozornění v dashboardu Jídelny").classes("text-subtitle1")
        warning_on = ui.checkbox("Povolit upozornění při chybě", value=values["dashboard_enabled"])
        template = ui.input("Cesta k dashboard.template.html", value=values["dashboard_path"]).classes("w-full")
        state = ui.label("")
        def warning_settings():
            return JidelnaWarningSettings(
                enabled=True, template_path=Path(template.value).expanduser()
            )
        def test_show():
            if not warning_on.value:
                ui.notify("Nejdřív povolte upozornění.", type="warning")
                return
            result = show_jidelnasql_mail_warning(
                warning_settings(), message="TEST MailPilot: upozornění funguje."
            )
            ui.notify(result or "Testovací upozornění vloženo.", type="negative" if result else "positive")
            refresh_state()
        def test_clear():
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

    with ui.card().classes("w-full"):
        ui.label("Odchozí e-mail").classes("text-subtitle1")
        transport = ui.select({"resend": "Resend API (stávající)", "smtp": "SMTP server"},
                              label="Způsob odesílání", value=values["transport"]).classes("w-full")
        host = ui.input("SMTP server", value=values["smtp_host"]).classes("w-full")
        port = ui.number("Port SMTP", value=values["smtp_port"], min=1, max=65535, step=1)
        security = ui.select({"starttls": "STARTTLS", "ssl": "SSL/TLS", "none": "Bez TLS"},
                             value=values["smtp_security"], label="Zabezpečení SMTP")
        username = ui.input("SMTP přihlašovací jméno", value=values["smtp_username"]).classes("w-full")
        ui.label("Heslo SMTP ukládejte do prostředí služby jako MAILPILOT_SMTP_PASSWORD, ne do JSON souboru.").classes("text-caption")
        from_email = ui.input("E-mail odesílatele", value=values["from_email"]).classes("w-full")
        from_name = ui.input("Zobrazované jméno odesílatele", value=values["from_name"]).classes("w-full")
        subject = ui.input("Výchozí předmět", value=values["subject_template"]).classes("w-full")
        body = ui.textarea("Výchozí text e-mailu", value=values["body_template"]).classes("w-full")
        ui.label("Dostupné proměnné: {report}, {date}.").classes("text-caption")

    def save():
        data = dict(
            nssm_path=nssm.value.strip(), service_name=name.value.strip(),
            dashboard_enabled=warning_on.value, dashboard_path=template.value.strip(),
            transport=transport.value, smtp_host=host.value.strip(),
            smtp_port=int(port.value), smtp_security=security.value,
            smtp_username=username.value.strip(), from_email=from_email.value.strip(),
            from_name=from_name.value.strip(), subject_template=subject.value,
            body_template=body.value,
        )
        try:
            save_settings(path, data)
        except (OSError, ValueError, TypeError) as exc:
            ui.notify(f"Uložení selhalo: {exc}", type="negative")
        else:
            ui.notify("Nastavení uloženo.", type="positive")

    ui.button("Uložit nastavení", on_click=save, icon="save").props("color=primary")
