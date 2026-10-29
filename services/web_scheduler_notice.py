"""Visible service activation result after saving an enabled task."""
from pathlib import Path

from nicegui import background_tasks, run, ui

from services.web_mail_nssm import ServiceReadiness, ensure_scheduler_running


class SchedulerServiceNotice:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.revision = 0
        with ui.column().classes('ds-scheduler-notice w-full').props('role="status" aria-live="polite" aria-atomic="true"').mark('scheduler-service-notice') as self.container:
            with ui.row().classes('items-start no-wrap gap-3'):
                self.icon = ui.icon('info', size='28px').props('aria-hidden="true"')
                self.label = ui.label('').classes('ds-scheduler-notice-text').mark('scheduler-service-message')
            self.retry = ui.button('Znovu ověřit a spustit službu', icon='play_arrow',
                                   on_click=lambda: self.activate(True)).props('outline no-caps').mark('scheduler-service-retry')
        self.clear()

    def clear(self):
        self.revision += 1
        self.container.set_visibility(False)

    def activate(self, enabled: bool):
        self.revision += 1
        revision = self.revision
        if not enabled:
            self.container.set_visibility(False)
            return
        self.show('Úloha je uložená. Ověřuji a spouštím službu plánovače…', 'pending')
        self.retry.set_visibility(False)
        background_tasks.create(self._activate(revision))

    async def _activate(self, revision: int):
        try:
            result = await run.io_bound(ensure_scheduler_running, self.directory)
        except Exception:
            result = ServiceReadiness(False, 'Ověření služby selhalo. Úloha je uložená, ale automatické spuštění zatím není zajištěné. Ověřte službu v Nastavení → Služba a odesílání.')
        if revision != self.revision or self.container.is_deleted:
            return
        self.show('Úloha je uložená. ' + result.message, 'positive' if result.running else 'warning')
        self.retry.set_visibility(not result.running)
        if not result.running:
            ui.notify(result.message, type='warning', timeout=15000)

    def show(self, message: str, state: str):
        self.container.classes(remove='ds-scheduler-notice--pending ds-scheduler-notice--positive ds-scheduler-notice--warning',
                               add=f'ds-scheduler-notice--{state}')
        self.icon.props('name=' + ('check_circle' if state == 'positive' else 'warning_amber' if state == 'warning' else 'hourglass_top'))
        self.label.set_text(message)
        self.container.set_visibility(True)
