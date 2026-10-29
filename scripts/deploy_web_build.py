"""Install an already verified build without letting PyInstaller erase live files."""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime
import os
from pathlib import Path
import shutil
import sys
from uuid import uuid4

SETTINGS = (
    'config.json', 'daily_reports.json', 'web_mail_settings.json',
    'web_mail_tasks.json', 'web_mail_worker_state.json', '.env', 'planovac.json',
)
PACKAGED = {
    'DataShip.exe', 'DataShip-Worker.exe', '_internal', 'nssm',
    # Do not copy obsolete script launchers from a previous installation.
    'START_WEB.cmd', 'START_WEB.vbs', 'START_WEB_DEBUG.cmd',
    'START_WORKER_MANUAL.cmd', 'config.example.json',
    'BUILD_INFO.json', 'web_mail_worker_runtime.json',
}


def check_executable(path: Path) -> None:
    """An exclusive Windows open detects running EXEs without killing processes."""
    if os.name != 'nt' or not path.exists():
        return
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = (
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
    )
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    # Request read and delete access, sharing nothing. A running GUI, worker or
    # NSSM holds an incompatible image handle. Access-denied is unsafe too.
    handle = kernel.CreateFileW(str(path.resolve()), 0x80010000, 0, None, 3, 0, None)
    if handle == ctypes.c_void_p(-1).value:
        code = ctypes.get_last_error()
        raise PermissionError(
            f'Soubor je pouzivany nebo nepristupny: {path} (WinError {code}). '
            'Zastav sluzbu DataShip v Nastaveni nebo services.msc, zavri DataShip '
            'a pripadny rucne spusteny worker. Pak zopakuj build. '
            'Zadny proces se automaticky neukoncuje.'
        )
    kernel.CloseHandle(handle)


def check_installation(app: Path) -> None:
    for relative in ('DataShip.exe', 'DataShip-Worker.exe', 'nssm/win64/nssm.exe'):
        check_executable(app / relative)


def install(stage: Path, app: Path, recovery: Path, legacy: Path) -> Path | None:
    stage, app = stage.resolve(), app.resolve()
    if stage == app or app in stage.parents or stage in app.parents:
        raise ValueError('Build a instalace musi byt v oddelenych slozkach.')
    for name in ('DataShip.exe', 'DataShip-Worker.exe', '_internal', 'nssm/win64/nssm.exe'):
        if not (stage / name).exists():
            raise FileNotFoundError(stage / name)
    check_installation(app)
    # Keep all user-created top-level files/folders (including logs and PDFs).
    # Program-owned payload is always taken from the clean, verified build.
    if app.exists():
        for source in app.iterdir():
            if source.name in PACKAGED:
                continue
            target = stage / source.name
            if source.is_dir():
                shutil.copytree(source, target, dirs_exist_ok=True)
            else:
                shutil.copy2(source, target)
    # The previous build script saved these files before deleting its output.
    # Recover them if that older build failed half way through COLLECT.
    complete_install = all((app / name).exists() for name in
                           ('DataShip.exe', 'DataShip-Worker.exe', '_internal'))
    sources = (app, legacy) if complete_install else (app, recovery, legacy)
    for name in SETTINGS:
        for source_dir in sources:
            source = source_dir / name
            if source.is_file():
                shutil.copy2(source, stage / name)
                break
    check_installation(app)  # The operator could have restarted the service.
    backup = None
    if app.exists():
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        backup = app.with_name(f'{app.name}.backup-{stamp}-{uuid4().hex[:8]}')
        app.rename(backup)
    try:
        stage.rename(app)
    except OSError as promotion_error:
        if backup is not None:
            try:
                backup.rename(app)
            except OSError as rollback_error:
                raise OSError(
                    f'Nasazeni i navrat slozky selhaly. Puvodni instalace zustava v {backup}; '
                    f'novy build v {stage}. {rollback_error}'
                ) from promotion_error
        raise
    return backup


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--stage', type=Path)
    parser.add_argument('--recovery', type=Path)
    parser.add_argument('--legacy', type=Path)
    args = parser.parse_args()
    try:
        if args.check_only:
            check_installation(args.app)
        else:
            if any(value is None for value in (args.stage, args.recovery, args.legacy)):
                parser.error('--stage, --recovery a --legacy jsou povinne pro instalaci')
            backup = install(args.stage, args.app, args.recovery, args.legacy)
            if backup:
                print(f'ZALOHA PUVODNI INSTALACE: {backup}')
        return 0
    except (OSError, ValueError) as exc:
        print(f'CHYBA: {exc}', file=sys.stderr)
        print('Zkontroluj zastaveni sluzby a pristupova prava. Puvodni soubory se nemazou.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
