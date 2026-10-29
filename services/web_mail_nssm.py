"""NSSM service operations with Czech feedback and redirected Unicode output."""
from __future__ import annotations

import ctypes
from dataclasses import dataclass
import locale
import logging
import os
import re
import shlex
from threading import Lock
import subprocess
import sys
from pathlib import Path, PureWindowsPath

from services.web_mail_settings import load_settings, settings_path
from services.web_branding import WORKER_EXE_NAME

LOG = logging.getLogger(__name__)
ADMIN_HELP = ('Spusťte DataShip.exe jako správce Windows: zavřete aplikaci, '
              'klikněte na DataShip.exe pravým tlačítkem a zvolte „Spustit jako správce“. '
              'Heslo do nastavení DataShipu tato oprávnění nenahrazuje.')


def windows_admin_state() -> bool | None:
    if os.name != 'nt':
        return None
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return None


def require_service_rights(action: str) -> None:
    if os.name != 'nt':
        raise ValueError('Službu NSSM lze spravovat pouze ve Windows.')
    if action != 'status' and not ctypes.windll.shell32.IsUserAnAdmin():
        raise PermissionError(ADMIN_HELP)


def decode_nssm_output(value: bytes | str | None) -> str:
    if isinstance(value, str):
        return value.replace('\x00', '').strip()
    if not value:
        return ''
    if value.startswith((b'\xff\xfe', b'\xfe\xff')):
        return value.decode('utf-16', errors='replace').strip()
    if value.count(b'\x00') > len(value) // 4:
        return value.decode('utf-16-le', errors='replace').strip()
    try:
        return value.decode('utf-8').strip()
    except UnicodeDecodeError:
        return value.decode(locale.getpreferredencoding(False), errors='replace').strip()


def service_error_message(output: str, *, code: int | None = None) -> str:
    text = output.casefold()
    def has(number: int) -> bool:
        # NSSM exit codes themselves are not Windows error codes (notably 1/2).
        return code == number or bool(re.search(rf'(?:error|chyba|code|kód|winerror)\s*[:=]?\s*\[?{number}\b|[\[(]{number}[\])]', text))
    if has(5) or has(740) or any(s in text for s in ('access is denied', 'administrator', 'elevation', 'přístup byl odepřen')):
        return 'Windows nepovolil změnu služby. ' + ADMIN_HELP
    if has(1073) or 'already exists' in text or 'služba již existuje' in text:
        return 'Služba již existuje. Další službu neinstalujte. Po přesunu aplikace klikněte na „Opravit cesty služby“, jinak použijte „Spustit službu“.'
    if has(1060) or 'does not exist' in text or 'not installed' in text or ('služba' in text and 'neexistuje' in text):
        return 'Služba zatím není nainstalovaná. Nejprve klikněte na „Instalovat službu“.'
    if has(1069) or 'logon failure' in text:
        return 'Windows službu nepřihlásil. V nastavení služby zkontrolujte její účet a heslo.'
    if has(1058):
        return 'Služba je ve Windows zakázaná. Povolte její spouštění ve správě služeb.'
    if has(1056):
        return 'Služba již běží. Její stav ověříte tlačítkem „Stav“.'
    if has(1062):
        return 'Služba již je zastavená.'
    if has(1072):
        return 'Windows službu ještě odstraňuje. Zavřete správu služeb a zkuste operaci znovu.'
    if has(193) or 'not a valid win32' in text:
        return 'Soubor nelze spustit. Použijte přibalený 64bitový nssm.exe a DataShip-Worker.exe.'
    if has(2) or any(s in text for s in ('cannot find the file', 'file not found', 'nemůže nalézt uvedený soubor', 'nelze nalézt uvedený soubor')):
        return 'Windows nenalezl soubor potřebný ke spuštění služby. Po přesunu DataShipu zůstala pravděpodobně stará cesta ve Windows. Zkontrolujte NSSM a DataShip-Worker.exe a klikněte na „Opravit cesty služby“.'
    if 'služba nebyla spuštěna' in text:
        return 'Služba je zastavená. Při chybě chybějícího souboru nejprve použijte „Opravit cesty služby“, potom „Spustit službu“.'
    if has(1053) or 'service_paused' in text or 'service_stopped' in text:
        return 'Worker se nespustil správně. Zkontrolujte logy/web_mail_worker.log, účet služby a přístup ke konfiguraci.'
    return 'Operaci služby se nepodařilo dokončit. Ověřte stav služby a logy ve složce logy. ' + ADMIN_HELP


