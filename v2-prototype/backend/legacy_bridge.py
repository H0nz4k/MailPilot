"""Bridge from DataShip 2 to the configuration and services of DataShip 1.4."""
from dataclasses import replace
from datetime import date
from pathlib import Path
from uuid import uuid4
from task_lock import task_store_lock

from services.database import probe_connection
from stravovaci_sestava import load_config, fetch_report, create_pdf


def configuration(path):
    if not isinstance(path, str) or not path.strip():
        raise ValueError('Vyberte konfigurační soubor DataShip 1.4.')
    return load_config(Path(path), date_override=date.today().strftime('%d.%m.%Y'))


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


def period_filter_options(path, start, end):
    from stravovaci_sestava import available_meal_types, available_delivery_types
    config = configuration(path)
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if not 0 <= (last - first).days <= 365:
        raise ValueError('Zadejte období nejvýše 366 dní.')
    meals = set()
    for year in range(first.year, last.year + 1):
        meals.update(available_meal_types(config.database, date(year, 1, 1)))
    return {'meals':sorted(meals, key=str.casefold),
            'deliveries':list(available_delivery_types(config.database))}


def collection(request, output_dir):
    config = configuration(request.get('config_path'))
    start, end = date.fromisoformat(request['start']), date.fromisoformat(request['end'])
    if not 0 <= (end - start).days <= 365:
        raise ValueError('Období musí obsahovat nejvýše 366 dní a datum do nesmí předcházet datu od.')
    status = request.get('status')
    if status not in ('both', 'collected', 'uncollected'):
        raise ValueError('Neplatný stav odběru.')
    category = request.get('category', 'all')
    selected = request.get('categories')
    if selected is not None:
        if not isinstance(selected, list) or not selected or any(not isinstance(item,str) for item in selected):
            raise ValueError('Vyberte alespoň jednu kategorii.')
        if config.categories and not set(selected).issubset(config.categories):
            raise ValueError('Kategorie není povolená konfigurací.')
        categories = tuple(dict.fromkeys(selected))
    elif category != 'all':
        if config.categories and category not in config.categories:
            raise ValueError('Kategorie není povolená konfigurací.')
        categories = (category,)
    else:
        categories = config.categories
    meals, deliveries = request.get('meals'), request.get('deliveries')
    if meals is not None or deliveries is not None:
        options = period_filter_options(request['config_path'],request['start'],request['end'])
        for selected, key in ((meals,'meals'),(deliveries,'deliveries')):
            if selected is not None and (not isinstance(selected,list) or not selected or
                    any(not isinstance(value,str) or value not in options[key] for value in selected)):
                raise ValueError('Vyberte alespoň jednu dostupnou možnost filtru.')
    by_category = request.get('show_by_categories', True)
    if not isinstance(by_category, bool):
        raise ValueError('Neplatná volba souhrnu kategorií.')
    config = replace(config, report_date=start, report_end_date=end, categories=categories,
                     collection_status=status, category_separation=False, show_by_categories=by_category,
                     meal_type=meals, delivery_types=tuple(deliveries or ()))
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


