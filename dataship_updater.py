"""Standalone DataShip updater for an existing Windows installation."""
from __future__ import annotations

import argparse
import base64
from datetime import datetime
import json
import os
from pathlib import Path, PureWindowsPath
import re
import shutil
import subprocess
import sys
import time
from uuid import uuid4

from credential_store import _dpapi_encrypt_machine
from runtime_paths import application_directory
from scripts.deploy_web_build import SETTINGS, check_executable
from services.dataship_update_github import GitHubReleases
from services.dataship_update_package import stage_package
from services.dataship_update_transaction import (
    JOURNAL, UPDATE_PAUSE, WORKSPACE, apply_update, journal_write, preserve_backup, rollback_update, update_lock,
)
from services.web_activity import migrate_activity
from services.web_mail_nssm import query_service, require_service_rights, _run_nssm
from services.web_mail_settings import load_settings, settings_path


class Scheduler:
    def __init__(self, app: Path, config: Path):
        self.config = config
        self.request = uuid4().hex
        self.marker = config.parent / UPDATE_PAUSE
        self.heartbeat = config.parent / 'web_mail_worker_runtime.json'
        settings = load_settings(settings_path(config.parent))
        self.name = settings['service_name']
        self.sc = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'sc.exe'
        status = query_service(config.parent)
        if status.installed is None:
            raise RuntimeError(status.detail)
        if status.installed:
            require_service_rights('restart')
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                rf'SYSTEM\CurrentControlSet\Services\{self.name}\Parameters') as key:
                application, _ = winreg.QueryValueEx(key, 'Application')
                parameters, _ = winreg.QueryValueEx(key, 'AppParameters')
            expected = PureWindowsPath(app / 'DataShip-Worker.exe')
            args = re.fullmatch(r'--config\s+(?:"([^"]+)"|(\S+))', parameters)
            if (PureWindowsPath(application.strip('"')) != expected or not args
                    or PureWindowsPath(args[1] or args[2]) != PureWindowsPath(config)):
                raise RuntimeError('Registrovaná služba patří jiné instalaci DataShipu.')

    def state(self):
        return query_service(self.config.parent, expected_name=self.name).state

    def pause(self):
        self.marker.write_text(self.request, encoding='ascii')

    def resume(self):
        self.marker.unlink(missing_ok=True)

    def _wait(self, predicate, seconds, error):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(1)
        raise RuntimeError(error)

    def _acknowledged(self, *, after=None):
        try:
            payload = json.loads(self.heartbeat.read_text(encoding='utf-8'))
            return (payload['phase'] == 'paused' and payload['task_id'] == self.request
                    and (after is None or datetime.fromisoformat(payload['heartbeat']) >= after))
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def drain(self):
        self._wait(self._acknowledged, 600, 'Služba nepotvrdila dokončení úloh a přechod do údržby.')

    def stop(self):
        if self.state() not in ('stopped', 'stopping'):
            _run_nssm([str(self.sc), 'stop', self.name])
        self._wait(lambda: self.state() == 'stopped', 60, 'Služba se nezastavila.')

    def start(self):
        self.started = datetime.now()
        if self.state() != 'running':
            _run_nssm([str(self.sc), 'start', self.name])
        self._wait(lambda: self.state() == 'running', 60, 'Služba se nespustila.')

    def check(self, version):
        self._wait(lambda: self.state() == 'running' and self._acknowledged(after=self.started), 90,
                   'Nový worker nepotvrdil funkčnost.')


def snapshot_settings(config: Path, backup: Path) -> None:
    """Take a current-Windows-user DPAPI snapshot without writing plaintext copies."""
    files = {}
    for name in SETTINGS:
        source = config.parent / name
        if source.is_file():
            files[name] = base64.b64encode(source.read_bytes()).decode('ascii')
    payload = json.dumps({'format': 1, 'files': files}).encode('utf-8')
    token = _dpapi_encrypt_machine(payload, flags=0x1)  # UI forbidden, user scope
    journal_write(backup / 'settings.dpapi.json', {'protected': token})


def probe(app: Path, output: Path, expected: str | None = None) -> str:
    output.unlink(missing_ok=True)
    subprocess.run([str(app / 'DataShip.exe'), '--version-file', str(output)],
                   check=True, timeout=60, cwd=app)
    match = re.fullmatch(r'DataShip (\S+) build \S+\s*', output.read_text(encoding='utf-8'))
    if not match or (expected and match[1] != expected):
        raise RuntimeError('Verzi instalace se nepodařilo ověřit.')
    worker = subprocess.run([str(app / 'DataShip-Worker.exe'), '--version'],
                            check=True, timeout=60, cwd=app, capture_output=True, text=True)
    if not worker.stdout.startswith(f'DataShip Worker {match[1]} build '):
        raise RuntimeError('Verze workeru neodpovídá instalaci.')
    return match[1]