def _run_nssm(command: list[str]) -> str:
    try:
        completed = subprocess.run(command, capture_output=True, timeout=30,
                                   stdin=subprocess.DEVNULL, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('Windows neodpověděl do 30 sekund. Ověřte stav služby a zkuste to znovu.') from exc
    except OSError as exc:
        raise RuntimeError(service_error_message(str(exc), code=getattr(exc, 'winerror', None) or exc.errno)) from exc
    output = '\n'.join(filter(None, (decode_nssm_output(completed.stdout), decode_nssm_output(completed.stderr))))
    if completed.returncode:
        LOG.warning('%s %s failed (exit=%s): %s', Path(command[0]).name, command[1], completed.returncode, output)
        code = completed.returncode if Path(command[0]).name.lower() == 'sc.exe' else None
        raise RuntimeError(service_error_message(output, code=code))
    return output


def _service_setup(config_directory: Path) -> tuple[Path, str]:
    settings = load_settings(settings_path(config_directory))
    nssm = Path(settings['nssm_path'])
    if not nssm.is_file():
        raise ValueError(f'NSSM nebyl nalezen: {nssm}. Rozbalte celý balíček s NSSM; soubor má být ve složce nssm\\win64 vedle DataShip.exe.')
    name = str(settings['service_name']).strip()
    if not name or not all(c.isascii() and (c.isalnum() or c in '_-') for c in name):
        raise ValueError('Název služby smí obsahovat jen písmena bez diakritiky, číslice, pomlčku a podtržítko.')
    return nssm, name


@dataclass(frozen=True)
class ServiceReadiness:
    running: bool
    message: str


_START_LOCK = Lock()


def ensure_scheduler_running(config_directory: Path) -> ServiceReadiness:
    """Start only this installation's existing service; never install or elevate."""
    with _START_LOCK:
        try:
            require_service_rights('status')
            nssm, name = _service_setup(config_directory)
            base = [str(nssm)]
            frozen = getattr(sys, 'frozen', False)
            expected = Path(sys.executable).resolve()
            if frozen:
                expected = expected.with_name(WORKER_EXE_NAME)
            registered = _run_nssm(base + ['get', name, 'Application']).strip().strip('"')
            if PureWindowsPath(registered) != PureWindowsPath(str(expected)):
                raise ValueError('Služba odkazuje na jiný program nebo jinou složku. V Nastavení → Služba a odesílání ověřte název služby a opravte její cesty.')
            parameters = _run_nssm(base + ['get', name, 'AppParameters'])
            args = [part.strip('"') for part in shlex.split(parameters, posix=False)]
            prefix = [] if frozen else ['-m', 'services.web_mail_worker']
            if (len(args) != len(prefix) + 2 or args[:len(prefix)] != prefix
                    or args[-2] != '--config'
                    or PureWindowsPath(args[-1]) != PureWindowsPath(str((Path(config_directory) / 'config.json').resolve()))):
                raise ValueError('Služba používá jinou konfiguraci. V Nastavení → Služba a odesílání opravte její cesty.')
            state = _run_nssm(base + ['status', name]).strip()
            if state == 'SERVICE_RUNNING':
                return ServiceReadiness(True, f'Služba {name} běží. Automatické úlohy zpracovává i po zavření aplikace.')
            if state == 'SERVICE_START_PENDING':
                return ServiceReadiness(False, 'Služba se spouští; její běh zatím není potvrzený. Za chvíli klikněte na Znovu ověřit a spustit službu.')
            if state != 'SERVICE_STOPPED':
                raise ValueError('Služba není připravená ke spuštění. V Nastavení → Služba a odesílání ověřte její stav a log workeru.')
            require_service_rights('start')
            _run_nssm(base + ['start', name])
            if _run_nssm(base + ['status', name]).strip() != 'SERVICE_RUNNING':
                raise ValueError('Po spuštění se nepodařilo potvrdit běh služby. Ověřte její stav a log workeru v Nastavení → Služba a odesílání.')
            return ServiceReadiness(True, f'Služba {name} byla automaticky spuštěna. Úlohy zpracovává i po zavření aplikace.')
        except (OSError, RuntimeError, ValueError) as exc:
            return ServiceReadiness(False, f'Automatické spuštění úlohy zatím není zajištěné. {exc}')


def service_command(config_directory: Path, action: str) -> str:
    if action not in ('install', 'repair', 'start', 'stop', 'restart', 'status', 'remove'):
        raise ValueError('Neznámá operace služby.')
    nssm, name = _service_setup(config_directory)
    require_service_rights(action)
    config = (Path(config_directory) / 'config.json').resolve()
    base = [str(nssm)]
    if action in ('install', 'repair'):
        if not config.is_file():
            raise ValueError('Nejprve ověřte připojení k databázi a uložte nastavení aplikace.')
        if getattr(sys, 'frozen', False):
            worker = Path(sys.executable).with_name(WORKER_EXE_NAME)
            if not worker.is_file():
                raise ValueError(f'Chybí {WORKER_EXE_NAME} vedle DataShip.exe. Rozbalte celý balíček aplikace.')
            command = [str(worker), '--config', str(config)]
        else:
            command = [sys.executable, '-m', 'services.web_mail_worker', '--config', str(config)]
        if action == 'install':
            commands = [
                base + ['install', name, *command],
                base + ['set', name, 'AppDirectory', str(config.parent)],
                base + ['set', name, 'Start', 'SERVICE_AUTO_START'],
                base + ['set', name, 'AppExit', 'Default', 'Restart'],
                base + ['set', name, 'AppRestartDelay', '10000'],
            ]
        else:
            registered = _run_nssm(base + ['get', name, 'Application']).strip().strip('"')
            if PureWindowsPath(registered).name.casefold() != Path(command[0]).name.casefold():
                raise ValueError('Vybraná služba nepoužívá tento worker DataShipu. Zkontrolujte název služby; její nastavení nebylo změněno.')
            if not getattr(sys, 'frozen', False):
                parameters = _run_nssm(base + ['get', name, 'AppParameters'])
                if '-m services.web_mail_worker' not in parameters:
                    raise ValueError('Vybraná služba není plánovač DataShipu. Její nastavení nebylo změněno.')
            if _run_nssm(base + ['status', name]).strip() != 'SERVICE_STOPPED':
                raise ValueError('Před opravou cest službu zastavte a počkejte na stav „Služba je zastavená“.')
            sc = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'sc.exe'
            commands = [
                [str(sc), 'config', name, 'binPath=', f'"{nssm.resolve()}"'],
                base + ['set', name, 'Application', command[0]],
                base + ['set', name, 'AppParameters', subprocess.list2cmdline(command[1:])],
                base + ['set', name, 'AppDirectory', str(config.parent)],
            ]
    elif action == 'remove':
        registered = _run_nssm(base + ['get', name, 'Application']).strip().strip('"')
        registered_name = PureWindowsPath(registered).name.casefold()
        if registered_name != WORKER_EXE_NAME.casefold():
            if registered_name != Path(sys.executable).name.casefold():
                raise ValueError('Vybraná služba není plánovač DataShipu. Nebyla zastavena ani odstraněna.')
            parameters = _run_nssm(base + ['get', name, 'AppParameters'])
            if not re.search(r'(?:^|\s)-m\s+services\.web_mail_worker(?=\s|$)', parameters):
                raise ValueError('Vybraná služba není plánovač DataShipu. Nebyla zastavena ani odstraněna.')
        if _run_nssm(base + ['status', name]).strip() != 'SERVICE_STOPPED':
            _run_nssm(base + ['stop', name])
            if _run_nssm(base + ['status', name]).strip() != 'SERVICE_STOPPED':
                raise ValueError('Služba ještě není zastavená. Ověřte stav a odstranění zopakujte.')
        commands = [base + ['remove', name, 'confirm']]
    elif action == 'restart':
        commands = [base + ['restart', name]]
    else:
        commands = [base + [action, name]]
    output = ''
    installed = False
    try:
        for command in commands:
            output = _run_nssm(command)
            installed = installed or command[1] == 'install'
    except RuntimeError as exc:
        if action == 'repair':
            raise RuntimeError('Oprava cest služby není dokončená. ' + str(exc)) from exc
        if installed:
            raise RuntimeError('Služba byla vytvořena, ale její nastavení není dokončené. ' + str(exc)) from exc
        raise
    if action == 'status':
        states = {'SERVICE_RUNNING': 'Služba běží.', 'SERVICE_STOPPED': 'Služba je zastavená.',
                  'SERVICE_START_PENDING': 'Služba se spouští.', 'SERVICE_STOP_PENDING': 'Služba se zastavuje.',
                  'SERVICE_PAUSED': 'Služba je pozastavená. Zkontrolujte log workeru.'}
        return states.get(output.strip(), 'Stav služby se nepodařilo rozpoznat. Ověřte jej ve správě služeb Windows.')
    return {'install': 'Služba je nainstalovaná a připravená. Zatím neběží; po kontrole odesílání klikněte na „Spustit“.',
            'repair': 'Cesty existující služby byly opraveny podle aktuální složky aplikace. Služba zůstává zastavená; klikněte na „Spustit službu“.',
            'start': 'Služba byla spuštěna.', 'stop': 'Služba byla zastavena.',
            'restart': 'Služba byla restartována.',
            'remove': 'Služba byla odstraněna z Windows. Uložené úlohy a nastavení zůstaly zachované.'}[action]

