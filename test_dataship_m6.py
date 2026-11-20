from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts.package_dataship_update import package
from services import web_mail_nssm as nssm
from services.dataship_update_package import stage_package


@pytest.mark.parametrize('code, output, expected', [
    (1060, b'', (False, 'missing')),
    (5, b'', (None, 'error')),
    (0, b'SERVICE_NAME: DataShip\n TYPE : 10 WIN32_OWN_PROCESS\n STATE : 4 RUNNING\n WIN32_EXIT_CODE : 0 (0x0)', (True, 'running')),
    (0, b'SERVICE_NAME: DataShip\n TYPE : 10 WIN32_OWN_PROCESS\n STATE : 1 STOPPED\n WIN32_EXIT_CODE : 0 (0x0)', (True, 'stopped')),
])
def test_service_queries_scm_without_nssm(tmp_path, code, output, expected):
    with patch.object(nssm, 'os', SimpleNamespace(name='nt', environ={})), \
         patch.object(nssm, 'load_settings', return_value={'service_name': 'DataShip'}), \
         patch.object(nssm.subprocess, 'run', return_value=SimpleNamespace(returncode=code, stdout=output)) as run:
        status = nssm.query_service(tmp_path)
    assert (status.installed, status.state) == expected
    assert run.call_args.args[0][1:] == ['query', 'DataShip']


@pytest.fixture
def signed_zip(tmp_path):
    app = tmp_path / 'app'
    (app / '_internal').mkdir(parents=True)
    for path in ('DataShip.exe', 'DataShip-Worker.exe', '_internal/runtime.dll'):
        (app / path).write_bytes(path.encode())
    archive = tmp_path / 'update.zip'
    key = Ed25519PrivateKey.generate()
    package(app, archive, '1.5.0', key)
    return archive, key.public_key().public_bytes_raw()


def test_signed_offline_package_stages_program_files(signed_zip, tmp_path):
    archive, key = signed_zip
    stage = tmp_path / 'stage'
    assert stage_package(archive, stage, key, '1.4.0') == '1.5.0'
    assert (stage / '_internal/runtime.dll').read_bytes() == b'_internal/runtime.dll'
    assert not (stage / 'config.json').exists()


def test_package_rejects_untrusted_signature_and_downgrade(signed_zip, tmp_path):
    archive, key = signed_zip
    with pytest.raises(ValueError, match='Podpis'):
        stage_package(archive, tmp_path / 'stage', Ed25519PrivateKey.generate().public_key().public_bytes_raw(), '1.4.0')
    with pytest.raises(ValueError, match='novější'):
        stage_package(archive, tmp_path / 'stage', key, '1.5.0')
    assert not (tmp_path / 'stage').exists()


def test_package_rejects_modified_binary_and_cleans_stage(signed_zip, tmp_path):
    archive, key = signed_zip
    modified = tmp_path / 'modified.zip'
    with ZipFile(archive) as original, ZipFile(modified, 'w') as altered:
        for item in original.infolist():
            altered.writestr(item, b'modified' if item.filename == 'DataShip.exe' else original.read(item))
    stage = tmp_path / 'stage'
    with pytest.raises(ValueError, match='součet'):
        stage_package(modified, stage, key, '1.4.0')
    assert not stage.exists()


def test_github_release_reads_notes_and_downloads_signed_asset(signed_zip, tmp_path, monkeypatch):
    import json
    from services.dataship_update_github import GitHubReleases

    archive, key = signed_zip
    github = GitHubReleases(authenticated=True)

    def get(endpoint, accept, output, maximum):
        if endpoint.endswith('/latest'):
            output.write(json.dumps({'tag_name': 'dataship-v1.5.0', 'body': 'Změny',
                                     'assets': [{'name': 'DataShip-1.5.0-Windows-x64-Update.zip', 'id': 42}]}).encode())
        else:
            assert endpoint.endswith('/assets/42')
            assert accept == 'application/octet-stream'
            output.write(archive.read_bytes())

    monkeypatch.setattr(github, '_get', get)
    release = github.latest('1.4.0')
    assert release.notes == 'Změny'
    downloaded = tmp_path / 'downloaded.zip'
    github.download(release, downloaded)
    assert stage_package(downloaded, tmp_path / 'stage', key, '1.4.0') == release.version