def task_revision(task):
    import hashlib
    import json
    value = json.dumps(task.to_dict(), ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def require_current_revision(task, revision):
    if revision is not None and revision != task_revision(task):
        raise ValueError('Úloha se mezitím změnila. Obnovte seznam a úpravu zopakujte.')


def imported_scheduler_jobs(path, workspace):
    """Expose preserved legacy jobs without executing their launchers."""
    from settings_bridge import workspace_path
    from planovac import ACTION_LABELS, format_schedule, load_jobs, scheduler_config_path
    config_path = workspace_path(path, workspace)
    return [{'name': job.name, 'action': ACTION_LABELS[job.action], 'schedule': format_schedule(replace(job, enabled=True)),
             'convertible': job.action == 'poctyemailem' and job.schedule_type == 'daily'}
            for job in load_jobs(scheduler_config_path(config_path.parent), config_path.parent)]


def legacy_job_wizard(path, workspace, name):
    """Prepare, but do not save or enable, a converted daily email job."""
    from settings_bridge import workspace_path
    from planovac import load_jobs, scheduler_config_path
    from services.web_meal_types import meal_filter_values
    from services.config_io import load_raw_config
    config_path = workspace_path(path, workspace)
    job = next((item for item in load_jobs(scheduler_config_path(config_path.parent), config_path.parent)
                if item.name == name), None)
    if job is None or job.action != 'poctyemailem' or job.schedule_type != 'daily':
        raise ValueError('Tuto starší úlohu zatím nelze převést průvodcem.')
    profile = legacy_global_profile(str(config_path), job.name)
    options = filter_options(str(config_path), date.today().isoformat())
    meal_names = {item.casefold(): item for item in options['meals']}
    raw = load_raw_config(config_path)
    recipients = raw.get('mail_prijemci') or []
    if isinstance(recipients, str):
        recipients = [recipients]
    if not isinstance(recipients, list) or any(not isinstance(item, str) for item in recipients):
        raise ValueError('Příjemce staré úlohy nelze načíst; nastavte je ručně.')
    values = {'name':job.name, 'date':date.today().isoformat(), 'categories':list(profile.categories),
              'meals':[meal_names.get(value.casefold(), value) for value in meal_filter_values(profile.meal_type)] or None,
              'deliveries':list(profile.delivery_types) or None,
              'content':'names' if profile.show_diner_list else 'counts', 'mode':'today',
              'output':'email', 'recipients':', '.join(recipients), 'time':job.time,
              'enabled':False, 'cooking':raw.get('mail_jen_varne_dny', False), 'calendar_mode':'report', 'calendars':[]}
    for field in ('category_separation','show_by_categories','show_by_norms','show_delivery_summary',
                  'delivery_show_names','delivery_page_per_type','pdf_orientation','pdf_bold','pdf_compact_rows',
                  'pdf_data_font_size','pdf_label_font_size','language','menu_list_number','pdf_layout','pdf_page_breaks'):
        values[field] = getattr(profile, field)
    return values


def tasks(path):
    from services.web_mail_task_store import load_tasks, task_file
    from services.web_worker_status import observed_status
    directory = Path(path).parent
    return [{**task.to_dict(), 'time': task.send_time, 'status': observed_status(directory, task),
             'output': task.output_mode, 'revision': task_revision(task)} for task in load_tasks(task_file(directory))]


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
    template_settings = {}
    template_id = data.get('pdf_template_id')
    if template_id:
        from services.pdf_templates import load_templates, template_file
        template = next((t for t in load_templates(template_file(Path(path).parent)) if t.id == template_id), None)
        if template is None:
            raise ValueError('Šablona PDF již neexistuje. Vyberte ji znovu.')
        template_settings = template.settings
    profile = DailyProfile.from_dict({**template_settings, 'name':data.get('name'), 'categories':categories,
                 'meal_type':selected_meals, 'delivery_types':selected_deliveries or (), 'show_diner_list':content != 'counts', 'collection_status':status,
                 'category_separation':data.get('category_separation', False),
                 'show_by_categories':data.get('show_by_categories', True),
                 'show_by_norms':data.get('show_by_norms', True),
                 'show_delivery_summary':data.get('show_delivery_summary', False),
                 'delivery_show_names':data.get('delivery_show_names', False),
                 'delivery_page_per_type':data.get('delivery_page_per_type', False),
                 'pdf_orientation':data.get('pdf_orientation'), 'pdf_bold':data.get('pdf_bold'),
                 'pdf_compact_rows':data.get('pdf_compact_rows', False),
                 **{key:data[key] for key in ('pdf_data_font_size','pdf_label_font_size','language','menu_list_number','pdf_layout','pdf_page_breaks') if key in data and data[key] is not None}})
    if profile.delivery_page_per_type and any('delivery' in row and len(row)==2 for row in profile.pdf_layout):
        raise ValueError('Pro samostatné stránky typů výdeje umístěte tento blok na vlastní řádek.')
    return profile


def save_report_profile(path, workspace, data):
    """Save a new standalone report without creating or modifying a task."""
    from services.web_daily_profiles import save_profile, profile_file
    from settings_bridge import workspace_path
    config_path = workspace_path(path, workspace)
    profile = profile_for_wizard(str(config_path), data)
    with task_store_lock(config_path.parent):
        save_profile(profile_file(config_path.parent), profile)
    return {'id': profile.id, 'name': profile.name}


def update_report_profile(path, workspace, data, profile_id, revision):
    """Update one saved report after checking its revision and category access."""
    from services.web_daily_profiles import load_profiles, save_profile, profile_file
    from settings_bridge import workspace_path
    config_path = workspace_path(path, workspace)
    updated = profile_for_wizard(str(config_path), data)
    allowed = {item['code'] for item in info(str(config_path))['categories']}
    with task_store_lock(config_path.parent):
        original = next((p for p in load_profiles(profile_file(config_path.parent)) if p.id == profile_id), None)
        if original is None:
            raise ValueError('Uložený přehled již neexistuje.')
        if not isinstance(revision, str) or revision != task_revision(original):
            raise ValueError('Přehled se mezitím změnil. Načtěte jej znovu.')
        if not set(original.categories).issubset(allowed):
            raise ValueError('Přehled obsahuje nepovolené kategorie a nelze jej změnit.')
        updated = replace(updated, id=original.id)
        save_profile(profile_file(config_path.parent), updated)
    return {'id': updated.id, 'name': updated.name, 'revision': task_revision(updated)}


def saved_report_profiles(path):
    """Return reusable report settings; permissions are rechecked on save/preview."""
    from services.web_daily_profiles import load_profiles, profile_file
    from services.web_meal_types import meal_filter_values
    configuration(path)
    allowed = {item['code'] for item in info(path)['categories']}
    results = []
    for profile in load_profiles(profile_file(Path(path).parent)):
        categories = [code for code in profile.categories if code in allowed]
        if not categories:
            continue
        values = profile.to_dict()
        values.update({
            'categories': categories,
            'restricted': len(categories) != len(profile.categories),
            'revision': task_revision(profile),
            'meals': list(meal_filter_values(profile.meal_type)) or None,
            'deliveries': list(profile.delivery_types) or None,
            'content': 'collection' if profile.collection_status else 'names' if profile.show_diner_list else 'counts',
            'collection': profile.collection_status or 'both',
        })
        results.append(values)
    return results


def legacy_global_profile(path, name):
    """Snapshot the effective global report settings used by a profile-less task."""
    from services.web_daily_profiles import DailyProfile
    config = configuration(path)
    categories = list(config.categories) or [item['code'] for item in info(path)['categories']]
    fields = ('meal_type', 'delivery_types', 'category_separation', 'show_by_categories',
              'show_by_norms', 'show_diner_list', 'show_delivery_summary', 'delivery_show_names',
              'delivery_page_per_type', 'pdf_orientation', 'pdf_data_font_size', 'pdf_label_font_size',
              'pdf_bold', 'language', 'menu_list_number', 'pdf_compact_rows', 'pdf_layout', 'pdf_page_breaks')
    return DailyProfile.from_dict({'id': 'legacy-global', 'name': name, 'categories': categories,
                                   **{key: getattr(config, key) for key in fields}})


def wizard_edit_data(path, task_id):
    from services.web_daily_profiles import load_profiles, profile_file
    from services.web_mail_task_store import load_tasks, task_file
    from services.web_meal_types import meal_filter_values
    configuration(path)
    directory = Path(path).parent
    task = next((t for t in load_tasks(task_file(directory)) if t.id == task_id), None)
    if task is None:
        raise ValueError('Úloha již neexistuje.')
    if task.report != 'daily':
        raise ValueError('Tento typ starší úlohy není podporován plánovačem.')
    profile = (next((p for p in load_profiles(profile_file(directory)) if p.id == task.profile_id), None)
               if task.profile_id else legacy_global_profile(path, task.name))
    if profile is None:
        raise ValueError('Uložený profil úlohy neexistuje.')
    options = filter_options(path, date.today().isoformat())
    meal_names = {name.casefold(): name for name in options['meals']}
    meals = [meal_names.get(value.casefold(), value) for value in meal_filter_values(profile.meal_type)]
    mode = task.date_mode
    days = abs(task.day_offset)
    if mode == 'offset' and task.day_offset < 0:
        mode = 'history'
    values = {'name': task.name, 'date': date.today().isoformat(), 'categories': list(profile.categories),
              'meals': meals or None, 'deliveries': list(profile.delivery_types) or None,
              'content': 'collection' if profile.collection_status else 'names' if profile.show_diner_list else 'counts',
              'collection':profile.collection_status or 'both', 'mode':mode, 'days':str(days),
              'fixed_date':task.fixed_date or '', 'output':task.output_mode,
              'recipients':', '.join(task.recipients), 'directory':task.output_directory or '',
              'filename':task.output_filename, 'time':task.send_time, 'enabled':task.enabled,
              'cooking':task.only_cooking_days,
              'calendar_mode':'all' if task.cooking_meal_type == '*' else 'selected' if task.cooking_meal_type else 'report',
              'calendars': ([task.cooking_meal_type] if isinstance(task.cooking_meal_type, str) and task.cooking_meal_type != '*'
                            else list(task.cooking_meal_type) if isinstance(task.cooking_meal_type, tuple) else [])}
    if not task.profile_id and task.cooking_meal_type is None and (task.only_cooking_days or task.date_mode == 'next_cooking_day'):
        from services.web_mail_cooking_days import task_calendar_type
        calendar = task_calendar_type(Path(path), task)
        values['calendar_mode'] = 'all' if calendar is None else 'selected'
        values['calendars'] = [] if calendar is None else list(calendar) if isinstance(calendar, tuple) else [calendar]
    for field in ('category_separation','show_by_categories','show_by_norms','show_delivery_summary',
                  'delivery_show_names','delivery_page_per_type','pdf_orientation','pdf_bold','pdf_compact_rows',
                  'pdf_data_font_size','pdf_label_font_size','language','menu_list_number','pdf_layout','pdf_page_breaks'):
        values[field] = getattr(profile, field)
    return {'data':values, 'id':task.id, 'revision':task_revision(task), 'profile_revision':task_revision(profile), 'legacy_global':not bool(task.profile_id)}


def preserve_profile(original, profile, revision):
    from services.web_daily_profiles import DailyProfile
    if revision != task_revision(original):
        raise ValueError('Profil úlohy se mezitím změnil. Obnovte seznam a úpravu zopakujte.')
    fields = ('name','categories','meal_type','delivery_types','show_diner_list','collection_status',
              'category_separation','show_by_categories','show_by_norms','show_delivery_summary',
              'delivery_show_names','delivery_page_per_type','pdf_orientation','pdf_bold','pdf_compact_rows',
              'pdf_data_font_size','pdf_label_font_size','language','menu_list_number','pdf_layout','pdf_page_breaks')
    values = original.to_dict()
    changed = profile.to_dict()
    values.update({key:changed[key] for key in fields})
    values['id'] = profile.id
    return DailyProfile.from_dict(values)


def cooking_calendars(path):
    from services.web_mail_cooking_days import available_cooking_calendars
    configuration(path)
    return list(available_cooking_calendars(Path(path)))


def validate_wizard_calendars(path, data):
    if data.get('calendar_mode', 'report') == 'selected':
        available = {name.casefold() for name in cooking_calendars(path)}
        if any(name.casefold() not in available for name in data['calendars']):
            raise ValueError('Vybraný kalendář varných dnů již není dostupný. Obnovte seznam.')


def task_for_wizard(data, profile, *, preview=False):
    from services.collection_status import validate_task_history
    from services.web_mail_tasks import MailTask
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
    if mode not in ('today', 'tomorrow', 'after_tomorrow', 'offset', 'yesterday', 'history', 'next_cooking_day', 'fixed'):
        raise ValueError('Neplatný den přehledu.')
    calendar_mode = data.get('calendar_mode', 'report')
    calendars = data.get('calendars', [])
    if calendar_mode not in ('report', 'all', 'selected'):
        raise ValueError('Neplatný výběr kalendářů.')
    if calendar_mode == 'selected' and (not isinstance(calendars, list) or not calendars or any(not isinstance(v, str) or not v.strip() for v in calendars)):
        raise ValueError('Vyberte alespoň jeden kalendář varných dnů.')
    raw = {'cooking_meal_type': '*' if calendar_mode == 'all' else calendars if calendar_mode == 'selected' else None,
           'name':data.get('name'), 'recipients':(['preview@example.invalid'] if preview else data.get('recipients', '').replace(';', ' ').replace(',', ' ').split()),
           'report':'daily', 'send_time':data.get('time'), 'enabled':data.get('enabled', False),
           'date_mode':'offset' if mode in offsets else mode, 'day_offset':offsets.get(mode, 0),
           'fixed_date':data.get('fixed_date') if mode == 'fixed' else None,
           'profile_id':profile.id, 'only_cooking_days':data.get('cooking', False),
           'output_mode':'email' if preview else data.get('output'), 'output_directory':data.get('directory'),
           'output_filename':data.get('filename')}
    task = MailTask.from_dict(raw)
    validate_task_history(task, status)
    return task


def save_task(path, data):
    from datetime import datetime
    from services.web_daily_profiles import profile_file, save_profile
    from services.web_mail_tasks import next_send_at
    from services.web_mail_task_store import load_tasks, save_tasks, task_file

    profile = profile_for_wizard(path, data)
    task = task_for_wizard(data, profile)
    validate_wizard_calendars(path, data)
    # Match 1.4: no catch-up on the day when the configured time has already passed.
    upcoming = next_send_at(replace(task, enabled=True), datetime.now())
    task = replace(task, first_send_date=upcoming.date().isoformat())
    directory = Path(path).parent
    with task_store_lock(directory):
        existing = load_tasks(task_file(directory))
        edit_id = data.get('edit_id')
        if edit_id:
            from services.web_daily_profiles import load_profiles
            original = next((item for item in existing if item.id == edit_id), None)
            if original is None:
                raise ValueError('Úloha již neexistuje.')
            if not isinstance(data.get('revision'), str):
                raise ValueError('Chybí verze upravované úlohy. Obnovte seznam.')
            require_current_revision(original, data['revision'])
            original_profile = (next((item for item in load_profiles(profile_file(directory)) if item.id == original.profile_id), None)
                                if original.profile_id else legacy_global_profile(path, original.name))
            if original_profile is None or original.report != 'daily':
                raise ValueError('Původní profil úlohy neexistuje nebo jej nelze upravit.')
            profile = preserve_profile(original_profile, profile, data.get('profile_revision'))
            first_send = (original.first_send_date if original.enabled and task.enabled and original.send_time == task.send_time
                          else max(task.first_send_date, original.first_send_date or task.first_send_date))
            task = replace(task, id=original.id, first_send_date=first_send)
            save_profile(profile_file(directory), profile)
            save_tasks(task_file(directory), [task if item.id == edit_id else item for item in existing])
        else:
            save_profile(profile_file(directory), profile)
            save_tasks(task_file(directory), existing + [task])
    from services.web_worker_status import observed_status
    return {'task':task.to_dict(), 'status':observed_status(directory, task), 'next_run':upcoming.isoformat()}


def set_task_enabled(path, task_id, enabled, revision=None):
    from datetime import datetime
    from services.web_mail_task_store import load_tasks, save_tasks, task_file
    from services.web_mail_tasks import next_send_at
    if not isinstance(enabled, bool) or not isinstance(task_id, str):
        raise ValueError('Neplatná změna stavu úlohy.')
    configuration(path)
    target = task_file(Path(path).parent)
    with task_store_lock(target.parent):
        existing = load_tasks(target)
        task = next((task for task in existing if task.id == task_id), None)
        if task is None:
            raise ValueError('Úloha již neexistuje.')
        require_current_revision(task, revision)
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


def update_task(path, task_id, changes, revision=None):
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
    with task_store_lock(directory):
        existing = load_tasks(target)
        original = next((item for item in existing if item.id == task_id), None)
        if original is None:
            raise ValueError('Úloha již neexistuje.')
        require_current_revision(original, revision)
        updated = MailTask.from_dict({**original.to_dict(), **changes})
        validate_task_history(updated, task_collection_status(directory, updated))
        if updated.send_time != original.send_time:
            next_run = next_send_at(replace(updated, enabled=True), datetime.now())
            first = next_run.date().isoformat()
            updated = replace(updated, first_send_date=max(first, original.first_send_date or first))
        save_tasks(target, [updated if item.id == task_id else item for item in existing])
    return {'id':updated.id}


def registered_scheduler(path, *, allow_moved=False):
    """Verify the worker and configuration before changing a service."""
    import shlex
    from pathlib import PureWindowsPath
    from services.web_branding import WORKER_EXE_NAME
    from services.web_mail_nssm import _service_setup, _run_nssm
    config_path = Path(path).resolve()
    configuration(path)
    nssm, name = _service_setup(config_path.parent)
    base = [str(nssm)]
    program = _run_nssm(base + ['get', name, 'Application']).strip().strip('"')
    program_name = PureWindowsPath(program).name.casefold()
    if program_name not in (WORKER_EXE_NAME.casefold(), 'dataship-v2-engine.exe'):
        raise ValueError('Služba nepoužívá worker DataShipu; zůstala beze změny.')
    if program_name == 'dataship-v2-engine.exe':
        import sys
        if not getattr(sys, 'frozen', False) or (not allow_moved and PureWindowsPath(program) != PureWindowsPath(str(Path(sys.executable).resolve()))):
            raise ValueError('Služba odkazuje na jinou instalaci DataShip 2; zůstala beze změny.')
    parameters = _run_nssm(base + ['get', name, 'AppParameters'])
    args = [part.strip('"') for part in shlex.split(parameters, posix=False)]
    prefix = ['--worker'] if program_name == 'dataship-v2-engine.exe' else []
    if len(args) != len(prefix)+2 or args[:len(prefix)] != prefix or args[-2] != '--config' or PureWindowsPath(args[-1]) != PureWindowsPath(str(config_path)):
        raise ValueError('Služba používá jinou konfiguraci; zůstala beze změny.')
    return nssm, name, program_name


def control_scheduler(path, action):
    from services.web_mail_nssm import require_service_rights, service_command
    if action not in ('start', 'stop'):
        raise ValueError('Neznámá operace služby.')
    registered_scheduler(path)
    require_service_rights(action)
    return {'message': service_command(Path(path).resolve().parent, action)}


def preview_wizard(path, data, output_dir):
    from automaticky_export import read_saved_settings
    from services.web_daily_profiles import apply_profile
    config = configuration(path)
    profile = profile_for_wizard(path, data)
    if data.get('edit_id'):
        from services.web_daily_profiles import load_profiles, profile_file
        from services.web_mail_task_store import load_tasks, task_file
        directory = Path(path).parent
        task = next((t for t in load_tasks(task_file(directory)) if t.id == data['edit_id']), None)
        if task is None:
            raise ValueError('Úloha již neexistuje.')
        require_current_revision(task, data.get('revision'))
        original = (next((p for p in load_profiles(profile_file(directory)) if p.id == task.profile_id), None)
                    if task.profile_id else legacy_global_profile(path, task.name))
        if original is None:
            raise ValueError('Původní profil úlohy neexistuje.')
        profile = preserve_profile(original, profile, data.get('profile_revision'))
    raw = read_saved_settings(Path(path))
    config = apply_profile(replace(config, report_date=date.fromisoformat(data['date']), report_end_date=None), profile, raw)
    report = fetch_report(config)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / f'Náhled-přehledu-{uuid4().hex[:8]}.pdf'
    create_pdf(config, report, output_path=path)
    return {'pdf': str(path), 'portions': sum(item.portions for item in report.menus)}


def delete_task(path, task_id, revision):
    from services.web_mail_task_store import load_tasks, save_tasks, task_file
    if not isinstance(task_id, str) or not isinstance(revision, str):
        raise ValueError('Chybí verze úlohy. Obnovte seznam.')
    configuration(path)
    target = task_file(Path(path).parent)
    with task_store_lock(target.parent):
        existing = load_tasks(target)
        task = next((item for item in existing if item.id == task_id), None)
        if task is None:
            raise ValueError('Úloha již neexistuje.')
        require_current_revision(task, revision)
        # Profiles may be shared with another task or used independently.
        save_tasks(target, [item for item in existing if item.id != task_id])
    return {'id':task_id}


def install_scheduler(path, workspace):
    """Install a separate stopped v2 service; never replace or start an existing service."""
    import sys
    from services.web_mail_nssm import _service_setup, _run_nssm, require_service_rights
    config_path = Path(path).resolve()
    if config_path != (Path(workspace).resolve() / 'config.json'):
        raise ValueError('Samostatnou službu lze instalovat pouze pro oddělený prostor DataShip 2.')
    configuration(path)
    if not getattr(sys, 'frozen', False) or Path(sys.executable).name.casefold() != 'dataship-v2-engine.exe':
        raise ValueError('Instalace vyžaduje sestavenou desktopovou aplikaci DataShip 2.')
    nssm, name = _service_setup(config_path.parent)
    if name != 'DataShip2Scheduler':
        raise ValueError('Název služby musí být DataShip2Scheduler; nastavení služby nebylo změněno.')
    require_service_rights('install')
    base = [str(nssm)]
    commands = [base + ['install', name, str(Path(sys.executable).resolve()), '--worker', '--config', str(config_path)],
                base + ['set', name, 'AppDirectory', str(config_path.parent)],
                base + ['set', name, 'Start', 'SERVICE_AUTO_START'],
                base + ['set', name, 'AppExit', 'Default', 'Restart'],
                base + ['set', name, 'AppRestartDelay', '10000']]
    installed = False
    try:
        for command in commands:
            _run_nssm(command)
            installed = True
    except RuntimeError as exc:
        if installed:
            raise RuntimeError('Služba byla vytvořena, ale její nastavení není dokončené. ' + str(exc)) from exc
        raise
    return {'message':'Služba byla nainstalována a zůstává zastavená.'}


def remove_scheduler(path, workspace):
    from services.web_mail_nssm import _run_nssm, require_service_rights
    config_path = Path(path).resolve()
    if config_path != Path(workspace).resolve() / 'config.json':
        raise ValueError('Odstranit lze pouze službu odděleného prostoru DataShip 2.')
    nssm, name, program_name = registered_scheduler(path)
    if name != 'DataShip2Scheduler' or program_name != 'dataship-v2-engine.exe':
        raise ValueError('Neodpovídá název služby; služba nebyla změněna.')
    require_service_rights('remove')
    base = [str(nssm)]
    if _run_nssm(base + ['status', name]).strip() != 'SERVICE_STOPPED':
        _run_nssm(base + ['stop', name])
        if _run_nssm(base + ['status', name]).strip() != 'SERVICE_STOPPED':
            raise ValueError('Službu se nepodařilo zastavit; nebyla odstraněna.')
    _run_nssm(base + ['remove', name, 'confirm'])
    return {'message':'Služba DataShip 2 byla odstraněna; úlohy a nastavení zůstaly zachovány.'}


def repair_scheduler(path, workspace):
    import os
    import subprocess
    import sys
    from services.web_mail_nssm import _run_nssm, require_service_rights
    config_path = Path(path).resolve()
    if config_path != Path(workspace).resolve() / 'config.json':
        raise ValueError('Opravit lze pouze službu odděleného prostoru DataShip 2.')
    nssm, name, program_name = registered_scheduler(path, allow_moved=True)
    worker = Path(sys.executable).resolve()
    if name != 'DataShip2Scheduler' or program_name != 'dataship-v2-engine.exe' or worker.name.casefold() != 'dataship-v2-engine.exe':
        raise ValueError('Neodpovídá služba DataShip 2; služba nebyla změněna.')
    require_service_rights('repair')
    base = [str(nssm)]
    if _run_nssm(base + ['status', name]).strip() != 'SERVICE_STOPPED':
        raise ValueError('Před opravou službu zastavte.')
    sc = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'sc.exe'
    commands = [[str(sc), 'config', name, 'binPath=', f'"{nssm.resolve()}"'],
                base + ['set', name, 'Application', str(worker)],
                base + ['set', name, 'AppParameters', subprocess.list2cmdline(['--worker','--config',str(config_path)])],
                base + ['set', name, 'AppDirectory', str(config_path.parent)]]
    try:
        for command in commands:
            _run_nssm(command)
    except RuntimeError as exc:
        raise RuntimeError('Oprava služby není dokončena. ' + str(exc)) from exc
    return {'message':'Cesty služby byly opraveny. Služba zůstává zastavená.'}


def send_collection(request, output_dir):
    """Create and send a one-off collection PDF; never create a scheduled task."""
    from automaticky_export import read_saved_settings
    from env_store import get_resend_api_key
    from mail_service import normalize_recipient, normalize_recipients, send_pdf_via_mailsender
    from services.collection_status import COLLECTION_TITLES
    from services.web_mail_settings import load_settings, settings_path
    from services.web_mail_smtp import smtp_send
    recipients = normalize_recipients(request.get('recipients'))
    path = Path(request['config_path'])
    settings = load_settings(settings_path(path.parent))
    raw = read_saved_settings(path)
    configuration(str(path))
    label = COLLECTION_TITLES.get(request.get('status'))
    if not label:
        raise ValueError('Neplatný stav odběru.')
    first, last = date.fromisoformat(request['start']), date.fromisoformat(request['end'])
    date_label = first.strftime('%d.%m.%Y') if first == last else f'{first:%d.%m.%Y} – {last:%d.%m.%Y}'
    fields = {'report':label, 'date':date_label}
    subject = settings['subject_template'].format(**fields)
    body = settings['body_template'].format(**fields)
    if settings['transport'] == 'smtp':
        transport = 'smtp'
    elif settings['transport'] == 'resend':
        transport = 'resend'
        sender = normalize_recipient(settings['from_email'] or raw.get('mail_odesilatel'))
        api_key = get_resend_api_key()
        if not api_key:
            raise ValueError('Chybí Resend API klíč.')
    else:
        raise ValueError('Neznámý způsob odesílání.')
    result = collection({**request,'action':'legacy_pdf'}, output_dir)
    pdf = Path(result['pdf'])
    if transport == 'smtp':
        smtp_send(settings, recipients, subject, body, pdf)
    else:
        send_pdf_via_mailsender(recipients, subject, body, pdf, api_key=api_key, sender_email=sender)
    return {**result, 'sent':len(recipients)}


def save_pdf(source, destination, output_dir):
    """Save a generated PDF without overwriting an existing user file."""
    import os
    import shutil
    source_path = Path(source).resolve()
    output_path = Path(output_dir).resolve()
    if source_path.parent != output_path or source_path.suffix.casefold() != '.pdf' or not source_path.is_file():
        raise ValueError('Vyberte nejprve PDF vytvořené v DataShip 2.')
    target = Path(destination)
    if not target.is_absolute() or target.suffix.casefold() != '.pdf':
        raise ValueError('Zadejte úplnou cestu k novému souboru PDF.')
    target = target.resolve()
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError('Soubor již existuje. Zvolte jiný název, aby se nepřepsal.') from exc
    try:
        with os.fdopen(descriptor, 'wb') as output, source_path.open('rb') as original:
            shutil.copyfileobj(original, output)
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return {'path':str(target)}


def preview_schedule(path, data):
    from datetime import datetime
    from services.web_mail_tasks import next_send_at, target_date
    from services.web_mail_cooking_days import any_cooking_day_lookup, cooking_day_lookup, selected_cooking_day_lookup
    config = configuration(path)
    profile = profile_for_wizard(path, data)
    task = task_for_wizard(data, profile, preview=True)
    validate_wizard_calendars(path, data)
    if data.get('edit_id'):
        from services.web_mail_task_store import load_tasks, task_file
        from services.web_daily_profiles import load_profiles, profile_file
        directory = Path(path).parent
        original = next((t for t in load_tasks(task_file(directory)) if t.id == data['edit_id']), None)
        if original is None:
            raise ValueError('Úloha již neexistuje.')
        require_current_revision(original, data.get('revision'))
        original_profile = (next((p for p in load_profiles(profile_file(directory)) if p.id == original.profile_id), None)
                            if original.profile_id else legacy_global_profile(path, original.name))
        if original_profile is None:
            raise ValueError('Původní profil úlohy neexistuje.')
        preserve_profile(original_profile, profile, data.get('profile_revision'))
    upcoming = next_send_at(replace(task, enabled=True), datetime.now())
    if task.date_mode == 'next_cooking_day':
        meal = task.cooking_meal_type if task.cooking_meal_type is not None else profile.meal_type
        if meal == '*':
            meal = None
        lookup = any_cooking_day_lookup if meal is None else selected_cooking_day_lookup if isinstance(meal, tuple) else cooking_day_lookup
        args = (config.database,) if meal is None else (config.database, meal)
        with lookup(*args) as is_day:
            current = target_date(task, date.today(), is_cooking_day=is_day)
            next_day = target_date(task, upcoming.date(), is_cooking_day=is_day)
    else:
        current = target_date(task, date.today())
        next_day = target_date(task, upcoming.date())
    return {'today_report':current.isoformat(), 'next_run':upcoming.isoformat(timespec='minutes'),
            'next_report':next_day.isoformat(), 'only_cooking_days':task.only_cooking_days}


def pdf_templates(path):
    from services.pdf_templates import load_templates, template_file
    configuration(path)
    return [item.to_dict() for item in load_templates(template_file(Path(path).parent))]


def checked_report_files(sources, output_dir):
    if not isinstance(sources,list) or not sources or any(not isinstance(x,str) for x in sources):
        raise ValueError('Nejsou vybrány žádné vytvořené soubory.')
    root = Path(output_dir).resolve()
    files = [Path(x).resolve() for x in sources]
    directory = files[0].parent
    if (directory.parent != root or any(p.parent != directory or p.suffix.casefold() not in ('.pdf','.zip')
                                       or not p.is_file() for p in files)
            or len({p.name.casefold() for p in files}) != len(files)):
        raise ValueError('Lze použít pouze soubory jedné vytvořené sestavy.')
    return files


def save_report_files(sources, destination, output_dir):
    """Copy generated PDFs/ZIPs into a new directory without overwriting files."""
    import os
    import shutil
    import tempfile
    files = checked_report_files(sources, output_dir)
    target = Path(destination)
    if not target.is_absolute():
        raise ValueError('Zadejte úplnou cestu k nové výstupní složce.')
    target = target.resolve()
    if target.exists():
        raise ValueError('Výstupní složka již existuje. Zvolte jiný název.')
    if not target.parent.is_dir():
        raise ValueError('Nadřazená složka neexistuje.')
    with tempfile.TemporaryDirectory(prefix='.dataship2-save-',dir=target.parent) as tmp:
        staging = Path(tmp)/'output'
        staging.mkdir()
        for source in files:
            shutil.copyfile(source,staging/source.name)
        if target.exists():
            raise ValueError('Výstupní složka již existuje. Zvolte jiný název.')
        os.rename(staging,target)
    return {'directory':str(target),'files':[str(target/p.name) for p in files]}


def send_report_files(config_path, sources, recipients, report_type, period, output_dir):
    from automaticky_export import read_saved_settings
    from env_store import get_resend_api_key
    from mail_service import normalize_recipient, normalize_recipients, send_files_via_mailsender
    from services.web_mail_settings import load_settings, settings_path
    from services.web_mail_smtp import smtp_send_files
    if report_type not in ('Uzávěrka', 'Z 17-01') or not isinstance(period,str) or len(period)>30:
        raise ValueError('Neplatný typ sestavy.')
    recipients = normalize_recipients(recipients)
    files = checked_report_files(sources, output_dir)
    path = Path(config_path)
    configuration(str(path))
    raw = read_saved_settings(path)
    settings = load_settings(settings_path(path.parent))
    fields = {'report':report_type, 'date':period}
    subject, body = settings['subject_template'].format(**fields), settings['body_template'].format(**fields)
    if settings['transport'] == 'smtp':
        smtp_send_files(settings,recipients,subject,body,files)
    elif settings['transport'] == 'resend':
        sender = normalize_recipient(settings['from_email'] or raw.get('mail_odesilatel'))
        key = get_resend_api_key()
        if not key:
            raise ValueError('Chybí Resend API klíč.')
        send_files_via_mailsender(recipients,subject,body,files,api_key=key,sender_email=sender)
    else:
        raise ValueError('Neznámý způsob odesílání.')
    return {'sent':len(recipients)}


def save_pdf_template(path, workspace, data, name):
    from services.pdf_templates import PdfTemplate, DEFAULT_SETTINGS, load_templates, save_template, template_file
    from settings_bridge import workspace_path
    # Template editing is a normal report-design operation, not administration.
    config_path = workspace_path(path, workspace)
    config = configuration(str(config_path))
    profile = profile_for_wizard(str(config_path), data)
    if data.get('edit_id'):
        from services.web_daily_profiles import load_profiles, profile_file
        from services.web_mail_task_store import load_tasks, task_file
        task = next((t for t in load_tasks(task_file(config_path.parent)) if t.id == data['edit_id']), None)
        if task is None:
            raise ValueError('Úloha již neexistuje.')
        require_current_revision(task, data.get('revision'))
        original = (next((p for p in load_profiles(profile_file(config_path.parent)) if p.id == task.profile_id), None)
                    if task.profile_id else legacy_global_profile(str(config_path), task.name))
        if original is None:
            raise ValueError('Původní profil úlohy neexistuje.')
        profile = preserve_profile(original, profile, data.get('profile_revision'))
    values = dict(DEFAULT_SETTINGS)
    source_id = data.get('pdf_template_id')
    if source_id:
        source = next((t for t in load_templates(template_file(config_path.parent)) if t.id == source_id), None)
        if source is None:
            raise ValueError('Šablona PDF již neexistuje.')
        values.update(source.settings)
    values['pdf_layout'] = profile.pdf_layout
    values['pdf_page_breaks'] = profile.pdf_page_breaks
    for key in ('category_separation','show_by_categories','show_by_norms','show_diner_list',
                'show_delivery_summary','delivery_show_names','delivery_page_per_type',
                'pdf_compact_rows'):
        values[key] = getattr(profile,key)
    for key in ('pdf_orientation','pdf_data_font_size','pdf_label_font_size','pdf_bold'):
        value = getattr(profile,key)
        values[key] = value if value is not None else getattr(config,key)
    template = PdfTemplate.from_dict({'name':name,'settings':values})
    with task_store_lock(config_path.parent):
        saved = save_template(template_file(config_path.parent),template)
    return {'template':template.to_dict(), 'count':len(saved)}


def render_pdf_page(source, page_index, output_dir):
    import base64
    from services.pdf_preview import render_preview_page
    path = Path(source).resolve()
    if path.parent != Path(output_dir).resolve() or path.suffix.casefold() != '.pdf' or not path.is_file():
        raise ValueError('Náhled je dostupný jen pro vytvořené PDF.')
    image, count = render_preview_page(path.read_bytes(),page_index)
    return {'image':base64.b64encode(image).decode('ascii'),'pages':count,'page':page_index}
