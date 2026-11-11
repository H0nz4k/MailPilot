"""Bridge from DataShip 2 to the configuration and services of DataShip 1.4."""
from dataclasses import replace
from datetime import date
from pathlib import Path
from uuid import uuid4

from services.database import probe_connection
from stravovaci_sestava import load_config, fetch_report, create_pdf


def configuration(path):
    if not isinstance(path, str) or not path.strip():
        raise ValueError('Vyberte konfigurační soubor DataShip 1.4.')
    return load_config(Path(path), date_override=date.today().isoformat())


def info(path):
    config = configuration(path)
    db = dict(config.database)
    password = db.pop('password')
    connection = probe_connection(db, password, remember=False)
    allowed = set(config.categories)
    categories = [{'code': code, 'name': name or code} for code, name in connection.categories
                  if not allowed or code in allowed]
    return {'subject': connection.subject_name or connection.database_name, 'categories': categories}


def filter_options(path, report_date):
    from stravovaci_sestava import available_meal_types, available_delivery_types
    config = configuration(path)
    selected_date = date.fromisoformat(report_date)
    return {'meals': list(available_meal_types(config.database, selected_date)),
            'deliveries': list(available_delivery_types(config.database))}


def collection(request, output_dir):
    config = configuration(request.get('config_path'))
    start, end = date.fromisoformat(request['start']), date.fromisoformat(request['end'])
    if not 0 <= (end - start).days <= 365:
        raise ValueError('Období musí obsahovat nejvýše 366 dní a datum do nesmí předcházet datu od.')
    status = request.get('status')
    if status not in ('both', 'collected', 'uncollected'):
        raise ValueError('Neplatný stav odběru.')
    category = request.get('category', 'all')
    if category != 'all':
        if config.categories and category not in config.categories:
            raise ValueError('Kategorie není povolená konfigurací.')
        categories = (category,)
    else:
        categories = config.categories
    config = replace(config, report_date=start, report_end_date=end, categories=categories,
                     collection_status=status, category_separation=False, show_by_categories=True)
    report = fetch_report(config)
    rows = [{'date': r.order_date.isoformat(), 'name': r.name or '[bez jména]', 'number': r.diner_number,
             'category': r.category_name or r.category_code, 'meal': r.meal_type,
             'menu': r.menu, 'collected': r.collected} for r in report.diners]
    result = {'rows': rows, 'collected': sum(r.collected is True for r in report.diners),
              'uncollected': sum(r.collected is False for r in report.diners)}
    if request.get('action') == 'legacy_pdf':
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        path = output / f'Odběry-{start}-{end}-{uuid4().hex[:8]}.pdf'
        create_pdf(config, report, output_path=path)
        result['pdf'] = str(path)
    return result


def tasks(path):
    from services.web_mail_task_store import load_tasks, task_file
    from services.web_worker_status import observed_status
    directory = Path(path).parent
    return [{**task.to_dict(), 'time': task.send_time, 'status': observed_status(directory, task),
             'output': task.output_mode} for task in load_tasks(task_file(directory))]


