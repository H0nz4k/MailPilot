"""Create an isolated v2 workspace from a 1.4 installation, without starting tasks."""
import json
import os
import shutil
import tempfile
from dataclasses import replace
from pathlib import Path

from credential_store import sanitize_config
from planovac import load_jobs, scheduler_config_path
from services.web_daily_profiles import load_profiles, profile_file
from services.web_mail_settings import load_settings, save_settings, settings_path
from services.web_mail_task_store import load_tasks, save_tasks, task_file
from services.pdf_templates import load_templates, template_file
from services.web_recipient_history import load_recipient_history, save_recipient_history


def import_workspace(source_config, destination):
    source = Path(source_config).resolve()
    target = Path(destination).resolve()
    if not source.is_file() or source.name.casefold() != 'config.json':
        raise ValueError('Vyberte existující soubor config.json verze 1.4.')
    if target.exists():
        raise ValueError('Prostor DataShip 2 již existuje; import jej nepřepíše.')
    if target == source.parent or source.parent in target.parents:
        raise ValueError('Prostor DataShip 2 musí být oddělený od původní instalace.')
    try:
        raw = json.loads(source.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError('Konfiguraci nelze načíst.') from exc
    if not isinstance(raw, dict):
        raise ValueError('Neplatná konfigurace.')
    profiles = load_profiles(profile_file(source.parent))
    tasks = load_tasks(task_file(source.parent))
    legacy_path = scheduler_config_path(source.parent)
    legacy_jobs = load_jobs(legacy_path, source.parent)
    legacy_payload = json.loads(legacy_path.read_text(encoding='utf-8')) if legacy_path.exists() else None
    if legacy_payload is not None and any(not isinstance(job, dict) for job in legacy_payload.get('jobs', [])):
        raise ValueError('Starý plánovač obsahuje neplatnou úlohu; import nebyl proveden.')
    templates = load_templates(template_file(source.parent))
    recipients = load_recipient_history(source.parent)
    ids = {p.id for p in profiles}
    if any(t.profile_id and t.profile_id not in ids for t in tasks):
        raise ValueError('Některé úlohy odkazují na chybějící profil. Import nebyl proveden.')
    settings = load_settings(settings_path(source.parent))
    settings['service_name'] = 'DataShip2Scheduler'
    bundled = source.parent / 'nssm' / 'win64' / 'nssm.exe'
    nssm = bundled if bundled.is_file() else Path(settings['nssm_path'])
    has_nssm = nssm.is_file()
    settings['nssm_path'] = str(target / 'nssm' / 'nssm.exe') if has_nssm else ''
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.dataship2-import-', dir=target.parent) as temp:
        staging = Path(temp) / 'workspace'
        staging.mkdir()
        (staging / 'config.json').write_text(json.dumps(sanitize_config(raw),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        if profile_file(source.parent).exists():
            profile_file(staging).write_text(json.dumps({'version':1,'profiles':[p.to_dict() for p in profiles]},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        if template_file(source.parent).exists():
            template_file(staging).write_text(json.dumps({'version':1,'templates':[t.to_dict() for t in templates]},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        if recipients:
            save_recipient_history(staging, recipients)
        save_tasks(task_file(staging), [replace(task, enabled=False) for task in tasks])
        if legacy_payload is not None:
            legacy_payload['jobs'] = [{**job, 'enabled': False} for job in legacy_payload.get('jobs', [])]
            scheduler_config_path(staging).write_text(json.dumps(legacy_payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        if has_nssm:
            (staging / 'nssm').mkdir()
            shutil.copyfile(nssm, staging / 'nssm' / 'nssm.exe')
        save_settings(settings_path(staging), settings)
        # Windows refuses to replace an existing nonempty destination directory.
        if target.exists():
            raise ValueError('Prostor DataShip 2 již existuje; import jej nepřepíše.')
        os.rename(staging, target)
    return {'config_path':str(target / 'config.json'), 'tasks':len(tasks), 'profiles':len(profiles), 'templates':len(templates), 'nssm_copied':has_nssm, 'legacy_jobs':len(legacy_jobs)}


def create_workspace(destination, database_values, database_password, admin_password, admin_repeat):
    """Provision an empty isolated workspace; no task or service is started."""
    from credential_store import get_admin_password, set_admin_password, set_password
    from services.config_io import normalize_database
    from services.database import probe_connection
    from services.web_mail_settings import save_settings
    from task_lock import task_store_lock
    import hmac
    target = Path(destination).resolve()
    if not isinstance(database_values, dict):
        raise ValueError('Vyplňte připojení k databázi.')
    database = normalize_database(database_values)
    if not isinstance(database_password,str) or not database_password:
        raise ValueError('Vyplňte heslo databáze.')
    if not isinstance(admin_password,str) or not admin_password.strip():
        raise ValueError('Vyplňte heslo administrace.')
    target.parent.mkdir(parents=True, exist_ok=True)
    with task_store_lock(target.parent, name='.dataship-v2-setup.lock'):
        if target.exists():
            raise ValueError('Prostor DataShip 2 již existuje; nastavení nebylo přepsáno.')
        stored = get_admin_password()
        if stored:
            if not hmac.compare_digest(admin_password.encode('utf-8'), stored.encode('utf-8')):
                raise ValueError('Nesprávné heslo administrace.')
        elif admin_password != admin_repeat or len(admin_password.strip()) < 4:
            raise ValueError('Zadejte shodné heslo administrace o délce alespoň 4 znaky.')
        connection = probe_connection(database, database_password, remember=False)
        with tempfile.TemporaryDirectory(prefix='.dataship2-setup-', dir=target.parent) as temp:
            staging = Path(temp) / 'workspace'
            staging.mkdir()
            (staging/'config.json').write_text(json.dumps({'databaze':database},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            save_tasks(task_file(staging), [])
            save_settings(settings_path(staging), {**load_settings(settings_path(staging)), 'service_name':'DataShip2Scheduler'})
            set_password(database, database_password)
            if not stored:
                set_admin_password(admin_password.strip())
            try:
                os.rename(staging,target)
            except OSError as exc:
                raise ValueError('Systémová hesla byla uložena, ale prostor aplikace se nepodařilo vytvořit.') from exc
    return {'config_path':str(target/'config.json'), 'subject':connection.subject_name or connection.database_name}
