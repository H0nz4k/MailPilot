"""Resend credentials are editable in settings without sending mail or running NSSM."""
import asyncio
from functools import partial
from unittest.mock import Mock, patch

import pytest
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from env_store import EnvStoreError, get_resend_api_key, set_resend_api_key
from services.web_mail_settings import load_settings, settings_path
from services.web_mail_settings_gui import build_web_settings_panel


@pytest.mark.asyncio
async def test_key_is_saved_explicitly_and_shared_with_existing_mail_editor(tmp_path):
    env = tmp_path / '.env'
    env.write_text('OTHER_SETTING=preserved\n')
    saved = Mock()
    with patch('services.web_mail_settings_gui.get_resend_api_key', partial(get_resend_api_key, path=env)), \
         patch('services.web_mail_settings_gui.set_resend_api_key', partial(set_resend_api_key, path=env)), \
         patch('services.web_mail_settings_gui.service_command') as command:
        async with user_simulation(lambda: build_web_settings_panel(tmp_path, on_api_key_saved=saved)) as user:
            await user.open('/')
            await user.should_see('API klíč zatím není nastaven.')
            with user:
                key = user.find(marker='resend-api-key').elements.pop()
                assert key.props['type'] == 'password'
                key.value = 're_test_only'
            await asyncio.sleep(.85)
            assert get_resend_api_key(env) is None
            user.find('Uložit API klíč').click()
            await user.should_see('API klíč je uložený a načtený.')
            assert get_resend_api_key(env) == 're_test_only'
            assert key.value == ''
            state = user.find(marker='resend-key-state').elements.pop()
            assert 'ds-api-key-state--positive' in state.classes
            assert user.find(marker='resend-key-icon').elements.pop().props['name'] == 'check_circle'
            saved.assert_called_once_with('re_test_only')
            assert 'OTHER_SETTING=preserved' in env.read_text()
            # A normal autosave contains preferences, never the API credential.
            with user:
                sender = next(e for e in user.client.elements.values()
                              if isinstance(e, ui.input) and e.props.get('label') == 'Zobrazované jméno odesílatele')
                sender.value = 'Jídelna'
            await asyncio.sleep(.85)
            assert load_settings(settings_path(tmp_path))['from_name'] == 'Jídelna'
            assert 're_test_only' not in settings_path(tmp_path).read_text()
            command.assert_not_called()


@pytest.mark.asyncio
async def test_existing_key_is_not_displayed_or_erased_and_locked_saves_are_rejected(tmp_path):
    env = tmp_path / '.env'
    set_resend_api_key('re_existing', env)
    access = {'valid': True}
    saved = Mock()
    with patch('services.web_mail_settings_gui.get_resend_api_key', partial(get_resend_api_key, path=env)), \
         patch('services.web_mail_settings_gui.set_resend_api_key', partial(set_resend_api_key, path=env)):
        async with user_simulation(lambda: build_web_settings_panel(
            tmp_path, require_admin=lambda: access['valid'], on_api_key_saved=saved,
        )) as user:
            await user.open('/')
            await user.should_see('API klíč je uložený a načtený.')
            with user:
                key = user.find(marker='resend-api-key').elements.pop()
                assert not key.value
            user.find('Uložit API klíč').click()
            await user.should_see('API klíč je uložený a načtený.')
            assert get_resend_api_key(env) == 're_existing'
            with user:
                key.value = 're_replacement'
                access['valid'] = False
            user.find('Uložit API klíč').click()
            await asyncio.sleep(.1)
            assert get_resend_api_key(env) == 're_existing'
            saved.assert_not_called()


@pytest.mark.asyncio
async def test_storage_error_keeps_draft_without_exposing_the_key(tmp_path):
    with patch('services.web_mail_settings_gui.get_resend_api_key', return_value=None), \
         patch('services.web_mail_settings_gui.set_resend_api_key', side_effect=EnvStoreError('re_private_value')):
        async with user_simulation(lambda: build_web_settings_panel(tmp_path)) as user:
            await user.open('/')
            with user:
                key = user.find(marker='resend-api-key').elements.pop()
                key.value = 're_private_value'
            user.find('Uložit API klíč').click()
            await user.should_see('API klíč se nepodařilo uložit.')
            status = user.find(marker='resend-key-status').elements.pop()
            assert 're_private_value' not in status.text
            assert 'ds-api-key-state--negative' in user.find(marker='resend-key-state').elements.pop().classes
            assert key.value == 're_private_value'


@pytest.mark.asyncio
async def test_reopened_settings_remain_green_without_displaying_saved_key(tmp_path):
    env = tmp_path / '.env'
    set_resend_api_key('re_saved_dummy', env)
    with patch('services.web_mail_settings_gui.get_resend_api_key', partial(get_resend_api_key, path=env)):
        async with user_simulation(lambda: build_web_settings_panel(tmp_path)) as user:
            await user.open('/')
            await user.should_see('API klíč je uložený a načtený.')
            state = user.find(marker='resend-key-state').elements.pop()
            assert 'ds-api-key-state--positive' in state.classes
            assert state.props['role'] == 'status'
            assert state.props['aria-live'] == 'polite'
            key = user.find(marker='resend-api-key').elements.pop()
            assert not key.value
            assert 're_saved_dummy' not in user.find(marker='resend-key-status').elements.pop().text
            with user:
                key.value = 're_new_dummy'
            await user.should_see('Nový API klíč ještě není uložený.')
            assert 'ds-api-key-state--warning' in state.classes
            assert 'ds-api-key-state--positive' not in state.classes
            with user:
                key.value = ''
            await user.should_see('API klíč je uložený a načtený.')
            assert 'ds-api-key-state--positive' in state.classes


@pytest.mark.asyncio
async def test_unreadable_key_is_red_on_open(tmp_path):
    with patch('services.web_mail_settings_gui.get_resend_api_key', side_effect=EnvStoreError('private detail')):
        async with user_simulation(lambda: build_web_settings_panel(tmp_path)) as user:
            await user.open('/')
            await user.should_see('Uložený API klíč se nepodařilo načíst.')
            assert 'ds-api-key-state--negative' in user.find(marker='resend-key-state').elements.pop().classes
            assert 'private detail' not in user.find(marker='resend-key-status').elements.pop().text


@pytest.mark.asyncio
@pytest.mark.parametrize('readback', [None, 're_old_dummy', EnvStoreError('private detail')])
async def test_save_is_not_green_until_same_key_can_be_read_back(tmp_path, readback):
    def read_key():
        if isinstance(readback, Exception):
            raise readback
        return readback
    saved = Mock()
    with patch('services.web_mail_settings_gui.get_resend_api_key', side_effect=read_key), \
         patch('services.web_mail_settings_gui.set_resend_api_key') as write:
        async with user_simulation(lambda: build_web_settings_panel(tmp_path, on_api_key_saved=saved)) as user:
            await user.open('/')
            with user:
                key = user.find(marker='resend-api-key').elements.pop()
                key.value = 're_new_dummy'
            user.find('Uložit API klíč').click()
            await user.should_see('jeho načtení se nepodařilo ověřit')
            assert 'ds-api-key-state--negative' in user.find(marker='resend-key-state').elements.pop().classes
            assert key.value == 're_new_dummy'
            write.assert_called_once_with('re_new_dummy')
            saved.assert_not_called()
