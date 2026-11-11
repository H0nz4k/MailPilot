"""Create an isolated v2 workspace from a 1.4 installation, without starting tasks."""
import json
import os
import tempfile
from dataclasses import replace
from pathlib import Path

from credential_store import sanitize_config
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
    templates = load_templates(template_file(source.parent))
    recipients = load_recipient_history(source.parent)
    ids = {p.id for p in profiles}
    if any(t.profile_id and t.profile_id not in ids for t in tasks):
        raise ValueError('Některé úlohy odkazují na chybějící profil. Import nebyl proveden.')
    settings = load_settings(settings_path(source.parent))
    settings['service_name'] = 'DataShip2Scheduler'
    settings['nssm_path'] = str(source.parent / 'nssm' / 'win64' / 'nssm.exe') if (source.parent / 'nssm' / 'win64' / 'nssm.exe').is_file() else settings['nssm_path']
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
        save_settings(settings_path(staging), settings)
        # Windows refuses to replace an existing nonempty destination directory.
        if target.exists():
            raise ValueError('Prostor DataShip 2 již existuje; import jej nepřepíše.')
        os.rename(staging, target)
    return {'config_path':str(target / 'config.json'), 'tasks':len(tasks), 'profiles':len(profiles), 'templates':len(templates)}
