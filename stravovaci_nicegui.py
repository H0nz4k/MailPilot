#!/usr/bin/env python3
"""NiceGUI rozhraní pro DataShip."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Sequence

from runtime_paths import application_directory
from services.web_windowed_runtime import prepare_windowed_streams

# A windowed EXE has no standard streams, but the web server still uses them.
prepare_windowed_streams(application_directory())

from nicegui import app, native, run, ui

from automaticky_export import main as automatic_export_main
from uzaverka import main as monthly_closing_main
from hromadna_zprava import (
    FILTER_CATEGORY,
    FILTER_CLASS,
    FILTER_LABELS,
    apply_bulk_ui,
    bulk_preview_summary,
    fetch_bulk_filters,
    missing_email_counts,
    missing_email_diners,
    option_label,
    peek_bulk_ui,
    preview_from_diners,
    send_bulk_message,
)
from uzaverka_nastaveni import (
    CLOSING_FLAG_HELP,
    CURRENT_CLOSING_PERIOD,
    REPORT_LABELS,
    SESTAVA_ARCH,
    SESTAVA_FKSP,
    SESTAVA_REKAPITULACE,
    apply_closing_ui,
    closing_flag,
    consume_closing_flag,
    peek_closing_ui,
)
from z17 import main as z17_main, run_z17_report
from z17_nastaveni import (
    Z17_FLAG_HELP,
    apply_z17_ui,
    consume_z17_flag,
    parse_z17_year,
    peek_z17_ui,
    z17_flag,
)

from credential_store import (
    CredentialStoreError,
    get_admin_password,
    get_password,
    sanitize_config,
    set_admin_password,
    set_password,
    write_config,
)
from pocty_nastaveni import all_client_categories, peek_client_categories
from env_store import EnvStoreError, get_resend_api_key, set_resend_api_key
from mail_service import (
    MailDispatchResult,
    cooking_status_message,
    fetch_cooking_status,
    mail_subject,
    normalize_recipient,
    normalize_recipients,
    send_pdf_via_mailsender,
    should_send_on_cooking_day,
)
from services.config_io import (
    CZECH_DATE_FORMAT,
    DEFAULT_PDF_OUTPUT,
    configured_date,
    connection_identity,
    database_parameters,
    open_document,
    parse_czech_date,
)
from services.config_io import load_raw_config as load_ui_config
from services.database import probe_connection
from services.web_branding import (
    BRAND_NAME, BRAND_STAGE, BRAND_FOOTER, BRAND_ICON, BRAND_FAVICON, WEB_VERSION, WEB_BUILD, version_caption,
)
from services.web_mail_settings import load_settings, settings_path
from services.web_mail_smtp import smtp_send
from services.web_first_run import FirstRunMixin, database_error_message
from services.web_date_ui import CZECH_DATE_LOCALE, initial_report_date
from services.web_navigation import EDITABLE_TABS, visible_tabs
from services.web_report_output import manual_pdf_path
from services.web_meal_types import normalize_meal_filter, meal_filter_values, meal_filter_caption
from services.web_daily_design import DailyDesignMixin
from services.web_daily_design_css import DATASHIP_CSS
from services.web_closing_design import ClosingDesignMixin
from services.web_admin_session import AdminSessionMixin
from ui_theme import (
    DEFAULT_UI_LAYOUT,
    DEFAULT_UI_TEMPLATE,
    DEFAULT_UI_TEXT_SIZE,
    DEFAULT_UI_THEME,
    DEFAULT_UI_ZOOM,
    UI_CSS,
    UI_DENSITY_LABELS,
    UI_LAYOUT_LABELS,
    UI_LAYOUTS,
    UI_LINE_HEIGHT,
    UI_SPACING_LABELS,
    UI_SPACING_PX,
    UI_STYLE_TEMPLATE_LABELS,
    UI_STYLE_TEMPLATES,
    UI_TEXT_SIZE_LABELS,
    UI_TEXT_SIZE_PX,
    UI_THEME_LABELS,
    UI_THEMES,
    UI_ZOOM_MAX,
    UI_ZOOM_MIN,
    UI_ZOOM_STEP,
    appearance_config,
    appearance_theme,
    appearance_css_vars,
    appearance_html_classes,
    apply_ui_appearance,
    layout_tokens,
    peek_ui_appearance,
    peek_ui_blocks,
    peek_ui_density,
    peek_ui_layout,
    peek_ui_line,
    peek_ui_size,
    peek_ui_spacing,
    peek_ui_template,
    peek_ui_text_size,
    peek_ui_theme,
    peek_ui_zoom,
)
import ui_widgets as w
from stravovaci_sestava import (
    SUBJECT_NAME_QUERY,
    ConfigError,
    create_pdf,
    fetch_report,
    available_meal_types,
    load_config,
    peek_jidelna_period,
)


APP_TITLE = BRAND_NAME
APP_VERSION = WEB_VERSION
NATIVE_WINDOW_SIZE = (1280, 860)
SCHEDULER_HELP_TEXT = (
    "Úlohu přiřaďte k funkci: Denní stav (--poctyemailem, "
    "spustit_automaticky_export.bat), Uzávěrka (--zaverka_MMRRRR za předchozí "
    "měsíc) nebo Special (--z17_RRRR). Jídelna může stejné EXE volat přímo."
)
CLI_HELP_INTRO = (
    "Bez parametru se otevře toto okno. Příkazy níže GUI neotevřou: použijí "
    "aktuální config.json vedle EXE a nastavení ze záložek. Pište je ve složce "
    "s DataShip.exe, v Jídelně, nebo v Plánovači úloh."
)
CLI_COMMANDS = (
    {
        "command": "DataShip.exe --poctyemailem",
        "title": "Denní stav bez okna",
        "detail": (
            "Vezme dnešní datum (uložené datum v configu ignoruje), spočítá počty "
            "jen z kategorií povolených v Denním stavu, vytvoří PDF a odešle ho "
            "příjemcům funkce Denní stav. Stejné jako --automatic nebo "
            "spustit_poctyemailem.bat. Když je zapnuté odesílání jen ve varných "
            "dnech a dnes se nevaří, nic se nevytvoří ani neodešle (návrat 0). "
            "Log: logy\\automaticky_export.log."
        ),
    },
    {
        "command": "DataShip.exe --zaverka_072026",
        "title": "Měsíční uzávěrka bez okna",
        "detail": (
            "Číslo 072026 znamená červenec 2026 (tvar MMRRRR). Vytvoří sestavy "
            "zaškrtnuté na záložce Uzávěrka (FKSP, stravovací arch, rekapitulace) "
            "do zvolené složky, případně je zabalí do ZIP a pošle příjemcům funkce "
            "Uzávěrka. Holé --zaverka bez měsíce aplikace odmítne. Starší "
            "--uzaverka_072026 funguje stejně. Z Jídelny: spustit_uzaverku.bat 072026. "
            "Log: logy\\uzaverka.log."
        ),
    },
    {
        "command": "DataShip.exe --zaverka_am",
        "title": "Uzávěrka aktuálního měsíce",
        "detail": (
            "Stejné sestavy, složka, ZIP a mail jako --zaverka_MMRRRR, ale období "
            "vezme z databáze: public.parametry / BACKUP / TentoMesic a TentoRok "
            "(například 7 a 2026 → 072026). Aktuální měsíc Jídelny je vidět "
            "v zeleném bloku po TESTu připojení. Alias --uzaverka_am. "
            "Z Jídelny: spustit_uzaverku.bat am. Log: logy\\uzaverka.log."
        ),
    },
    {
        "command": "DataShip.exe --z17_2026",
        "title": "Podklad Z 17-01 bez okna",
        "detail": (
            "Spočítá roční podklad k výkazu Z 17-01 za rok 2026 (stav zapsaných "
            "k 31. 10. a součty porcí za školní rok) a uloží PDF do složky ze "
            "záložky Special. Kategorie bere z volby na této záložce, ne z Denního stavu. "
            "Z Jídelny: spustit_z17.bat 2026. Log: logy\\z17.log."
        ),
    },
)


def placeholder_path_tail(path_text: str) -> list[str]:
    """Vrátí koncové části cesty, které obsahují {zástupné} hodnoty."""
    text = str(path_text or "").replace("\\", "/").strip()
    if not text:
        return []
    tail: list[str] = []
    for part in reversed(Path(text).parts):
        if "{" in part and "}" in part:
            tail.append(part)
        else:
            break
    tail.reverse()
    return tail


def join_picked_directory(
    current: str,
    picked: str,
    *,
    filename: str | None = None,
) -> str:
    """Složí vybranou složku s původním názvem souboru nebo {zástupnými} částmi."""
    picked_path = Path(str(picked).strip())
    current_text = str(current or "").strip()
    if filename:
        name = Path(current_text or filename).name
        if not name.lower().endswith(".pdf"):
            name = filename
        return str(picked_path / name)
    result = picked_path
    for part in placeholder_path_tail(current_text):
        result = result / part
    return str(result)


def existing_directory_for_dialog(
    path_text: str,
    *,
    config_directory: Path | None = None,
) -> str | None:
    """Najde existující složku, od které má dialog Procházet začít."""
    text = str(path_text or "").strip()
    candidates: list[Path] = []
    if text:
        raw = Path(text)
        if raw.suffix.lower() == ".pdf":
            raw = raw.parent
        while raw.parts and "{" in raw.name and "}" in raw.name:
            raw = raw.parent
        if raw.parts and str(raw) not in {".", ""}:
            if not raw.is_absolute() and config_directory is not None:
                raw = config_directory / raw
            candidates.append(raw)
            candidates.extend(raw.parents)
    if config_directory is not None:
        candidates.append(config_directory)
    for candidate in candidates:
        try:
            if candidate.is_dir():
                return str(candidate)
        except OSError:
            continue
    return None


def pick_local_directory(initial: str | None = None) -> str | None:
    """Otevře systémový dialog pro výběr složky na tomto počítači."""
    if sys.platform.startswith("win"):
        try:
            return _pick_directory_windows(initial)
        except Exception:
            return _pick_directory_tkinter(initial)
    return _pick_directory_tkinter(initial)


def _pick_directory_tkinter(initial: str | None) -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return None
    root = tk.Tk()
    root.withdraw()
    try:
        root.wm_attributes("-topmost", True)
    except tk.TclError:
        pass
    kwargs: dict[str, Any] = {
        "mustexist": True,
        "title": "Vyberte složku pro uložení sestav",
    }
    if initial:
        kwargs["initialdir"] = initial
    try:
        path = filedialog.askdirectory(**kwargs)
    finally:
        root.destroy()
    return str(path) if path else None


def _pick_directory_windows(initial: str | None) -> str | None:
    """Windows dialog výběru složky; při chybě se zkusí Tkinter."""
    del initial
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return None

    bif_return_only_fs_dirs = 0x0001
    bif_new_dialog_style = 0x0040
    bif_edit_box = 0x0010

    class BrowseInfo(ctypes.Structure):
        _fields_ = [
            ("hwndOwner", wintypes.HWND),
            ("pidlRoot", ctypes.c_void_p),
            ("pszDisplayName", wintypes.LPWSTR),
            ("lpszTitle", wintypes.LPCWSTR),
            ("ulFlags", wintypes.UINT),
            ("lpfn", ctypes.c_void_p),
            ("lParam", wintypes.LPARAM),
            ("iImage", ctypes.c_int),
        ]

    ole32 = ctypes.windll.ole32
    shell32 = ctypes.windll.shell32
    user32 = ctypes.windll.user32
    try:
        ole32.CoInitialize(None)
    except OSError:
        pass
    display = ctypes.create_unicode_buffer(260)
    info = BrowseInfo()
    info.hwndOwner = user32.GetForegroundWindow()
    info.pszDisplayName = display
    info.lpszTitle = "Vyberte složku pro uložení sestav"
    info.ulFlags = bif_return_only_fs_dirs | bif_new_dialog_style | bif_edit_box
    pidl = shell32.SHBrowseForFolderW(ctypes.byref(info))
    if not pidl:
        return None
    try:
        path = ctypes.create_unicode_buffer(260)
        if shell32.SHGetPathFromIDListW(pidl, path):
            return path.value or None
        return None
    finally:
        ole32.CoTaskMemFree(pidl)


def native_ui_available() -> bool:
    """Je k dispozici pywebview pro klasické Windows okno."""
    try:
        import webview  # noqa: F401
    except ImportError:
        return False
    return True


def configure_ui_window(*, browser: bool, native_window: bool, port: int) -> dict[str, Any]:
    """Výchozí je prohlížeč. Klasické okno jen při --native, pokud je pywebview."""
    if native_window and not browser and native_ui_available():
        return {
            "native": True,
            "window_size": NATIVE_WINDOW_SIZE,
            "fullscreen": False,
            "reload": False,
            "host": "127.0.0.1",
            "port": port,
            "show": False,
        }
    return {"native": False, "host": "127.0.0.1", "port": port, "show": True}


def shutdown_when_last_client_closes(current_client: Any) -> None:
    """Ukončí lokální server po zavření poslední stránky DataShipu."""
    other_clients = [
        client
        for client in app.clients()
        if client is not current_client and not client.is_deleted
    ]
    if not other_clients:
        app.shutdown()


class NiceGuiApp(FirstRunMixin, DailyDesignMixin, ClosingDesignMixin, AdminSessionMixin):
    """Stav a obslužné funkce zákaznické aplikace."""

    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path.resolve()
        self.raw = load_ui_config(self.config_path)
        self.connection_ok = False
        self.connection_caption = "Nepřipojeno"
        self.connection_name = "Jídelna zatím není připojena"
        self.connection_details = "Kliknutím otevřete TEST připojení"
        self.categories: list[tuple[str, str]] = []
        self.all_categories = all_client_categories(self.raw)
        self.allowed_categories: set[str] = set(peek_client_categories(self.raw))
        self.selected_categories: set[str] = set()
        self._connection_password: str | None = None
        self.z17_selected_categories: set[str] = set(
            peek_z17_ui(self.raw)["povolene_kategorie"]
        )
        self.last_z17_pdf: Path | None = None
        self.bulk_classes: list[tuple[str, str]] = []
        self.bulk_diners: list[Any] = []
        self.bulk_selected: list[str] = []
        self.bulk_preview = None
        self.last_pdf: Path | None = None
        self.last_mail_note = "zatím žádné"
        self.initial_status = ""
        self.admin_unlocked = False
        self.layout = dict(UI_LAYOUTS[peek_ui_layout(self.raw)])
        self._admin_target_section = "db"
        self._migrate_legacy_secrets()

    def _migrate_legacy_secrets(self) -> None:
        """Přesune staré citlivé údaje z JSON do systémového trezoru."""
        changed = False
        database = database_parameters(self.raw)
        raw_database = self.raw.get("databaze")
        if isinstance(raw_database, dict):
            legacy_password = raw_database.get("password")
            if isinstance(legacy_password, str) and legacy_password:
                try:
                    set_password(database, legacy_password)
                    changed = True
                    self.initial_status = (
                        "Heslo bylo přesunuto z config.json do systémového trezoru."
                    )
                except CredentialStoreError as exc:
                    self.initial_status = str(exc)

        legacy_api_key: str | None = None
        secret_names = ("resend_api_key", "mail_api_key", "RESEND_API_KEY")
        for key in secret_names:
            value = self.raw.get(key)
            if isinstance(value, str) and value.strip():
                legacy_api_key = value.strip()
                break
        raw_mail = self.raw.get("mail")
        if legacy_api_key is None and isinstance(raw_mail, dict):
            for key in secret_names:
                value = raw_mail.get(key)
                if isinstance(value, str) and value.strip():
                    legacy_api_key = value.strip()
                    break
        if legacy_api_key:
            try:
                set_resend_api_key(legacy_api_key)
                changed = True
                self.initial_status = (
                    "Resend API klíč byl přesunut z configu do souboru .env."
                )
            except EnvStoreError as exc:
                self.initial_status = str(exc)

        if changed:
            self.raw = sanitize_config(self.raw)
            write_config(self.config_path, self.raw)

    def _stored_password(self) -> str:
        try:
            return get_password(database_parameters(self.raw)) or ""
        except CredentialStoreError:
            return ""

    def _stored_api_key(self) -> str:
        try:
            return get_resend_api_key() or ""
        except EnvStoreError:
            return ""

    def build(self) -> None:
        """Sestaví jednu lokální stránku NiceGUI."""
        current_client = ui.context.client
        current_client.on_delete(
            lambda: shutdown_when_last_client_closes(current_client)
        )
        ui.add_css(UI_CSS)
        ui.add_css(DATASHIP_CSS)
        self._dark_mode = ui.dark_mode(False)
        appearance = peek_ui_appearance(self.raw)
        apply_ui_appearance(appearance, dark_mode=self._dark_mode)
        self.layout = layout_tokens(appearance)
        self._install_admin_session()

        with ui.column().classes("app-page dataship-ui gap-0 px-3 py-2"):
            self._build_topbar()
            self.status_label = ui.label("").classes(
                "status-strip w-full px-2 py-1 mt-1"
            )
            self.status_label.set_visibility(False)
            if self.initial_status:
                self.set_status(self.initial_status)
            self._build_workspace()
            with ui.row().classes("w-full justify-end pt-1"):
                ui.label(BRAND_FOOTER).classes("app-footer")
        self._build_database_setup_dialog()
        current_client.on_connect(self._schedule_first_run)

    def _build_topbar(self) -> None:
        """Kompaktní hlavička: DataShip | provozovna | stav DB | období | Administrace."""
        with ui.element("div").classes("app-topbar no-wrap"):
            self._build_header_identity()
            self._build_navigation()
            self.lock_admin_button = (
                ui.button(icon="lock_open", on_click=self.lock_admin)
                .props('outline dense no-caps aria-label="Uzamknout nastavení"')
                .classes("shrink-0")
            )
            self.lock_admin_button.tooltip("Uzamknout nastavení")
            self.admin_button = (
                ui.button("Nastavení", icon="settings", on_click=self.open_admin_dialog)
                .props("outline dense no-caps")
                .classes("shrink-0")
            )
            self.lock_admin_button.set_visibility(False)
            ui.button(icon="contrast", on_click=self.toggle_color_mode).props(
                'flat round aria-label="Přepnout světlý a tmavý režim"'
            ).classes("ds-theme-toggle")
            self.brand_home.on("keydown.enter", self.go_home)
            self.brand_home.on("keydown.space", self.go_home)
            self._build_admin_dialog()

    def _build_header_identity(self) -> None:
        with ui.column().classes("ds-identity gap-1 min-w-0"):
            with ui.row().classes(
                "brand-mark items-center no-wrap shrink-0 cursor-pointer"
            ).on("click", self.go_home).props(
                'role="link" tabindex="0" aria-label="DataShip – hlavní obrazovka"'
            ) as self.brand_home:
                ui.icon(BRAND_ICON, size="1.25rem")
                ui.label(APP_TITLE).classes("app-title")
            self.version_label = ui.label(
                version_caption(frozen=bool(getattr(sys, "frozen", False)))
            ).classes("ui-help").style("white-space: normal; overflow-wrap: anywhere").mark("app-version")
            with ui.row().classes(
                "db-chip items-center gap-2 no-wrap px-2 py-1 flex-grow min-w-0"
            ).on("click", self.open_database_settings) as self.connection_strip:
                self.connection_icon = ui.icon(
                    "cloud_off", size="1.05rem", color="negative"
                )
                self.connection_caption_label = ui.label(
                    self.connection_caption
                ).classes("connection-caption shrink-0")
                self.connection_name_label = ui.label(self.connection_name).classes(
                    "connection-name shrink-0"
                )
                self.connection_details_label = ui.label(
                    self.connection_details
                ).classes("connection-details truncate")
                self.connection_details_label.set_visibility(False)
                self.connection_tooltip = ui.tooltip("Připojení k Jídelně")

    def go_home(self) -> None:
        """Logo vždy vrací na hlavní obrazovku bez změny admin oprávnění."""
        self.tabs.value = "daily"

    def toggle_color_mode(self) -> None:
        current = self._appearance_from_widgets()["schema"]
        if appearance_theme(self._appearance_from_widgets())["dark"]:
            target = getattr(self, "_last_light_schema", "svetle")
        else:
            self._last_light_schema = current
            target = "tmave"
        self.ui_theme.value = target
        self.save_ui_appearance()

    def _build_workspace(self) -> None:
        """Navigace a obsah. Umístění navigace řídí CSS podle zvolené šablony."""
        with ui.element("div").classes("app-shell workspace w-full mt-1"):
            self._build_panels()

    def _build_navigation(self) -> None:
        with ui.tabs().props("inline-label dense no-caps").classes(
            "app-nav"
        ) as self.tabs:
            self.daily_tab = ui.tab("daily", label="Přehledy", icon="today")
            self.mail_tasks_tab = ui.tab("mail_tasks", label="Plánovač", icon="schedule_send")
            self.closing_tab = ui.tab("closing", label="Uzávěrka", icon="print")
            self.special_tab = ui.tab("special", label="Speciál", icon="assignment")
            self.bulk_tab = ui.tab("bulk", label="Hromadná zpráva", icon="campaign")
            self.admin_tab = ui.tab("admin", label="Nastavení", icon="settings")
        self.nav_tab_elements = {
            "daily": self.daily_tab, "closing": self.closing_tab,
            "special": self.special_tab, "bulk": self.bulk_tab,
            "mail_tasks": self.mail_tasks_tab,
        }
        self.admin_tab_elements = (self.admin_tab,)
        self._apply_admin_visibility()

    def _build_panels(self) -> None:
        with ui.tab_panels(self.tabs, value="daily").props("animated=false").classes(
            "w-full flex-grow min-w-0"
        ):
            with ui.tab_panel("daily"):
                self._build_daily_panel()
            with ui.tab_panel("closing"):
                self._build_closing_panel()
            with ui.tab_panel("special"):
                self._build_special_panel()
            with ui.tab_panel("bulk"):
                self._build_bulk_panel()
            with ui.tab_panel("mail_tasks"):
                self._build_sending_panel()
            with ui.tab_panel("admin"):
                self._build_admin_panel()

    def _build_sending_panel(self) -> None:
        """The planner has one list; new reports start in the wizard."""
        from services.web_mail_gui import build_mail_tasks_panel
        self.mail_tasks_editor = build_mail_tasks_panel(
            self.config_path.parent, config_path=self.config_path,
            category_names=lambda: dict(self.categories),
            on_open_reports=self.go_home,
            on_new_plan=lambda: (self._wizard_new(), self.go_home()),
        )
        self.mail_tasks_refresh = self.mail_tasks_editor.refresh

    def _build_admin_dialog(self) -> None:
        with ui.dialog() as self.admin_dialog, ui.card().classes("w-[420px] gap-2"):
            with ui.column().classes("w-full gap-2"):
                self.admin_dialog_title = ui.label("Administrace").classes("app-heading")
                self.admin_dialog_help = ui.label(
                    "Zadejte heslo pro administraci."
                ).classes("ui-help")
                self.admin_password_input = ui.input("Heslo administrace", password=True).classes(
                    "w-full"
                ).on("keydown.enter.prevent", self._submit_admin_dialog)
                self.admin_password_repeat = ui.input(
                    "Heslo administrace znovu", password=True
                ).classes("w-full").on("keydown.enter.prevent", self._submit_admin_dialog)
                self.admin_dialog_error = ui.label("").classes("ui-help text-red-700")
                ui.label("Administrace se po 10 minutách nečinnosti automaticky uzamkne.").classes("ui-help")
                with ui.row().classes("w-full justify-end gap-2 pt-2"):
                    ui.button("Zrušit", on_click=self.admin_dialog.close).props(
                        "type=button outline no-caps"
                    )
                    ui.button("Potvrdit", on_click=self._submit_admin_dialog).props("type=button no-caps").style("color: var(--ds-on-primary) !important")

    def _admin_password_is_set(self) -> bool:
        # An unreadable vault must never be mistaken for first-time setup.
        return bool(get_admin_password())

    def open_admin_dialog(self) -> None:
        self.admin_dialog.open()
        self.admin_dialog_error.set_text("")
        try:
            first_setup = not self._admin_password_is_set()
        except CredentialStoreError as exc:
            self.admin_dialog_error.set_text(str(exc))
            return
        self.admin_password_input.value = ""
        self.admin_password_repeat.value = ""
        self.admin_dialog_error.set_text("")
        if first_setup:
            self.admin_dialog_title.set_text("Nastavit heslo administrátora")
            self.admin_dialog_help.set_text(
                "Zvolte si heslo pro nastavení DataShipu. V dalším kroku připojíme Jídelnu."
            )
            self.admin_password_repeat.set_visibility(True)
        else:
            self.admin_dialog_title.set_text("Administrace")
            self.admin_dialog_help.set_text(
                "Zadejte heslo pro administraci."
            )
            self.admin_password_repeat.set_visibility(False)
        self.admin_dialog.open()
        self.admin_password_input.run_method("focus")

    def _submit_admin_dialog(self, _event: Any = None) -> None:
        """Enter v poli hesla potvrdí dialog; při prvním nastavení skočí na kontrolu."""
        if not self.admin_dialog.value:
            return
        try:
            first_setup = not self._admin_password_is_set()
        except CredentialStoreError as exc:
            self.admin_dialog_error.set_text(str(exc))
            return
        if first_setup and not str(self.admin_password_repeat.value or "").strip():
            self.admin_password_repeat.run_method("focus")
            return
        self.confirm_admin()

    def confirm_admin(self) -> None:
        password = str(self.admin_password_input.value or "")
        try:
            first_setup = not self._admin_password_is_set()
            if first_setup:
                repeat = str(self.admin_password_repeat.value or "")
                if password != repeat:
                    self.admin_dialog_error.set_text("Hesla se neshodují.")
                    return
                set_admin_password(password)
            else:
                stored = get_admin_password() or ""
                if password != stored:
                    self.admin_dialog_error.set_text("Nesprávné heslo administrace.")
                    return
        except CredentialStoreError as exc:
            self.admin_dialog_error.set_text(str(exc))
            return
        self._start_admin_session()
        self.admin_password_input.value = ""
        self.admin_password_repeat.value = ""
        self._apply_admin_visibility()
        self.admin_dialog.close()
        self._open_admin_section(self._admin_target_section)
        self.set_status("")
        if getattr(self, "_database_setup_pending", False):
            self._open_database_setup()

    def lock_admin(self) -> None:
        self._close_admin_session()
        self._apply_admin_visibility()
        if self.tabs.value == "admin":
            self.tabs.value = "daily"
        self.set_status("")

    def _open_admin_section(self, section: str = "db") -> None:
        """Přepne na administraci a vybere v jejím sidebaru konkrétní sekci."""
        if not self._require_admin():
            return
        self.tabs.value = "admin"
        if hasattr(self, "admin_sections"):
            self.admin_sections.value = section

    def open_database_settings(self) -> None:
        """Otevře sekci Databáze; při zamčené administraci nejdřív heslo."""
        if self._require_admin(silent=True):
            self._open_admin_section("db")
            return
        self._admin_target_section = "db"
        self.open_admin_dialog()

    def _apply_admin_visibility(self) -> None:
        for tab in getattr(self, "admin_tab_elements", ()):
            tab.set_visibility(self.admin_unlocked)
        if hasattr(self, "admin_button"):
            self.admin_button.set_visibility(not self.admin_unlocked)
        if hasattr(self, "lock_admin_button"):
            self.lock_admin_button.set_visibility(self.admin_unlocked)
        self._apply_navigation_visibility()

    def _apply_navigation_visibility(self) -> None:
        """Apply persisted top-tab visibility immediately; admin remains protected."""
        settings = visible_tabs(self.raw)
        if hasattr(self, "daily_schedule_card"):
            self.daily_schedule_card.set_visibility(False if hasattr(self, "_wizard_step") else settings["mail_tasks"])
        for key, tab in getattr(self, "nav_tab_elements", {}).items():
            tab.set_visibility(settings[key])
        if getattr(self, "tabs", None) is not None:
            active = str(self.tabs.value or "")
            if active in settings and not settings[active]:
                self.tabs.value = "daily"

    def _section_header(self, title: str, help_text: str, icon: str) -> None:
        w.section_header(title, help_text, icon)

    def _bind_dialog_enter(self, dialog: Any, on_enter: Callable[[], None]) -> None:
        w.bind_dialog_enter(dialog, on_enter)

    def _open_info_dialog(self, title: str, lines: Sequence[str]) -> None:
        w.open_info_dialog(title, lines)

    def _open_item_picker_dialog(
        self,
        *,
        title: str,
        options: Sequence[tuple[str, str]],
        selected: Sequence[str],
        missing_by_code: dict[str, int] | None = None,
        on_confirm: Callable[[list[str]], None],
    ) -> None:
        w.open_picker_dialog(
            title=title,
            options=options,
            selected=selected,
            label_for=option_label,
            on_confirm=on_confirm,
            missing_by_code=missing_by_code,
        )

    def _build_db_panel(self) -> None:
        w.section_header(
            "Databáze",
            "Po úspěšném testu se zpřístupní kategorie, PDF a hromadné zprávy.",
            "storage",
        )
        db = database_parameters(self.raw)
        with w.card():
            with w.form_grid(3):
                self.host_input = w.setting_input(
                    "IP / server", db["host"], "Adresa serveru s databází Jídelny."
                )
                self.port_input = w.setting_number(
                    "Port", int(db["port"]), 1, 65535, 1, "Obvykle 5432."
                )
                self.dbname_input = w.setting_input(
                    "Název databáze", db["dbname"], "Například jidelna nebo vyvoj."
                )
                self.user_input = w.setting_input(
                    "Uživatel", db["user"], "Účet s právem čtení."
                )
                self.password_input = w.setting_input(
                    "Heslo k databázi",
                    self._stored_password(),
                    "Ukládá se do Windows Credential Manageru, ne do config.json.",
                    password=True,
                )
            with w.toolbar():
                self.test_button = (
                    ui.button(
                        "TEST připojení", icon="cable", on_click=self._test_admin_connection
                    )
                    .props("no-caps unelevated")
                    .classes("shrink-0")
                )
                self.db_status = ui.label("Připojení zatím nebylo ověřeno.").classes(
                    "inline-status"
                )
                ui.space()
                w.hint(
                    "Heslo se neukládá do config.json. Ve Windows je v Credential Manageru."
                )

        for element in (
            self.host_input,
            self.port_input,
            self.dbname_input,
            self.user_input,
            self.password_input,
        ):
            element.on("change", self.invalidate_connection)

    def _build_category_panel(self) -> None:
        """Uživatel vybírá podmnožinu kategorií povolených správcem."""
        with ui.row().classes("items-center gap-2 flex-wrap"):
            w.field_label("Kategorie")
            self.daily_category_button = ui.button(
                self._daily_category_caption(),
                icon="checklist",
                on_click=self.open_daily_category_dialog,
            ).props("outline no-caps").classes("ds-secondary-action")

    def _build_category_settings_panel(self) -> None:
        """Filtrovat kategorie smí pouze správce. Defaultně jsou všechny."""
        w.section_header(
            "Povolené kategorie",
            "Správce určuje, které kategorie smí běžný uživatel vybrat. "
            "Výchozí jsou všechny z databáze. Stejný seznam platí pro automatický export.",
            "checklist",
        )
        with w.card():
            self.category_mode = ui.radio(
                {
                    "all": "Všechny kategorie (doporučeno)",
                    "selected": "Jen vybrané kategorie",
                },
                value="all" if self.all_categories else "selected",
            ).props("inline dense")
            with ui.column().classes("w-full gap-1") as self.category_settings_custom:
                with w.toolbar():
                    self.admin_category_count = ui.label(
                        self._daily_category_caption()
                    ).classes("count-badge")
                    ui.button(
                        "Změnit výběr", icon="checklist",
                        on_click=self.open_allowed_category_dialog,
                    ).props("outline dense no-caps")
                self.daily_category_list = ui.row().classes("chip-row w-full")
            self.category_mode.on(
                "update:model-value", lambda: self._refresh_category_settings_panel()
            )
            self._refresh_category_settings_panel()
            with w.toolbar():
                ui.button(
                    "Uložit nastavení kategorií", icon="save",
                    on_click=self.save_category_settings,
                ).props("no-caps unelevated")
                self.category_settings_status = ui.label("").classes("inline-status")

    def _refresh_category_settings_panel(self) -> None:
        if hasattr(self, "category_settings_custom"):
            selected = str(self.category_mode.value) == "selected"
            self.category_settings_custom.set_visibility(selected)
        self._render_daily_selection()

    def save_category_settings(self) -> None:
        if not self._require_admin(silent=True):
            ui.notify("Nejprve odemkněte Administraci.", type="warning")
            return
        all_categories = str(self.category_mode.value) == "all"
        if not all_categories and not self.categories:
            self.category_settings_status.set_text(
                "Nejprve proveďte TEST připojení k databázi."
            )
            return
        chosen = (
            [code for code, _ in self.categories] if all_categories and self.categories
            else self._allowed_category_order()
        )
        if not all_categories and not chosen:
            self.category_settings_status.set_text(
                "Vyberte alespoň jednu kategorii; případně použijte Všechny."
            )
            return
        raw = sanitize_config(self.raw)
        block = raw.get("poctyemailem")
        block = dict(block) if isinstance(block, dict) else {}
        block["vsechny_kategorie"] = all_categories
        block["povolene_kategorie"] = chosen
        raw["poctyemailem"] = block
        raw["povolene_kategorie"] = chosen
        try:
            write_config(self.config_path, raw)
        except OSError as exc:
            self.category_settings_status.set_text(f"Uložení selhalo: {exc}")
            return
        self.raw = raw
        self.all_categories = all_categories
        self.allowed_categories = set(chosen)
        self.selected_categories = (self.selected_categories & self.allowed_categories
                                    if getattr(self, "daily_profile_id", None) else set(chosen))
        self._render_daily_selection()
        self.category_settings_status.set_text(
            "Uloženo: všechny kategorie." if all_categories
            else f"Uloženo: {len(chosen)} vybraných kategorií."
        )

    _build_daily_panel = DailyDesignMixin._build_daily_workspace

    def _build_daily_overview(self) -> None:
        """Přehledové dlaždice; zobrazí je jen šablona s přehledem (CSS)."""
        with ui.row().classes("overview-row w-full gap-2 no-wrap overflow-x-auto"):
            self.tile_connection = w.stat_card("Databáze", self.connection_caption)
            self.tile_period = w.stat_card("Období", "—")
            self.tile_pdf = w.stat_card("Poslední PDF", "zatím žádné")
            self.tile_mail = w.stat_card("Poslední odeslání", "zatím žádné")

    def _current_period_text(self) -> str:
        marker = "Aktuální měsíc:"
        details = str(self.connection_details or "")
        if marker in details:
            return details.split(marker, 1)[1].strip()
        return "po TESTu připojení"

    def _refresh_overview_tiles(self) -> None:
        if hasattr(self, "tile_connection"):
            self.tile_connection.set_text(self.connection_caption)
        if hasattr(self, "tile_period"):
            self.tile_period.set_text(self._current_period_text())
        if hasattr(self, "tile_pdf"):
            self.tile_pdf.set_text(
                self.last_pdf.name if self.last_pdf else "zatím žádné"
            )
        if hasattr(self, "tile_mail"):
            self.tile_mail.set_text(self.last_mail_note)

    def _build_date_field(self) -> None:
        # A new GUI session starts today; config.json may contain an old report date.
        selected = initial_report_date()
        with ui.input(
            "Datum přehledu", value=selected.strftime(CZECH_DATE_FORMAT)
        ).props(
            'dense mask="##.##.####" placeholder="DD.MM.RRRR" inputmode="numeric"'
        ).classes(
            "w-36 shrink-0"
        ) as self.date_input:
            with ui.menu().props("no-parent-event") as self.date_menu:
                self.date_picker = ui.date(
                    value=selected.isoformat(),
                    on_change=self._calendar_date_changed,
                ).props("first-day-of-week=1")
                # QDate needs its own Quasar locale object, not just ui.run(language=...).
                self.date_picker.props[":locale"] = json.dumps(
                    CZECH_DATE_LOCALE, ensure_ascii=False,
                )
            with self.date_input.add_slot("append"):
                ui.button(icon="event", on_click=self.date_menu.open).props(
                    'flat round aria-label="Vybrat datum přehledu"'
                )
        self.date_input.on("change", self._on_date_changed)

    async def _on_date_changed(self) -> None:
        self.update_mail_subject()
        self._queue_daily_summary()
        await self._reload_meal_types()

    async def _reload_meal_types(self) -> None:
        """Po TESTu nabídne typy stravy objednané na zvolený den."""
        if not self.connection_ok or not self._connection_password:
            return
        try:
            day = self._selected_date()
            database = self._collect_database()
            meal_types = await run.io_bound(
                available_meal_types,
                dict(database, password=self._connection_password),
                day,
            )
        except Exception as exc:
            ui.notify(f"Typy stravy nebylo možné načíst: {exc}", type="warning")
            return
        normalized: dict[str, str] = {}
        for name in meal_types:
            label = str(name).strip()
            if label:
                normalized.setdefault(label.casefold(), label)
        # A newer date may have been selected while the DB query was running.
        if day != self._selected_date():
            return
        options = dict(normalized)
        selected = list(meal_filter_values(self._selected_daily_meal_type()))
        for meal in selected:
            if meal not in normalized:
                options[meal] = f"{meal} (bez objednávek v tomto dni)"
        self.meal_type_select.options = options
        self.meal_type_select.value = selected
        self.meal_type_select.set_visibility(True)
        self.meal_type_select.update()
        self._queue_daily_summary()

    _build_closing_panel = ClosingDesignMixin._build_closing_workspace

    def _selected_closing_reports(self) -> list[str]:
        selected: list[str] = []
        if bool(self.closing_fksp.value):
            selected.append(SESTAVA_FKSP)
        if bool(self.closing_arch.value):
            selected.append(SESTAVA_ARCH)
        if bool(self.closing_recap.value):
            selected.append(SESTAVA_REKAPITULACE)
        return selected

    def _collect_closing_block(self) -> dict[str, Any]:
        current = self.raw.get("uzaverka")
        if not isinstance(current, dict):
            current = {}
        return apply_closing_ui(
            current,
            reports=self._selected_closing_reports(),
            output=str(self.closing_output.value or ""),
            pack_zip=bool(self.closing_zip.value),
            send_mail=bool(self.closing_mail.value),
        )

    def save_closing_settings(self) -> None:
        try:
            block = self._collect_closing_block()
        except ConfigError as exc:
            if hasattr(self, "closing_status"):
                self.closing_status.set_text(str(exc))
            return
        raw = sanitize_config(self.raw)
        raw["uzaverka"] = block
        write_config(self.config_path, raw)
        self.raw = raw
        if hasattr(self, "closing_status"):
            self.closing_status.set_text("Nastavení uzávěrky je uložené.")

    def _build_special_panel(self) -> None:
        z17 = peek_z17_ui(self.raw)
        with ui.column().classes("ui-block w-full"):
            w.section_header(
                "Speciál · Z 17-01",
                "Roční podklad k 31. 10. Kategorie jsou nezávislé na Denním stavu.",
                "assignment",
            )
            with w.card():
                with w.toolbar():
                    self.z17_year = w.setting_number(
                        "Rok výkazu",
                        int(z17["rok"]),
                        2000,
                        2100,
                        1,
                        "Školní rok, za který se podklad počítá.",
                    )
                    self.z17_year.classes(remove="w-full").classes("w-28 shrink-0")
                    self.z17_output = self._output_path_field(
                        "Složka pro uložení",
                        str(z17["vystup"]),
                        "Relativní cesta je vůči složce aplikace. {rok} se za "
                        "vybranou složku doplní.",
                        on_change=self.save_special_settings,
                        grow=True,
                        show_help=False,
                    )
                self.z17_year.on("change", lambda: self.save_special_settings())
                with w.toolbar():
                    w.field_label(
                        "Kategorie",
                        "Jídelna spustí DataShip.exe --z17_RRRR se stejným výběrem.",
                    )
                    self.z17_category_mode = ui.radio(
                        {"all": "Všechny", "selected": "Jen zvolené"},
                        value="all" if z17["vsechny_kategorie"] else "selected",
                    ).props("inline dense")
                    self.z17_category_mode.on(
                        "update:model-value",
                        lambda: self._on_z17_category_mode_changed(),
                    )
                    self.z17_expansion_label = ui.label(
                        self._z17_category_caption()
                    ).classes("count-badge")
                    with ui.row().classes(
                        "items-center gap-2 no-wrap"
                    ) as self.z17_add_row:
                        ui.button(
                            "Změnit výběr",
                            icon="checklist",
                            on_click=self.open_z17_category_dialog,
                        ).props("outline dense no-caps")
                self.z17_category_list = ui.row().classes("chip-row w-full")
            with w.action_bar():
                self.special_status = ui.label(
                    "Podklad Z 17-01 zatím nebyl vytvořen."
                ).classes("inline-status flex-grow truncate")
                self.z17_open_button = ui.button(
                    "Otevřít poslední PDF",
                    icon="open_in_new",
                    on_click=self.open_last_z17_pdf,
                ).props("outline no-caps")
                self.z17_open_button.disable()
                self.z17_generate_button = ui.button(
                    "Vytvořit podklad Z 17-01",
                    icon="picture_as_pdf",
                    on_click=self.generate_z17,
                ).props("no-caps unelevated")
                self.z17_generate_button.disable()
        self._render_z17_selection()
        self._sync_z17_category_picker()

    def _z17_uses_selected_categories(self) -> bool:
        return (
            hasattr(self, "z17_category_mode")
            and str(self.z17_category_mode.value) == "selected"
        )

    def _z17_category_caption(self) -> str:
        total = len(self.categories)
        selected = len(self.z17_selected_categories)
        if not self._z17_uses_selected_categories():
            if total:
                return f"všechny · {total}"
            return "všechny · po TESTu"
        if total:
            return f"{selected} / {total}"
        return f"{selected} · po TESTu"

    def _update_z17_expansion_caption(self) -> None:
        if hasattr(self, "z17_expansion_label"):
            self.z17_expansion_label.set_text(self._z17_category_caption())

    def _sync_z17_category_picker(self) -> None:
        selected_mode = self._z17_uses_selected_categories()
        if hasattr(self, "z17_add_row"):
            self.z17_add_row.set_visibility(selected_mode)
        if hasattr(self, "z17_category_list"):
            self.z17_category_list.set_visibility(selected_mode)
        self._render_z17_selection()
        self._update_z17_expansion_caption()

    def _on_z17_category_mode_changed(self) -> None:
        self._sync_z17_category_picker()
        self.save_special_settings()

    def _selected_z17_category_order(self) -> list[str]:
        if self.categories:
            return [
                code
                for code, _name in self.categories
                if code in self.z17_selected_categories
            ]
        return [
            code
            for code in peek_z17_ui(self.raw)["povolene_kategorie"]
            if str(code).strip()
        ]

    def _collect_z17_block(self) -> dict[str, Any]:
        current = self.raw.get("z17")
        if not isinstance(current, dict):
            current = {}
        year = date.today().year
        if hasattr(self, "z17_year"):
            try:
                year = parse_z17_year(self.z17_year.value)
            except ConfigError:
                year = date.today().year
        use_all = not self._z17_uses_selected_categories()
        return apply_z17_ui(
            current,
            output=str(self.z17_output.value or ""),
            use_all_categories=use_all,
            categories=self._selected_z17_category_order(),
            year=year,
        )

    def save_special_settings(self) -> None:
        try:
            block = self._collect_z17_block()
        except ConfigError as exc:
            if hasattr(self, "special_status"):
                self.special_status.set_text(str(exc))
            return
        raw = sanitize_config(self.raw)
        raw["z17"] = block
        write_config(self.config_path, raw)
        self.raw = raw
        if hasattr(self, "special_status"):
            self.special_status.set_text("Nastavení Z 17-01 je uložené.")

    def _build_bulk_panel(self) -> None:
        bulk = peek_bulk_ui(self.raw)
        with ui.column().classes("ui-block w-full"):
            w.section_header(
                "Hromadná zpráva",
                "Odejde strávníkům ve zvolené třídě nebo kategorii, kteří mají e-mail.",
                "campaign",
            )
            with w.card():
                with w.toolbar():
                    w.field_label("Filtr", "Podle čeho se vyberou strávníci.")
                    self.bulk_filter_type = ui.radio(
                        FILTER_LABELS, value=FILTER_CLASS
                    ).props("inline dense")
                    self.bulk_expansion_label = ui.label(
                        self._bulk_selection_caption()
                    ).classes("count-badge")
                    ui.button(
                        "Změnit výběr",
                        icon="checklist",
                        on_click=self.open_bulk_picker,
                    ).props("outline dense no-caps")
                    self.bulk_count_label = ui.label(
                        "Nejprve otestujte připojení k databázi, potom zvolte filtr."
                    ).classes("inline-status truncate")
                self.bulk_selection_list = ui.row().classes("chip-row w-full")
                self.bulk_subject = w.setting_input(
                    "Předmět", bulk["predmet"], "Předmět odchozí zprávy."
                )
                self.bulk_body = (
                    ui.textarea("Text zprávy", value=bulk["text"])
                    .props("dense rows=5")
                    .classes("w-full")
                )
            with w.action_bar():
                self.bulk_status = ui.label("Zpráva zatím nebyla odeslána.").classes(
                    "inline-status flex-grow truncate"
                )
                self.bulk_send_button = ui.button(
                    "Odeslat hromadnou zprávu",
                    icon="send",
                    on_click=self.send_bulk_mail,
                ).props("no-caps unelevated")
                self.bulk_send_button.disable()
        self.bulk_filter_type.on(
            "update:model-value", lambda: self._on_bulk_filter_type_changed()
        )
        self._render_bulk_selection()

    def _bulk_options(self) -> list[tuple[str, str]]:
        if str(self.bulk_filter_type.value) == FILTER_CATEGORY:
            return list(self.categories)
        return list(self.bulk_classes)

    def _bulk_selection_caption(self) -> str:
        selected = len(self.bulk_selected)
        total = len(self._bulk_options())
        if total:
            return f"{selected} / {total}"
        return f"{selected} · po TESTu"

    def _sync_bulk_filter_options(self) -> None:
        self.bulk_selected = [
            code for code in self.bulk_selected if code in {item[0] for item in self._bulk_options()}
        ]
        self._render_bulk_selection()
        self._refresh_bulk_preview_from_cache()

    def _on_bulk_filter_type_changed(self) -> None:
        self.bulk_selected = []
        self.bulk_preview = None
        self._sync_bulk_filter_options()

    def _render_selection_chips(
        self,
        container: Any,
        *,
        options: Sequence[tuple[str, str]],
        selected: Sequence[str],
        missing_by_code: dict[str, int] | None = None,
        on_missing: Callable[[str], None] | None = None,
    ) -> None:
        if container is None or not hasattr(container, "clear"):
            return
        lookup = {code: extra for code, extra in options}
        container.clear()
        with container:
            if not selected:
                ui.label("Nic není zvolené – použijte Změnit výběr.").classes("ui-help")
                return
            for code in selected:
                label = option_label(code, lookup.get(code, ""))
                missing = missing_by_code.get(code, 0) if missing_by_code is not None else 0
                warn = missing_by_code is not None and missing > 0
                text = f"{label} !!" if warn else label
                chip = ui.element("div").classes(
                    "selection-chip selection-chip-warn" if warn else "selection-chip"
                )
                with chip:
                    ui.label(text)
                if warn and on_missing is not None:
                    chip.on("click", lambda _e=None, item=code: on_missing(item))

    def _daily_category_caption(self) -> str:
        total = len(self._allowed_category_order())
        selected = len(self.selected_categories)
        if not self.categories:
            return "Vybrat kategorie"
        return f"Kategorie ({selected})"

    def _render_daily_selection(self) -> None:
        self._render_daily_preview_categories()
        if hasattr(self, "daily_expansion_label"):
            self.daily_expansion_label.set_text(self._daily_category_caption())
        if hasattr(self, "daily_category_button"):
            self.daily_category_button.set_text(self._daily_category_caption())
        if hasattr(self, "admin_category_count"):
            self.admin_category_count.set_text(
                f"{len(self.allowed_categories)} / {len(self.categories)}"
            )
        ordered = [
            code for code, _name in self.categories if code in self.selected_categories
        ]
        if not ordered and self.selected_categories:
            ordered = [code for code in self.selected_categories if str(code).strip()]
        self._render_selection_chips(
            getattr(self, "daily_category_list", None),
            options=self.categories,
            selected=self._allowed_category_order(),
        )
        self._queue_daily_summary()

    def _render_z17_selection(self) -> None:
        self._update_z17_expansion_caption()
        if not self._z17_uses_selected_categories():
            container = getattr(self, "z17_category_list", None)
            if container is not None:
                container.clear()
                with container:
                    ui.label("Použijí se všechny kategorie z databáze.").classes("ui-help")
            return
        ordered = self._selected_z17_category_order()
        self._render_selection_chips(
            getattr(self, "z17_category_list", None),
            options=self.categories,
            selected=ordered,
        )

    def _render_bulk_selection(self) -> None:
        if hasattr(self, "bulk_expansion_label"):
            self.bulk_expansion_label.set_text(self._bulk_selection_caption())
        filter_type = str(getattr(self, "bulk_filter_type", None) and self.bulk_filter_type.value or FILTER_CLASS)
        missing = missing_email_counts(self.bulk_diners, filter_type)
        self._render_selection_chips(
            getattr(self, "bulk_selection_list", None),
            options=self._bulk_options(),
            selected=self.bulk_selected,
            missing_by_code=missing,
            on_missing=self.open_bulk_missing_names,
        )

    def open_daily_category_dialog(self) -> None:
        """Kterýkoli uživatel smí zvolit jen povolené kategorie."""
        options = [
            (code, name) for code, name in self.categories
            if code in self.allowed_categories
        ]
        if not options:
            ui.notify("Nejprve proveďte TEST připojení nebo nastavte povolené kategorie.", type="warning")
            return
        self._open_item_picker_dialog(
            title="Kategorie přehledu",
            options=options,
            selected=[code for code, _ in options if code in self.selected_categories],
            on_confirm=self._apply_daily_categories,
        )

    def _apply_daily_categories(self, codes: list[str]) -> None:
        self.selected_categories = set(codes) & self.allowed_categories
        self._render_daily_selection()
        self._mark_daily_dirty()

    def open_allowed_category_dialog(self) -> None:
        """Globální omezení kategorií vyžaduje odemčeného správce."""
        if not self.admin_unlocked:
            ui.notify("Nejprve odemkněte Administraci.", type="warning")
            return
        if not self.categories:
            ui.notify("Nejprve proveďte TEST připojení.", type="warning")
            return
        self._open_item_picker_dialog(
            title="Povolené kategorie pro uživatele",
            options=self.categories,
            selected=[code for code, _ in self.categories if code in self.allowed_categories],
            on_confirm=self._apply_allowed_categories,
        )

    def _apply_allowed_categories(self, codes: list[str]) -> None:
        if not self._require_admin():
            return
        known = {code for code, _ in self.categories}
        self.allowed_categories = set(codes) & known
        self._render_daily_selection()

    def open_z17_category_dialog(self) -> None:
        if not self._z17_uses_selected_categories():
            return
        if not self.categories:
            ui.notify("Nejprve proveďte úspěšný TEST připojení.", type="warning")
            return
        self._open_item_picker_dialog(
            title="Zvolit kategorie",
            options=self.categories,
            selected=self._selected_z17_category_order(),
            on_confirm=self._apply_z17_categories,
        )

    def _apply_z17_categories(self, codes: list[str]) -> None:
        self.z17_selected_categories = set(codes)
        self._render_z17_selection()
        self.save_special_settings()

    def open_bulk_picker(self) -> None:
        if not self.connection_ok:
            ui.notify("Nejprve proveďte úspěšný TEST připojení.", type="warning")
            return
        options = self._bulk_options()
        if not options:
            kind = FILTER_LABELS.get(str(self.bulk_filter_type.value), "filtr")
            ui.notify(f"V databázi není žádná {kind.casefold()}.", type="warning")
            return
        filter_type = str(self.bulk_filter_type.value or FILTER_CLASS)
        self._open_item_picker_dialog(
            title=f"Zvolit {FILTER_LABELS[filter_type].casefold()}",
            options=options,
            selected=self.bulk_selected,
            missing_by_code=missing_email_counts(self.bulk_diners, filter_type),
            on_confirm=self._apply_bulk_selection,
        )

    def _apply_bulk_selection(self, codes: list[str]) -> None:
        self.bulk_selected = list(codes)
        self._render_bulk_selection()
        self._refresh_bulk_preview_from_cache()

    def open_bulk_missing_names(self, code: str) -> None:
        filter_type = str(self.bulk_filter_type.value or FILTER_CLASS)
        missing = missing_email_diners(
            self.bulk_diners, filter_type=filter_type, filter_value=code
        )
        lookup = {item: extra for item, extra in self._bulk_options()}
        title = f"Bez e-mailu · {option_label(code, lookup.get(code, ''))}"
        self._open_info_dialog(title, [diner.name for diner in missing])

    def _refresh_bulk_preview_from_cache(self) -> None:
        if not hasattr(self, "bulk_count_label"):
            return
        if not self.connection_ok:
            self.bulk_preview = None
            self.bulk_count_label.set_text(
                "Nejprve otestujte připojení k databázi, potom zvolte filtr."
            )
            if hasattr(self, "bulk_send_button"):
                self.bulk_send_button.disable()
            return
        if not self.bulk_selected:
            self.bulk_preview = None
            kind = FILTER_LABELS.get(str(self.bulk_filter_type.value), "filtr")
            self.bulk_count_label.set_text(
                f"Zvolte {kind.casefold()}. Počet příjemců se dopočítá."
            )
            if hasattr(self, "bulk_send_button"):
                self.bulk_send_button.disable()
            return
        filter_type = str(self.bulk_filter_type.value or FILTER_CLASS)
        self.bulk_preview = preview_from_diners(
            self.bulk_diners,
            filter_type=filter_type,
            filter_values=self.bulk_selected,
        )
        self._render_bulk_preview()

    def _render_bulk_preview(self) -> None:
        preview = self.bulk_preview
        if preview is None:
            if hasattr(self, "bulk_send_button"):
                self.bulk_send_button.disable()
            return
        self.bulk_count_label.set_text(bulk_preview_summary(preview))
        if preview.recipient_count and self.connection_ok:
            self.bulk_send_button.enable()
        else:
            self.bulk_send_button.disable()

    async def send_bulk_mail(self) -> None:
        if not self.connection_ok:
            ui.notify("Nejprve proveďte úspěšný TEST připojení.", type="warning")
            return
        preview = self.bulk_preview
        if preview is None:
            ui.notify("Nejprve zvolte třídu nebo kategorii.", type="warning")
            return
        try:
            api_key = get_resend_api_key() or ""
            if not api_key:
                raise ConfigError("Zadejte Resend API klíč v Nastavení → Služba a odesílání.")
            sender = normalize_recipient(self._outgoing_sender())
            subject = str(self.bulk_subject.value or "").strip()
            body = str(self.bulk_body.value or "").strip()
            if not subject:
                raise ConfigError("Zadejte předmět hromadné zprávy.")
            if not body:
                raise ConfigError("Zadejte text hromadné zprávy.")
            if not preview.recipients:
                raise ConfigError(
                    "Ve zvoleném filtru nemá žádný strávník vyplněný e-mail."
                )
        except (ConfigError, CredentialStoreError, EnvStoreError) as exc:
            ui.notify(str(exc), type="negative", position="top")
            return

        missing_note = ""
        extra = ""
        if preview.missing_count:
            missing_note = (
                f" {preview.missing_count} strávníkům zpráva nedorazí (chybí e-mail)."
            )
            extra = (
                f"{preview.missing_count} strávníkům zpráva nedorazí, "
                "protože nemají vyplněný e-mail."
            )
        if not await self._confirm_send(
            preview.recipient_count,
            subject,
            title=f"Hromadná zpráva bude odeslána {preview.recipient_count} příjemcům.",
            extra=extra,
            confirm_label="Odeslat",
        ):
            return
        self.bulk_status.set_text(
            f"Odesílám {preview.recipient_count} příjemcům…{missing_note}"
        )
        self.bulk_send_button.disable()
        try:
            if api_key:
                await run.io_bound(set_resend_api_key, api_key)
            raw = apply_bulk_ui(
                sanitize_config(self.raw),
                subject=subject,
                body=body,
            )
            await run.io_bound(write_config, self.config_path, raw)
            self.raw = raw
            result = await run.io_bound(
                lambda: send_bulk_message(
                    preview,
                    subject=subject,
                    body=body,
                    api_key=api_key,
                    sender_email=sender,
                )
            )
        except Exception as exc:
            self.bulk_status.set_text(f"Odeslání selhalo: {exc}")
            ui.notify(str(exc), type="negative", position="top", timeout=8000)
            if preview.recipient_count:
                self.bulk_send_button.enable()
            return
        detail = f" ({result.detail})" if result.detail else ""
        self.bulk_status.set_text(
            f"Odesláno {len(result.recipients)} příjemcům{detail}.{missing_note}"
        )
        ui.notify("Hromadná zpráva byla odeslána.", type="positive", position="top")
        self.bulk_send_button.enable()

    def _build_pdf_settings_section(self) -> None:
        with w.toolbar():
            self.category_separation = w.setting_switch(
                "Oddělit dle kategorií",
                bool(self.raw.get("kategor_separ", True)),
                "Každá kategorie dostane vlastní nadpis a seznam.",
            )
            self.show_categories = w.setting_switch(
                "Souhrn dle kategorií",
                bool(self.raw.get("dle_kategorii", True)),
                "Zobrazí tabulku počtu přihlášek podle kategorií.",
            )
            self.show_norms = w.setting_switch(
                "Souhrn dle norem",
                bool(self.raw.get("dle_norem", True)),
                "Zobrazí rozpad Menu 1–9 podle norem A–D.",
            )
            self.show_diner_list = w.setting_switch(
                "Seznam strávníků",
                bool(self.raw.get("seznam_stravniku", True)),
                "Zapnuto: PDF obsahuje seznam jmen. Vypnuto: pouze souhrny a počty.",
            )
            self.pdf_bold = w.setting_switch(
                "Tučná data",
                bool(self.raw.get("pdf_tucne", False)),
                "Vytiskne tučně obsah tabulek; nadpisy jsou tučné vždy.",
            )
        with w.form_grid(4):
            self.language_input = w.setting_input(
                "Jazyk jídelníčku",
                str(self.raw.get("jazyk_jidelnicku", "česky")),
                "Hodnota sloupce jazyk v tabulce jidelnicek.",
            )
            self.menu_number = w.setting_number(
                "Číslo jídelníčku",
                int(self.raw.get("cislo_jidelnicku", 1)),
                1,
                99,
                1,
                "Určuje, ze kterého jídelníčku se načtou názvy menu.",
            )
            self.pdf_orientation = w.setting_select(
                "Orientace PDF",
                {"na_vysku": "Na výšku", "na_sirku": "Na šířku"},
                str(self.raw.get("pdf_orientace", "na_vysku")),
                "Na šířku poskytne více místa dlouhým názvům jídel.",
            )
            self.pdf_data_size = w.setting_number(
                "Velikost dat",
                float(self.raw.get("pdf_velikost_dat", 8.5)),
                5,
                18,
                0.5,
                "Velikost hodnot v tabulkách, v bodech.",
            )
            self.pdf_label_size = w.setting_number(
                "Velikost popisků",
                float(self.raw.get("pdf_velikost_popisku", 9.0)),
                5,
                18,
                0.5,
                "Velikost záhlaví, nadpisů a popisků, v bodech.",
            )
        self.pdf_output = self._output_path_field(
            "Výstupní PDF",
            str(self.raw.get("pdf_vystup", DEFAULT_PDF_OUTPUT)),
            "Procházet vybere složku. Název souboru zůstane. "
            "Lze použít {datum} a {datum_cz}.",
            filename="DataShip_{datum}.pdf",
            on_change=self.save_pdf_output_path,
            grow=False,
        )

    ADMIN_SECTIONS = (
        ("logs", "Logy", "history"),
        ("db", "Databáze", "storage"),
        ("categories", "Kategorie denního stavu", "checklist"),
        ("mail_settings", "Služba a odesílání", "outgoing_mail"),
        ("navigation", "Hlavní nabídka", "view_list"),
        ("appearance", "Vzhled", "palette"),
        ("cli", "Bez GUI", "terminal"),
    )

    def _build_admin_panel(self) -> None:
        """Administrace se sidebarem; každá sekce se vejde bez dlouhého scrollování."""
        with ui.column().classes("ds-admin-layout w-full gap-3"):
            with ui.tabs().props("dense no-caps inline-label").classes(
                "ds-admin-nav w-full"
            ) as self.admin_sections:
                for name, label, icon in self.ADMIN_SECTIONS:
                    ui.tab(name, label=label, icon=icon)
            with ui.tab_panels(self.admin_sections, value="db").props(
                "animated=false"
            ).classes("flex-grow min-w-0"):
                with ui.tab_panel("db"):
                    self._build_db_panel()
                with ui.tab_panel("categories"):
                    self._build_category_settings_panel()
                with ui.tab_panel("mail_settings"):
                    from services.web_mail_settings_gui import build_web_settings_panel
                    build_web_settings_panel(
                        self.config_path.parent, require_admin=self._require_admin,
                        before_lock=self._admin_before_lock,
                    )
                with ui.tab_panel("navigation"):
                    self._build_navigation_settings_panel()
                with ui.tab_panel("appearance"):
                    self._build_appearance_panel()
                with ui.tab_panel("logs"):
                    from services.web_activity_gui import build_activity_panel
                    build_activity_panel(self.config_path.parent, self._require_admin, self._admin_before_lock)
                with ui.tab_panel("cli"):
                    self._build_cli_help_panel()

    def _build_navigation_settings_panel(self) -> None:
        """Choose which sections ordinary users see in the top navigation."""
        w.section_header(
            "Hlavní nabídka",
            "Zvolte záložky viditelné pro běžného uživatele. "
            "Přehledy, Odesílání a přístup k Nastavení jsou vždy dostupné.",
            "view_list",
        )
        saved = visible_tabs(self.raw)
        with w.card():
            ui.label("Přehledy a Odesílání – vždy zobrazeny").classes("ui-help")
            self.navigation_switches = {
                key: ui.checkbox(label, value=saved[key]).props("dense")
                for key, label in EDITABLE_TABS.items()
            }
            ui.label(
                "Skrytí záložky mění nabídku, nikoli oprávnění k datům. "
                "Plánování a e-maily najdete v Odesílání bez přihlášení. Správa služby zůstává v Nastavení."
            ).classes("ui-help")
            ui.button(
                "Uložit hlavní nabídku", icon="save",
                on_click=self.save_navigation_settings,
            ).props("no-caps unelevated")
            self.navigation_status = ui.label("").classes("inline-status")

    def save_navigation_settings(self) -> None:
        if not self._require_admin():
            return
        raw = sanitize_config(self.raw)
        raw["ui_visible_tabs"] = {
            "daily": True,
            **{key: bool(field.value)
               for key, field in self.navigation_switches.items()},
        }
        try:
            write_config(self.config_path, raw)
        except OSError as exc:
            self.navigation_status.set_text(f"Uložení nabídky selhalo: {exc}")
            return
        self.raw = raw
        self._apply_navigation_visibility()
        self.navigation_status.set_text("Hlavní nabídka uložena a aktualizována.")

    def _build_cli_help_panel(self) -> None:
        w.section_header(
            "Spuštění bez GUI",
            "Jak volat DataShip z Jídelny, BAT souboru nebo Plánovače úloh.",
            "terminal",
        )
        with w.card():
            ui.label(CLI_HELP_INTRO).classes("ui-help")
            for item in CLI_COMMANDS:
                with ui.expansion(str(item["title"])).props("dense").classes(
                    "w-full app-note"
                ):
                    ui.code(item["command"]).classes("w-full")
                    ui.label(item["detail"]).classes("ui-help")

    LAYOUT_PREVIEWS = {
        "compact": (
            '<div class="template-preview"><div class="pv-col">'
            '<i class="pv-bar"></i><i class="pv-fill"></i></div></div>'
        ),
        "dashboard": (
            '<div class="template-preview"><i class="pv-side"></i>'
            '<div class="pv-col"><i class="pv-bar"></i>'
            '<i class="pv-fill"></i></div></div>'
        ),
        "minimal": (
            '<div class="template-preview"><div class="pv-col">'
            '<i class="pv-bar"></i><i class="pv-bar"></i>'
            '<i class="pv-bar"></i><i class="pv-bar"></i></div></div>'
        ),
    }

    def _build_appearance_panel(self) -> None:
        appearance = peek_ui_appearance(self.raw)
        w.section_header(
            "Vzhled aplikace",
            "Šablona řídí rozvržení i hustotu. PDF sestavy zůstávají bez změny.",
            "palette",
        )
        with w.card():
            w.field_label(
                "Šablona UI",
                "Mění navigaci, hustotu prvků a rámování. Uloží se do config.json.",
            )
            self.ui_layout = ui.select(
                UI_LAYOUT_LABELS,
                label="Šablona",
                value=appearance["layout"],
            ).props("dense options-dense").classes("w-full max-w-[320px]")
            self.layout_cards: dict[str, Any] = {}
            with w.form_grid(3):
                for name, label in UI_LAYOUT_LABELS.items():
                    tokens = UI_LAYOUTS[name]
                    card = ui.element("div").classes("template-card")
                    card.on("click", lambda _e=None, item=name: self._pick_layout(item))
                    self.layout_cards[name] = card
                    with card:
                        ui.html(self.LAYOUT_PREVIEWS[name])
                        ui.label(label).classes("app-label")
                        ui.label(str(tokens["popis"])).classes("ui-help")
                        ui.tooltip(str(tokens["vhodne"]))
            self.ui_layout.on("update:model-value", lambda: self.save_ui_appearance())

        with w.card():
            w.field_label("Barvy a přiblížení", "Platí okamžitě v celém okně.")
            with w.form_grid(2):
                self.ui_theme = w.setting_select(
                    "Barevné schéma",
                    UI_THEME_LABELS,
                    appearance["schema"],
                    "Tmavé zapne dark mode. Schéma nemění hustotu prvků.",
                )
                with ui.row().classes("items-center gap-2 no-wrap"):
                    ui.label("Přiblížení").classes("app-label shrink-0")
                    self.ui_zoom = (
                        ui.slider(
                            min=UI_ZOOM_MIN,
                            max=UI_ZOOM_MAX,
                            step=UI_ZOOM_STEP,
                            value=appearance["zoom"],
                        )
                        .props("label dense")
                        .classes("flex-grow")
                    )
                    self.ui_zoom_value = ui.label(f"{appearance['zoom']} %").classes(
                        "app-label w-12 text-right shrink-0"
                    )
            ui.button("Upravit vlastní barvy", icon="palette", on_click=self._use_custom_colors).props("outline no-caps")
            self._build_custom_palette(appearance)

        with ui.expansion("Doladění hustoty a písma", icon="tune").props(
            "dense"
        ).classes("w-full app-note"):
            with w.form_grid(4):
                self.ui_template = w.setting_select(
                    "Hustota (předvolba)",
                    UI_STYLE_TEMPLATE_LABELS,
                    appearance["sablona"],
                    "Předvolí rozestupy, řádkování a hustotu polí.",
                )
                self.ui_spacing = w.setting_select(
                    "Rozestupy prvků",
                    UI_SPACING_LABELS,
                    appearance["rozestupy"],
                    "Mezery mezi sekcemi, poli a tlačítky.",
                )
                self.ui_line = w.setting_select(
                    "Řádkování textu",
                    UI_SPACING_LABELS,
                    appearance["radkovani"],
                    "Výška řádku u všech textů.",
                )
                self.ui_density = w.setting_select(
                    "Hustota polí",
                    UI_DENSITY_LABELS,
                    appearance["hustota"],
                    "Výška vstupních polí a selectů.",
                )
            with w.form_grid(3):
                with ui.column().classes("w-full gap-0"):
                    self.ui_heading_size = w.setting_select(
                        "Nadpisy", UI_TEXT_SIZE_LABELS, appearance["nadpis"],
                        "Velikost nadpisů sekcí.",
                    )
                    self.ui_heading_bold = w.setting_switch(
                        "Tučné nadpisy", appearance["tucne_nadpisy"],
                    )
                with ui.column().classes("w-full gap-0"):
                    self.ui_text_size = w.setting_select(
                        "Běžný text", UI_TEXT_SIZE_LABELS, appearance["text"],
                        "Velikost hodnot, tlačítek a seznamů.",
                    )
                    self.ui_text_bold = w.setting_switch(
                        "Tučný běžný text", appearance["tucny_text"],
                    )
                with ui.column().classes("w-full gap-0"):
                    self.ui_help_size = w.setting_select(
                        "Popisy", UI_TEXT_SIZE_LABELS, appearance["popis"],
                        "Velikost popisků polí, nápověd a stavových hlášek.",
                    )
                    self.ui_help_bold = w.setting_switch(
                        "Tučné popisy a nápověda", appearance["tucne_popisy"],
                    )
            self.ui_blocks = w.setting_switch(
                "Zvýraznit rámování",
                bool(appearance["zvyrazneni"]),
                "Orámuje sekce výrazněji a podbarví nadpisy.",
            )
            with ui.column().classes("w-full app-note p-2 gap-0"):
                ui.label("Nadpis sekce").classes("app-heading")
                ui.label("Běžný text, tlačítka a hodnoty ve formulářích.").classes(
                    "app-text"
                )
                ui.label("Popis, nápověda a stavové hlášky.").classes("ui-help")

        self.ui_text_status = ui.label("").classes("inline-status")
        self.ui_template.on("update:model-value", lambda: self._apply_style_template())
        for element in (
            self.ui_theme,
            self.ui_heading_size,
            self.ui_help_size,
            self.ui_text_size,
            self.ui_heading_bold,
            self.ui_text_bold,
            self.ui_help_bold,
            self.ui_zoom,
            self.ui_spacing,
            self.ui_line,
            self.ui_density,
        ):
            element.on("update:model-value", lambda: self._save_admin_appearance())
        self.ui_blocks.on("update:model-value", lambda: self._save_admin_appearance())
        self._highlight_layout_card(appearance["layout"])

    def _build_custom_palette(self, appearance: dict[str, Any]) -> None:
        from services.web_custom_palette import CUSTOM_COLOR_LABELS, normalize_palette

        self.custom_palette = normalize_palette(appearance["vlastni_barvy"])
        self._updating_palette = False
        self.ui_palette_panel = ui.column().classes("ds-palette-editor w-full")
        self.ui_palette_panel.bind_visibility_from(self.ui_theme, "value", backward=lambda value: value == "vlastni")
        self.ui_custom_colors = {}
        with self.ui_palette_panel:
            ui.label("Vlastní barevné schéma").classes("app-heading")
            ui.label("Klikněte na barevné kolečko. Změny se projeví ihned a uloží automaticky.").classes("ui-help")
            with w.form_grid(3):
                for key, label in CUSTOM_COLOR_LABELS.items():
                    field = ui.color_input(label, value=self.custom_palette[key], preview=True,
                        on_change=lambda event, name=key: self._save_palette_color(name, event.value)).props("outlined dense").classes("w-full")
                    field.button.props(f'aria-label="Vybrat barvu: {label}"')
                    field.picker.classes("ds-palette-picker")
                    field.picker.q_color.props("format-model=hex")
                    field.picker.q_color.props["dark"] = False
                    self.ui_custom_colors[key] = field
            self.custom_palette_preview = ui.column().classes("ds-palette-preview w-full")
            with self.custom_palette_preview:
                ui.label("Náhled barev").classes("app-label")
                with ui.column().classes("ds-palette-sample w-full"):
                    ui.label("Takto bude vypadat váš přehled.").classes("app-text")
                    ui.label("Doplňkový text a vysvětlení.").classes("ui-help")
                    ui.label("Ukázka tlačítka").classes("ds-palette-button")
            self.custom_palette_contrast = ui.label().classes("ui-help").props('role="status" aria-live="polite"')
            ui.button("Obnovit výchozí barvy", icon="restart_alt", on_click=self._reset_custom_colors).props("flat no-caps")
        self._refresh_custom_preview()

    def _use_custom_colors(self) -> None:
        if not self._require_admin():
            return
        self.ui_theme.value = "vlastni"
        self.save_ui_appearance()

    def _save_palette_color(self, key: str, value: object) -> None:
        if not self._require_admin():
            return
        from services.web_custom_palette import hex_color

        if self._updating_palette:
            return
        field = self.ui_custom_colors[key]
        color = hex_color(value)
        if color is None:
            field.props["error"] = True
            field.props["error-message"] = "Vyberte barvu kolečkem nebo zadejte kód #RRGGBB."
            field.update()
            return
        field.props(remove="error error-message")
        field.update()
        self.custom_palette[key] = color
        self._refresh_custom_preview()
        self.save_ui_appearance()

    def _refresh_custom_preview(self) -> None:
        from services.web_custom_palette import palette_tokens, contrast

        palette = self.custom_palette
        self.custom_palette_preview.style("; ".join(f"{key}: {value}" for key, value in palette_tokens(palette).items()))
        readable = min(contrast(palette[key], palette[background])
                       for key in ("text", "muted") for background in ("page", "surface")) >= 4.5
        readable = readable and min(contrast(palette["primary"], palette[background])
                                    for background in ("surface", "soft")) >= 3
        self.custom_palette_contrast.set_text(
            "Text má dobrý kontrast vůči pozadí." if readable else
            "Text a pozadí jsou si příliš podobné. Pro lepší čitelnost upravte jejich barvy."
        )

    def _reset_custom_colors(self) -> None:
        if not self._require_admin():
            return
        from services.web_custom_palette import DEFAULT_CUSTOM_PALETTE

        self._updating_palette = True
        try:
            self.custom_palette = dict(DEFAULT_CUSTOM_PALETTE)
            for key, field in self.ui_custom_colors.items():
                field.props(remove="error error-message")
                field.value = self.custom_palette[key]
        finally:
            self._updating_palette = False
        self._refresh_custom_preview()
        self.save_ui_appearance()

    def _pick_layout(self, name: str) -> None:
        """Výběr šablony z dlaždice; hustotu předvolí podle šablony."""
        if not self._require_admin():
            return
        if name not in UI_LAYOUTS:
            return
        self.ui_layout.value = name
        preset = UI_STYLE_TEMPLATES[str(UI_LAYOUTS[name]["sablona"])]
        if hasattr(self, "ui_template"):
            self.ui_template.value = str(UI_LAYOUTS[name]["sablona"])
            self.ui_spacing.value = preset["rozestupy"]
            self.ui_line.value = preset["radkovani"]
            self.ui_density.value = preset["hustota"]
        self.save_ui_appearance()

    def _highlight_layout_card(self, name: str) -> None:
        for key, card in getattr(self, "layout_cards", {}).items():
            if key == name:
                card.classes(add="template-card-active")
            else:
                card.classes(remove="template-card-active")

    def _apply_style_template(self) -> None:
        if not self._require_admin():
            return
        name = peek_ui_template(
            {"ui_sablona": getattr(self, "ui_template", None) and self.ui_template.value}
        )
        preset = UI_STYLE_TEMPLATES[name]
        if hasattr(self, "ui_spacing"):
            self.ui_spacing.value = preset["rozestupy"]
        if hasattr(self, "ui_line"):
            self.ui_line.value = preset["radkovani"]
        if hasattr(self, "ui_density"):
            self.ui_density.value = preset["hustota"]
        self.save_ui_appearance()

    def _appearance_from_widgets(self) -> dict[str, Any]:
        if not hasattr(self, "ui_theme"):
            return peek_ui_appearance(self.raw)
        zoom_widget = getattr(self, "ui_zoom", None)
        return peek_ui_appearance(
            {
                "ui_layout": getattr(self, "ui_layout", None)
                and self.ui_layout.value,
                "ui_velikost_textu": getattr(self, "ui_text_size", None)
                and self.ui_text_size.value,
                "ui_velikost_nadpisu": getattr(self, "ui_heading_size", None)
                and self.ui_heading_size.value,
                "ui_velikost_popisu": getattr(self, "ui_help_size", None)
                and self.ui_help_size.value,
                "ui_tucne_nadpisy": self.ui_heading_bold.value,
                "ui_tucny_text": self.ui_text_bold.value,
                "ui_tucne_popisy": self.ui_help_bold.value,
                "ui_barevne_schema": self.ui_theme.value,
                "ui_vlastni_barvy": getattr(self, "custom_palette", self.raw.get("ui_vlastni_barvy")),
                "ui_zvyrazneni_bloku": bool(self.ui_blocks.value),
                "ui_zoom": None if zoom_widget is None else zoom_widget.value,
                "ui_sablona": getattr(self, "ui_template", None)
                and self.ui_template.value,
                "ui_rozestupy": getattr(self, "ui_spacing", None)
                and self.ui_spacing.value,
                "ui_radkovani": getattr(self, "ui_line", None) and self.ui_line.value,
                "ui_hustota_poli": getattr(self, "ui_density", None)
                and self.ui_density.value,
            }
        )

    def _save_admin_appearance(self) -> None:
        if self._require_admin():
            self.save_ui_appearance()

    def save_ui_appearance(self) -> None:
        appearance = self._appearance_from_widgets()
        apply_ui_appearance(appearance, dark_mode=getattr(self, "_dark_mode", None))
        self.layout = layout_tokens(appearance)
        raw = sanitize_config(self.raw)
        raw.update(appearance_config(appearance))
        write_config(self.config_path, raw)
        self.raw = raw
        if hasattr(self, "ui_layout"):
            self.ui_layout.value = appearance["layout"]
            self._highlight_layout_card(appearance["layout"])
        if hasattr(self, "ui_theme"):
            self.ui_theme.value = appearance["schema"]
            self.ui_blocks.value = appearance["zvyrazneni"]
            self.ui_heading_size.value = appearance["nadpis"]
            self.ui_help_size.value = appearance["popis"]
            self.ui_text_size.value = appearance["text"]
        if hasattr(self, "ui_template"):
            self.ui_template.value = appearance["sablona"]
            self.ui_spacing.value = appearance["rozestupy"]
            self.ui_line.value = appearance["radkovani"]
            self.ui_density.value = appearance["hustota"]
        if hasattr(self, "ui_zoom"):
            self.ui_zoom.value = appearance["zoom"]
        if hasattr(self, "ui_zoom_value"):
            self.ui_zoom_value.set_text(f"{appearance['zoom']} %")
        if hasattr(self, "ui_text_status"):
            theme = UI_THEME_LABELS[appearance["schema"]]
            self.ui_text_status.set_text(f"Vzhled uložen. Barevné schéma: {theme}.")

    def _setting_switch(self, label: str, value: bool, help_text: str):
        return w.setting_switch(label, value, help_text)

    def _setting_input(self, label: str, value: str, help_text: str):
        return w.setting_input(label, value, help_text)

    def _output_path_field(
        self,
        label: str,
        value: str,
        help_text: str,
        *,
        filename: str | None = None,
        on_change=None,
        grow: bool = True,
        show_help: bool = False,
    ):
        del show_help  # nápověda je v tooltipu, ať neroste výška panelu
        element = w.path_field(
            label,
            value,
            help_text,
            grow=grow,
            on_browse=lambda field: self._browse_output_path(
                field, filename=filename, on_change=on_change
            ),
        )
        if on_change is not None:
            element.on("change", on_change)
        return element

    def _browse_output_path(
        self,
        input_element,
        *,
        filename: str | None = None,
        on_change=None,
    ) -> None:
        current = str(input_element.value or "")
        initial = existing_directory_for_dialog(
            current, config_directory=self.config_path.parent
        )
        picked = pick_local_directory(initial)
        if not picked:
            return
        input_element.value = join_picked_directory(
            current, picked, filename=filename
        )
        input_element.update()
        if on_change is not None:
            on_change()

    def save_pdf_output_path(self) -> None:
        output = str(self.pdf_output.value or "").strip() or DEFAULT_PDF_OUTPUT
        raw = sanitize_config(self.raw)
        raw["pdf_vystup"] = output
        write_config(self.config_path, raw)
        self.raw = raw

    def _setting_number(
        self,
        label: str,
        value: float,
        minimum: float,
        maximum: float,
        step: float,
        help_text: str,
    ):
        return w.setting_number(label, value, minimum, maximum, step, help_text)

    def _setting_select(
        self, label: str, options: dict[str, str], value: str, help_text: str
    ):
        return w.setting_select(label, options, value, help_text)

    def _build_pdf_panel(self) -> None:
        """Sticky lišta hlavních akcí denního stavu."""
        with w.action_bar():
            with ui.column().classes("gap-0 min-w-0 flex-grow"):
                self.pdf_status = ui.label("").classes(
                    "inline-status truncate"
                )
                with ui.row().classes("items-center gap-2 no-wrap min-w-0"):
                    self.mail_status = ui.label("").classes(
                        "inline-status shrink-0"
                    )
                    self.mail_subject_label = ui.label(
                        mail_subject(self._selected_date())
                    ).classes("inline-status truncate")
                    self.mail_subject_label.set_visibility(False)
                    ui.tooltip(
                        "Příjemce jednorázového e-mailu zadáte ve čtvrtém kroku průvodce."
                    )
            self.open_pdf_button = ui.button(
                "Otevřít poslední", icon="open_in_new", on_click=self.open_last_pdf
            ).props("flat no-caps")
            self.open_pdf_button.disable()
            self.generate_button = ui.button(
                "Vytvořit PDF",
                icon="picture_as_pdf",
                on_click=self.generate_pdf,
            ).props("no-caps unelevated")
            self.send_button = ui.button(
                "Odeslat jednou…", icon="send", on_click=self.send_mail
            ).props("outline no-caps")
            self.send_button.disable()
            self.daily_summary_detail_button = ui.button(
                "Detail porcí", icon="table_rows", on_click=lambda: self.daily_summary_dialog.open()
            ).props("outline no-caps")

    def set_status(self, message: str) -> None:
        text = str(message or "").strip()
        self.status_label.set_text(text)
        self.status_label.set_visibility(bool(text))
        self.status_label.update()

    def set_connection_display(
        self,
        *,
        connected: bool,
        name: str | None = None,
        details: str | None = None,
    ) -> None:
        """Aktualizuje tlačítko stavu databáze v hlavičce."""
        self.connection_ok = connected
        if connected:
            self.connection_caption = "Připojeno"
            self.connection_name = name or "Název provozovny není nastaven"
            self.connection_details = details or "Databáze je připojená."
            self.connection_strip.classes(add="connection-ready")
            self.connection_icon.props("name=check_circle color=positive")
        else:
            self.connection_caption = "Nepřipojeno"
            self.connection_name = "Jídelna zatím není připojena"
            self.connection_details = details or "Kliknutím otevřete TEST připojení"
            self.connection_strip.classes(remove="connection-ready")
            self.connection_icon.props("name=cloud_off color=negative")

        self.connection_caption_label.set_text(self.connection_caption)
        self.connection_name_label.set_text(self.connection_name)
        self.connection_details_label.set_text(self.connection_details)
        if hasattr(self, "connection_tooltip"):
            self.connection_tooltip.set_text("Připojení k Jídelně je v pořádku." if connected else "Připojení pomůže nastavit správce aplikace.")
            self.connection_tooltip.update()
        self._refresh_overview_tiles()

        # Explicitní update je pojistka pro NiceGUI 3.15 po návratu z run.io_bound.
        for element in (
            self.connection_strip,
            self.connection_icon,
            self.connection_caption_label,
            self.connection_name_label,
            self.connection_details_label,
        ):
            element.update()

    def invalidate_connection(self) -> None:
        if not self.connection_ok:
            return
        self.set_connection_display(
            connected=False,
            details="Údaje se změnily – spojení je potřeba ověřit znovu.",
        )
        self.send_button.disable()
        self._connection_password = None
        if hasattr(self, "meal_type_select"):
            self.meal_type_select.value = []
            self.meal_type_select.set_visibility(True)
        self._queue_daily_summary()
        if hasattr(self, "z17_generate_button"):
            self.z17_generate_button.disable()
        if hasattr(self, "bulk_send_button"):
            self.bulk_send_button.disable()
            self.bulk_preview = None
            self.bulk_diners = []
            self._sync_bulk_filter_options()
        self.db_status.set_text("Údaje se změnily – proveďte TEST znovu.")
        self.db_status.update()
        self.set_status("Připojení je nutné znovu ověřit.")

    def _collect_database(self) -> dict[str, Any]:
        host = str(self.host_input.value or "").strip()
        dbname = str(self.dbname_input.value or "").strip()
        user = str(self.user_input.value or "").strip()
        if not host or not dbname or not user:
            raise ConfigError("IP/server, název databáze a uživatel jsou povinné.")
        try:
            port = int(self.port_input.value)
        except (TypeError, ValueError) as exc:
            raise ConfigError("Port musí být celé číslo.") from exc
        if not 1 <= port <= 65535:
            raise ConfigError("Port musí být v rozsahu 1–65535.")
        return {
            "host": host,
            "port": port,
            "dbname": dbname,
            "user": user,
            "sslmode": "prefer",
            "connect_timeout": 10,
        }

    def _allowed_category_order(self) -> list[str]:
        if self.categories:
            return [code for code, _ in self.categories if code in self.allowed_categories]
        return peek_client_categories(self.raw) if not self.all_categories else []

    def _selected_category_order(self) -> list[str]:
        # Never include a category outside the administrator's allowed set.
        return [
            code for code, _ in self.categories
            if code in self.selected_categories and code in self.allowed_categories
        ]

    def _selected_date(self) -> date:
        return parse_czech_date(self.date_input.value)

    def _calendar_date_changed(self, event: Any) -> None:
        value = str(getattr(event, "value", "") or self.date_picker.value or "")
        try:
            selected = date.fromisoformat(value)
        except ValueError:
            return
        self.date_input.value = selected.strftime(CZECH_DATE_FORMAT)
        self.date_menu.close()
        self.update_mail_subject()
        self._queue_daily_summary()
        asyncio.create_task(self._reload_meal_types())

    def _collect_config(self) -> dict[str, Any]:
        allowed = self._allowed_category_order()
        if not self.all_categories and not allowed:
            raise ConfigError("Správce musí povolit alespoň jednu kategorii.")
        selected_date = self._selected_date()
        language = str(self.language_input.value or "").strip()
        output = str(self.pdf_output.value or "").strip()
        if not language or not output:
            raise ConfigError("Jazyk jídelníčku a výstupní cesta nesmí být prázdné.")
        try:
            menu_number = int(self.menu_number.value)
            data_size = float(self.pdf_data_size.value)
            label_size = float(self.pdf_label_size.value)
        except (TypeError, ValueError) as exc:
            raise ConfigError("Číselná nastavení exportu nejsou platná.") from exc
        if menu_number < 1:
            raise ConfigError("Číslo jídelníčku musí být kladné.")
        if not 5 <= data_size <= 18 or not 5 <= label_size <= 18:
            raise ConfigError("Velikosti písma musí být v rozsahu 5 až 18.")

        raw = sanitize_config(self.raw)
        pocty_block = raw.get("poctyemailem")
        if not isinstance(pocty_block, dict):
            pocty_block = {}
        pocty_block = dict(pocty_block)
        pocty_block["vsechny_kategorie"] = self.all_categories
        pocty_block["povolene_kategorie"] = allowed
        try:
            closing_block = self._collect_closing_block()
        except ConfigError:
            existing = self.raw.get("uzaverka")
            closing_block = dict(existing) if isinstance(existing, dict) else {}
        try:
            z17_block = self._collect_z17_block()
        except ConfigError:
            existing_z17 = self.raw.get("z17")
            z17_block = dict(existing_z17) if isinstance(existing_z17, dict) else {}
        raw["uzaverka"] = closing_block
        raw["z17"] = z17_block
        raw.update(appearance_config(self._appearance_from_widgets()))
        raw.update(
            {
                "databaze": self._collect_database(),
                "povolene_kategorie": allowed,
                "poctyemailem": pocty_block,
                "kategor_separ": bool(self.category_separation.value),
                "dle_kategorii": bool(self.show_categories.value),
                "dle_norem": bool(self.show_norms.value),
                "datum": selected_date.strftime("%d.%m.%Y"),
                "jazyk_jidelnicku": language,
                "cislo_jidelnicku": menu_number,
                "pdf_vystup": output,
                "pdf_orientace": str(self.pdf_orientation.value),
                "pdf_velikost_dat": data_size,
                "pdf_velikost_popisku": label_size,
                "pdf_tucne": bool(self.pdf_bold.value),
                "seznam_stravniku": bool(self.show_diner_list.value),
                # Typ stravy je volba pro jeden ruční export, ne pro worker.
                "typ_stravy_denne": None,
            }
        )
        return raw

    @staticmethod
    def _test_database(
        database: dict[str, Any], password: str
    ) -> tuple[list[tuple[str, str]], str, str | None, tuple[int, int] | None]:
        """Test připojení; sdílený se desktopovým rozhraním."""
        info = probe_connection(database, password)
        return (
            list(info.categories),
            info.database_name,
            info.subject_name,
            info.period,
        )

    async def _test_admin_connection(self) -> bool:
        if not self._require_admin():
            return False
        return await self.test_connection()

    async def test_connection(self) -> bool:
        try:
            database = self._collect_database()
            password = str(self.password_input.value or "")
            if not password:
                password = get_password(database) or ""
            if not password:
                raise ConfigError("Vyplňte heslo k databázi.")
        except (ConfigError, CredentialStoreError, EnvStoreError) as exc:
            self.db_status.set_text(str(exc))
            ui.notify(str(exc), type="negative", position="top")
            return False

        self.test_button.disable()
        self.db_status.set_text("Testuji připojení…")
        self.set_status("Probíhá test připojení k databázi.")
        try:
            categories, database_name, subject_name, jidelna_period = await run.io_bound(
                self._test_database, database, password
            )
        except Exception as exc:
            message = database_error_message(exc)
            self.set_connection_display(
                connected=False,
                details=message,
            )
            self.db_status.set_text(message)
            self.db_status.update()
            self.set_status("Připojení k databázi se nepodařilo.")
            ui.notify(message, type="negative", position="top", timeout=8000)
        else:
            self.raw["databaze"] = database
            write_config(self.config_path, self.raw)
            self._connection_password = password
            self.populate_categories(categories)
            try:
                classes, _unused, diners = await run.io_bound(
                    fetch_bulk_filters, dict(database, password=password)
                )
                self.bulk_classes = classes
                self.bulk_diners = diners
            except Exception:
                self.bulk_classes = []
                self.bulk_diners = []
            self.send_button.enable()
            if hasattr(self, "z17_generate_button"):
                self.z17_generate_button.enable()
            connection_name, connection_details = connection_identity(
                subject_name, database_name, database, jidelna_period
            )
            self.set_connection_display(
                connected=True,
                name=connection_name,
                details=connection_details,
            )
            await self._reload_meal_types()
            # Až po nastavení stavu, jinak by hlášky v Hromadné zprávě zůstaly
            # ve variantě „bez připojení“.
            self._sync_bulk_filter_options()
            self.db_status.set_text(
                f"Připojení je v pořádku: {connection_name} "
                f"· {database_name} ({len(categories)} kategorií)."
            )
            self.db_status.update()
            self.set_status("")
            ui.notify(
                f"Databáze je dostupná · {connection_name}",
                type="positive",
                position="top",
            )
        finally:
            self.test_button.enable()
        return self.connection_ok

    def populate_categories(self, categories: Sequence[tuple[str, str]]) -> None:
        self.categories = list(categories)
        configured_set = set(peek_client_categories(self.raw))
        self.allowed_categories = {
            code for code, _name in self.categories
            if self.all_categories or code in configured_set
        }
        # Preserve a saved profile while rechecking current DB/admin permissions.
        profile = next((p for p in getattr(self, "daily_profiles", [])
                        if p.id == getattr(self, "daily_profile_id", None)), None)
        self.selected_categories = (set(profile.categories) & self.allowed_categories
                                    if profile else set(self.allowed_categories))
        known = {code for code, _name in self.categories}
        saved_z17 = set(peek_z17_ui(self.raw)["povolene_kategorie"])
        if saved_z17:
            self.z17_selected_categories = {
                code for code in saved_z17 if code in known
            }
        else:
            self.z17_selected_categories = {
                code for code in self.z17_selected_categories if code in known
            }
        self.render_categories()
        if hasattr(self, "daily_profile_choices"):
            self._render_daily_profile_choices()
        self.render_z17_categories()
        self._update_z17_expansion_caption()

    def render_categories(self) -> None:
        self._render_daily_selection()

    def select_all(self) -> None:
        self.selected_categories = {code for code, _name in self.categories if code in self.allowed_categories}
        self._render_daily_selection()

    def clear_all(self) -> None:
        self.selected_categories.clear()
        self._render_daily_selection()

    def render_z17_categories(self) -> None:
        self._render_z17_selection()

    def select_all_z17(self) -> None:
        self.z17_selected_categories = {code for code, _name in self.categories}
        self._render_z17_selection()
        self.save_special_settings()

    def clear_all_z17(self) -> None:
        self.z17_selected_categories.clear()
        self._render_z17_selection()
        self.save_special_settings()

    def update_mail_subject(self) -> None:
        try:
            selected = self._selected_date()
            value = mail_subject(selected)
            self.date_picker.value = selected.isoformat()
        except ConfigError:
            value = "Seznam strávníků: [neplatné datum]"
        if hasattr(self, "mail_subject_label"):
            self.mail_subject_label.set_text(value)

    def _outgoing_mail_settings(self) -> dict:
        try:
            return load_settings(settings_path(self.config_path.parent))
        except (OSError, ValueError) as exc:
            raise ConfigError("Zkontrolujte odchozí e-mail v Nastavení → Služba a odesílání.") from exc

    def _outgoing_sender(self) -> str:
        settings = self._outgoing_mail_settings()
        return str(settings["from_email"] or self.raw.get("mail_odesilatel") or "")

    async def _persist_settings(self, *, require_api_key: bool = False) -> str:
        """Automaticky uloží kompletní stav před vytvořením PDF."""
        raw = self._collect_config()
        password = str(self.password_input.value or "")
        if password:
            await run.io_bound(set_password, raw["databaze"], password)

        api_key = ""
        if require_api_key:
            api_key = await run.io_bound(get_resend_api_key) or ""
        if require_api_key and not api_key:
            raise ConfigError("Zadejte Resend API klíč v Nastavení → Služba a odesílání.")

        await run.io_bound(write_config, self.config_path, raw)
        self.raw = raw
        return api_key

    def _selected_daily_meal_type(self) -> str | tuple[str, ...] | None:
        value = self.meal_type_select.value
        return normalize_meal_filter(None if value == "__all__" else value)

    def _manual_daily_categories(self) -> tuple[str, ...]:
        selected = tuple(self._selected_category_order())
        if not selected:
            raise ConfigError("Pro sestavu vyberte alespoň jednu povolenou kategorii.")
        return selected

    async def generate_pdf(self) -> None:
        if not self.connection_ok:
            ui.notify("Nejprve proveďte úspěšný TEST připojení.", type="warning")
            return
        try:
            categories = self._manual_daily_categories()
            allowed = tuple(self._allowed_category_order())
            await self._persist_settings()
        except (ConfigError, CredentialStoreError, EnvStoreError) as exc:
            ui.notify(str(exc), type="negative", position="top")
            return

        self.generate_button.disable()
        self.pdf_status.set_text("Načítám data a vytvářím PDF…")
        self.set_status("Probíhá tvorba PDF.")
        try:
            path = await run.io_bound(
                self._create_pdf, self._selected_daily_meal_type(), categories, allowed
            )
        except Exception as exc:
            self.pdf_status.set_text(f"Vytvoření PDF selhalo: {exc}")
            self.set_status("PDF se nepodařilo vytvořit.")
            ui.notify(str(exc), type="negative", position="top", timeout=8000)
        else:
            self.last_pdf = path
            self.open_pdf_button.enable()
            self.pdf_status.set_text(f"PDF vytvořeno: {path}")
            self._refresh_overview_tiles()
            self.set_status("PDF bylo vytvořeno a otevřeno.")
            try:
                open_document(path)
            except Exception as exc:
                ui.notify(
                    f"PDF je hotové, ale nepodařilo se automaticky otevřít: {exc}",
                    type="warning",
                    timeout=8000,
                )
        finally:
            self.generate_button.enable()

    def _create_pdf(
        self,
        meal_type: str | None = None,
        categories: tuple[str, ...] | None = None,
        allowed_categories: tuple[str, ...] | None = None,
    ) -> Path:
        config = load_config(self.config_path)
        config = replace(
            config,
            meal_type=meal_type,
            categories=categories if categories is not None else config.categories,
        )
        report = fetch_report(config)
        output_path = (
            manual_pdf_path(config.pdf_output, categories, allowed_categories, meal_type)
            if categories is not None and allowed_categories is not None else None
        )
        return create_pdf(config, report, output_path=output_path)

    async def generate_z17(self) -> None:
        if not self.connection_ok:
            ui.notify("Nejprve proveďte úspěšný TEST připojení.", type="warning")
            return
        try:
            self.save_special_settings()
            year = parse_z17_year(self.z17_year.value)
        except ConfigError as exc:
            ui.notify(str(exc), type="negative", position="top")
            return

        self.z17_generate_button.disable()
        self.special_status.set_text("Načítám přihlášky a vytvářím podklad Z 17-01…")
        self.set_status("Probíhá tvorba podkladu Z 17-01.")
        try:
            path = await run.io_bound(self._create_z17, year)
        except Exception as exc:
            self.special_status.set_text(f"Podklad Z 17-01 selhal: {exc}")
            self.set_status("Podklad Z 17-01 se nepodařilo vytvořit.")
            ui.notify(str(exc), type="negative", position="top", timeout=8000)
        else:
            self.last_z17_pdf = path
            self.z17_open_button.enable()
            self.special_status.set_text(f"Podklad Z 17-01 vytvořen: {path}")
            self.set_status("Podklad Z 17-01 byl vytvořen a otevřen.")
            try:
                open_document(path)
            except Exception as exc:
                ui.notify(
                    f"PDF je hotové, ale nepodařilo se automaticky otevřít: {exc}",
                    type="warning",
                    timeout=8000,
                )
        finally:
            self.z17_generate_button.enable()

    def _create_z17(self, year: int) -> Path:
        result = run_z17_report(self.config_path, year=year)
        files = result.get("files") or []
        if not files:
            raise ConfigError("Podklad Z 17-01 nevytvořil žádný soubor.")
        return Path(files[0])

    def open_last_z17_pdf(self) -> None:
        if self.last_z17_pdf and self.last_z17_pdf.is_file():
            try:
                open_document(self.last_z17_pdf)
            except Exception as exc:
                ui.notify(str(exc), type="negative", position="top")

    def open_last_pdf(self) -> None:
        if self.last_pdf and self.last_pdf.is_file():
            try:
                open_document(self.last_pdf)
            except Exception as exc:
                ui.notify(str(exc), type="negative", position="top")

    async def _confirm_send(
        self,
        count: int,
        subject: str,
        *,
        title: str | None = None,
        extra: str = "",
        confirm_label: str = "Vytvořit a odeslat",
    ) -> bool:
        return await w.confirm_dialog(
            title="Potvrdit odeslání",
            message=title or f"PDF bude odesláno {count} příjemcům.",
            detail=extra,
            note=f"Předmět: {subject}",
            confirm_label=confirm_label,
        )

    async def send_mail(self) -> None:
        if not self.connection_ok:
            ui.notify("Nejprve proveďte úspěšný TEST připojení.", type="warning")
            return
        try:
            categories = self._manual_daily_categories()
            allowed = tuple(self._allowed_category_order())
            if not self.wizard_recipients.commit_pending():
                return
            recipients = normalize_recipients(self.wizard_recipients.addresses)
            outgoing = self._outgoing_mail_settings()
            api_key = await self._persist_settings(require_api_key=outgoing["transport"] == "resend")
            sender = normalize_recipient(self._outgoing_sender())
            template_data = {"report": "Denní stav", "date": self._selected_date().strftime("%d.%m.%Y")}
            subject = outgoing["subject_template"].format(**template_data)
            body = outgoing["body_template"].format(**template_data)
        except (ConfigError, CredentialStoreError, EnvStoreError) as exc:
            ui.notify(str(exc), type="negative", position="top")
            return

        if not await self._confirm_send(len(recipients), subject):
            return

        self.send_button.disable()
        self.mail_status.set_text("Kontroluji data a připravuji mail…")
        self.set_status("Probíhá příprava mailového exportu.")
        try:
            result = await run.io_bound(
                self._send_mail_worker,
                recipients,
                api_key,
                sender,
                body,
                False,
                self._selected_daily_meal_type(),
                categories,
                allowed,
                subject=subject,
            )
        except Exception as exc:
            self.mail_status.set_text(f"Odeslání selhalo: {exc}")
            self.set_status("Mail se nepodařilo odeslat.")
            ui.notify(str(exc), type="negative", position="top", timeout=8000)
        else:
            if result["skipped"]:
                message = str(result["message"])
                self.mail_status.set_text(f"Neodesláno: {message}")
                self.set_status("Mail nebyl odeslán – není relevantní varný den.")
                ui.notify(message, type="info", timeout=8000)
            else:
                path = Path(result["path"])
                dispatch = result["dispatch"]
                self.last_pdf = path
                self.open_pdf_button.enable()
                detail = f" ({dispatch.detail})" if dispatch.detail else ""
                self.mail_status.set_text(
                    f"Odesláno {len(dispatch.recipients)} příjemcům{detail}."
                )
                self.last_mail_note = (
                    f"{datetime.now().strftime('%d.%m.%Y %H:%M')} · "
                    f"{len(dispatch.recipients)} příjemců"
                )
                self.pdf_status.set_text(f"PDF vytvořeno: {path}")
                self._refresh_overview_tiles()
                self.set_status("PDF bylo vytvořeno a mail odeslán.")
                ui.notify("Mail byl odeslán.", type="positive", position="top")
        finally:
            self.send_button.enable()

    def _send_mail_worker(
        self,
        recipients: tuple[str, ...],
        api_key: str,
        sender: str,
        body: str,
        only_cooking_days: bool,
        meal_type: str | None = None,
        categories: tuple[str, ...] | None = None,
        allowed_categories: tuple[str, ...] | None = None,
        *, subject: str | None = None,
    ) -> dict[str, Any]:
        config = load_config(self.config_path)
        config = replace(
            config,
            meal_type=meal_type,
            categories=categories if categories is not None else config.categories,
        )
        statuses = fetch_cooking_status(config) if only_cooking_days else ()
        if only_cooking_days and not should_send_on_cooking_day(statuses):
            return {"skipped": True, "message": cooking_status_message(statuses)}

        report = fetch_report(config)
        output_path = (
            manual_pdf_path(config.pdf_output, categories, allowed_categories, meal_type)
            if categories is not None and allowed_categories is not None else None
        )
        path = create_pdf(config, report, output_path=output_path)
        subject = subject or mail_subject(config.report_date)
        settings = self._outgoing_mail_settings()
        if settings["transport"] == "smtp":
            dispatch = MailDispatchResult(
                recipients=smtp_send(settings, recipients, subject, body, path), detail="SMTP",
            )
        else:
            dispatch = send_pdf_via_mailsender(
                recipients, subject, body, path, api_key=api_key, sender_email=sender,
            )
        return {"skipped": False, "path": path, "dispatch": dispatch}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    remaining, period = consume_closing_flag(raw_argv)
    remaining, z17_year = consume_z17_flag(remaining)
    parser = argparse.ArgumentParser(description="NiceGUI pro DataShip")
    parser.add_argument(
        "--config",
        type=Path,
        default=application_directory() / "config.json",
        help="cesta ke config.json",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="otevřít UI v prohlížeči (výchozí)",
    )
    parser.add_argument(
        "--native",
        action="store_true",
        help="otevřít UI v klasickém okně aplikace (pywebview)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="port pro prohlížeč; 0 automaticky vybere volný port",
    )
    parser.add_argument(
        "--automatic",
        action="store_true",
        help="bez GUI vytvoří dnešní PDF a odešle je podle nastavení",
    )
    parser.add_argument(
        "--poctyemailem",
        action="store_true",
        help="stejné jako --automatic: denní sestava počtů e-mailem (SCIO)",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=application_directory() / "logy" / "automaticky_export.log",
        help="provozní log automatického exportu nebo uzávěrky",
    )
    parser.add_argument(
        "--version", action="version", version=f"{APP_TITLE} {APP_VERSION} build {WEB_BUILD}"
    )
    parser.add_argument("--version-file", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(remaining)
    args.uzaverka_current = period == CURRENT_CLOSING_PERIOD
    args.uzaverka_period = period if isinstance(period, tuple) else None
    args.uzaverka = period is not None
    args.z17_year = z17_year
    args.z17 = z17_year is not None
    args.automatic = bool(args.automatic or args.poctyemailem)
    return args


def main(argv: Sequence[str] | None = None) -> int:
    os.chdir(application_directory())
    try:
        args = parse_args(argv)
    except ConfigError as exc:
        print(f"CHYBA: {exc}", file=sys.stderr)
        return 2
    if args.version_file is not None:
        try:
            args.version_file.write_text(f"{APP_TITLE} {APP_VERSION} build {WEB_BUILD}\n", encoding="utf-8")
        except OSError as exc:
            print(f"Verzi nelze zapsat: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.automatic and args.uzaverka:
        print(
            "Zvolte jen --poctyemailem / --automatic, nebo jen přepínač uzávěrky.",
            file=sys.stderr,
        )
        return 2
    if args.automatic and args.z17:
        print(
            "Zvolte jen --poctyemailem / --automatic, nebo jen přepínač Z 17-01.",
            file=sys.stderr,
        )
        return 2
    if args.uzaverka and args.z17:
        print("Zvolte jen přepínač uzávěrky, nebo jen přepínač Z 17-01.", file=sys.stderr)
        return 2
    if args.automatic:
        return automatic_export_main(
            ["--config", str(args.config), "--log", str(args.log)]
        )
    if args.uzaverka:
        if args.uzaverka_current:
            closing_switch = "--zaverka_am"
        elif args.uzaverka_period is None:
            print(f"CHYBA: {CLOSING_FLAG_HELP}", file=sys.stderr)
            return 2
        else:
            year, month = args.uzaverka_period
            closing_switch = closing_flag(year, month)
        return monthly_closing_main(
            [
                closing_switch,
                "--config",
                str(args.config),
                "--log",
                str(args.log),
            ]
        )
    if args.z17:
        if args.z17_year is None:
            print(f"CHYBA: {Z17_FLAG_HELP}", file=sys.stderr)
            return 2
        return z17_main(
            [
                z17_flag(args.z17_year),
                "--config",
                str(args.config),
                "--log",
                str(args.log),
            ]
        )
    try:
        application = NiceGuiApp(args.config)
    except Exception as exc:
        print(f"{APP_TITLE}: {exc}", file=sys.stderr)
        return 2

    run_options: dict[str, Any] = {
        "root": application.build,
        "title": f"{APP_TITLE} · {APP_VERSION}",
        "favicon": BRAND_FAVICON,
        "language": "cs-CZ",
        "reload": False,
        "show_welcome_message": False,
        "fastapi_docs": False,
        "endpoint_documentation": "none",
        "reconnect_timeout": 5.0,
    }
    port = args.port or native.find_open_port()
    if args.native and args.browser:
        print("Zvolte jen --native, nebo jen --browser.", file=sys.stderr)
        return 2
    if args.native and not native_ui_available():
        print(
            "Chybí balíček pywebview, otevírám UI v prohlížeči. "
            "Nainstalujte: py -3 -m pip install pywebview",
            file=sys.stderr,
        )
    run_options.update(
        configure_ui_window(
            browser=args.browser or not args.native,
            native_window=bool(args.native),
            port=port,
        )
    )
    print(f"Spouštím DataShip na http://127.0.0.1:{port}", flush=True)
    ui.run(**run_options)
    return 0


if __name__ in {"__main__", "__mp_main__"}:
    from multiprocessing import freeze_support

    freeze_support()
    raise SystemExit(main())






