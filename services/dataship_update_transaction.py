"""Recoverable replacement of DataShip program files on the installation volume."""
from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

PROGRAM = ('DataShip.exe', 'DataShip-Worker.exe', '_internal')
WORKSPACE = '.dataship-update'
JOURNAL = 'transaction.json'
UPDATE_PAUSE = '.dataship-worker-pause'


@contextmanager
def update_lock(installation: Path):
    # A crashed process releases the lock but leaves the recovery journal.
    with (installation / '.dataship-update.lock').open('a+b') as stream:
        if os.name == 'nt':
            import msvcrt
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError('Jiná aktualizace DataShipu už probíhá.') from exc
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise RuntimeError('Jiná aktualizace DataShipu už probíhá.') from exc
        yield


def journal_write(path: Path, value: dict) -> None:
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def recover_files(installation: Path, workspace: Path) -> None:
    """Restore every moved original, including after repeated interruption."""
    backup, stage = workspace / 'backup', workspace / 'stage'
    for name in reversed(PROGRAM):
        original, current, candidate = backup / name, installation / name, stage / name
        if original.exists():
            if current.exists():
                current.rename(candidate)
            original.rename(current)


def replace_files(installation: Path, workspace: Path) -> None:
    backup, stage = workspace / 'backup', workspace / 'stage'
    backup.mkdir()
    for name in PROGRAM:
        (installation / name).rename(backup / name)
        (stage / name).rename(installation / name)


def apply_update(installation: Path, workspace: Path, service, version: str, check, migrate, progress) -> None:
    """Apply a verified stage. The caller holds the installation lock."""
    initial = service.state()
    if initial not in ('missing', 'stopped', 'running'):
        raise RuntimeError('Před aktualizací ověřte stabilní stav služby DataShip.')
    journal = workspace / JOURNAL
    state = {'state': initial, 'version': version, 'phase': 'draining'}
    journal_write(journal, state)
    try:
        progress('Čekám na dokončení službou přijatých úloh')
        service.pause()
        if initial == 'running':
            service.drain()
            service.stop()
        state['phase'] = 'replacing'
        journal_write(journal, state)
        progress('Zálohuji a nahrazuji programové soubory')
        replace_files(installation, workspace)
        progress('Ověřuji instalaci a verzi dat')
        migrate()
        check(version)
        if initial == 'running':
            service.start()
            service.check(version)
        state['phase'] = 'committed'
        journal_write(journal, state)
        service.resume()
    except Exception:
        rollback_update(installation, workspace, service)
        raise


def preserve_backup(installation: Path, workspace: Path) -> Path | None:
    backup = workspace / 'backup'
    if not backup.exists():
        return None
    destination = installation / f'.dataship-backup-{uuid4().hex}'
    backup.rename(destination)
    return destination


def rollback_update(installation: Path, workspace: Path, service) -> None:
    journal = workspace / JOURNAL
    if not journal.exists():
        return
    state = json.loads(journal.read_text(encoding='utf-8'))
    if state['phase'] == 'replacing':
        if state['state'] == 'running' and service.state() != 'stopped':
            service.stop()
        recover_files(installation, workspace)
    if state['phase'] != 'committed' and state['state'] == 'running' and service.state() != 'running':
        service.start()
    service.resume()
    if state['phase'] == 'committed':
        preserve_backup(installation, workspace)
    shutil.rmtree(workspace)
