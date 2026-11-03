"""Enabled-task saves ensure the right service and visibly report failed starts."""
from datetime import date
from pathlib import Path
import shutil
import subprocess
from unittest.mock import patch

import pytest
from nicegui.testing.user_simulation import user_simulation

from services import web_mail_nssm as nssm
from services.web_mail_settings import DEFAULTS
from services.web_mail_tasks import MailTask
from services.web_mail_task_store import task_file, load_tasks, save_tasks
from services.web_daily_profiles import DailyProfile, profile_file, save_profile, load_profiles
from services.web_mail_gui import build_mail_tasks_panel
from stravovaci_nicegui import NiceGuiApp


@pytest.mark.parametrize('case', ['running', 'stopped', 'no_rights', 'not_installed',
                                  'foreign_app', 'foreign_config', 'failed_start', 'unconfirmed_start', 'pending', 'paused'])
def test_ensure_service_only_starts_own_stopped_worker(tmp_path, case):
    app = tmp_path / 'Honzák složka'
    app.mkdir()
    gui = app / 'DataShip.exe'
    gui.touch()
    worker = app / 'DataShip-Worker.exe'
    worker.touch()
    binary = app / 'nssm.exe'
    binary.touch()
    config = app / 'config.json'
    config.write_text('{}')
    (app / 'web_mail_tasks.json').write_text('saved tasks')
    state = ['SERVICE_RUNNING' if case == 'running' else 'SERVICE_PAUSED' if case == 'paused' else 'SERVICE_START_PENDING' if case == 'pending' else 'SERVICE_STOPPED']
    def rights(action):
        if case == 'no_rights' and action == 'start':
            raise PermissionError(nssm.ADMIN_HELP)
    def respond(command):
        if case == 'not_installed':
            raise RuntimeError('Služba zatím není nainstalovaná.')
        if command[1] == 'get' and command[3] == 'Application':
            return str(app / 'foreign.exe') if case == 'foreign_app' else str(worker)
        if command[1] == 'get' and command[3] == 'AppParameters':
            return subprocess.list2cmdline(['--config', str(app / 'other.json' if case == 'foreign_config' else config)])
        if command[1] == 'status':
            return state[0]
        if command[1] == 'start':
            if case == 'failed_start':
                raise RuntimeError('Windows nepovolil změnu služby.')
            if case != 'unconfirmed_start':
                state[0] = 'SERVICE_RUNNING'
        return ''
    with patch.object(nssm, 'load_settings', return_value={**DEFAULTS, 'nssm_path': str(binary)}), \
         patch.object(nssm, 'require_service_rights', side_effect=rights) as check, \
         patch.object(nssm.sys, 'frozen', True, create=True), \
         patch.object(nssm.sys, 'executable', str(gui)), \
         patch.object(nssm, '_run_nssm', side_effect=respond) as run:
        result = nssm.ensure_scheduler_running(app)
    assert result.running == (case in ('running', 'stopped'))
    commands = [call.args[0] for call in run.call_args_list]
    assert sum(command[1] == 'start' for command in commands) == (case in ('stopped', 'failed_start', 'unconfirmed_start'))
    assert not any(command[1] in ('install', 'remove', 'restart', 'stop', 'set') for command in commands)
    if case == 'running':
        assert [call.args[0] for call in check.call_args_list] == ['status']
    if case == 'no_rights':
        assert 'správce Windows' in result.message
        assert 'není zajištěné' in result.message
    assert (app / 'web_mail_tasks.json').read_text() == 'saved tasks'


@pytest.mark.asyncio
async def test_wizard_saves_before_start_and_warns_without_losing_task(tmp_path):
    config = tmp_path / 'config.json'
    shutil.copyfile(Path(__file__).with_name('config.example.json'), config)
    pages = []
    def root():
        page = NiceGuiApp(config)
        page.build()
        page.populate_categories([('1', 'Žáci')])
        pages.append(page)
    def ensure(directory):
        stored = load_tasks(task_file(directory))
        assert len(stored) == 1
        assert stored[0].profile_id == load_profiles(profile_file(directory))[0].id
        return nssm.ServiceReadiness(False, 'Automatické spuštění úlohy zatím není zajištěné. Spusťte DataShip jako správce Windows.')
    with patch.object(NiceGuiApp, '_stored_password', return_value=''), \
         patch.object(NiceGuiApp, '_stored_api_key', return_value=''), \
         patch.object(NiceGuiApp, '_schedule_first_run'), \
         patch('services.web_scheduler_notice.ensure_scheduler_running', side_effect=ensure) as start:
        async with user_simulation(root) as user:
            await user.open('/')
            with user:
                page = pages[0]
                page.wizard_name.value = 'Test sestava'
                page._apply_daily_categories(['1'])
                page.wizard_recipients.input.value = 'dummy@example.org'
                page._wizard_save()
            await user.should_see('Spusťte DataShip jako správce Windows.')
            notice = page.wizard_service_notice
            assert notice.container.visible
            assert 'ds-scheduler-notice--warning' in notice.container.classes
            assert notice.retry.visible
            start.assert_called_once_with(tmp_path)
            assert len(load_tasks(task_file(tmp_path))) == 1
            start.side_effect = None
            start.return_value = nssm.ServiceReadiness(True, 'Služba byla automaticky spuštěna.')
            retry = user.find(marker='scheduler-service-retry')
            retry.elements = {notice.retry}
            retry.click()
            await user.should_see('Služba byla automaticky spuštěna.')
            assert 'ds-scheduler-notice--positive' in notice.container.classes
            assert not notice.retry.visible
            assert len(load_tasks(task_file(tmp_path))) == 1
            with user:
                page._wizard_new()
                page.wizard_name.value = 'Druhá sestava'
                page.wizard_enabled.value = False
                page.wizard_recipients.input.value = 'disabled@example.org'
                page._wizard_save()
            assert len(load_tasks(task_file(tmp_path))) == 2
            assert start.call_count == 2
            assert not notice.container.visible


@pytest.mark.asyncio
async def test_planner_activation_edit_and_copy_check_service_but_disable_does_not(tmp_path):
    profile = DailyProfile.from_dict({'name': 'Škola', 'categories': ['1']})
    save_profile(profile_file(tmp_path), profile)
    old = MailTask.from_dict({'name': 'Test', 'recipients': ['dummy@example.org'],
                             'profile_id': profile.id, 'enabled': False, 'send_time': '08:00'})
    save_tasks(task_file(tmp_path), [old])
    with patch('services.web_mail_gui.resolve_task_date', return_value=date.today()), \
         patch('services.web_scheduler_notice.ensure_scheduler_running',
               return_value=nssm.ServiceReadiness(True, 'Služba pro test běží.')) as start:
        async with user_simulation(lambda: build_mail_tasks_panel(tmp_path)) as user:
            await user.open('/')
            start.assert_not_called()
            user.find('Zapnout').click()
            await user.should_see('Služba pro test běží.')
            assert start.call_count == 1
            assert load_tasks(task_file(tmp_path))[0].enabled
            user.find('Upravit').click()
            user.find('Uložit').click()
            await user.should_see('Služba pro test běží.')
            assert start.call_count == 2
            user.find('Kopírovat').click()
            user.find('Uložit').click()
            await user.should_see('Služba pro test běží.')
            assert start.call_count == 3
            assert len(load_tasks(task_file(tmp_path))) == 2
            user.find('Vypnout').click()
            assert start.call_count == 3
