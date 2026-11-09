"""Saved-report shortcuts create a PDF without opening the UI or sending mail."""
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
import json
import shutil
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services import web_saved_report_cli as export
from services.web_daily_profiles import DailyProfile, save_profile, profile_file
from stravovaci_sestava import ConfigError
import stravovaci_nicegui as web


def setup(tmp_path):
    config = tmp_path / 'config.json'
    shutil.copyfile(Path(__file__).with_name('config.example.json'), config)
    raw = json.loads(config.read_text(encoding='utf-8'))
    raw.update(poctyemailem={'vsechny_kategorie': False, 'povolene_kategorie': ['1', '2']}, povolene_kategorie=['1', '2'])
    config.write_text(json.dumps(raw), encoding='utf-8')
    profile = DailyProfile.from_dict({
        'name': 'Můj přehled', 'categories': ['2'], 'meal_type': ['Oběd', 'Večeře'],
        'show_diner_list': False, 'pdf_orientation': 'na_sirku', 'pdf_data_font_size': 12,
    })
    save_profile(profile_file(tmp_path), profile)
    return config, profile


def render(_config, _report, *, output_path):
    Path(output_path).write_bytes(b'%PDF-1.4 fixture')
    return output_path


def test_named_export_uses_saved_content_current_date_and_preserves_settings(tmp_path):
    config, profile = setup(tmp_path)
    before = {path.name: path.read_bytes() for path in (config, profile_file(tmp_path))}
    with patch('stravovaci_sestava.get_password', return_value='dummy-db'), \
         patch.object(export, 'fetch_report', return_value=object()) as fetch, \
         patch.object(export, 'create_pdf', side_effect=render), \
         patch('env_store.get_resend_api_key', side_effect=AssertionError('PDF needs no email key')), \
         patch('mail_service.send_pdf_via_mailsender', side_effect=AssertionError('Must not send email')):
        output = export.export_saved_report(config, name='můj PŘEHLED')
    args = fetch.call_args.args[0]
    assert args.report_date == date.today()  # Not the old preview date in config.
    assert args.categories == ('2',) and args.meal_type == ('oběd', 'večeře')
    assert not args.show_diner_list
    assert args.pdf_orientation == 'na_sirku' and args.pdf_data_font_size == 12
    assert output.parent == tmp_path / 'exporty'
    assert output.name.startswith('muj-prehled_' + date.today().isoformat())
    assert output.read_bytes().startswith(b'%PDF')
    assert not list(output.parent.glob('.dataship-export-*'))
    assert before == {path.name: path.read_bytes() for path in (config, profile_file(tmp_path))}


def test_date_and_custom_output_and_id_selection(tmp_path):
    config, profile = setup(tmp_path)
    with patch('stravovaci_sestava.get_password', return_value='dummy-db'), \
         patch.object(export, 'fetch_report', return_value=object()) as fetch, \
         patch.object(export, 'create_pdf', side_effect=render):
        output = export.export_saved_report(config, profile_id=profile.id,
                                           report_date=date(2026, 11, 2), output=Path('PDF složka/muj.pdf'))
    assert output == tmp_path / 'PDF složka/muj.pdf'
    assert fetch.call_args.args[0].report_date == date(2026, 11, 2)


@pytest.mark.parametrize('name', ['missing', ''])
def test_unknown_report_never_queries_database(tmp_path, name):
    config, profile = setup(tmp_path)
    with patch.object(export, 'fetch_report') as fetch, patch.object(export, 'load_config') as load:
        with pytest.raises(ValueError):
            export.export_saved_report(config, name=name)
    fetch.assert_not_called()
    load.assert_not_called()


def test_duplicate_names_require_id_instead_of_guessing(tmp_path):
    config, first = setup(tmp_path)
    second = replace(first, id='other-id', name='MŮJ PŘEHLED')
    save_profile(profile_file(tmp_path), second)
    with pytest.raises(ValueError, match='--export-report-id'):
        export.select_saved_report(tmp_path, name='Můj přehled')
    assert export.select_saved_report(tmp_path, profile_id=second.id) == second


