"""Password-protected, minimal settings bridge for the isolated v2 workspace."""
from pathlib import Path
import hmac


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
