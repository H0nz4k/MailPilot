"""Hlavní okno MailPilotu: navigace, stav a obsluha akcí."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QPoint, QTimer, Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from credential_store import (
    CredentialStoreError,
    get_admin_password,
    set_admin_password,
)
from env_store import EnvStoreError, get_resend_api_key
from gui_qt import APP_CREDIT, APP_TITLE, APP_VERSION
from gui_qt.icons import (
    NAV_ADMIN,
    NAV_BULK,
    NAV_CLOSING,
    NAV_DAILY,
    NAV_HELP,
    NAV_SPECIAL,
    muted_icon,
    nav_icon,
)
from gui_qt.pages.admin import (
    SECTION_ADVANCED,
    SECTION_DATABASE,
    SECTION_SCHEDULER,
    AdminPage,
)
from gui_qt.pages.bulk import BulkPage
from gui_qt.pages.closing import ClosingPage
from gui_qt.pages.daily import DailyPage
from gui_qt.pages.special import SpecialPage
from gui_qt.pages.user_settings import UserSettingsPage
from gui_qt.theme import apply_theme, metrics_for, palette_for
from gui_qt.widgets.header import STATE_ERROR, STATE_IDLE, STATE_OK, HeaderBar
from gui_qt.widgets.sidebar import NavItem, NavigationSidebar
from gui_qt.workers import BackgroundRunner
from services.bulk import (
    BulkData,
    BulkPreview,
    apply_bulk_form,
    bulk_preview_summary,
    filter_options,
    load_bulk_data,
    peek_bulk_form,
    preview_for,
    recipient_rows,
    send_bulk,
    validate_message,
)
from services.closing import (
    ClosingRun,
    apply_closing_form,
    existing_outputs,
    peek_closing_form,
    resolve_output as resolve_closing_output,
    run_closing,
)
from services.config_io import (
    database_parameters,
    load_raw_config,
    normalize_database,
    open_document,
    save_raw_config,
)
from services.daily import (
    DailyDispatch,
    DailyOverview,
    DailyResult,
    action_state,
    apply_daily_settings,
    create_daily_pdf,
    describe_moment,
    fetch_daily_overview,
    peek_daily_mail,
    peek_daily_settings,
    reconcile_categories,
    recipients_phrase,
    send_daily_pdf,
)
from services.database import ConnectionInfo, probe_connection, stored_password
from services.mail_settings import (
    apply_mail_settings,
    peek_mail_settings,
    read_api_key,
    save_api_key,
)
from services.jidelnasql_warning import (
    JidelnaWarningSettings,
    apply_warning_settings,
    clear_jidelnasql_mail_warning,
    is_jidelnasql_mail_warning_active,
    peek_warning_settings,
    show_jidelnasql_mail_warning,
)
from services.user_overview import (
    RetryResult,
    load_automail_overview,
    retry_daily_mail,
)
from services.pdf_settings import apply_pdf_settings, peek_pdf_settings
from services.scheduler import PlannedJob, read_jobs, run_job_now, scheduler_path, write_jobs
from services.scheduler_runtime import (
    DEFAULT_SERVICE_NAME,
    apply_service_config,
    install_service,
    peek_service_config,
    read_runtime_snapshot,
    read_service_status,
    read_runtime_status,
    remove_service,
    restart_service,
    start_runtime,
    stop_runtime,
)
from services.special import (
    SpecialRun,
    apply_row_mapping,
    apply_special_form,
    existing_pdf,
    peek_row_mapping,
    peek_special_form,
    peek_supplement_rows,
    resolve_output as resolve_special_output,
    run_special,
    validate_form as validate_special_form,
)
from services.ui_settings import (
    FONT_BOLD_LABELS,
    THEME_LABELS,
    UiSettings,
    apply_ui_settings,
    scale_label,
)
from stravovaci_sestava import ConfigError


PAGE_DAILY = "daily"
PAGE_CLOSING = "closing"
PAGE_SPECIAL = "special"
PAGE_BULK = "bulk"
PAGE_USER = "user"
PAGE_ADMIN = "admin"
PAGE_HELP = "help"

NAV_ITEMS = (
    NavItem(PAGE_DAILY, "Denní stav", "Ctrl+1", NAV_DAILY),
    NavItem(PAGE_CLOSING, "Uzávěrka", "Ctrl+2", NAV_CLOSING),
    NavItem(PAGE_SPECIAL, "Speciál", "Ctrl+3", NAV_SPECIAL),
    NavItem(PAGE_BULK, "Hromadná zpráva", "Ctrl+4", NAV_BULK),
    NavItem(PAGE_HELP, "Nápověda", "F1", NAV_HELP),
)

ABOUT_TEXT = (
    "{title} {version}\n\n"
    "Desktopová aplikace pro školní jídelny: denní sestavy, měsíční "
    "uzávěrka, roční výkaz Z 17-01 a hromadné zprávy strávníkům.\n\n"
    "{credit}"
)


class MainWindow(QMainWindow):
    """Prezentační vrstva; veškerá práce běží v servisní vrstvě."""

    def __init__(
        self,
        config_path: Path,
        ui_settings: UiSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._config_path = config_path.resolve()
        self._ui = ui_settings
        self._metrics = metrics_for(ui_settings.ui_scale)
        self._palette = palette_for(
            ui_settings.theme,
            custom_palette_enabled=ui_settings.custom_palette_enabled,
            custom_palette=ui_settings.custom_palette,
        )
        self._runner = BackgroundRunner(self)
        self._raw = load_raw_config(self._config_path)
        self._connection: ConnectionInfo | None = None
        self._last_pdf: Path | None = None
        self._last_mail_note = ""
        self._last_mail_state = ""
        self._busy = False
        self._db_options: tuple[tuple[str, str], ...] = ()
        self._scheduler_path = scheduler_path(self._config_path)
        self._pending_admin: set[str] = set()
        self._bulk_data = BulkData()
        self._bulk_preview: BulkPreview | None = None
        self._admin_unlocked = False
        self._runtime_snapshot = None

        self.setWindowTitle(f"{APP_TITLE} {APP_VERSION}")
        self.setMinimumSize(940, 600)
        self._build_ui()
        self._build_menu()
        self._setup_status_bar()
        self._install_shortcuts()
        self._restore_state()
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(lambda: self._persist(silent=True))
        self._admin_timer = QTimer(self)
        self._admin_timer.setSingleShot(True)
        self._admin_timer.setInterval(600)
        self._admin_timer.timeout.connect(self._flush_admin_save)
        self._runtime_timer = QTimer(self)
        self._runtime_timer.setInterval(5000)
        self._runtime_timer.timeout.connect(self._refresh_scheduler_runtime)
        self._runtime_timer.start()
        self._admin_idle_timer = QTimer(self)
        self._admin_idle_timer.setSingleShot(True)
        self._admin_idle_timer.setInterval(60_000)
        self._admin_idle_timer.timeout.connect(self._auto_lock_admin_idle)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
        QTimer.singleShot(0, self._auto_connect)

    # ------------------------------------------------------------------
    # Stavba rozhraní
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        metrics = self._metrics
        central = QWidget(self)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.header = HeaderBar(metrics, central)
        self.header.database_setup_requested.connect(
            self._open_database_setup_from_header
        )
        self.header.home_requested.connect(self._open_overview_page)
        self.header.admin_requested.connect(self._toggle_admin_from_header)
        self.header.set_home_icon(nav_icon(NAV_DAILY, self._palette, metrics.icon_size))
        self.header.set_admin_icon(
            muted_icon(NAV_ADMIN, self._palette, metrics.icon_size)
        )
        outer.addWidget(self.header)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.sidebar = NavigationSidebar(
            NAV_ITEMS, metrics, central, palette=self._palette
        )
        self.sidebar.page_selected.connect(self._show_page)
        body.addWidget(self.sidebar)

        self.stack = QStackedWidget(central)
        self.daily_page = DailyPage(metrics, self.stack, palette=self._palette)
        self.daily_page.settings_changed.connect(self._schedule_save)
        self.daily_page.create_requested.connect(self._create_pdf)
        self.daily_page.send_requested.connect(self._send_mail)
        self.daily_page.open_last_requested.connect(self._open_last_pdf)
        self.daily_page.overview_requested.connect(self._load_overview)

        self.closing_page = ClosingPage(metrics, self.stack, palette=self._palette)
        self.closing_page.settings_changed.connect(self._closing_changed)
        self.closing_page.run_requested.connect(self._run_closing)
        self.closing_page.open_folder_requested.connect(self._open_closing_folder)
        self.closing_page.open_file_requested.connect(self._open_document)

        self.special_page = SpecialPage(metrics, self.stack, palette=self._palette)
        self.special_page.settings_changed.connect(self._special_changed)
        self.special_page.run_requested.connect(self._run_special)
        self.special_page.open_folder_requested.connect(self._open_special_folder)
        self.special_page.open_file_requested.connect(self._open_document)

        self.bulk_page = BulkPage(metrics, self.stack, palette=self._palette)
        self.bulk_page.settings_changed.connect(
            lambda: self._schedule_admin_save("bulk")
        )
        self.bulk_page.filter_changed.connect(self._refresh_bulk_preview)
        self.bulk_page.reload_requested.connect(self._load_bulk_data)
        self.bulk_page.send_requested.connect(self._send_bulk)

        self.user_page = UserSettingsPage(metrics, self.stack)
        self.user_page.resend_requested.connect(self._retry_automail)

        self.admin_page = AdminPage(metrics, self.stack, palette=self._palette)
        self.admin_page.nav.section_selected.connect(self._admin_section_changed)
        self.admin_page.database_page.test_requested.connect(self._test_connection)
        self.admin_page.appearance_page.theme_selected.connect(self._change_theme)
        self.admin_page.appearance_page.scale_selected.connect(self._change_scale)
        self.admin_page.appearance_page.bold_mode_selected.connect(
            self._change_font_bold_mode
        )
        self.admin_page.appearance_page.custom_palette_enabled_toggled.connect(
            self._change_custom_palette_enabled
        )
        self.admin_page.appearance_page.custom_palette_changed.connect(
            self._change_custom_palette
        )
        self.admin_page.mail_page.settings_changed.connect(
            lambda: self._schedule_admin_save("mail")
        )
        self.admin_page.mail_page.api_key_save_requested.connect(self._save_api_key)
        self.admin_page.mail_page.failed.connect(
            lambda message: self._show_error("E-maily", message)
        )
        self.admin_page.pdf_page.settings_changed.connect(
            lambda: self._schedule_admin_save("pdf")
        )
        self.admin_page.scheduler_page.save_requested.connect(self._save_jobs)
        self.admin_page.scheduler_page.failed.connect(
            lambda message: self._show_error("Plánovač", message)
        )
        self.admin_page.scheduler_page.runtime_start_requested.connect(
            self._start_scheduler_runtime
        )
        self.admin_page.scheduler_page.runtime_stop_requested.connect(
            self._stop_scheduler_runtime
        )
        self.admin_page.scheduler_page.runtime_restart_requested.connect(
            self._restart_scheduler_runtime
        )
        self.admin_page.scheduler_page.runtime_open_log_requested.connect(
            self._open_scheduler_log
        )
        self.admin_page.scheduler_page.service_install_requested.connect(
            self._install_scheduler_service
        )
        self.admin_page.scheduler_page.service_remove_requested.connect(
            self._remove_scheduler_service
        )
        self.admin_page.scheduler_page.service_restart_requested.connect(
            self._restart_scheduler_service
        )
        self.admin_page.scheduler_page.run_job_requested.connect(
            self._run_scheduler_job_now
        )
        self.admin_page.headless_page.copy_requested.connect(self._copy_to_clipboard)
        self.admin_page.advanced_page.open_path_requested.connect(self._open_folder)
        self.admin_page.advanced_page.mapping_changed.connect(
            lambda: self._schedule_admin_save("advanced")
        )
        self.admin_page.advanced_page.warning_show_requested.connect(
            self._manual_show_warning
        )
        self.admin_page.advanced_page.warning_show_custom_requested.connect(
            self._manual_show_warning_custom
        )
        self.admin_page.advanced_page.warning_clear_requested.connect(
            self._manual_clear_warning
        )

        self._pages: dict[str, QWidget] = {
            PAGE_DAILY: self.daily_page,
            PAGE_CLOSING: self.closing_page,
            PAGE_SPECIAL: self.special_page,
            PAGE_BULK: self.bulk_page,
            PAGE_USER: self.user_page,
            PAGE_ADMIN: self.admin_page,
        }
        self._page_indexes = {
            key: self.stack.addWidget(page) for key, page in self._pages.items()
        }
        body.addWidget(self.stack, 1)
        outer.addLayout(body, 1)
        self.setCentralWidget(central)

        self._load_from_config()
        self._open_overview_page()

    def _build_menu(self) -> None:
        """Horní menu skrýváme; nápověda je v levé navigaci."""
        bar = self.menuBar()
        bar.clear()
        bar.setVisible(False)
        self._refresh_admin_lock_state()

    def _setup_status_bar(self) -> None:
        status = self.statusBar()
        status.setSizeGripEnabled(True)
        credit = QLabel(APP_CREDIT)
        credit.setProperty("role", "hint")
        status.addPermanentWidget(credit)
        self.set_status("Připraveno")

    def _install_shortcuts(self) -> None:
        for item in NAV_ITEMS:
            if not item.shortcut_hint:
                continue
            shortcut = QShortcut(QKeySequence(item.shortcut_hint), self)
            shortcut.activated.connect(
                lambda key=item.key: self.sidebar.select(key)
            )
        # Ctrl++ na numerické klávesnici i s háčkem nad rovnítkem.
        for sequence in ("Ctrl++", "Ctrl+="):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(lambda: self._zoom(1))
        shortcut = QShortcut(QKeySequence("Ctrl+-"), self)
        shortcut.activated.connect(lambda: self._zoom(-1))
        shortcut = QShortcut(QKeySequence("Ctrl+5"), self)
        shortcut.activated.connect(self._toggle_admin_from_header)

    def _load_from_config(self) -> None:
        """Naplní obrazovky hodnotami z config.json."""
        settings = peek_daily_settings(self._raw)
        self.daily_page.set_settings(settings)
        options = self._db_options or tuple(
            (code, "") for code in settings.categories
        )
        self.daily_page.set_category_options(options)
        self.daily_page.set_last_pdf(self._last_pdf)
        self.daily_page.set_last_mail(self._last_mail_note, self._last_mail_state)

        self.closing_page.set_form(peek_closing_form(self._raw))
        self._refresh_closing_output()
        self.special_page.set_form(peek_special_form(self._raw))
        self.special_page.set_category_options(options)
        self._refresh_special_output()
        self.bulk_page.set_form(peek_bulk_form(self._raw))
        self._apply_bulk_data()

        database = database_parameters(self._raw)
        self.admin_page.database_page.set_values(database)
        self._sync_appearance_pages()
        self._refresh_user_overview()
        self.admin_page.mail_page.set_settings(peek_mail_settings(self._raw))
        self.admin_page.mail_page.set_api_key(read_api_key())
        self.admin_page.pdf_page.set_settings(peek_pdf_settings(self._raw))
        self.admin_page.advanced_page.set_context(self._config_path, database)
        self.admin_page.advanced_page.set_mapping(
            peek_row_mapping(self._raw), peek_supplement_rows(self._raw), options
        )
        warning = peek_warning_settings(self._raw)
        self.admin_page.advanced_page.set_warning_settings(
            enabled=warning.enabled,
            template_path=warning.template_path,
        )
        self._sync_warning_state_from_file(silent=True)
        self._load_planned_jobs()
        self._refresh_actions()

    def _load_planned_jobs(self) -> None:
        try:
            jobs = read_jobs(self._scheduler_path)
        except (ConfigError, OSError) as exc:
            jobs = []
            self.set_status("Plánovač se nepodařilo načíst", str(exc))
        self.admin_page.scheduler_page.set_jobs(jobs, self._config_path.parent)
        service_cfg = peek_service_config(self._raw)
        self.admin_page.scheduler_page.set_service_config(
            service_name=service_cfg.service_name,
            nssm_path=service_cfg.nssm_path,
        )
        self._refresh_scheduler_runtime()
        self._refresh_scheduler_service()

    # ------------------------------------------------------------------
    # Navigace a stav
    # ------------------------------------------------------------------
    def _show_page(self, key: str) -> None:
        if key == PAGE_HELP:
            active = self._current_page_key()
            self._show_help()
            if active in {PAGE_DAILY, PAGE_CLOSING, PAGE_SPECIAL, PAGE_BULK, PAGE_HELP}:
                QTimer.singleShot(0, lambda value=active: self.sidebar.select(value))
            else:
                self.sidebar.clearSelection()
            return
        if key == PAGE_ADMIN and not self._admin_unlocked:
            if not self._unlock_admin_interactive():
                self.sidebar.select(PAGE_DAILY)
                return
        self._activate_page(key)

    def _activate_page(self, key: str) -> None:
        index = self._page_indexes.get(key)
        if index is None:
            return
        self.stack.setCurrentIndex(index)
        page = self._pages.get(key)
        if key == PAGE_ADMIN:
            self.admin_page.focus_section(self.admin_page.current_section())
        elif page is not None and hasattr(page, "focus_default"):
            page.focus_default()

    def _current_page_key(self) -> str:
        current_index = self.stack.currentIndex()
        for key, index in self._page_indexes.items():
            if index == current_index:
                return key
        return ""

    def _open_overview_page(self) -> None:
        self._refresh_user_overview()
        self._activate_page(PAGE_USER)
        self.sidebar.clearSelection()

    def _toggle_admin_from_header(self) -> None:
        if self._admin_unlocked:
            if self._current_page_key() == PAGE_ADMIN:
                self._lock_admin()
            else:
                self._activate_page(PAGE_ADMIN)
                self.sidebar.clearSelection()
            return
        if not self._unlock_admin_interactive():
            return
        self._activate_page(PAGE_ADMIN)
        self.sidebar.clearSelection()

    def _open_database_setup_from_header(self) -> None:
        if self._connection is not None:
            return
        if not self._admin_unlocked and not self._unlock_admin_interactive():
            return
        self.admin_page.show_section(SECTION_DATABASE)
        self._activate_page(PAGE_ADMIN)
        self.sidebar.clearSelection()

    def _admin_section_changed(self, key: str) -> None:
        if key == SECTION_ADVANCED:
            self._sync_warning_state_from_file(silent=True)
        elif key == SECTION_SCHEDULER:
            self._refresh_scheduler_service()
            self._refresh_scheduler_runtime()

    def set_status(self, text: str, detail: str = "") -> None:
        """Krátká zpráva do lišty; delší vysvětlení nese tooltip lišty."""
        self.statusBar().showMessage(text)
        self.statusBar().setToolTip(detail)

    # ------------------------------------------------------------------
    # Čtení stavu (testy a kontrolní průchod)
    # ------------------------------------------------------------------
    def connection(self) -> ConnectionInfo | None:
        return self._connection

    def ui_settings(self) -> UiSettings:
        return self._ui

    def last_pdf(self) -> Path | None:
        return self._last_pdf

    def last_closing(self) -> Path | None:
        return self.closing_page.last_output()

    def last_special(self) -> Path | None:
        return self.special_page.last_output()

    def bulk_data(self) -> BulkData:
        return self._bulk_data

    def _refresh_actions(self) -> None:
        mail = peek_daily_mail(self._raw)
        connected = self._connection is not None
        state = action_state(
            connected=connected,
            selected_categories=len(self.daily_page.selected_categories()),
            recipients=len(mail.recipients),
            has_last_pdf=self._last_pdf is not None and self._last_pdf.is_file(),
            busy=self._busy,
        )
        self.daily_page.set_action_state(state)
        self.daily_page.set_overview_enabled(state.can_create)
        blocked = "" if connected else "Nejprve ověřte připojení k databázi."
        if self._busy:
            blocked = "Probíhá jiná operace."
        self.closing_page.set_run_enabled(connected and not self._busy, blocked)
        self.special_page.set_run_enabled(connected and not self._busy, blocked)
        self.bulk_page.set_picker_enabled(connected and not self._busy)
        self._refresh_bulk_send_state(blocked)

    def _refresh_bulk_send_state(self, blocked: str) -> None:
        preview = self._bulk_preview
        if blocked:
            self.bulk_page.set_send_enabled(False, blocked)
            return
        if preview is None or not preview.recipients:
            self.bulk_page.set_send_enabled(
                False, "Vyberte příjemce s platným e-mailem."
            )
            return
        self.bulk_page.set_send_enabled(True)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy:
            QApplication.setOverrideCursor(Qt.BusyCursor)
        else:
            QApplication.restoreOverrideCursor()
        self._refresh_actions()

    # ------------------------------------------------------------------
    # Konfigurace
    # ------------------------------------------------------------------
    def _schedule_save(self) -> None:
        self._refresh_actions()
        self._save_timer.start()

    def _persist(self, *, silent: bool) -> bool:
        """Uloží nastavení denní sestavy a bloku ui do config.json."""
        try:
            updated = apply_daily_settings(self._raw, self.daily_page.settings())
        except ConfigError as exc:
            if silent:
                self.set_status(str(exc))
                return False
            self._show_error("Nastavení sestavy", str(exc))
            return False
        updated = apply_ui_settings(updated, self._ui)
        try:
            save_raw_config(self._config_path, updated)
        except OSError as exc:
            self._show_error("Uložení konfigurace", str(exc))
            return False
        self._raw = updated
        self.admin_page.pdf_page.set_settings(peek_pdf_settings(self._raw))
        return True

    def _write_config(self, updated: dict[str, Any], title: str) -> bool:
        try:
            save_raw_config(self._config_path, updated)
        except OSError as exc:
            self._show_error(title, str(exc))
            return False
        self._raw = updated
        return True

    # ------------------------------------------------------------------
    # Administrace
    # ------------------------------------------------------------------
    def _schedule_admin_save(self, kind: str) -> None:
        self._pending_admin.add(kind)
        self._admin_timer.start()

    def _warning_settings(self) -> JidelnaWarningSettings:
        page = self.admin_page.advanced_page
        return JidelnaWarningSettings(
            enabled=page.warning_enabled(),
            template_path=page.warning_template_path(),
        )

    def _sync_warning_state_from_file(self, *, silent: bool) -> bool:
        settings = self._warning_settings()
        active = is_jidelnasql_mail_warning_active(settings)
        self.admin_page.advanced_page.set_warning_active(active)
        if not active and not settings.template_path.is_file() and not silent:
            self.set_status(
                "Dashboard šablona nebyla nalezena",
                str(settings.template_path),
            )
        return active

    def _flush_admin_save(self) -> None:
        pending = set(self._pending_admin)
        self._pending_admin.clear()
        if "mail" in pending:
            self._save_mail_settings()
        if "pdf" in pending:
            self._save_pdf_settings()
        if "closing" in pending:
            self._save_closing_settings()
        if "special" in pending:
            self._save_special_settings()
        if "bulk" in pending:
            self._save_bulk_settings()
        if "advanced" in pending:
            self._save_row_mapping()

    def _save_row_mapping(self) -> None:
        page = self.admin_page.advanced_page
        updated = apply_row_mapping(
            self._raw, page.mapping(), page.supplement_rows()
        )
        warning = JidelnaWarningSettings(
            enabled=page.warning_enabled(),
            template_path=page.warning_template_path(),
        )
        updated = apply_warning_settings(updated, warning)
        if not self._write_config(updated, "Mapování Z 17-01"):
            return
        if not warning.enabled:
            note = clear_jidelnasql_mail_warning(
                JidelnaWarningSettings(
                    enabled=True, template_path=warning.template_path
                )
            )
            if note:
                self.set_status("Warning JídelnaSQL se nepodařilo smazat", note)
        self._sync_warning_state_from_file(silent=True)
        self.set_status("Pokročilá nastavení uložena.")

    def _manual_show_warning(self) -> None:
        settings = JidelnaWarningSettings(
            enabled=True,
            template_path=self._warning_settings().template_path,
        )
        note = show_jidelnasql_mail_warning(settings)
        if note:
            self.set_status("Test warningu selhal", note)
            self._show_error("JídelnaSQL warning", note)
            return
        active = self._sync_warning_state_from_file(silent=True)
        if not active:
            self._show_error(
                "JídelnaSQL warning",
                "Warning nebyl po zápisu v dashboardu nalezen.",
            )
            return
        self.set_status(
            "Test warningu: blok byl vložen do dashboard.template.html",
            str(settings.template_path),
        )

    def _manual_show_warning_custom(self) -> None:
        message, ok = QInputDialog.getText(
            self,
            "Test warningu JídelnaSQL",
            "Zadejte text chyby (např. SMTP timeout):",
            QLineEdit.Normal,
            "Automatický export selhal: SMTP timeout",
        )
        if not ok:
            return
        text = str(message or "").strip()
        if not text:
            self.set_status("Text chyby je prázdný, warning nebyl vložen")
            return
        settings = JidelnaWarningSettings(
            enabled=True,
            template_path=self._warning_settings().template_path,
        )
        note = show_jidelnasql_mail_warning(settings, message=text)
        if note:
            self.set_status("Test warningu selhal", note)
            self._show_error("JídelnaSQL warning", note)
            return
        active = self._sync_warning_state_from_file(silent=True)
        if not active:
            self._show_error(
                "JídelnaSQL warning",
                "Warning nebyl po zápisu v dashboardu nalezen.",
            )
            return
        self.set_status(
            "Test warningu: vložen vlastní text chyby do dashboardu",
            text,
        )

    def _manual_clear_warning(self) -> None:
        settings = JidelnaWarningSettings(
            enabled=True,
            template_path=self._warning_settings().template_path,
        )
        note = clear_jidelnasql_mail_warning(settings)
        if note:
            self.set_status("Mazání warningu selhalo", note)
            self._show_error("JídelnaSQL warning", note)
            return
        active = self._sync_warning_state_from_file(silent=True)
        if active:
            self._show_error(
                "JídelnaSQL warning",
                "Warning se nepodařilo odstranit z dashboardu.",
            )
            return
        self.set_status(
            "Test warningu: blok byl odstraněn z dashboard.template.html",
            str(settings.template_path),
        )

    def _save_mail_settings(self) -> None:
        try:
            updated = apply_mail_settings(
                self._raw, self.admin_page.mail_page.settings()
            )
        except ConfigError as exc:
            self.set_status("Nastavení e-mailů se neuložilo", str(exc))
            return
        if not self._write_config(updated, "Nastavení e-mailů"):
            return
        self.set_status("Nastavení e-mailů uloženo.")
        self.closing_page.set_recipients(peek_closing_form(self._raw).recipients)
        self._refresh_actions()

    def _save_pdf_settings(self) -> None:
        try:
            updated = apply_pdf_settings(
                self._raw, self.admin_page.pdf_page.settings()
            )
        except ConfigError as exc:
            self.set_status("Nastavení PDF se neuložilo", str(exc))
            return
        if not self._write_config(updated, "Nastavení PDF"):
            return
        self.daily_page.set_settings(peek_daily_settings(self._raw))
        self.set_status("Nastavení PDF uloženo.")

    def _save_api_key(self, api_key: str) -> None:
        try:
            save_api_key(api_key)
        except EnvStoreError as exc:
            self._show_error("Resend API klíč", str(exc))
            return
        self.set_status(
            "Resend API klíč uložen.", f"Soubor .env vedle {self._config_path.name}"
        )

    def _save_jobs(self, jobs: list) -> None:
        try:
            write_jobs(self._scheduler_path, jobs)
        except OSError as exc:
            self._show_error("Plánovač", str(exc))
            return
        if not self._save_scheduler_service_config():
            return
        self.admin_page.scheduler_page.mark_saved()
        service_note = self._auto_setup_scheduler_service(len(jobs))
        self.set_status(
            f"Plánovač uložen · {len(jobs)} úloh",
            f"{self._scheduler_path} · {service_note}",
        )
        self.admin_page.advanced_page.set_context(
            self._config_path, database_parameters(self._raw)
        )
        self._refresh_user_overview()
        self._refresh_scheduler_runtime()
        self._refresh_scheduler_service()

    def _auto_setup_scheduler_service(self, job_count: int) -> str:
        service_name, nssm_path = self._service_inputs()
        status = read_service_status(service_name or DEFAULT_SERVICE_NAME)
        if job_count <= 0:
            return "Bez úloh: služba se nespouští."
        try:
            if not status.installed:
                note = install_service(
                    self._config_path,
                    service_name=service_name or DEFAULT_SERVICE_NAME,
                    nssm_path=nssm_path,
                )
                return f"Auto NSSM: {note}"
            note = restart_service(
                service_name=service_name or DEFAULT_SERVICE_NAME,
                nssm_path=nssm_path,
            )
            return f"Auto NSSM: {note}"
        except (FileNotFoundError, RuntimeError) as exc:
            return f"Auto NSSM: {exc}"

    def _refresh_scheduler_runtime(self) -> None:
        service_name, _nssm = self._service_inputs()
        snapshot = read_runtime_snapshot(
            self._config_path,
            service_name or DEFAULT_SERVICE_NAME,
            probe_service=False,
        )
        cached = self._runtime_snapshot
        service_running = bool(getattr(cached, "service_running", False))
        service_installed = bool(getattr(cached, "service_installed", False))
        service_account = str(getattr(cached, "service_account", "—"))
        service_name_text = str(
            getattr(cached, "service_name", service_name or DEFAULT_SERVICE_NAME)
        )
        running = bool(snapshot.running or service_running)
        runtime_type = "NSSM service" if service_running else snapshot.runtime_type
        next_run = snapshot.next_run if running else "—"
        detail = (
            f"{runtime_type} · heartbeat: {snapshot.last_heartbeat} · "
            f"poslední běh: {snapshot.last_run} · {snapshot.last_result} · "
            f"další: {next_run}"
        )
        if snapshot.last_error != "—":
            detail = f"{detail} · chyba: {snapshot.last_error}"
        self.admin_page.scheduler_page.set_runtime_status(
            detail,
            running=running,
        )
        service_text = ""
        if service_installed:
            state = "běží" if service_running else "nainstalovaná, ale zastavená"
            service_text = (
                f"{service_name_text}: {state} · účet: {service_account}"
            )
        self.admin_page.scheduler_page.set_service_status(
            service_text,
            running=service_running,
            installed=service_installed,
        )

    def _service_inputs(self) -> tuple[str, str]:
        page = self.admin_page.scheduler_page
        return page.service_name(), page.nssm_path()

    def _save_scheduler_service_config(self) -> bool:
        service_name, nssm_path = self._service_inputs()
        updated = apply_service_config(
            self._raw,
            service_name=service_name,
            nssm_path=nssm_path,
        )
        return self._write_config(updated, "Plánovač")

    def _refresh_scheduler_service(self) -> None:
        service_name, _nssm = self._service_inputs()
        snapshot = read_runtime_snapshot(
            self._config_path,
            service_name or DEFAULT_SERVICE_NAME,
            probe_service=True,
        )
        self._runtime_snapshot = snapshot
        text = ""
        if snapshot.service_installed:
            state = "běží" if snapshot.service_running else "nainstalovaná, ale zastavená"
            text = (
                f"{snapshot.service_name}: {state} · účet: {snapshot.service_account} · "
                f"credentials: {'OK' if snapshot.credential_ok else 'NEOK'}"
            )
            if snapshot.credential_detail:
                text = f"{text} · {snapshot.credential_detail}"
        self.admin_page.scheduler_page.set_runtime_status(
            f"{snapshot.runtime_type} · poslední běh: {snapshot.last_run} · "
            f"{snapshot.last_result} · další: {snapshot.next_run}"
            + (f" · chyba: {snapshot.last_error}" if snapshot.last_error != "—" else ""),
            running=snapshot.running,
        )
        self.admin_page.scheduler_page.set_service_status(
            text,
            running=snapshot.service_running,
            installed=snapshot.service_installed,
        )

    def _start_scheduler_runtime(self) -> None:
        self._save_scheduler_service_config()
        note = start_runtime(self._config_path)
        self.set_status(note)
        QTimer.singleShot(700, self._refresh_scheduler_runtime)
        QTimer.singleShot(700, self._refresh_scheduler_service)

    def _stop_scheduler_runtime(self) -> None:
        note = stop_runtime(self._config_path)
        self.set_status(note)
        self._refresh_scheduler_runtime()

    def _restart_scheduler_runtime(self) -> None:
        self._save_scheduler_service_config()
        stop_note = stop_runtime(self._config_path)
        start_note = start_runtime(self._config_path)
        self.set_status(f"{stop_note} {start_note}".strip())
        QTimer.singleShot(700, self._refresh_scheduler_runtime)
        QTimer.singleShot(700, self._refresh_scheduler_service)

    def _open_scheduler_log(self) -> None:
        status = read_runtime_status(self._config_path)
        self._open_folder(status.log_path)

    def _install_scheduler_service(self) -> None:
        if not self._save_scheduler_service_config():
            return
        service_name, nssm_path = self._service_inputs()
        try:
            note = install_service(
                self._config_path,
                service_name=service_name or DEFAULT_SERVICE_NAME,
                nssm_path=nssm_path,
            )
        except (FileNotFoundError, RuntimeError) as exc:
            self._show_error("NSSM služba", str(exc))
            return
        self.set_status(note)
        self._refresh_scheduler_service()
        self._refresh_scheduler_runtime()

    def _remove_scheduler_service(self) -> None:
        if not self._save_scheduler_service_config():
            return
        service_name, nssm_path = self._service_inputs()
        try:
            note = remove_service(
                service_name=service_name or DEFAULT_SERVICE_NAME,
                nssm_path=nssm_path,
            )
        except (FileNotFoundError, RuntimeError) as exc:
            self._show_error("NSSM služba", str(exc))
            return
        self.set_status(note)
        self._refresh_scheduler_service()
        self._refresh_scheduler_runtime()

    def _restart_scheduler_service(self) -> None:
        if not self._save_scheduler_service_config():
            return
        service_name, nssm_path = self._service_inputs()
        try:
            note = restart_service(
                service_name=service_name or DEFAULT_SERVICE_NAME,
                nssm_path=nssm_path,
            )
        except (FileNotFoundError, RuntimeError) as exc:
            self._show_error("NSSM služba", str(exc))
            return
        self.set_status(note)
        self._refresh_scheduler_service()
        self._refresh_scheduler_runtime()

    def _run_scheduler_job_now(self, job: PlannedJob) -> None:
        self._set_busy(True)
        self.set_status(f"Spouštím úlohu „{job.name}“…")
        self._runner.run(
            run_job_now,
            job,
            config_directory=self._config_path.parent,
            on_success=lambda result: self._scheduler_job_finished(job, result),
            on_error=lambda message, _exc: self._scheduler_job_failed(job, message),
        )

    def _scheduler_job_finished(self, job: PlannedJob, result: tuple[int, str]) -> None:
        self._set_busy(False)
        code, detail = result
        if code == 0:
            self.set_status(f"Úloha „{job.name}“ dokončena.", detail)
            return
        self._show_error(
            "Plánovač",
            f"Úloha „{job.name}“ skončila chybou (kód {code}).\n\n{detail or 'Bez detailu.'}",
        )

    def _scheduler_job_failed(self, job: PlannedJob, message: str) -> None:
        self._set_busy(False)
        self._show_error("Plánovač", f"Spuštění úlohy „{job.name}“ selhalo: {message}")

    def _copy_to_clipboard(self, text: str) -> None:
        QApplication.clipboard().setText(text)
        self.set_status("Příkaz zkopírován do schránky.", text)

    def _open_folder(self, path: Path) -> None:
        target = path if path.is_dir() else path.parent
        if not target.exists():
            self.set_status("Složka zatím neexistuje.", str(target))
            return
        try:
            open_document(target)
        except OSError as exc:
            self.set_status("Složku se nepodařilo otevřít", str(exc))

    def _persist_ui_only(self) -> None:
        self._raw = apply_ui_settings(self._raw, self._ui)
        try:
            save_raw_config(self._config_path, self._raw)
        except OSError as exc:  # pragma: no cover - selhání disku
            self.set_status(f"Nastavení vzhledu se nepodařilo uložit: {exc}")

    # ------------------------------------------------------------------
    # Vzhled
    # ------------------------------------------------------------------
    def _change_theme(self, theme: str) -> None:
        if theme == self._ui.theme:
            return
        self._ui = self._ui.with_theme(theme)
        self._rebuild_ui()
        self.set_status(f"Motiv: {THEME_LABELS.get(self._ui.theme, theme)}")

    def _change_scale(self, scale: float) -> None:
        updated = self._ui.with_scale(scale)
        if abs(updated.ui_scale - self._ui.ui_scale) < 0.001:
            return
        self._ui = updated
        self._rebuild_ui()
        self.set_status(f"Velikost rozhraní: {scale_label(self._ui.ui_scale)}")

    def _change_font_bold_mode(self, mode: str) -> None:
        updated = self._ui.with_font_bold_mode(mode)
        if updated.font_bold_mode == self._ui.font_bold_mode:
            return
        self._ui = updated
        self._rebuild_ui()
        self.set_status(f"Písmo: {FONT_BOLD_LABELS[self._ui.font_bold_mode]}")

    def _change_custom_palette_enabled(self, enabled: bool) -> None:
        updated = self._ui.with_custom_palette(enabled, self._ui.custom_palette)
        if updated.custom_palette_enabled == self._ui.custom_palette_enabled:
            return
        self._ui = updated
        self._rebuild_ui()
        self.set_status(
            "Vlastní barevné schéma zapnuto"
            if self._ui.custom_palette_enabled
            else "Vlastní barevné schéma vypnuto"
        )

    def _change_custom_palette(self, colors: dict[str, str]) -> None:
        updated = self._ui.with_custom_palette(
            self._ui.custom_palette_enabled, colors
        )
        if updated.custom_palette == self._ui.custom_palette:
            return
        self._ui = updated
        self._rebuild_ui()
        self.set_status("Vlastní barevné schéma upraveno")

    def _zoom(self, step: int) -> None:
        self._change_scale(self._ui.zoomed(step).ui_scale)

    def _rebuild_ui(self) -> None:
        """Postaví rozhraní znovu; ikony i tečky se obarví novou paletou."""
        current_page = self._current_page_key() or self.sidebar.current_key() or PAGE_DAILY
        admin_section = self.admin_page.current_section() or SECTION_DATABASE
        if not self._persist(silent=True):
            self._raw = apply_ui_settings(self._raw, self._ui)
        self._metrics = metrics_for(self._ui.ui_scale)
        self._palette = palette_for(
            self._ui.theme,
            custom_palette_enabled=self._ui.custom_palette_enabled,
            custom_palette=self._ui.custom_palette,
        )
        apply_theme(
            QApplication.instance(),
            self._ui.theme,
            self._ui.ui_scale,
            font_bold_mode=self._ui.font_bold_mode,
            custom_palette_enabled=self._ui.custom_palette_enabled,
            custom_palette=self._ui.custom_palette,
        )
        self._build_ui()
        self._build_menu()
        self._apply_connection_to_view()
        nav_keys = {item.key for item in NAV_ITEMS}
        if current_page in nav_keys:
            self.sidebar.select(current_page)
        else:
            self._activate_page(current_page)
            self.sidebar.clearSelection()
        self.admin_page.show_section(admin_section)
        self._fit_to_screen()
        self._persist_ui_only()

    def _sync_appearance_pages(self) -> None:
        args = dict(
            font_bold_mode=self._ui.font_bold_mode,
            custom_palette_enabled=self._ui.custom_palette_enabled,
            custom_palette=self._ui.custom_palette,
        )
        self.admin_page.appearance_page.set_values(
            self._ui.theme, self._ui.ui_scale, **args
        )

    def _refresh_user_overview(self) -> None:
        try:
            overview = load_automail_overview(self._config_path)
        except Exception as exc:
            self.set_status("Přehled automailu se nepodařilo načíst", str(exc))
            return
        self.user_page.set_overview(overview)

    def _retry_automail(self) -> None:
        overview = load_automail_overview(self._config_path)
        if not overview.configured:
            self.set_status(
                "Automatické odesílání není nastavené.",
                "Vytvořte úlohu Denní stav v Administraci -> Plánovač.",
            )
            return
        self._set_busy(True)
        self.user_page.set_overview_busy(True)
        self.set_status("Odesílám denní mail znovu…")
        self._runner.run(
            retry_daily_mail,
            self._config_path,
            on_success=self._retry_automail_done,
            on_error=lambda message, _exc: self._retry_automail_failed(message),
        )

    def _retry_automail_done(self, result: RetryResult) -> None:
        self._set_busy(False)
        self.user_page.set_overview_busy(False)
        self._refresh_user_overview()
        if result.success:
            self.set_status(result.message)
            return
        self.set_status("Ruční odeslání neproběhlo", result.message)

    def _retry_automail_failed(self, message: str) -> None:
        self._set_busy(False)
        self.user_page.set_overview_busy(False)
        self._refresh_user_overview()
        self.set_status("Ruční odeslání selhalo", message)

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            f"O aplikaci {APP_TITLE}",
            ABOUT_TEXT.format(
                title=APP_TITLE, version=APP_VERSION, credit=APP_CREDIT
            ),
        )

    def _show_help(self) -> None:
        text = (
            "<h3>MailPilot v12.8 · nápověda</h3>"
            "<p><b>Běžný uživatel</b> používá stránky Denní stav, Uzávěrka, "
            "Speciál, Hromadná zpráva a Přehled.</p>"
            "<p><b>Administrace</b> je chráněná heslem. Vstup: "
            "<i>tlačítko Administrace</i> v horní liště. Zamknutí: "
            "<i>tlačítko Uzamknout</i>.</p>"
            "<h4>První spuštění</h4>"
            "<ol>"
            "<li>V Administraci vyplňte Databázi a spusťte test připojení.</li>"
            "<li>Nastavte E-maily (odesílatel, příjemci, texty).</li>"
            "<li>Zkontrolujte Plánovač automatických úloh a runtime stav.</li>"
            "</ol>"
            "<h4>Základní ovládání</h4>"
            "<ul>"
            "<li>Ctrl + / Ctrl - změní velikost UI, Ctrl 0 vrátí 100 %.</li>"
            "<li>Denní stav: zvolte datum, kategorie, vytvořte PDF nebo odešlete e-mail.</li>"
            "<li>Vzhled měníte v Administraci -> Vzhled (motiv, velikost, písmo, barvy).</li>"
            "<li>JídelnaSQL warning: v Administraci -> Pokročilé jsou test tlačítka "
            "Show / Show sample error / Clear pro ruční ověření.</li>"
            "</ul>"
            "<p>Tip: když se něco nevejde na monitor, snižte velikost UI v menu "
            "Zobrazení nebo v Administraci -> Vzhled.</p>"
            "<p><b>Pravidlo warningu:</b> zobrazí se při chybě automatického exportu, "
            "nezobrazí se při SKIP (např. ne-varný den), a po úspěšném automatickém "
            "odeslání se z dashboardu odstraní.</p>"
        )
        QMessageBox.information(self, "Návod a nastavení", text)

    def _refresh_admin_lock_state(self) -> None:
        action = getattr(self, "_lock_admin_action", None)
        if action is not None:
            action.setEnabled(self._admin_unlocked)
        self.header.set_admin_unlocked(self._admin_unlocked)
        timer = getattr(self, "_admin_idle_timer", None)
        if timer is not None:
            if self._admin_unlocked:
                timer.start()
            else:
                timer.stop()

    def _lock_admin(self) -> None:
        if not self._admin_unlocked:
            return
        self._admin_unlocked = False
        self._refresh_admin_lock_state()
        if self._current_page_key() == PAGE_ADMIN:
            self._open_overview_page()
        self.set_status("Administrace byla uzamčena")

    def _auto_lock_admin_idle(self) -> None:
        if not self._admin_unlocked:
            return
        self._lock_admin()
        self.set_status("Administrace uzamčena po 60 s nečinnosti")

    def _unlock_admin_interactive(self) -> bool:
        try:
            stored = (get_admin_password() or "").strip()
        except CredentialStoreError as exc:
            self._show_error("Administrace", str(exc))
            return False
        if not stored:
            first, ok = QInputDialog.getText(
                self,
                "Nastavit heslo administrátora",
                "Zadejte nové heslo administrátora:",
                QLineEdit.Password,
            )
            if not ok:
                return False
            second, ok = QInputDialog.getText(
                self,
                "Nastavit heslo administrátora",
                "Zopakujte heslo:",
                QLineEdit.Password,
            )
            if not ok:
                return False
            if first.strip() != second.strip():
                self._show_error("Administrace", "Hesla se neshodují.")
                return False
            try:
                set_admin_password(first.strip())
            except CredentialStoreError as exc:
                self._show_error("Administrace", str(exc))
                return False
            stored = first.strip()
        entered, ok = QInputDialog.getText(
            self,
            "Administrace",
            "Zadejte heslo administrátora:",
            QLineEdit.Password,
        )
        if not ok:
            return False
        if entered.strip() != stored:
            self._show_error("Administrace", "Nesprávné heslo.")
            return False
        self._admin_unlocked = True
        self._refresh_admin_lock_state()
        self.set_status("Administrace odemčena")
        return True

    def eventFilter(self, watched, event):  # noqa: N802, ANN001
        if event is None:
            return super().eventFilter(watched, event)
        event_type = event.type()
        if watched is self and event_type == QEvent.WindowActivate:
            self._sync_warning_state_from_file(silent=True)
            if self._current_page_key() == PAGE_USER:
                self._refresh_user_overview()
        if self._admin_unlocked:
            tracked = {
                QEvent.MouseButtonPress,
                QEvent.MouseButtonDblClick,
                QEvent.KeyPress,
                QEvent.Wheel,
                QEvent.TouchBegin,
            }
            if event_type in tracked:
                self._admin_idle_timer.start()
        return super().eventFilter(watched, event)

    # ------------------------------------------------------------------
    # Databáze
    # ------------------------------------------------------------------
    def _auto_connect(self) -> None:
        """Při startu se pokusí použít heslo ze systémového trezoru."""
        database = database_parameters(self._raw)
        try:
            password = stored_password(database)
        except CredentialStoreError as exc:
            self.header.set_state(
                STATE_ERROR, "DB nepřipojeno - nastav zde", str(exc)
            )
            self.header.set_setup_hint_enabled(True)
            self.set_status("Připraveno · heslo k databázi není dostupné")
            return
        if not password:
            self.header.set_state(
                STATE_ERROR,
                "DB nepřipojeno - nastav zde",
                "Uložte heslo v Administraci → Databáze a spusťte test.",
            )
            self.header.set_setup_hint_enabled(True)
            self.set_status("Připraveno · databáze není připojena")
            return
        self._start_connection(database, password, silent=True)

    def _test_connection(self, values: dict[str, Any], password: str) -> None:
        try:
            database = normalize_database(values)
        except ConfigError as exc:
            self.admin_page.database_page.set_status(str(exc), error=True)
            return
        if not password:
            try:
                password = stored_password(database)
            except CredentialStoreError as exc:
                self.admin_page.database_page.set_status(str(exc), error=True)
                return
        if not password:
            self.admin_page.database_page.set_status(
                "Vyplňte heslo k databázi.", error=True
            )
            return
        self._start_connection(database, password, silent=False)

    def _start_connection(
        self, database: dict[str, Any], password: str, *, silent: bool
    ) -> None:
        self._set_busy(True)
        self.header.set_state(STATE_IDLE, "Testuji…", "Probíhá test připojení.")
        self.set_status("Testuji připojení k databázi…")
        if not silent:
            self.admin_page.database_page.set_busy(True)
        self._runner.run(
            probe_connection,
            database,
            password,
            on_success=lambda info: self._connection_ok(info, silent=silent),
            on_error=lambda message, _exc: self._connection_failed(
                message, silent=silent
            ),
        )

    def _connection_ok(self, info: ConnectionInfo, *, silent: bool) -> None:
        self._set_busy(False)
        self._connection = info
        self._raw = dict(self._raw, databaze=dict(info.database))
        self._db_options = tuple(info.categories)
        resolution = reconcile_categories(
            self.daily_page.selected_categories(),
            [code for code, _name in info.categories],
        )
        self.daily_page.set_selected_categories(resolution.selected)
        self.special_page.set_category_options(self._db_options)
        self.admin_page.advanced_page.set_category_options(self._db_options)
        self.admin_page.database_page.set_busy(False)
        self.admin_page.database_page.clear_password_field()
        self.admin_page.database_page.set_status(
            f"Připojeno · {info.name}",
            f"{info.details} · {len(info.categories)} kategorií · "
            f"Cenový režim: {info.pricing_mode_text}",
        )
        self._apply_connection_to_view()
        self._persist(silent=True)
        message = f"Připojeno · {info.name}"
        note = resolution.status_note(len(info.categories))
        note_parts = [part for part in (note, f"Cenový režim: {info.pricing_mode_text}") if part]
        if note:
            message += " · výběr kategorií upraven podle databáze"
        self.set_status(message, " · ".join(note_parts))
        self._load_bulk_data()

    def _connection_failed(self, message: str, *, silent: bool) -> None:
        self._set_busy(False)
        self._connection = None
        self.header.set_state(STATE_ERROR, "DB nepřipojeno - nastav zde", message)
        self.header.set_setup_hint_enabled(True)
        self.header.set_connection_meta("", "")
        self.admin_page.database_page.set_busy(False)
        self.admin_page.database_page.set_status(
            "Připojení selhalo.", message, error=True
        )
        self.set_status("Připojení k databázi se nepodařilo")
        self._refresh_actions()
        if not silent:
            self.admin_page.show_section(SECTION_DATABASE)

    def _apply_connection_to_view(self) -> None:
        info = self._connection
        if info is None:
            self.header.set_state(
                STATE_ERROR,
                "DB nepřipojeno - nastav zde",
                "Připojení nebylo ověřeno. Klikněte sem pro nastavení databáze.",
            )
            self.header.set_setup_hint_enabled(True)
            self.header.set_connection_meta("", "")
            self._refresh_actions()
            return
        host = str(info.database.get("host", "")).strip()
        port = info.database.get("port", "")
        detail_parts = [info.details]
        if host:
            detail_parts.append(f"{host}:{port}")
        detail = " · ".join(part for part in detail_parts if part)
        meta_parts = [info.database_name]
        if info.period_label:
            meta_parts.append(info.period_label)
        meta_parts.append(f"Cenový režim: {info.pricing_mode_text}")
        self.header.set_state(STATE_OK, "Připojeno", detail)
        self.header.set_setup_hint_enabled(False)
        self.header.set_connection_meta(
            info.name, " · ".join(part for part in meta_parts if part), detail
        )
        self.daily_page.set_category_options(self._db_options)
        self.special_page.set_category_options(self._db_options)
        self._refresh_actions()

    # ------------------------------------------------------------------
    # Denní stav
    # ------------------------------------------------------------------
    def _create_pdf(self) -> None:
        if not self._persist(silent=False):
            return
        self._set_busy(True)
        self.set_status("Načítám data a vytvářím PDF…")
        self._runner.run(
            create_daily_pdf,
            self._config_path,
            on_success=self._pdf_created,
            on_error=lambda message, _exc: self._operation_failed(
                "Vytvoření PDF", message
            ),
        )

    def _pdf_created(self, result: DailyResult) -> None:
        self._set_busy(False)
        self._last_pdf = Path(result.pdf_path)
        self.daily_page.set_last_pdf(self._last_pdf)
        self.daily_page.set_overview(result.overview)
        self.set_status(f"PDF vytvořeno · {self._last_pdf.name}")
        self._refresh_actions()
        self._open_document(self._last_pdf)

    def _load_overview(self) -> None:
        if not self._persist(silent=False):
            return
        self._set_busy(True)
        self.set_status("Načítám přehled porcí…")
        self._runner.run(
            fetch_daily_overview,
            self._config_path,
            on_success=self._overview_loaded,
            on_error=lambda message, _exc: self._overview_failed(message),
        )

    def _overview_loaded(self, overview: DailyOverview) -> None:
        self._set_busy(False)
        self.daily_page.set_overview(overview)
        self.set_status(
            f"Přehled načten · {overview.total_portions} porcí"
        )

    def _overview_failed(self, message: str) -> None:
        self._set_busy(False)
        self.daily_page.clear_overview("Přehled se nepodařilo načíst", message)
        self.set_status("Přehled se nepodařilo načíst")

    def _send_mail(self) -> None:
        mail = peek_daily_mail(self._raw)
        if not mail.recipients:
            self._show_error(
                "Odeslání e-mailu",
                "Nejsou vyplnění příjemci pro funkci Denní stav.",
            )
            return
        try:
            api_key = get_resend_api_key() or ""
        except EnvStoreError as exc:
            self._show_error("Odeslání e-mailu", str(exc))
            return
        if not api_key:
            self._show_error(
                "Odeslání e-mailu",
                "Chybí Resend API klíč v souboru .env vedle aplikace.",
            )
            return
        if not self._persist(silent=False):
            return
        question = (
            f"Odeslat denní sestavu {len(mail.recipients)} příjemcům?\n\n"
            + "\n".join(mail.recipients)
        )
        if QMessageBox.question(
            self,
            "Odeslání e-mailu",
            question,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        ) != QMessageBox.Yes:
            self.set_status("Odeslání zrušeno.")
            return
        self._set_busy(True)
        self.set_status("Vytvářím PDF a odesílám e-mail…")
        self._runner.run(
            send_daily_pdf,
            self._config_path,
            recipients=mail.recipients,
            api_key=api_key,
            sender=mail.sender,
            body=mail.body,
            only_cooking_days=mail.only_cooking_days,
            on_success=self._mail_sent,
            on_error=lambda message, _exc: self._operation_failed(
                "Odeslání e-mailu", message
            ),
        )

    def _mail_sent(self, result: DailyDispatch) -> None:
        self._set_busy(False)
        if result.skipped:
            self._last_mail_note = f"neodesláno · {result.message}"
            self._last_mail_state = ""
            self.daily_page.set_last_mail(
                self._last_mail_note, self._last_mail_state
            )
            self.set_status("E-mail nebyl odeslán")
            return
        if result.pdf_path is not None:
            self._last_pdf = Path(result.pdf_path)
            self.daily_page.set_last_pdf(self._last_pdf)
        count = len(result.dispatch.recipients) if result.dispatch else 0
        stamp = describe_moment(datetime.now())
        self._last_mail_note = (
            f"odesláno {stamp} · {recipients_phrase(count)}"
        )
        self._last_mail_state = "statusOk"
        self.daily_page.set_last_mail(self._last_mail_note, self._last_mail_state)
        self.set_status(f"E-mail odeslán · {recipients_phrase(count)}")
        self._refresh_actions()

    def _open_last_pdf(self) -> None:
        if self._last_pdf is None or not self._last_pdf.is_file():
            self.set_status("Poslední PDF není k dispozici.")
            return
        self._open_document(self._last_pdf)

    # ------------------------------------------------------------------
    # Uzávěrka
    # ------------------------------------------------------------------
    def _closing_changed(self) -> None:
        self._refresh_closing_output()
        self._schedule_admin_save("closing")

    def _save_closing_settings(self) -> None:
        try:
            updated = apply_closing_form(self._raw, self.closing_page.form())
        except ConfigError as exc:
            self.set_status("Nastavení uzávěrky se neuložilo", str(exc))
            return
        if not self._write_config(updated, "Nastavení uzávěrky"):
            return
        self.set_status("Nastavení uzávěrky uloženo.")

    def _closing_directory(self) -> Path | None:
        form = self.closing_page.form()
        try:
            return resolve_closing_output(
                form.output,
                year=form.year,
                month=form.month,
                config_directory=self._config_path.parent,
            )
        except ConfigError:
            return None

    def _refresh_closing_output(self) -> None:
        form = self.closing_page.form()
        directory = self._closing_directory()
        if directory is None:
            self.closing_page.set_resolved_output(
                "Cesta smí používat jen zástupné hodnoty {rok} a {mesic}."
            )
            self.closing_page.set_last_output(None)
            return
        if form.use_current_period:
            self.closing_page.set_resolved_output(
                f"Složka podle období z Jídelny, například {directory}"
            )
        else:
            self.closing_page.set_resolved_output(f"Uloží se do {directory}")
        files = existing_outputs(directory)
        if files:
            newest = files[0]
            stamp = describe_moment(
                datetime.fromtimestamp(newest.stat().st_mtime)
            )
            self.closing_page.set_last_output(
                newest, f"{newest.name} · {stamp}"
            )
        else:
            self.closing_page.set_last_output(None)

    def _run_closing(self) -> None:
        form = self.closing_page.form()
        if not form.reports:
            self._show_error(
                "Uzávěrka", "Vyberte alespoň jednu tiskovou sestavu."
            )
            return
        try:
            updated = apply_closing_form(self._raw, form)
        except ConfigError as exc:
            self._show_error("Uzávěrka", str(exc))
            return
        if not self._write_config(updated, "Nastavení uzávěrky"):
            return
        if form.send_mail and not peek_closing_form(self._raw).recipients:
            self._show_error(
                "Uzávěrka",
                "Uzávěrka se má odeslat e-mailem, ale nejsou vyplnění "
                "příjemci. Doplňte je v Administraci → E-maily → Uzávěrka.",
            )
            return
        period = (
            "aktuální měsíc z Jídelny"
            if form.use_current_period
            else form.period_label
        )
        question = (
            f"Vytvořit uzávěrku za {period}?\n\n"
            f"Sestavy: {len(form.reports)}\n"
            + ("Po vytvoření se odešle e-mailem." if form.send_mail else "")
        )
        if QMessageBox.question(
            self,
            "Uzávěrka",
            question.strip(),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        ) != QMessageBox.Yes:
            self.set_status("Uzávěrka zrušena.")
            return
        self._set_busy(True)
        self.closing_page.set_busy(True)
        self.closing_page.set_progress(0, "Spouštím měsíční uzávěrku…")
        self.set_status(f"Vytvářím uzávěrku · {period}")
        self._runner.run(
            run_closing,
            self._config_path,
            year=None if form.use_current_period else form.year,
            month=None if form.use_current_period else form.month,
            current_month=form.use_current_period,
            on_success=self._closing_done,
            on_error=lambda message, _exc: self._closing_failed(message),
            on_progress=self.closing_page.set_progress,
        )

    def _closing_done(self, result: ClosingRun) -> None:
        self._set_busy(False)
        self.closing_page.set_busy(False)
        summary = result.summary()
        self.closing_page.set_result(f"Hotovo · {summary}. {result.detail}".strip())
        newest = result.zip_file or (result.files[0] if result.files else None)
        if newest is not None:
            self.closing_page.set_last_output(newest, newest.name)
        self.set_status(f"Uzávěrka hotová · {summary}", result.detail)
        self._refresh_actions()

    def _closing_failed(self, message: str) -> None:
        self._set_busy(False)
        self.closing_page.set_busy(False)
        self.closing_page.set_result(
            f"Uzávěrka selhala: {message}", state="statusError"
        )
        self.set_status("Uzávěrka selhala", message)
        self._show_error("Uzávěrka", message)

    def _open_closing_folder(self) -> None:
        directory = self._closing_directory()
        if directory is None:
            self.set_status("Cesta uzávěrky není platná.")
            return
        self._open_folder(directory)

    # ------------------------------------------------------------------
    # Speciál · Z 17-01
    # ------------------------------------------------------------------
    def _special_changed(self) -> None:
        self._refresh_special_output()
        self._schedule_admin_save("special")

    def _save_special_settings(self) -> None:
        try:
            updated = apply_special_form(self._raw, self.special_page.form())
        except ConfigError as exc:
            self.set_status("Nastavení Z 17-01 se neuložilo", str(exc))
            return
        if not self._write_config(updated, "Nastavení Z 17-01"):
            return
        self.set_status("Nastavení Z 17-01 uloženo.")

    def _special_directory(self) -> Path | None:
        form = self.special_page.form()
        try:
            return resolve_special_output(
                form.output,
                year=form.year,
                config_directory=self._config_path.parent,
            )
        except ConfigError:
            return None

    def _refresh_special_output(self) -> None:
        form = self.special_page.form()
        directory = self._special_directory()
        if directory is None:
            self.special_page.set_resolved_output(
                "Cesta smí používat jen zástupnou hodnotu {rok}."
            )
            self.special_page.set_last_pdf(None)
            return
        self.special_page.set_resolved_output(f"Uloží se do {directory}")
        self.special_page.set_last_pdf(existing_pdf(directory, form.year))

    def _run_special(self) -> None:
        form = self.special_page.form()
        try:
            validate_special_form(form)
            updated = apply_special_form(self._raw, form)
        except ConfigError as exc:
            self._show_error("Z 17-01", str(exc))
            return
        if not self._write_config(updated, "Nastavení Z 17-01"):
            return
        self._set_busy(True)
        self.special_page.set_busy(True)
        self.special_page.set_progress(0, "Spouštím podklad Z 17-01…")
        self.set_status(f"Vytvářím podklad Z 17-01 za rok {form.year}")
        self._runner.run(
            run_special,
            self._config_path,
            year=form.year,
            on_success=self._special_done,
            on_error=lambda message, _exc: self._special_failed(message),
            on_progress=self.special_page.set_progress,
        )

    def _special_done(self, result: SpecialRun) -> None:
        self._set_busy(False)
        self.special_page.set_busy(False)
        self.special_page.set_result(f"Hotovo · {result.detail}")
        path = result.pdf_path
        if path is not None:
            self.special_page.set_last_pdf(path)
            self.set_status(f"Podklad Z 17-01 vytvořen · {path.name}")
            self._open_document(path)
        else:
            self.set_status("Podklad Z 17-01 vytvořen.")
        self._refresh_actions()

    def _special_failed(self, message: str) -> None:
        self._set_busy(False)
        self.special_page.set_busy(False)
        self.special_page.set_result(
            f"Podklad se nepodařilo vytvořit: {message}", state="statusError"
        )
        self.set_status("Z 17-01 selhal", message)
        self._show_error("Z 17-01", message)

    def _open_special_folder(self) -> None:
        directory = self._special_directory()
        if directory is None:
            self.set_status("Cesta podkladu není platná.")
            return
        self._open_folder(directory)

    # ------------------------------------------------------------------
    # Hromadná zpráva
    # ------------------------------------------------------------------
    def _save_bulk_settings(self) -> None:
        updated = apply_bulk_form(self._raw, self.bulk_page.form())
        if not self._write_config(updated, "Hromadná zpráva"):
            return
        self.set_status("Text hromadné zprávy uložen.")

    def _load_bulk_data(self) -> None:
        info = self._connection
        if info is None:
            self.bulk_page.set_status(
                "Nejprve ověřte připojení k databázi.", state="statusError"
            )
            return
        database = dict(info.database)
        try:
            password = stored_password(database)
        except CredentialStoreError as exc:
            self.bulk_page.set_status(str(exc), state="statusError")
            return
        self.bulk_page.set_status("Načítám strávníky z databáze…")
        self._runner.run(
            load_bulk_data,
            database,
            password,
            on_success=self._bulk_data_loaded,
            on_error=lambda message, _exc: self.bulk_page.set_status(
                f"Strávníky se nepodařilo načíst: {message}", state="statusError"
            ),
        )

    def _bulk_data_loaded(self, data: BulkData) -> None:
        self._bulk_data = data
        self._apply_bulk_data()
        self.bulk_page.set_status(
            f"Načteno {len(data.diners)} strávníků · {len(data.classes)} tříd "
            f"· {len(data.categories)} kategorií"
        )

    def _apply_bulk_data(self) -> None:
        filter_type = self.bulk_page.filter_type()
        self.bulk_page.set_filter_options(
            filter_options(self._bulk_data, filter_type)
        )
        self._refresh_bulk_preview()

    def _refresh_bulk_preview(self) -> None:
        filter_type = self.bulk_page.filter_type()
        self.bulk_page.set_filter_options(
            filter_options(self._bulk_data, filter_type)
        )
        values = self.bulk_page.selected_values()
        if not values:
            self._bulk_preview = None
            self.bulk_page.set_recipients((), "", can_send=False)
            self._refresh_actions()
            return
        preview = preview_for(
            self._bulk_data, filter_type=filter_type, values=values
        )
        self._bulk_preview = preview
        self.bulk_page.set_recipients(
            recipient_rows(preview),
            bulk_preview_summary(preview),
            can_send=bool(preview.recipients) and not self._busy,
        )
        self._refresh_actions()

    def _send_bulk(self) -> None:
        preview = self._bulk_preview
        form = self.bulk_page.form()
        try:
            validate_message(form, preview)
        except ConfigError as exc:
            self._show_error("Hromadná zpráva", str(exc))
            return
        try:
            api_key = get_resend_api_key() or ""
        except EnvStoreError as exc:
            self._show_error("Hromadná zpráva", str(exc))
            return
        if not api_key:
            self._show_error(
                "Hromadná zpráva",
                "Chybí Resend API klíč v souboru .env vedle aplikace.",
            )
            return
        mail = peek_mail_settings(self._raw)
        sender = mail.sender.strip()
        if not sender:
            self._show_error(
                "Hromadná zpráva",
                "Doplňte odesílatele v Administraci → E-maily.",
            )
            return
        self._save_bulk_settings()
        missing = len(preview.missing) if preview is not None else 0
        question = (
            f"Odeslat zprávu {len(preview.recipients)} příjemcům?\n\n"
            f"Předmět: {form.subject}"
        )
        if missing:
            question += f"\n\n{missing} strávníků nemá e-mail, těm zpráva nedorazí."
        if QMessageBox.question(
            self,
            "Hromadná zpráva",
            question,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        ) != QMessageBox.Yes:
            self.set_status("Odeslání zrušeno.")
            return
        self._set_busy(True)
        self.bulk_page.set_busy(True)
        self.bulk_page.set_status("Odesílám hromadnou zprávu…")
        self.set_status("Odesílám hromadnou zprávu…")
        self._runner.run(
            send_bulk,
            preview,
            subject=form.subject,
            body=form.body,
            api_key=api_key,
            sender_email=sender,
            on_success=self._bulk_sent,
            on_error=lambda message, _exc: self._bulk_failed(message),
        )

    def _bulk_sent(self, result: Any) -> None:
        self._set_busy(False)
        self.bulk_page.set_busy(False)
        count = len(result.recipients)
        stamp = describe_moment(datetime.now())
        self.bulk_page.set_status(
            f"Odesláno {stamp} · {recipients_phrase(count)} · {result.detail}",
            state="statusOk",
        )
        self.set_status(f"Hromadná zpráva odeslána · {recipients_phrase(count)}")
        self._refresh_actions()

    def _bulk_failed(self, message: str) -> None:
        self._set_busy(False)
        self.bulk_page.set_busy(False)
        self.bulk_page.set_status(
            f"Odeslání selhalo: {message}", state="statusError"
        )
        self.set_status("Hromadná zpráva se neodeslala", message)
        self._show_error("Hromadná zpráva", message)

    # ------------------------------------------------------------------
    # Společné
    # ------------------------------------------------------------------
    def _open_document(self, path: Path) -> None:
        try:
            open_document(path)
        except OSError:
            self.set_status("Soubor je hotový, ale nepodařilo se otevřít")

    def _operation_failed(self, title: str, message: str) -> None:
        self._set_busy(False)
        self.set_status(f"{title} selhalo")
        self._show_error(title, message)

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)

    # ------------------------------------------------------------------
    # Okno
    # ------------------------------------------------------------------
    def _restore_state(self) -> None:
        settings = self._ui
        self.resize(settings.window_width, settings.window_height)
        if settings.window_x is not None and settings.window_y is not None:
            self.move(settings.window_x, settings.window_y)
            if not self._is_on_screen():
                self._center_on_primary()
        else:
            self._center_on_primary()
        self._fit_to_screen()
        if settings.maximized:
            self.setWindowState(self.windowState() | Qt.WindowMaximized)

    def _is_on_screen(self) -> bool:
        frame = self.frameGeometry()
        for screen in QGuiApplication.screens():
            if screen.availableGeometry().intersects(frame):
                return True
        return False

    def _fit_to_screen(self) -> None:
        """Uložená velikost může pocházet z většího monitoru nebo menšího zvětšení."""
        if self.isMaximized() or self.isFullScreen():
            return
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:  # pragma: no cover - bez displeje
            return
        available = screen.availableGeometry()
        width = min(self.width(), available.width())
        height = min(self.height(), available.height())
        if width != self.width() or height != self.height():
            self.resize(width, height)
        frame = self.frameGeometry()
        moved = QPoint(self.x(), self.y())
        if frame.right() > available.right():
            moved.setX(moved.x() - (frame.right() - available.right()))
        if frame.bottom() > available.bottom():
            moved.setY(moved.y() - (frame.bottom() - available.bottom()))
        moved.setX(max(moved.x(), available.left()))
        moved.setY(max(moved.y(), available.top()))
        if moved != QPoint(self.x(), self.y()):
            self.move(moved)

    def _center_on_primary(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:  # pragma: no cover - bez displeje
            return
        available = screen.availableGeometry()
        size = self.size()
        self.move(
            available.center().x() - size.width() // 2,
            available.center().y() - size.height() // 2,
        )

    def closeEvent(self, event) -> None:  # noqa: N802, ANN001 - Qt API
        maximized = bool(self.windowState() & Qt.WindowMaximized)
        geometry = self.normalGeometry() if maximized else self.geometry()
        self._ui = self._ui.with_geometry(
            width=geometry.width(),
            height=geometry.height(),
            x=geometry.x(),
            y=geometry.y(),
            maximized=maximized,
        )
        if not self._persist(silent=True):
            self._persist_ui_only()
        self._runner.shutdown(3000)
        super().closeEvent(event)
