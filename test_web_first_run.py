from pathlib import Path
import json
import shutil
from unittest.mock import AsyncMock, patch

import pytest
from nicegui.testing.user_simulation import user_simulation
import stravovaci_nicegui as gui


@pytest.mark.asyncio
async def test_first_run_requests_admin_then_database_and_keeps_failed_attempt_open(tmp_path):
    config = tmp_path / 'config.json'
    shutil.copyfile(Path(__file__).with_name('config.example.json'), config)
    pages = []
    store = {'password': None}
    def root():
        page = gui.NiceGuiApp(config)
        page.build()
        pages.append(page)
    with patch.object(gui, 'get_admin_password', side_effect=lambda: store['password']), \
         patch.object(gui, 'set_admin_password', side_effect=lambda p: store.update(password=p)), \
         patch.object(gui.NiceGuiApp, '_stored_password', return_value=''), \
         patch.object(gui.NiceGuiApp, '_stored_api_key', return_value=''):
        async with user_simulation(root) as user:
            await user.open('/')
            page = pages[0]
            with user:
                await page._start_first_run()
            assert page.admin_dialog.value
            assert not page.database_setup_dialog.value
            with user:
                page.admin_password_input.value = 'spravce'
                page.admin_password_repeat.value = 'spravce'
                page.confirm_admin()
            assert page.admin_unlocked
            assert page.database_setup_dialog.value
            with user:
                page.setup_password.value = ''
                await page._verify_database_setup()
            assert 'heslo k databázi' in page.setup_error.text
            assert page.database_setup_dialog.value
            def fail_probe(*_):
                raise RuntimeError('password authentication failed')
            with patch.object(page, '_test_database', side_effect=fail_probe):
                with user:
                    page.setup_password.value = 'wrong'
                    await page._verify_database_setup()
            assert 'Databáze odmítla' in page.setup_error.text
            assert page.database_setup_dialog.value
            assert not page.connection_ok
            with patch.object(page, '_test_database', return_value=([('1', 'Žáci')], 'jidelna', 'Škola', (2026, 10))), \
                 patch.object(gui, 'fetch_bulk_filters', return_value=([], [], [])), \
                 patch.object(page, '_reload_meal_types', new=AsyncMock()):
                with user:
                    page.setup_host.value = 'db.local'
                    page.setup_password.value = 'correct'
                    await page._verify_database_setup()
            assert page.connection_ok
            assert not page.database_setup_dialog.value
            assert page.tabs.value == 'daily'
            assert json.loads(config.read_text(encoding='utf-8'))['databaze']['host'] == 'db.local'
            assert 'correct' not in config.read_text(encoding='utf-8')


@pytest.mark.asyncio
async def test_saved_connection_reconnects_without_prompting_admin_again(tmp_path):
    config = tmp_path / 'config.json'
    shutil.copyfile(Path(__file__).with_name('config.example.json'), config)
    pages = []
    def root():
        page = gui.NiceGuiApp(config)
        page.build()
        pages.append(page)
    with patch.object(gui, 'get_admin_password', return_value='admin'), \
         patch.object(gui.NiceGuiApp, '_stored_password', return_value='saved'), \
         patch.object(gui.NiceGuiApp, '_stored_api_key', return_value=''), \
         patch.object(gui.NiceGuiApp, 'test_connection', new_callable=AsyncMock, return_value=True) as probe:
        async with user_simulation(root) as user:
            await user.open('/')
            with user:
                await pages[0]._start_first_run()
                await pages[0]._start_first_run()
            assert probe.await_count == 1
            assert not pages[0].admin_dialog.value
            assert not pages[0].database_setup_dialog.value
