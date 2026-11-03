"""Preview changes stay local; scheduling receives the exact saved report."""
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from services.web_daily_profiles import DailyProfile, load_profiles, profile_file, save_profile
from services.web_mail_task_store import load_tasks, task_file
from stravovaci_nicegui import NiceGuiApp


def field(user, kind, label):
    return next(e for e in reversed(list(user.client.elements.values()))
                if isinstance(e, kind) and (e.props.get('label') or e.props.get('aria-label')) == label)


def setup_page(tmp_path, profiles=()):
    config = tmp_path / 'config.json'
    shutil.copyfile(Path(__file__).with_name('config.example.json'), config)
    for profile in profiles:
        save_profile(profile_file(tmp_path), profile)
    pages = []
    def root():
        page = NiceGuiApp(config)
        page.build()
        page.populate_categories([('1', 'Žáci'), ('2', 'Zaměstnanci'), ('3', 'Hosté')])
        pages.append(page)
    return root, pages


@pytest.mark.asyncio
async def test_preview_switch_and_restore_never_update_saved_reports(tmp_path):
    first = DailyProfile.from_dict({'name': 'Školní obědy', 'categories': ['1'], 'meal_type': 'Oběd'})
    second = DailyProfile.from_dict({'name': 'Hosté', 'categories': ['3']})
    root, pages = setup_page(tmp_path, [first, second])
    original = profile_file(tmp_path).read_bytes()
    config_before = (tmp_path / 'config.json').read_bytes()
    with patch.object(NiceGuiApp, '_stored_password', return_value=''), \
         patch.object(NiceGuiApp, '_stored_api_key', return_value=''), \
         patch.object(NiceGuiApp, '_schedule_first_run'), \
         patch.object(NiceGuiApp, '_send_mail_worker') as send:
        async with user_simulation(root) as user:
            await user.open('/')
            with user:
                page = pages[0]
                page._apply_daily_categories(['1', '2'])
                assert page.daily_profile_status.text == 'Náhled změn'
                assert page.daily_update_button.enabled
                assert profile_file(tmp_path).read_bytes() == original
                page._choose_daily_profile(second)
                assert page.selected_categories == {'3'}
                page._choose_daily_profile(first)
                assert page.selected_categories == {'1'}
                page._apply_daily_categories(['2'])
                page._restore_daily_profile()
                assert page.selected_categories == {'1'}
                assert page.daily_profile_status.text == 'Prohlížení'
                assert page.daily_update_button.text == 'Upravit název…'
                assert profile_file(tmp_path).read_bytes() == original
                assert (tmp_path / 'config.json').read_bytes() == config_before
            send.assert_not_called()
            assert not task_file(tmp_path).exists()


@pytest.mark.asyncio
async def test_schedule_handoff_keeps_exact_report_without_intermediate_save(tmp_path):
    dinner = DailyProfile.from_dict({'name': 'Večeře pro hosty', 'categories': ['3'], 'meal_type': 'Večeře'})
    root, pages = setup_page(tmp_path, [dinner])
    before = profile_file(tmp_path).read_bytes()
    with patch.object(NiceGuiApp, '_stored_password', return_value=''), \
         patch.object(NiceGuiApp, '_stored_api_key', return_value=''), \
         patch.object(NiceGuiApp, '_schedule_first_run'), \
         patch.object(NiceGuiApp, '_send_mail_worker') as send:
        async with user_simulation(root) as user:
            await user.open('/')
            with user:
                page = pages[0]
                page.wizard_name.value = 'Nová večeře'
                page.date_input.value = '31.12.2026'
            user.find(marker='wizard-next').click()
            user.find(marker='wizard-next').click()
            with user:
                assert page._wizard_step == 3
                assert page.wizard_mode.value == 'today'
                assert page.wizard_name.value == 'Nová večeře'
                assert page._selected_daily_meal_type() == 'večeře'
                assert page.selected_categories == {'3'}
                page._wizard_show_step(1)
                assert page.date_input.value == '31.12.2026'
            assert profile_file(tmp_path).read_bytes() == before
            assert not task_file(tmp_path).exists()
            send.assert_not_called()


@pytest.mark.asyncio
async def test_wizard_invalid_name_stays_open_and_single_final_save(tmp_path):
    root, pages = setup_page(tmp_path)
    with patch.object(NiceGuiApp, '_stored_password', return_value=''), \
         patch.object(NiceGuiApp, '_stored_api_key', return_value=''), \
         patch.object(NiceGuiApp, '_schedule_first_run'):
        async with user_simulation(root) as user:
            await user.open('/')
            with user:
                page = pages[0]
                page._apply_daily_categories(['1', '2'])
            user.find(marker='wizard-next').click()
            assert page._wizard_step == 1 and page.wizard_error.text
            with user:
                page.wizard_name.value = 'Škola'
            for _ in range(3):
                user.find(marker='wizard-next').click()
            assert not profile_file(tmp_path).exists()
            with user:
                page.wizard_recipients.input.value = 'test@example.org'
            user.find(marker='wizard-next').click()
            stored = load_profiles(profile_file(tmp_path))
            assert len(stored) == 1
            assert stored[0].categories == ('1', '2')
            assert load_tasks(task_file(tmp_path))[0].profile_id == stored[0].id
            assert page.wizard_receipt.visible


@pytest.mark.asyncio
async def test_updating_a_report_requires_explicit_save_and_copy_keeps_original(tmp_path):
    first = DailyProfile.from_dict({'name': 'Původní přehled', 'categories': ['1']})
    root, pages = setup_page(tmp_path, [first])
    with patch.object(NiceGuiApp, '_stored_password', return_value=''), \
         patch.object(NiceGuiApp, '_stored_api_key', return_value=''), \
         patch.object(NiceGuiApp, '_schedule_first_run'):
        async with user_simulation(root) as user:
            await user.open('/')
            with user:
                page = pages[0]
                page._apply_daily_categories(['2'])
            user.find('Uložit změny…').click()
            assert load_profiles(profile_file(tmp_path)) == [first]
            await user.should_see('Změny se použijí i u pravidelných odesílání, která tento přehled používají. Datum náhledu se neukládá.')
            user.find(marker='daily-save-confirm').click()
            updated = load_profiles(profile_file(tmp_path))[0]
            assert updated.id == first.id
            assert updated.categories == ('2',)
            user.find('Uložit jako nový…').click()
            with user:
                page.daily_profile_name.value = 'Nový přehled'
            user.find(marker='daily-save-confirm').click()
            stored = load_profiles(profile_file(tmp_path))
            assert len(stored) == 2
            assert stored[0] == updated
            assert stored[1].id != updated.id