@pytest.mark.parametrize('failure', ['render', 'empty', 'replace'])
def test_failed_export_preserves_previous_pdf_and_cleans_temporary_file(tmp_path, failure):
    config, profile = setup(tmp_path)
    target = tmp_path / 'original.pdf'
    target.write_bytes(b'original')
    def create(*args, **kwargs):
        if failure == 'render':
            raise OSError('render failed')
        if failure != 'empty':
            return render(*args, **kwargs)
    with patch('stravovaci_sestava.get_password', return_value='dummy-db'), \
         patch.object(export, 'fetch_report', return_value=object()), \
         patch.object(export, 'create_pdf', side_effect=create), \
         patch.object(export.os, 'replace', side_effect=PermissionError('locked') if failure == 'replace' else export.os.replace):
        with pytest.raises((OSError, ValueError)):
            export.export_saved_report(config, name=profile.name, output=target)
    assert target.read_bytes() == b'original'
    assert not list(tmp_path.glob('.dataship-export-*'))


def test_current_admin_permissions_cannot_be_bypassed_by_saved_profile(tmp_path):
    config, profile = setup(tmp_path)
    raw = json.loads(config.read_text(encoding='utf-8'))
    raw['poctyemailem']['povolene_kategorie'] = ['1']
    config.write_text(json.dumps(raw), encoding='utf-8')
    with patch('stravovaci_sestava.get_password', return_value='dummy-db'), patch.object(export, 'fetch_report') as fetch:
        with pytest.raises(ValueError, match='povolena správcem'):
            export.export_saved_report(config, name=profile.name)
    fetch.assert_not_called()


@pytest.mark.parametrize('value,expected', [('2026-11-02', date(2026, 11, 2)), ('02.11.2026', date(2026, 11, 2)), (None, date.today())])
def test_explicit_date_and_today(value, expected):
    assert export.export_date(value) == expected


@pytest.mark.parametrize('value', ['2026-02-30', '2.11.2026', '20261102', 'bad'])
def test_invalid_dates_are_rejected(value):
    with pytest.raises(ValueError):
        export.export_date(value)


def test_days_ahead_is_calendar_offset():
    assert export.export_date(days_ahead=5) == date.today() + timedelta(days=5)
    for value in (-1, 371, 2.5, True):
        with pytest.raises(ValueError):
            export.export_date(days_ahead=value)


@pytest.mark.parametrize('arguments', [
    ['--export-report', 'muj', '--browser'], ['--export-report', 'muj', '--automatic'],
    ['--export-report', 'muj', '--export-report-id', 'id'], ['--output', 'x.pdf'],
    ['--open-pdf'], ['--days-ahead', '1'],
    ['--export-report', 'muj', '--date', '2026-11-02', '--days-ahead', '1'],
])
def test_cli_rejects_conflicting_modes(arguments):
    with pytest.raises(SystemExit) as error:
        web.parse_args(arguments)
    assert error.value.code == 2


@pytest.mark.parametrize('open_pdf', [False, True])
def test_exe_entry_exports_without_constructing_gui_or_starting_service(tmp_path, monkeypatch, open_pdf):
    config, profile = setup(tmp_path)
    monkeypatch.chdir(tmp_path)
    with patch.object(web, 'application_directory', return_value=tmp_path), \
         patch.object(web, 'NiceGuiApp') as gui, patch.object(web.ui, 'run') as browser, \
         patch.object(export, 'export_saved_report', return_value=tmp_path / 'done.pdf') as run, \
         patch.object(export, 'open_document') as viewer, \
         patch('services.web_mail_nssm.ensure_scheduler_running') as service:
        arguments = ['--export-report', profile.name, '--output', 'done.pdf'] + (['--open-pdf'] if open_pdf else [])
        assert web.main(arguments) == 0
    run.assert_called_once()
    assert viewer.call_count == open_pdf
    gui.assert_not_called()
    browser.assert_not_called()
    service.assert_not_called()


def test_exe_entry_returns_error_and_logs_it_without_opening_gui(tmp_path, monkeypatch):
    setup(tmp_path)
    monkeypatch.chdir(tmp_path)
    with patch.object(web, 'application_directory', return_value=tmp_path), \
         patch.object(web, 'NiceGuiApp') as gui:
        assert web.main(['--export-report', 'not found']) == 2
    gui.assert_not_called()
    assert 'nebyl nalezen' in (tmp_path / 'logy/automaticky_export.log').read_text(encoding='utf-8')
