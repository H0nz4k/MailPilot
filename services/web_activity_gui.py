"""Administrator-only activity history; no transport action is available here."""
from nicegui import ui
from services.web_activity import read_events


def build_activity_panel(directory, require_admin, before_lock):
    ui.label('Logy MailShip').classes('ds-page-title')
    ui.label('Posledních 200 akcí workeru. Historie se ukládá od aktualizace workeru; starší technický log zůstává ve složce logy.').classes('ui-help')
    content = ui.column().classes('w-full')

    previous = None

    def refresh():
        nonlocal previous
        if not require_admin(silent=True):
            content.clear()
            previous = None
            return
        try:
            rows = read_events(directory)
        except Exception:
            content.clear()
            previous = None
            with content:
                ui.label('Historii nelze načíst. Zkontrolujte přístup ke složce logy.').props('role=alert')
            return
        if rows == previous:
            return
        previous = rows
        content.clear()
        with content:
            if not rows:
                ui.label('Zatím nejsou zaznamenané žádné akce. Aktualizujte a spusťte také worker.').classes('ui-help')
            for event in rows:
                with ui.card().classes('w-full'):
                    ui.label(f"{event['time'].replace('T', ' ')} · {event['task_name'] or 'Worker'}").classes('text-weight-bold')
                    ui.label(event['message']).classes('w-full').style('overflow-wrap:anywhere')
                    if event['report_date']:
                        ui.label(f"Přehled za {event['report_date']}").classes('ui-help')

    ui.button('Obnovit logy', icon='refresh', on_click=refresh).props('outline no-caps')
    before_lock.append(content.clear)
    # Read activity only while administrator access is unlocked.
    ui.timer(5, refresh)