def profile_for_wizard(path, data):
    from services.collection_status import validate_report_history
    from services.web_daily_profiles import DailyProfile
    configuration(path)
    available = {c['code'] for c in info(path)['categories']}
    selected_categories = data.get('categories')
    category = data.get('category', 'all')
    categories = (sorted(available) if category == 'all' else [category]) if selected_categories is None else selected_categories
    if not isinstance(categories, list) or any(not isinstance(c, str) for c in categories):
        raise ValueError('Neplatný výběr kategorií.')
    if not categories or any(c not in available for c in categories):
        raise ValueError('Vyberte alespoň jednu dostupnou a povolenou kategorii.')
    content = data.get('content')
    if content not in ('counts', 'names', 'collection'):
        raise ValueError('Neplatný obsah přehledu.')
    status = data.get('collection') if content == 'collection' else None
    preview_date = date.fromisoformat(data['date'])
    validate_report_history(preview_date, status)
    selected_meals = data.get('meals')
    selected_deliveries = data.get('deliveries')
    if selected_meals is not None or selected_deliveries is not None:
        options = filter_options(path, data['date'])
        for selected, key in ((selected_meals, 'meals'), (selected_deliveries, 'deliveries')):
            if selected is not None and (not isinstance(selected, list) or not selected or
                    any(not isinstance(item, str) or item not in options[key] for item in selected)):
                raise ValueError('Vyberte alespoň jednu dostupnou možnost filtru.')
    profile = DailyProfile.from_dict({'name':data.get('name'), 'categories':categories,
                 'meal_type':selected_meals, 'delivery_types':selected_deliveries or (), 'show_diner_list':content != 'counts', 'collection_status':status,
                 'category_separation':data.get('category_separation', False),
                 'show_by_categories':data.get('show_by_categories', True),
                 'show_by_norms':data.get('show_by_norms', True),
                 'show_delivery_summary':data.get('show_delivery_summary', False),
                 'delivery_show_names':data.get('delivery_show_names', False),
                 'delivery_page_per_type':data.get('delivery_page_per_type', False),
                 'pdf_orientation':data.get('pdf_orientation'), 'pdf_bold':data.get('pdf_bold'),
                 'pdf_compact_rows':data.get('pdf_compact_rows', False)})
    return profile


def save_task(path, data):
    from datetime import datetime
    from services.collection_status import validate_task_history
    from services.web_daily_profiles import profile_file, save_profile
    from services.web_mail_tasks import MailTask, next_send_at
    from services.web_mail_task_store import load_tasks, save_tasks, task_file

    profile = profile_for_wizard(path, data)
    status = profile.collection_status
    mode = data.get('mode')
    offsets = {'after_tomorrow': 2, 'yesterday': -1}
    if mode in ('offset', 'history'):
        try:
            days = int(data['days'])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError('Zadejte platný počet dní.') from exc
        if str(days) != str(data['days']) or not (1 if mode == 'history' else 0) <= days <= 370:
            raise ValueError('Zadejte platný počet dní.')
        offsets[mode] = -days if mode == 'history' else days
    if mode not in ('today', 'tomorrow', 'after_tomorrow', 'offset', 'yesterday', 'history', 'next_cooking_day'):
        raise ValueError('Neplatný den přehledu.')
    raw = {'name':data.get('name'), 'recipients':data.get('recipients', '').replace(';', ' ').replace(',', ' ').split(),
           'report':'daily', 'send_time':data.get('time'), 'enabled':data.get('enabled', False),
           'date_mode':'offset' if mode in offsets else mode, 'day_offset':offsets.get(mode, 0),
           'profile_id':profile.id, 'only_cooking_days':data.get('cooking', False),
           'output_mode':data.get('output'), 'output_directory':data.get('directory'),
           'output_filename':data.get('filename')}
    task = MailTask.from_dict(raw)
    validate_task_history(task, status)
    # Match 1.4: no catch-up on the day when the configured time has already passed.
    upcoming = next_send_at(replace(task, enabled=True), datetime.now())
    task = replace(task, first_send_date=upcoming.date().isoformat())
    directory = Path(path).parent
    existing = load_tasks(task_file(directory))
    save_profile(profile_file(directory), profile)
    save_tasks(task_file(directory), existing + [task])
    from services.web_worker_status import observed_status
    return {'task':task.to_dict(), 'status':observed_status(directory, task), 'next_run':upcoming.isoformat()}


def set_task_enabled(path, task_id, enabled):
    from datetime import datetime
    from services.web_mail_task_store import load_tasks, save_tasks, task_file
    from services.web_mail_tasks import next_send_at
    if not isinstance(enabled, bool) or not isinstance(task_id, str):
        raise ValueError('Neplatná změna stavu úlohy.')
    configuration(path)
    target = task_file(Path(path).parent)
    existing = load_tasks(target)
    task = next((task for task in existing if task.id == task_id), None)
    if task is None:
        raise ValueError('Úloha již neexistuje.')
    updated = replace(task, enabled=enabled)
    if enabled and not task.enabled:
        upcoming = next_send_at(updated, datetime.now())
        first = upcoming.date().isoformat()
        updated = replace(updated, first_send_date=max(first, task.first_send_date or first))
    save_tasks(target, [updated if item.id == task_id else item for item in existing])
    return {'id': updated.id, 'enabled': updated.enabled}


