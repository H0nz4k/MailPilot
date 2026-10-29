"""A failed build/deployment must not destroy the installed app or its settings."""
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts import deploy_web_build as deploy


def put(root, name, content='new'):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def layout(tmp_path):
    app = tmp_path / 'dist-web' / 'DataShip'
    stage = tmp_path / 'dist-web' / '.build' / 'DataShip'
    for name in ('DataShip.exe', 'DataShip-Worker.exe', '_internal/library', 'nssm/win64/nssm.exe'):
        put(stage, name)
    put(stage, 'config.json', 'example')
    put(stage, 'START_WEB.vbs', 'new launcher')
    return stage, app, tmp_path / 'recovery', tmp_path / 'legacy'


def test_install_preserves_settings_logs_and_custom_files_including_backup(tmp_path):
    stage, app, recovery, legacy = layout(tmp_path)
    for name in ('DataShip.exe', 'DataShip-Worker.exe', '_internal/stale.dll',
                 'config.json', '.env', 'web_mail_tasks.json', 'web_mail_worker_state.json',
                 'logy/history.log', 'exports/report.pdf', 'custom.txt',
                 'web_mail_worker_runtime.json', 'START_WEB.vbs'):
        put(app, name, 'old')
    put(recovery, 'config.json', 'stale recovery')
    put(legacy, 'config.json', 'legacy')
    backup = deploy.install(stage, app, recovery, legacy)
    assert backup.is_dir()
    assert (backup / '_internal/stale.dll').read_text() == 'old'
    for name in ('config.json', '.env', 'web_mail_tasks.json', 'web_mail_worker_state.json',
                 'logy/history.log', 'exports/report.pdf', 'custom.txt'):
        assert (app / name).read_text() == 'old'
    assert (app / 'DataShip-Worker.exe').read_text() == 'new'
    assert (app / 'START_WEB.vbs').read_text() == 'new launcher'
    assert not (app / '_internal/stale.dll').exists()
    assert not (app / 'web_mail_worker_runtime.json').exists()
    assert not stage.exists()


def test_recover_settings_from_previous_failed_pyinstaller_collect(tmp_path):
    stage, app, recovery, legacy = layout(tmp_path)
    put(app, 'DataShip-Worker.exe', 'locked leftover')
    for name in deploy.SETTINGS:
        put(recovery, name, 'recovered')
        put(legacy, name, 'legacy')
    deploy.install(stage, app, recovery, legacy)
    for name in deploy.SETTINGS:
        assert (app / name).read_text() == 'recovered'
        assert (recovery / name).read_text() == 'recovered'


def test_first_install_can_import_legacy_settings_without_touching_legacy(tmp_path):
    stage, app, recovery, legacy = layout(tmp_path)
    put(legacy, 'config.json', 'legacy')
    assert deploy.install(stage, app, recovery, legacy) is None
    assert (app / 'config.json').read_text() == 'legacy'
    assert (legacy / 'config.json').read_text() == 'legacy'


def test_fresh_install_keeps_example_configuration(tmp_path):
    stage, app, recovery, legacy = layout(tmp_path)
    deploy.install(stage, app, recovery, legacy)
    assert (app / 'config.json').read_text() == 'example'


@pytest.mark.parametrize('check', [1, 2])
def test_busy_installation_is_never_renamed(tmp_path, check):
    stage, app, recovery, legacy = layout(tmp_path)
    put(app, 'config.json', 'original')
    effects = [PermissionError('busy')] if check == 1 else [None, PermissionError('restarted')]
    with patch.object(deploy, 'check_installation', side_effect=effects):
        with pytest.raises(PermissionError):
            deploy.install(stage, app, recovery, legacy)
    assert (app / 'config.json').read_text() == 'original'
    assert not list(app.parent.glob('DataShip.backup-*'))


def test_failed_settings_copy_keeps_original_installation(tmp_path):
    stage, app, recovery, legacy = layout(tmp_path)
    put(app, 'config.json', 'original')
    with patch.object(deploy.shutil, 'copy2', side_effect=PermissionError('copy denied')):
        with pytest.raises(PermissionError):
            deploy.install(stage, app, recovery, legacy)
    assert (app / 'config.json').read_text() == 'original'