def run_update(app: Path, config: Path, public_key: bytes | None, archive: Path | None,
               repository: str, private: bool, recover: bool, wait_for_gui: bool = False, tag: str | None = None) -> None:
    with update_lock(app):
        workspace = app / WORKSPACE
        if (workspace / JOURNAL).exists():
            check_executable(app / 'DataShip.exe')
            rollback_update(app, workspace, Scheduler(app, config))
            print('Předchozí aktualizace byla uzavřena.')
            if recover:
                return
        elif recover:
            return
        if archive is not None and workspace in archive.resolve().parents:
            raise ValueError('Aktualizační ZIP musí být mimo pracovní složku aktualizátoru.')
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir()
        try:
            installed = probe(app, workspace / 'version.txt')
            print('Ověřuji podpis a integritu aktualizačního balíčku.', flush=True)
            expected_version = None
            if archive is None:
                github = GitHubReleases(repository, authenticated=private)
                release = github.latest(installed, tag=tag)
                if release is None:
                    print('Novější podepsaná aktualizace není dostupná.')
                    return
                expected_version = release.version
                archive = workspace / 'download.zip'
                github.download(release, archive)
            version = stage_package(archive, workspace / 'stage', public_key, installed)
            if expected_version and version != expected_version:
                raise ValueError('Podepsaný balíček má jinou verzi než vydání na GitHubu.')
            if wait_for_gui:
                print('Čekám na zavření DataShipu.', flush=True)
                deadline = time.monotonic() + 180
                while True:
                    try:
                        check_executable(app / 'DataShip.exe')
                        break
                    except PermissionError:
                        if time.monotonic() >= deadline:
                            raise
                        time.sleep(1)
            check_executable(app / 'DataShip.exe')
            if query_service(config.parent).state != 'running':
                check_executable(app / 'DataShip-Worker.exe')
            service = Scheduler(app, config)
            apply_update(app, workspace, service, version,
                         lambda value: probe(app, workspace / 'version.txt', value),
                         lambda: migrate_activity(config.parent), lambda status: print(status, flush=True),
                         snapshot=lambda backup: snapshot_settings(config, backup))
            # Preserve the previous binaries; application data was untouched.
            backup = preserve_backup(app, workspace)
            print(f'Aktualizováno na {version}. Záloha: {backup}', flush=True)
        finally:
            journal = workspace / JOURNAL
            if workspace.exists() and (not journal.exists() or (
                json.loads(journal.read_text(encoding='utf-8'))['phase'] == 'committed'
                and not (workspace / 'backup').exists()
            )):
                shutil.rmtree(workspace)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--installation', type=Path, default=application_directory())
    parser.add_argument('--config', type=Path)
    parser.add_argument('--public-key', type=Path, help='Důvěryhodný 32bajtový veřejný klíč Ed25519')
    parser.add_argument('--zip', type=Path)
    parser.add_argument('--repository', default='H0nz4k/MailPilot')
    parser.add_argument('--tag')
    parser.add_argument('--private', action='store_true')
    parser.add_argument('--recover', action='store_true')
    parser.add_argument('--wait-for-gui', action='store_true')
    parser.add_argument('--reopen', action='store_true')
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('Aktualizátor je určený pro Windows.')
    if not args.recover and args.public_key is None:
        parser.error('--public-key je povinný pro ověření aktualizace.')
    app = args.installation.resolve()
    config = (args.config or app / 'config.json').resolve()
    outcome = 0
    try:
        print(f'{datetime.now():%Y-%m-%d %H:%M:%S} · DataShip Updater', flush=True)
        if config.name.casefold() != 'config.json' or app / '_internal' in config.parents:
            raise ValueError('Aktualizace vyžaduje konfigurační soubor config.json.')
        run_update(app, config, args.public_key.read_bytes() if args.public_key else None,
                   args.zip, args.repository, args.private, args.recover, args.wait_for_gui, args.tag)
    except Exception as exc:
        print(f'Aktualizace selhala: {exc}', file=sys.stderr)
        outcome = 2
    if args.reopen:
        try:
            with update_lock(app):
                if not (app / WORKSPACE / JOURNAL).exists():
                    subprocess.Popen(
                        [str(app / 'DataShip.exe'), '--browser', '--config', str(config)], cwd=app,
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        env={**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'},
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
        except (OSError, RuntimeError) as exc:
            print(f'DataShip se nepodařilo znovu otevřít: {exc}', file=sys.stderr)
            outcome = 2
    return outcome


if __name__ == '__main__':
    from multiprocessing import freeze_support
    freeze_support()
    raise SystemExit(main())