@pytest.mark.asyncio
@pytest.mark.parametrize('accept', [False, True])
async def test_first_launch_offers_install_once(tmp_path, monkeypatch, accept):
    import asyncio
    from nicegui import ui
    from nicegui.testing.user_simulation import user_simulation
    from services import web_first_run

    class Page(web_first_run.FirstRunMixin):
        config_path = tmp_path / 'config.json'
        connection_ok = True
        _startup_checked = False

        def _require_admin(self, *, silent):
            return True

    page = Page()
    monkeypatch.setattr(web_first_run, '_service_prompt_shown', False)
    monkeypatch.setattr(web_first_run, 'query_service', lambda _: nssm.ServiceStatus(False, 'missing'))
    monkeypatch.setattr(web_first_run, 'windows_admin_state', lambda: True)
    actions = []
    monkeypatch.setattr(web_first_run, 'service_command', lambda directory, action: actions.append((directory, action)))

    async with user_simulation(lambda: ui.label('DataShip')) as user:
        await user.open('/')
        with user:
            await page._start_first_run()
        await user.should_see('Instalovat službu')
        user.find('Instalovat službu' if accept else 'Nyní ne').click()
        for _ in range(40):
            with user:
                dialogs = list(ui.context.client.elements.values())
                dialogs = [item for item in dialogs if isinstance(item, ui.dialog)]
            if len(dialogs) == 1 and not dialogs[0].value:
                break
            await asyncio.sleep(0.05)
        assert len(dialogs) == 1 and not dialogs[0].value
        with user:
            await page._start_first_run()
            await Page()._start_first_run()
        for _ in range(40):
            with user:
                dialogs = list(ui.context.client.elements.values())
                dialogs = [item for item in dialogs if isinstance(item, ui.dialog)]
            if len(dialogs) == 1 and not dialogs[0].value:
                break
            await asyncio.sleep(0.05)
        assert len(dialogs) == 1 and not dialogs[0].value
    assert actions == ([(tmp_path, 'install')] if accept else [])


@pytest.mark.parametrize('failure', [None, 'migration', 'health', 'interrupted'])
def test_transaction_preserves_user_files_and_restores_program(tmp_path, failure):
    from services.dataship_update_transaction import PROGRAM, apply_update, rollback_update, update_lock

    app = tmp_path / 'app'
    workspace = app / '.dataship-update'
    stage = workspace / 'stage'
    stage.mkdir(parents=True)
    for name in PROGRAM:
        (app / name).write_text('old')
        (stage / name).write_text('new')
    saved = ('config.json', 'planovac.json', 'web_mail_tasks.json', 'history.json', '.env', 'report.pdf')
    for name in saved:
        (app / name).write_text(name)

    class Failed(RuntimeError):
        pass

    class Interrupted(BaseException):
        pass

    class Service:
        status = 'running'
        paused = False

        def state(self):
            return self.status

        def pause(self):
            self.paused = True

        def drain(self):
            assert self.paused

        def stop(self):
            self.status = 'stopped'

        def start(self):
            self.status = 'running'

        def check(self, version):
            assert self.paused
            if failure == 'health':
                raise Failed()

        def resume(self):
            self.paused = False

    def migrate():
        if failure == 'migration':
            raise Failed()
        if failure == 'interrupted':
            raise Interrupted()

    service = Service()
    with update_lock(app):
        with pytest.raises(RuntimeError, match='Jiná aktualizace'):
            with update_lock(app):
                pytest.fail('second updater entered')
        args = (app, workspace, service, '1.5.0', lambda _: None, migrate, lambda _: None)
        if failure == 'interrupted':
            with pytest.raises(Interrupted):
                apply_update(*args)
            assert service.paused and service.status == 'stopped'
            rollback_update(app, workspace, service)
        elif failure:
            with pytest.raises(Failed):
                apply_update(*args)
        else:
            apply_update(*args)
    assert not service.paused and service.status == 'running'
    for name in saved:
        assert (app / name).read_text() == name
    for name in PROGRAM:
        assert (app / name).read_text() == ('old' if failure else 'new')
