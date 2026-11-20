"""Administration panel for the standalone Windows updater."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from nicegui import run, ui

from runtime_paths import application_directory
from services.dataship_update_github import GitHubReleases
from services.web_branding import WEB_VERSION
from services.web_mail_nssm import ADMIN_HELP, query_service, windows_admin_state
from services.web_path_picker import pick_local_file


def build_update_panel(config: Path, require_admin) -> None:
    root = application_directory()
    logfile = root / 'logy' / 'dataship_updates.log'
    release = None
    updater = root / 'DataShip-Updater.exe'
    key = root / 'dataship-update-public-key.bin'
    ready = os.name == 'nt' and getattr(sys, 'frozen', False) and updater.is_file() and key.is_file()
    ui.label('Aktualizace').classes('ds-page-title')
    with ui.card().classes('ds-settings-card'):
        ui.label(f'Aktuální verze: {WEB_VERSION}')
        available = ui.label('Dostupná verze: —')
        notes = ui.label('').style('white-space: pre-wrap; max-height: 12rem; overflow: auto')
        private = ui.checkbox('Použít přihlášení GitHub CLI')
        status = ui.label('').props('role="status"')
        if not ready:
            status.set_text('Instalace potřebuje DataShip-Updater.exe a důvěryhodný veřejný klíč aktualizací.')

        async def check():
            nonlocal release
            if not require_admin():
                return
            check_button.disable()
            online.disable()
            try:
                release = await run.io_bound(GitHubReleases(authenticated=private.value).latest, WEB_VERSION)
                available.set_text(f'Dostupná verze: {release.version if release else "—"}')
                notes.set_text(release.notes if release else '')
                status.set_text('Aktualizace je dostupná.' if release else 'Novější podepsaná verze není dostupná.')
                online.set_enabled(bool(release and ready))
            except (OSError, ValueError, RuntimeError, KeyError, subprocess.TimeoutExpired) as exc:
                status.set_text(str(exc))
            finally:
                check_button.enable()

        async def launch(local: bool):
            if not ready or not require_admin():
                return
            service = await run.io_bound(query_service, config.parent)
            if service.installed is None:
                status.set_text(service.detail)
                return
            if service.installed and not windows_admin_state():
                status.set_text(ADMIN_HELP)
                return
            argv = [str(updater), '--installation', str(root), '--config', str(config),
                    '--public-key', str(key), '--wait-for-gui']
            if local:
                selected = await run.io_bound(lambda: pick_local_file(str(root), kind='update'))
                if not selected or not require_admin():
                    return
                argv.extend(['--zip', selected])
            elif private.value:
                argv.append('--private')
            try:
                logfile.parent.mkdir(exist_ok=True)
                with logfile.open('ab') as output:
                    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                     env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
                                     creationflags=subprocess.CREATE_NO_WINDOW)
                status.set_text('Aktualizátor čeká na zavření DataShipu. Dokončete práci a zavřete okno. Výsledek uvidíte po dalším spuštění.')
            except OSError as exc:
                status.set_text(str(exc))

        with ui.row().classes('gap-2'):
            check_button = ui.button('Zkontrolovat aktualizace', on_click=check).props('outline no-caps')
            online = ui.button('Aktualizovat', on_click=lambda: launch(False)).props('no-caps')
            online.disable()
            ui.button('Aktualizovat z místního ZIP', on_click=lambda: launch(True)).props('outline no-caps').set_enabled(ready)
    with ui.card().classes('ds-settings-card'):
        ui.label('Průběh a historie').classes('app-heading')
        history = ui.label('').style('white-space: pre-wrap; max-height: 18rem; overflow: auto')

        def refresh():
            try:
                with logfile.open('rb') as stream:
                    size = stream.seek(0, os.SEEK_END)
                    stream.seek(max(0, size - 16384))
                    text = stream.read().decode('utf-8', errors='replace')
                history.set_text(text)
            except OSError:
                history.set_text('Zatím bez historie.')

        refresh()
        ui.timer(3, refresh)
