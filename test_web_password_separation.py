"""Admin login and database credentials use different fields and vault accounts."""
from pathlib import Path
import shutil
from unittest.mock import MagicMock, patch

import pytest
from nicegui.testing.user_simulation import user_simulation

import credential_store as vault
from stravovaci_nicegui import NiceGuiApp


def test_vault_writes_do_not_cross_admin_and_database_accounts(tmp_path):
    database = {'host': 'localhost', 'port': 5432, 'dbname': 'test', 'user': 'reader'}
    account = vault.credential_account(database)
    assert account != vault.ADMIN_ACCOUNT
    secrets = {(vault.SERVICE_NAME, vault.ADMIN_ACCOUNT): 'admin-example',
               (vault.SERVICE_NAME, account): 'database-example'}
    keyring = MagicMock()
    keyring.get_password.side_effect = lambda service, name: secrets.get((service, name))
    keyring.set_password.side_effect = lambda service, name, value: secrets.__setitem__((service, name), value)
    with patch.object(vault, '_keyring_module', return_value=(keyring, Exception)), \
         patch.object(vault, '_read_user_admin_password', return_value=None), \
         patch.object(vault, '_read_machine_password', return_value=None), \
         patch.object(vault, '_write_machine_password'), \
         patch.object(vault, '_user_admin_path', return_value=tmp_path / 'admin.dpapi'):
        assert vault.get_admin_password() == 'admin-example'
        assert vault.get_password(database) == 'database-example'
        vault.set_admin_password('new-admin-example')
        assert vault.get_password(database) == 'database-example'
        vault.set_password(database, 'new-database-example')
        assert vault.get_admin_password() == 'new-admin-example'


@pytest.mark.asyncio
async def test_database_password_does_not_unlock_admin_or_get_overwritten_by_login(tmp_path):
    config = tmp_path / 'config.json'
    shutil.copyfile(Path(__file__).with_name('config.example.json'), config)
    pages = []
    def root():
        page = NiceGuiApp(config)
        page.build()
        pages.append(page)
    with patch.object(NiceGuiApp, '_stored_password', return_value='database-example'), \
         patch.object(NiceGuiApp, '_schedule_first_run'), \
         patch('stravovaci_nicegui.get_admin_password', return_value='admin-example'), \
         patch('stravovaci_nicegui.set_admin_password') as write_admin, \
         patch('stravovaci_nicegui.set_password') as write_database:
        async with user_simulation(root) as user:
            await user.open('/')
            with user:
                page = pages[0]
                page.open_admin_dialog()
                assert page.admin_dialog_help.text == 'Zadejte heslo pro administraci.'
                assert page.admin_password_input.props['label'] == 'Heslo administrace'
                assert page.password_input.props['label'] == 'Heslo k databázi'
                assert page.admin_password_input.value == ''
                page.admin_password_input.value = 'database-example'
                page.confirm_admin()
                assert not page.admin_unlocked
                assert page.admin_dialog_error.text == 'Nesprávné heslo administrace.'
                page.admin_password_input.value = 'admin-example'
                page.confirm_admin()
                assert page.admin_unlocked
                assert page.password_input.value == 'database-example'
                assert page.admin_password_input.value == ''
            write_admin.assert_not_called()
            write_database.assert_not_called()
