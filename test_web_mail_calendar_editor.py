from datetime import date
from unittest.mock import patch
import pytest
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation
from services.web_daily_profiles import DailyProfile, profile_file, save_profile
from services.web_mail_gui import build_mail_tasks_panel
from services.web_mail_settings import DEFAULTS, save_settings, settings_path
from services.web_mail_task_store import load_tasks, save_tasks, task_file
from services.web_mail_tasks import MailTask


def field(user, kind, label):
    return next(e for e in reversed(list(user.client.elements.values()))
                if isinstance(e, kind) and (e.props.get('label') or e.props.get('aria-label')) == label)


@pytest.mark.asyncio
async def test_new_task_uses_report_calendar_and_copy_keeps_report(tmp_path):
    profile = DailyProfile.from_dict({'name': 'Večeře', 'categories': ['1'], 'meal_type': 'Večeře'})
    save_profile(profile_file(tmp_path), profile)
    with patch('services.web_mail_gui.resolve_task_date', return_value=date(2026, 10, 25)):
        async with user_simulation(lambda: build_mail_tasks_panel(tmp_path)) as user:
            await user.open('/')
            user.find('Nové odesílání').click()
            with user:
                field(user, ui.input, 'Název odesílání').value = 'Večerní přehled'
                field(user, ui.input, 'E-mail příjemce').value = 'test@example.org'
                field(user, ui.select, 'Za který den posílat?').value = 'next_cooking_day'
                assert not any(isinstance(e, ui.select) and e.props.get('label') == 'Kalendář varných dnů' for e in user.client.elements.values())
            user.find('Uložit').click()
            stored = load_tasks(task_file(tmp_path))
            assert stored[0].profile_id == profile.id
            assert stored[0].cooking_meal_type is None
            await user.should_see('Kopírovat')
            user.find('Kopírovat').click()
            user.find('Uložit').click()
            stored = load_tasks(task_file(tmp_path))
            assert len(stored) == 2
            assert {job.profile_id for job in stored} == {profile.id}
            assert all(job.cooking_meal_type is None for job in stored)


@pytest.mark.asyncio
async def test_legacy_calendar_is_preserved_on_save(tmp_path):
    old = MailTask.from_dict({'name': 'Starší obědy', 'recipients': ['test@example.org'],
                              'send_time': '08:00', 'date_mode': 'next_cooking_day',
                              'cooking_meal_type': 'Oběd'})
    save_tasks(task_file(tmp_path), [old])
    save_settings(settings_path(tmp_path), {**DEFAULTS, 'cooking_meal_type': 'Večeře'})
    with patch('services.web_mail_gui.resolve_task_date', return_value=date(2026, 10, 26)):
        async with user_simulation(lambda: build_mail_tasks_panel(tmp_path)) as user:
            await user.open('/')
            await user.should_see('Den přehledu: Následující varný den · varné dny: Oběd')
            user.find('Upravit').click()
            user.find('Uložit').click()
            stored = load_tasks(task_file(tmp_path))
            assert stored[0].id == old.id
            assert stored[0].cooking_meal_type == 'Oběd'
