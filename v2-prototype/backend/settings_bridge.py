"""Password-protected, minimal settings bridge for the isolated v2 workspace."""
from pathlib import Path
import hmac
from task_lock import task_store_lock


def authorize(password):
    from credential_store import get_admin_password
    stored = get_admin_password()
    if not stored:
        raise ValueError('Heslo administrace zatím není nastavené. Nastavte jej nejprve v DataShip 1.4.')
    if not isinstance(password, str) or not hmac.compare_digest(password.encode('utf-8'), stored.encode('utf-8')):
        raise ValueError('Nesprávné heslo administrace.')


def workspace_path(config_path, workspace):
    path = Path(config_path).resolve()
    if path != Path(workspace).resolve() / 'config.json' or not path.is_file():
        raise ValueError('Nastavení lze upravovat pouze v odděleném prostoru DataShip 2.')
    return path


def read_settings(config_path, workspace, password):
    from env_store import get_resend_api_key
    from services.config_io import database_parameters, load_raw_config
    from services.web_mail_settings import DEFAULTS, load_settings, settings_path
    authorize(password)
    path = workspace_path(config_path, workspace)
    settings = load_settings(settings_path(path.parent))
    return {'database':database_parameters(load_raw_config(path)),
            'mail':{key:settings[key] for key in DEFAULTS},
            'resend_key_present':bool(get_resend_api_key())}


def save_mail(config_path, workspace, password, changes, resend_key=None):
    from env_store import EnvStoreError, set_resend_api_key
    from services.web_mail_settings import load_settings, save_settings, settings_path
    authorize(password)
    path = workspace_path(config_path, workspace)
    allowed = {'transport','smtp_host','smtp_port','smtp_security','smtp_username',
               'from_email','from_name','subject_template','body_template','nssm_path'}
    if not isinstance(changes, dict) or set(changes) - allowed:
        raise ValueError('Neplatné nastavení e-mailu.')
    if resend_key is not None and not isinstance(resend_key, str):
        raise ValueError('Neplatný API klíč.')
    with task_store_lock(path.parent):
        settings_file = settings_path(path.parent)
        settings = load_settings(settings_file)
        settings.update(changes)
        # Never accept or alter the isolated service's name via mail settings.
        settings['service_name'] = 'DataShip2Scheduler'
        from services.web_mail_smtp import normalize_recipient
        if str(settings.get('from_email') or '').strip():
            normalize_recipient(settings['from_email'])
        if settings.get('transport') == 'smtp' and settings.get('smtp_security') == 'none':
            raise ValueError('Pro SMTP vyberte STARTTLS nebo SSL/TLS.')
        save_settings(settings_file, settings)
        if resend_key and resend_key.strip():
            try:
                set_resend_api_key(resend_key)
            except (EnvStoreError, OSError) as exc:
                raise ValueError('Nastavení bylo uloženo, ale API klíč se nepodařilo uložit.') from exc
    return {'saved':True}


def save_connection(config_path, workspace, password, values, new_database_password=None):
    from credential_store import get_password, set_password
    from services.config_io import load_raw_config, normalize_database, save_raw_config
    from services.database import probe_connection
    authorize(password)
    path = workspace_path(config_path, workspace)
    if not isinstance(values, dict):
        raise ValueError('Neplatné nastavení databáze.')
    database = normalize_database(values)
    if new_database_password is not None and not isinstance(new_database_password, str):
        raise ValueError('Neplatné heslo databáze.')
    secret = new_database_password or get_password(database)
    if not secret:
        raise ValueError('Zadejte heslo databáze; pro toto připojení není uložené.')
    connection = probe_connection(database, secret, remember=False)
    with task_store_lock(path.parent):
        raw = load_raw_config(path)
        raw['databaze'] = database
        if new_database_password:
            set_password(database, new_database_password)
        try:
            save_raw_config(path, raw)
        except (OSError, ValueError) as exc:
            if new_database_password:
                raise ValueError('Heslo databáze bylo uloženo, ale konfiguraci se nepodařilo zapsat.') from exc
            raise
    return {'saved':True, 'subject':connection.subject_name or connection.database_name}


def category_settings(config_path, workspace, password):
    from services.config_io import load_raw_config
    from services.database import probe_connection
    from pocty_nastaveni import all_client_categories, peek_client_categories
    from legacy_bridge import configuration
    authorize(password)
    path = workspace_path(config_path, workspace)
    config = configuration(str(path))
    db = dict(config.database)
    secret = db.pop('password')
    info = probe_connection(db, secret, remember=False)
    raw = load_raw_config(path)
    return {'all':all_client_categories(raw), 'selected':peek_client_categories(raw),
            'available':[{'code':code,'name':name or code} for code,name in info.categories]}


def save_category_settings(config_path, workspace, password, use_all, selected):
    from services.config_io import load_raw_config, save_raw_config
    authorize(password)
    path = workspace_path(config_path, workspace)
    if not isinstance(use_all, bool) or not isinstance(selected, list) or any(not isinstance(c,str) or not c for c in selected):
        raise ValueError('Neplatný výběr kategorií.')
    with task_store_lock(path.parent):
        options = category_settings(str(path), workspace, password)
        available = {item['code'] for item in options['available']}
        if not use_all and (not selected or not set(selected).issubset(available)):
            raise ValueError('Vyberte alespoň jednu dostupnou kategorii.')
        raw = load_raw_config(path)
        block = raw.get('poctyemailem') or {}
        if not isinstance(block, dict):
            raise ValueError('Neplatné nastavení kategorií.')
        raw['poctyemailem'] = {**block,'vsechny_kategorie':use_all,'povolene_kategorie':list(dict.fromkeys(selected))}
        save_raw_config(path, raw)
    return {'saved':True}


def admin_password_status(config_path, workspace):
    from credential_store import get_admin_password
    workspace_path(config_path, workspace)
    return {'configured':bool(get_admin_password())}


def initialize_admin_password(config_path, workspace, password, repeat):
    from credential_store import get_admin_password, set_admin_password
    from task_lock import task_store_lock
    workspace_path(config_path, workspace)
    if not isinstance(password, str) or password != repeat or len(password.strip()) < 4:
        raise ValueError('Zadejte shodné heslo administrace o délce alespoň 4 znaky.')
    with task_store_lock(workspace):
        if get_admin_password():
            raise ValueError('Heslo administrace již existuje; přihlaste se existujícím heslem.')
        set_admin_password(password.strip())
    return {'configured':True}


def change_admin_password(config_path, workspace, password, new_password, repeat):
    from credential_store import set_admin_password
    workspace_path(config_path, workspace)
    authorize(password)
    if not isinstance(new_password, str) or new_password != repeat or len(new_password.strip()) < 4:
        raise ValueError('Zadejte shodné nové heslo o délce alespoň 4 znaky.')
    set_admin_password(new_password.strip())
    return {'changed':True}


def read_activity(config_path, workspace, password):
    from services.web_activity import read_events
    authorize(password)
    path = workspace_path(config_path, workspace)
    return read_events(path.parent, limit=200)
