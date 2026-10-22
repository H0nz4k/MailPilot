"""First connection: administrator access, then a short database dialog."""
from __future__ import annotations

from typing import Any
from nicegui import ui


def database_error_message(error: Exception) -> str:
    text = str(error).casefold()
    if 'password authentication failed' in text or 'invalid password' in text:
        return 'Databáze odmítla přihlášení. Zkontrolujte uživatele a heslo k databázi.'
    if 'does not exist' in text and 'database' in text:
        return 'Databáze s tímto názvem neexistuje. Zkontrolujte její název.'
    if any(part in text for part in ('connection refused', 'timeout', 'timed out', 'could not translate host', 'name or service not known')):
        return 'Server databáze neodpovídá. Zkontrolujte jeho adresu, port a připojení k síti.'
    return 'Připojení k Jídelně se nepodařilo ověřit. Zkontrolujte údaje a dostupnost databázového serveru.'


class FirstRunMixin:
    def _build_database_setup_dialog(self) -> None:
        self._startup_checked = False
        self._database_setup_pending = False
        self._setup_busy = False
        with ui.dialog() as self.database_setup_dialog, ui.card().classes('ds-mail-dialog'):
            ui.label('Připojení k Jídelně').classes('ds-dialog-title')
            with ui.column().classes('ds-dialog-body w-full'):
                ui.label('Vyplňte připojení k databázi. Po úspěšném ověření se otevře denní přehled.').classes('ui-help')
                ui.label('Použijte heslo k databázi Jídelny. Je jiné než heslo do nastavení DataShipu.').classes('ui-help')
                self.setup_host = ui.input('Server databáze').props('outlined dense').classes('w-full')
                self.setup_port = ui.number('Port', value=5432, min=1, max=65535, step=1).props('outlined dense').classes('w-full')
                self.setup_database = ui.input('Název databáze').props('outlined dense').classes('w-full')
                self.setup_user = ui.input('Uživatel databáze').props('outlined dense').classes('w-full')
                self.setup_password = ui.input('Heslo k databázi', password=True).props('outlined dense').classes('w-full')
                self.setup_password.on('keydown.enter', self._verify_database_setup)
                self.setup_error = ui.label('').classes('ui-help text-negative').props('role="alert"')
            with ui.row().classes('ds-dialog-footer w-full justify-end'):
                self.setup_later = ui.button('Později', on_click=self.database_setup_dialog.close).props('flat no-caps')
                self.setup_verify = ui.button('Ověřit a pokračovat', icon='cable', on_click=self._verify_database_setup).props('no-caps')

    def _schedule_first_run(self) -> None:
        if not self._startup_checked and not getattr(self, "_startup_timer", None):
            self._startup_timer = ui.timer(0.1, self._start_first_run, once=True)

    async def _start_first_run(self) -> None:
        # Reconnecting the same browser must not reopen dialogs or retest twice.
        if self._startup_checked:
            return
        self._startup_checked = True
        if self.connection_ok:
            return
        if self._admin_password_is_set() and self._stored_password():
            try:
                if await self.test_connection():
                    return
            except Exception:
                self.db_status.set_text('Uložené připojení nelze použít. Ověřte nastavení databáze a právo zápisu do složky aplikace.')
        self._database_setup_pending = True
        self._admin_target_section = 'db'
        if self.admin_unlocked:
            self._open_database_setup()
        else:
            self.open_admin_dialog()

    def _open_database_setup(self) -> None:
        if not self.admin_unlocked:
            self._database_setup_pending = True
            self.open_admin_dialog()
            return
        for target, source in ((self.setup_host, self.host_input), (self.setup_port, self.port_input),
                               (self.setup_database, self.dbname_input), (self.setup_user, self.user_input),
                               (self.setup_password, self.password_input)):
            target.value = source.value
        self.setup_error.set_text('')
        self.database_setup_dialog.open()
        self.setup_host.run_method('focus')

    async def _verify_database_setup(self, _event: Any = None) -> None:
        if self._setup_busy:
            return
        if not self.admin_unlocked:
            self.database_setup_dialog.close()
            self._database_setup_pending = True
            self.open_admin_dialog()
            return
        self._setup_busy = True
        self.setup_verify.disable()
        self.setup_later.disable()
        fields = (self.setup_host, self.setup_port, self.setup_database, self.setup_user, self.setup_password)
        for field in fields:
            field.disable()
        self.setup_error.set_text('Ověřuji připojení…')
        try:
            for source, target in ((self.setup_host, self.host_input), (self.setup_port, self.port_input),
                                   (self.setup_database, self.dbname_input), (self.setup_user, self.user_input),
                                   (self.setup_password, self.password_input)):
                target.value = source.value
            # Invalid values must not leave a previous connection marked ready.
            self.invalidate_connection()
            if not str(self.setup_password.value or '').strip():
                self.setup_error.set_text('Vyplňte heslo k databázi.')
                return
            if await self.test_connection():
                self._database_setup_pending = False
                self.database_setup_dialog.close()
                self.tabs.value = 'daily'
            else:
                self.setup_error.set_text(self.db_status.text)
        except Exception:
            self.setup_error.set_text('Nastavení se nepodařilo uložit. Ověřte údaje a právo zápisu do složky aplikace.')
        finally:
            self._setup_busy = False
            self.setup_verify.enable()
            self.setup_later.enable()
            for field in fields:
                field.enable()