def test_failed_promotion_rolls_back_original_directory(tmp_path):
    stage, app, recovery, legacy = layout(tmp_path)
    put(app, 'config.json', 'original')
    original = Path.rename
    def rename(source, target):
        if source == stage:
            raise PermissionError('promotion denied')
        return original(source, target)
    with patch.object(Path, 'rename', rename):
        with pytest.raises(PermissionError):
            deploy.install(stage, app, recovery, legacy)
    assert (app / 'config.json').read_text() == 'original'
    assert stage.is_dir()
    assert not list(app.parent.glob('DataShip.backup-*'))


def test_incomplete_build_never_changes_installation(tmp_path):
    stage, app, recovery, legacy = layout(tmp_path)
    put(app, 'config.json', 'original')
    (stage / 'DataShip-Worker.exe').unlink()
    with pytest.raises(FileNotFoundError):
        deploy.install(stage, app, recovery, legacy)
    assert (app / 'config.json').read_text() == 'original'


@pytest.mark.skipif(os.name != 'nt', reason='Real Windows sharing handles required')
def test_windows_open_file_blocks_preflight_and_closing_it_unblocks(tmp_path):
    executable = put(tmp_path, 'DataShip-Worker.exe')
    with executable.open('rb'):
        with pytest.raises(PermissionError, match='WinError'):
            deploy.check_executable(executable)
    deploy.check_executable(executable)


def test_complete_install_does_not_resurrect_stale_recovery_settings(tmp_path):
    stage, app, recovery, legacy = layout(tmp_path)
    for name in ('DataShip.exe', 'DataShip-Worker.exe', '_internal/library'):
        put(app, name, 'old')
    put(recovery, 'config.json', 'obsolete')
    deploy.install(stage, app, recovery, legacy)
    assert (app / 'config.json').read_text() == 'example'


@pytest.mark.skipif(os.name == 'nt', reason='POSIX shims simulate Git Bash orchestration')
def test_pyinstaller_failure_never_targets_or_deletes_installed_app(tmp_path):
    import shutil
    import subprocess
    import sys
    root = tmp_path / 'project'
    scripts = root / 'scripts'
    scripts.mkdir(parents=True)
    for name in ('build_web_windows.sh', 'deploy_web_build.py'):
        shutil.copy2(Path(__file__).parent / 'scripts' / name, scripts / name)
    app = root / 'dist-web/DataShip'
    put(app, 'DataShip-Worker.exe', 'old worker')
    put(app, '.env', 'dummy-secret')
    put(app, 'config.json', 'original settings')
    fakebin = root / 'fakebin'
    for name, content in (
        ('uname', '#!/bin/sh\necho MINGW64_NT\n'),
        ('cygpath', '#!/bin/sh\necho "$2"\n'),
    ):
        put(fakebin, name, content).chmod(0o755)
    # Execute the real deployment preflight, but fail a simulated PyInstaller.
    # Its recorded arguments must point into the temporary staging directory.
    shim = '#!' + sys.executable + '\n' + (
        'import os, subprocess, sys, json\n'
        'from pathlib import Path\n'
        'if sys.argv[1:3] == ["-m", "pip"]: raise SystemExit(0)\n'
        'if sys.argv[1:3] == ["-m", "PyInstaller"]:\n'
        '    Path("build_args.json").write_text(json.dumps(sys.argv[1:]))\n'
        '    raise SystemExit(7)\n'
        'raise SystemExit(subprocess.call([sys.executable, *sys.argv[1:]]))\n'
    )
    put(root, '.venv-web/Scripts/python.exe', shim).chmod(0o755)
    result = subprocess.run(['bash', str(scripts / 'build_web_windows.sh')],
                            env={**os.environ, 'PATH': str(fakebin) + os.pathsep + os.environ['PATH']},
                            text=True, capture_output=True)
    assert result.returncode == 7, result.stderr
    import json
    args = json.loads((root / 'build_args.json').read_text())
    dist = Path(args[args.index('--distpath') + 1])
    assert dist.parent == app.parent and dist.name.startswith('.dataship-build-')
    assert (app / 'DataShip-Worker.exe').read_text() == 'old worker'
    assert (app / '.env').read_text() == 'dummy-secret'
    assert (app / 'config.json').read_text() == 'original settings'
    assert 'puvodni instalace se nemaze' in result.stderr