def scheduler_status(path):
    from services.web_mail_nssm import scheduler_installation_notice, service_command
    from services.web_worker_status import observed_status
    directory = Path(path).parent
    installation = scheduler_installation_notice(directory)
    try:
        service = service_command(directory, 'status')
    except (OSError, ValueError, RuntimeError) as exc:
        service = f'Stav služby nelze zjistit: {exc}'
    return {'worker': observed_status(directory), 'service': service, 'notice': installation}


def update_task(path, task_id, changes):
    from datetime import datetime
    from services.collection_status import validate_task_history
    from services.web_daily_profiles import task_collection_status
    from services.web_mail_tasks import MailTask, next_send_at
    from services.web_mail_task_store import load_tasks, save_tasks, task_file
    allowed = {'name', 'send_time', 'recipients', 'output_directory', 'output_filename',
               'date_mode', 'day_offset', 'only_cooking_days'}
    if not isinstance(task_id, str) or not isinstance(changes, dict) or set(changes) - allowed:
        raise ValueError('Neplatná úprava úlohy.')
    configuration(path)
    directory = Path(path).parent
    target = task_file(directory)
    existing = load_tasks(target)
    original = next((item for item in existing if item.id == task_id), None)
    if original is None:
        raise ValueError('Úloha již neexistuje.')
    updated = MailTask.from_dict({**original.to_dict(), **changes})
    validate_task_history(updated, task_collection_status(directory, updated))
    if updated.send_time != original.send_time:
        next_run = next_send_at(replace(updated, enabled=True), datetime.now())
        first = next_run.date().isoformat()
        updated = replace(updated, first_send_date=max(first, original.first_send_date or first))
    save_tasks(target, [updated if item.id == task_id else item for item in existing])
    return {'id':updated.id}


def control_scheduler(path, action):
    """Control only an existing 1.4 worker bound to the selected configuration."""
    import shlex
    from pathlib import PureWindowsPath
    from services.web_branding import WORKER_EXE_NAME
    from services.web_mail_nssm import _service_setup, _run_nssm, require_service_rights, service_command
    if action not in ('start', 'stop'):
        raise ValueError('Neznámá operace služby.')
    config_path = Path(path).resolve()
    configuration(path)
    nssm, name = _service_setup(config_path.parent)
    base = [str(nssm)]
    program = _run_nssm(base + ['get', name, 'Application']).strip().strip('"')
    if PureWindowsPath(program).name.casefold() != WORKER_EXE_NAME.casefold():
        raise ValueError('Služba nepoužívá worker DataShipu; zůstala beze změny.')
    parameters = _run_nssm(base + ['get', name, 'AppParameters'])
    args = [part.strip('"') for part in shlex.split(parameters, posix=False)]
    if len(args) != 2 or args[0] != '--config' or PureWindowsPath(args[1]) != PureWindowsPath(str(config_path)):
        raise ValueError('Služba používá jinou konfiguraci; zůstala beze změny.')
    require_service_rights(action)
    return {'message': service_command(config_path.parent, action)}


def preview_wizard(path, data, output_dir):
    from automaticky_export import read_saved_settings
    from services.web_daily_profiles import apply_profile
    config = configuration(path)
    profile = profile_for_wizard(path, data)
    raw = read_saved_settings(Path(path))
    config = apply_profile(replace(config, report_date=date.fromisoformat(data['date']), report_end_date=None), profile, raw)
    report = fetch_report(config)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / f'Náhled-přehledu-{uuid4().hex[:8]}.pdf'
    create_pdf(config, report, output_path=path)
    return {'pdf': str(path), 'portions': sum(item.portions for item in report.menus)}
