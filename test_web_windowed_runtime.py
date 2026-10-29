"""Windowed startup keeps logs and supports build verification without stdout."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from services import web_windowed_runtime as runtime
from services.web_branding import WEB_BUILD
from scripts import verify_web_build as build_check
import stravovaci_nicegui as web


def test_windowed_streams_share_utf8_log_and_flush_lines(tmp_path):
    streams = SimpleNamespace(stdout=None, stderr=None)
    with patch.object(runtime, 'sys', streams):
        runtime.prepare_windowed_streams(tmp_path)
        assert streams.stdout is streams.stderr
        streams.stdout.write('Spouštím aplikaci\n')
        assert (tmp_path / 'logy/dataship_web.log').read_text(encoding='utf-8') == 'Spouštím aplikaci\n'
        streams.stdout.close()


def test_existing_console_streams_are_preserved(tmp_path):
    streams = SimpleNamespace(stdout=object(), stderr=object())
    stdout, stderr = streams.stdout, streams.stderr
    with patch.object(runtime, 'sys', streams):
        runtime.prepare_windowed_streams(tmp_path)
    assert streams.stdout is stdout and streams.stderr is stderr
    assert not (tmp_path / 'logy').exists()


def test_read_only_log_directory_does_not_block_startup(tmp_path):
    streams = SimpleNamespace(stdout=None, stderr=None)
    with patch.object(runtime, 'sys', streams), patch.object(Path, 'mkdir', side_effect=PermissionError):
        runtime.prepare_windowed_streams(tmp_path)
    assert streams.stdout is not None and streams.stderr is streams.stdout
    streams.stdout.close()


def test_version_file_does_not_open_gui_or_load_credentials(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    identity = tmp_path / 'version.txt'
    with patch.object(web, 'application_directory', return_value=tmp_path), \
         patch.object(web, 'NiceGuiApp') as gui:
        assert web.main(['--version-file', str(identity)]) == 0
    assert identity.read_text().strip().endswith(f' build {WEB_BUILD}')
    gui.assert_not_called()


def test_unwritable_version_file_fails_without_launching_gui(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch.object(web, 'application_directory', return_value=tmp_path), \
         patch.object(web, 'NiceGuiApp') as gui:
        assert web.main(['--version-file', str(tmp_path / 'absent/version.txt')]) == 2
    gui.assert_not_called()


@pytest.mark.parametrize('gui_version, worker_version, missing, accepted', [
    (WEB_BUILD, WEB_BUILD, False, True),
    ('old', WEB_BUILD, False, False),
    (WEB_BUILD, 'old', False, False),
    (WEB_BUILD, WEB_BUILD, True, False),
])
def test_build_checks_windowed_gui_file_and_console_worker(tmp_path, gui_version, worker_version, missing, accepted):
    app = tmp_path / 'DataShip'
    app.mkdir()
    def run(command, **kwargs):
        assert kwargs['check'] is True
        if Path(command[0]).name == 'DataShip.exe':
            assert command[1] == '--version-file'
            if not missing:
                Path(command[2]).write_text(f'MailShip rc.10 build {gui_version}\n')
            return SimpleNamespace(returncode=0)
        assert command[1] == '--version'
        return SimpleNamespace(stdout=f'DataShip Worker rc.10 build {worker_version}\r\n')
    with patch.object(build_check.subprocess, 'run', side_effect=run):
        if accepted:
            build_check.verify(app)
        else:
            with pytest.raises((OSError, ValueError)):
                build_check.verify(app)
    assert list(tmp_path.iterdir()) == [app]
