from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from services import web_mail_nssm as nssm
from services import web_mail_settings as settings


@pytest.mark.parametrize('action, output, expected', [
    ('status', 'SERVICE_RUNNING', 'Služba běží.'),
    ('status', 'SERVICE_STOPPED', 'Služba je zastavená.'),
    ('start', 'successfully started', 'Služba byla spuštěna.'),
])
def test_service_feedback_is_czech_and_decodes_utf16(tmp_path, action, output, expected):
    binary = tmp_path / 'nssm.exe'
    binary.touch()
    values = {**settings.DEFAULTS, 'nssm_path': str(binary)}
    with patch.object(nssm, 'load_settings', return_value=values), \
         patch.object(nssm, 'require_service_rights'), \
         patch.object(nssm.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=output.encode('utf-16-le'), stderr=b'')):
        assert nssm.service_command(tmp_path, action) == expected


@pytest.mark.parametrize('output, expected', [
    ('Access is denied.', 'správce Windows'),
    ('CreateService(): error 1073', 'již existuje'),
    ('OpenService(): error 1060', 'není nainstalovaná'),
    ('Error 1069', 'účet a heslo'),
    ('Unexpected status SERVICE_PAUSED', 'Worker se nespustil'),
    ('Unknown failure from C:/version/rc.5/nssm.exe', 'Operaci služby'),
])
def test_service_errors_have_czech_recovery_steps(output, expected):
    assert expected in nssm.service_error_message(output)


def test_install_uses_sibling_worker_with_spaces_and_unicode_without_starting(tmp_path):
    app = tmp_path / 'Honzák složka'
    app.mkdir()
    gui = app / 'DataShip.exe'; gui.touch()
    worker = app / 'DataShip-Worker.exe'; worker.touch()
    binary = app / 'nssm/win64/nssm.exe'; binary.parent.mkdir(parents=True); binary.touch()
    (app / 'config.json').write_text('{}')
    values = {**settings.DEFAULTS, 'nssm_path': str(binary)}
    with patch.object(nssm, 'load_settings', return_value=values), \
         patch.object(nssm, 'require_service_rights'), \
         patch.object(nssm.sys, 'frozen', True, create=True), \
         patch.object(nssm.sys, 'executable', str(gui)), \
         patch.object(nssm, '_run_nssm', return_value='') as run:
        result = nssm.service_command(app, 'install')
    commands = [c.args[0] for c in run.call_args_list]
    assert commands[0] == [str(binary), 'install', 'DataShipScheduler', str(worker), '--config', str(app / 'config.json')]
    assert not any(c[1] == 'start' for c in commands)
    assert 'Zatím neběží' in result


def test_empty_saved_path_uses_executable_directory_instead_of_config_directory(tmp_path, monkeypatch):
    executable_dir = tmp_path / 'program'
    config_dir = tmp_path / 'settings'
    config_dir.mkdir()
    monkeypatch.setattr(settings, 'application_directory', lambda: executable_dir)
    file = config_dir / 'web_mail_settings.json'
    file.write_text('{"nssm_path":""}')
    assert settings.load_settings(file)['nssm_path'] == str(executable_dir / 'nssm/win64/nssm.exe')
    file.write_text('{"nssm_path":"C:/old/nssm/win64/nssm.exe"}')
    assert settings.load_settings(file)['nssm_path'] == str(executable_dir / 'nssm/win64/nssm.exe')


def test_install_requires_windows_elevation_but_status_does_not():
    windows = SimpleNamespace(windll=SimpleNamespace(shell32=SimpleNamespace(IsUserAnAdmin=lambda: False)))
    with patch.object(nssm, 'os', SimpleNamespace(name='nt')), patch.object(nssm, 'ctypes', windows):
        with pytest.raises(PermissionError, match='správce Windows'):
            nssm.require_service_rights('install')
        nssm.require_service_rights('status')
