"""Service removal requires confirmation and leaves saved application data intact."""
from unittest.mock import patch

import pytest
from nicegui.testing.user_simulation import user_simulation

from services import web_mail_nssm as nssm
from services.web_mail_settings import DEFAULTS
from services.web_mail_settings_gui import build_web_settings_panel


@pytest.mark.parametrize('initial_state', ['SERVICE_STOPPED', 'SERVICE_RUNNING'])
def test_remove_stops_running_worker_and_preserves_data(tmp_path, initial_state):
    binary = tmp_path / 'nssm.exe'
    binary.touch()
    files = ['config.json', 'web_mail_tasks.json', 'daily_reports.json', '.env']
    for filename in files:
        (tmp_path / filename).write_text('saved data')
    state = [initial_state]

    def respond(command):
        if command[1] == 'get':
            # Removal works even after the old install directory has disappeared.
            return r'C:\Old folder\DataShip-Worker.exe'
        if command[1] == 'status':
            return state[0]
        if command[1] == 'stop':
            state[0] = 'SERVICE_STOPPED'
        return ''

    with patch.object(nssm, 'load_settings', return_value={**DEFAULTS, 'nssm_path': str(binary)}), \
         patch.object(nssm, 'require_service_rights') as rights, \
         patch.object(nssm, '_run_nssm', side_effect=respond) as run:
        result = nssm.service_command(tmp_path, 'remove')
    rights.assert_called_once_with('remove')
    commands = [c.args[0] for c in run.call_args_list]
    assert commands[-1] == [str(binary), 'remove', 'DataShipScheduler', 'confirm']
    assert any(c[1] == 'stop' for c in commands) == (initial_state == 'SERVICE_RUNNING')
    assert not any(c[1] in ('install', 'start', 'restart') for c in commands)
    assert 'Služba byla odstraněna' in result
    for filename in files:
        assert (tmp_path / filename).read_text() == 'saved data'


@pytest.mark.parametrize('failure', ['foreign_worker', 'stop_failure', 'still_stopping', 'no_rights'])
def test_remove_rejects_foreign_service_and_failed_stop(tmp_path, failure):
    binary = tmp_path / 'nssm.exe'
    binary.touch()

    def respond(command):
        if command[1] == 'get':
            return 'OtherWorker.exe' if failure == 'foreign_worker' else 'DataShip-Worker.exe'
        if command[1] == 'status':
            return 'SERVICE_RUNNING'
        if command[1] == 'stop' and failure == 'stop_failure':
            raise RuntimeError('Windows nepovolil zastavení.')
        return ''

    with patch.object(nssm, 'load_settings', return_value={**DEFAULTS, 'nssm_path': str(binary)}), \
         patch.object(nssm, 'require_service_rights', side_effect=PermissionError('správce') if failure == 'no_rights' else None), \
         patch.object(nssm, '_run_nssm', side_effect=respond) as run:
        with pytest.raises((ValueError, RuntimeError, PermissionError)):
            nssm.service_command(tmp_path, 'remove')
    commands = [c.args[0] for c in run.call_args_list]
    assert not any(c[1] == 'remove' for c in commands)
    if failure in ('foreign_worker', 'no_rights'):
        assert not any(c[1] == 'stop' for c in commands)


@pytest.mark.asyncio
async def test_removal_dialog_cancel_and_confirm(tmp_path):
    with patch('services.web_mail_settings_gui.windows_admin_state', return_value=True), \
         patch('services.web_mail_settings_gui.get_resend_api_key', return_value=None), \
         patch('services.web_mail_settings_gui.service_command', return_value='Služba byla odstraněna z Windows.') as command:
        async with user_simulation(lambda: build_web_settings_panel(tmp_path)) as user:
            await user.open('/')
            user.find(marker='remove-service').click()
            await user.should_see('Služba: DataShipScheduler')
            command.assert_not_called()
            user.find(marker='cancel-service-removal').click()
            command.assert_not_called()
            user.find(marker='remove-service').click()
            user.find(marker='confirm-service-removal').click()
            await user.should_see('Služba byla odstraněna z Windows.', retries=30)
            command.assert_called_once_with(tmp_path, 'remove')
