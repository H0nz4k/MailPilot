import asyncio
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


async def choices_loaded(calendar):
    for _ in range(100):
        if 'Večeře' in calendar.options:
            return
        await asyncio.sleep(.01)
    pytest.fail('Calendar options did not load')


@pytest.mark.asyncio
async def test_new_task_requires_explicit_calendar_and_edit_copy_preserve_it(tmp_path):
    profile = DailyProfile.from_dict({'name': 'Všechny porce', 'categories': ['1']})
    save_profile(profile_file(tmp_path), profile)
    with patch('services.web_mail_gui.resolve_task_date', return_value=date(2026, 10, 25)), \
         patch('services.web_mail_gui.available_cooking_calendars', return_value=('Oběd', 'Večeře')) as lookup:
        async with user_simulation(lambda: build_mail_tasks_panel(tmp_path)) as user:
            await user.open('/')
            user.find('Nové odesílání').click()
            with user:
                field(user, ui.input, 'Název odesílání').value = 'Večerní přehled'
                field(user, ui.input, 'E-mail příjemce').value = 'test@example.org'
                mode = field(user, ui.select, 'Za který den posílat?')
                calendar = field(user, ui.select, 'Kalendář varných dnů')
                assert not calendar.parent_slot.parent.visible
                assert not lookup.called
                mode.value = 'next_cooking_day'
                assert calendar.parent_slot.parent.visible
            await choices_loaded(calendar)
            user.find('Uložit').click()
            assert calendar.props['error']
            assert not load_tasks(task_file(tmp_path))
            with user:
                calendar.value = 'Večeře'
                assert not calendar.props.get('error')
            await user.should_not_see('Vyberte kalendář varných dnů pro toto odesílání.')
            user.find('Uložit').click()
            stored = load_tasks(task_file(tmp_path))
            assert stored[0].cooking_meal_type == 'Večeře'
            await user.should_see('Upravit')
            user.find('Upravit').click()
            with user:
                assert field(user, ui.select, 'Kalendář varných dnů').value == 'Večeře'
            user.find('Zrušit').click()
            user.find('Kopírovat').click()
            with user:
                assert field(user, ui.select, 'Kalendář varných dnů').value == 'Večeře'
            user.find('Uložit').click()
            stored = load_tasks(task_file(tmp_path))
            assert len(stored) == 2
            assert {job.cooking_meal_type for job in stored} == {'Večeře'}


@pytest.mark.asyncio
async def test_legacy_calendar_is_visible_and_pinned_on_save(tmp_path):
    old = MailTask.from_dict({'name': 'Starší obědy', 'recipients': ['test@example.org'],
                              'send_time': '08:00', 'date_mode': 'next_cooking_day'})
    save_tasks(task_file(tmp_path), [old])
    save_settings(settings_path(tmp_path), {**DEFAULTS, 'cooking_meal_type': 'Oběd'})
    with patch('services.web_mail_gui.resolve_task_date', return_value=date(2026, 10, 26)), \
         patch('services.web_mail_gui.available_cooking_calendars', return_value=('Oběd', 'Večeře')):
        async with user_simulation(lambda: build_mail_tasks_panel(tmp_path)) as user:
            await user.open('/')
            await user.should_see('Den přehledu: Následující varný den · kalendář: Oběd (dosavadní nastavení)')
            user.find('Upravit').click()
            with user:
                assert field(user, ui.select, 'Kalendář varných dnů').value == 'Oběd'
            user.find('Uložit').click()
            stored = load_tasks(task_file(tmp_path))
            assert stored[0].id == old.id
            assert stored[0].cooking_meal_type == 'Oběd'
            save_settings(settings_path(tmp_path), {**DEFAULTS, 'cooking_meal_type': 'Večeře'})
            assert load_tasks(task_file(tmp_path))[0].cooking_meal_type == 'Oběd'
