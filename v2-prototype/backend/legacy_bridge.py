"""Read-only access to the 1.4 configuration and report services for DataShip 2."""
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
    return [{'id': task.id, 'name': task.name, 'time': task.send_time,
             'enabled': task.enabled, 'status': observed_status(directory, task),
             'output': task.output_mode} for task in load_tasks(task_file(directory))]


def save_task(path, data):
    from datetime import datetime
    from services.collection_status import validate_report_history, validate_task_history
    from services.web_daily_profiles import DailyProfile, profile_file, save_profile
    from services.web_mail_tasks import MailTask, next_send_at
    from services.web_mail_task_store import load_tasks, save_tasks, task_file

    configuration(path)
    available = {c['code'] for c in info(path)['categories']}
    category = data.get('category')
    categories = sorted(available) if category == 'all' else [category]
    if not categories or any(c not in available for c in categories):
        raise ValueError('Vyberte alespoň jednu dostupnou a povolenou kategorii.')
    content = data.get('content')
    if content not in ('counts', 'names', 'collection'):
        raise ValueError('Neplatný obsah přehledu.')
    status = data.get('collection') if content == 'collection' else None
    preview_date = date.fromisoformat(data['date'])
    validate_report_history(preview_date, status)
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
    if data.get('meal') != 'all':
        raise ValueError('Výběr jednotlivého typu stravy zatím není připojen.')
    profile = DailyProfile.from_dict({'name':data.get('name'), 'categories':categories,
                 'meal_type':None, 'show_diner_list':content != 'counts', 'collection_status':status,
                 'category_separation':False, 'show_by_categories':True, 'show_by_norms':True})
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
