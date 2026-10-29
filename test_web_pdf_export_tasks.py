"""Scheduled PDF-only exports never load email credentials or contact a transport."""
from datetime import date, datetime
import asyncio
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from nicegui.testing.user_simulation import user_simulation

from services.web_activity import read_events
from services.web_daily_profiles import DailyProfile, save_profile, profile_file
from services.web_mail_gui import build_mail_tasks_panel
from services.web_mail_task_store import load_tasks, save_tasks, task_file
from services.web_mail_tasks import MailTask, validate_pdf_destination
from services import web_mail_worker as worker
from services.web_controls import day_stepper
from services.web_task_output import TaskOutputEditor
from nicegui import ui
from stravovaci_nicegui import NiceGuiApp


def export_task(tmp_path, **values):
    return MailTask.from_dict({
        'name': 'PDF do složky', 'send_time': '08:00', 'date_mode': 'tomorrow',
        'output_mode': 'pdf', 'output_directory': str(tmp_path / 'Výstupy'),
        'output_filename': 'Prehled_{date}.pdf', **values,
    })


def test_pdf_mode_roundtrip_and_email_mode_still_requires_recipients(tmp_path):
    task = export_task(tmp_path, recipients=['ignored even if invalid'])
    assert task.recipients == ()
    assert MailTask.from_dict(task.to_dict()) == task
    with pytest.raises(ValueError):
        MailTask.from_dict({**task.to_dict(), 'output_mode': 'email'})
    old = MailTask.from_dict({'name': 'Starý e-mail', 'send_time': '08:00', 'recipients': ['a@example.org']})
    assert old.output_mode == 'email'
    assert validate_pdf_destination(r'C:\DataShip\Exporty', 'Prehled_{date}.pdf')
    assert validate_pdf_destination(r'\\server\sdilena\Exporty', 'Prehled_{date}.pdf')


@pytest.mark.parametrize('directory, filename', [
    ('relative/folder', 'Prehled.pdf'), ('C:relative', 'Prehled.pdf'),
    ('/tmp', '../outside.pdf'), ('/tmp', r'..\outside.pdf'),
    ('/tmp', '{unknown}.pdf'), ('/tmp', '{date[0]}.pdf'),
    ('/tmp', 'CON.pdf'), ('/tmp', 'Prehled.txt'),
])
def test_invalid_destinations_are_rejected(directory, filename):
    with pytest.raises(ValueError):
        validate_pdf_destination(directory, filename)


def test_due_export_creates_dated_file_once_without_any_email_settings(tmp_path):
    config = tmp_path / 'config.json'
    shutil.copyfile(Path(__file__).with_name('config.example.json'), config)
    task = export_task(tmp_path)
    save_tasks(task_file(tmp_path), [task])

    def render(_config, _report, output_path=None):
        Path(output_path).write_bytes(b'%PDF-1.4 export-test')
        return output_path

    with patch('stravovaci_sestava.get_password', return_value='test'), \
         patch.object(worker, 'fetch_report', return_value=object()), \
         patch.object(worker, 'create_pdf', side_effect=render) as pdf, \
         patch.object(worker, 'load_settings', side_effect=AssertionError('Email settings must not be read')), \
         patch.object(worker, 'get_resend_api_key', side_effect=AssertionError('API must not be read')), \
         patch.object(worker, 'smtp_send') as smtp, \
         patch.object(worker, 'send_pdf_via_mailsender') as resend:
        worker.tick(config, datetime(2026, 10, 29, 8, 0))
        worker.tick(config, datetime(2026, 10, 29, 8, 1))
        output = tmp_path / 'Výstupy/Prehled_2026-10-30.pdf'
        assert output.read_bytes() == b'%PDF-1.4 export-test'
        pdf.assert_called_once()
        smtp.assert_not_called()
        resend.assert_not_called()
    events = read_events(tmp_path)
    assert events[0]['kind'] == 'exported'
    assert str(output) in events[0]['message']
    assert not list(output.parent.glob('.dataship-*'))


def test_failed_export_preserves_existing_pdf_and_removes_temporary_file(tmp_path):
    config = tmp_path / 'config.json'
    shutil.copyfile(Path(__file__).with_name('config.example.json'), config)
    task = export_task(tmp_path)
    output = tmp_path / 'Výstupy/Prehled_2026-10-30.pdf'
    output.parent.mkdir()
    output.write_bytes(b'previous good PDF')

    def fail(_config, _report, output_path=None):
        Path(output_path).write_bytes(b'partial file')
        raise OSError('Disk write failed')

    with patch('stravovaci_sestava.get_password', return_value='test'), \
         patch.object(worker, 'fetch_report', return_value=object()), \
         patch.object(worker, 'create_pdf', side_effect=fail), \
         patch.object(worker, 'get_resend_api_key') as api:
        with pytest.raises(OSError):
            worker.deliver_daily(config, task, date(2026, 10, 30))
        api.assert_not_called()
    assert output.read_bytes() == b'previous good PDF'
    assert not list(output.parent.glob('.dataship-*'))


@pytest.mark.asyncio
async def test_wizard_hides_mail_fields_and_saves_export_without_recipients(tmp_path):
    config = tmp_path / 'config.json'
    shutil.copyfile(Path(__file__).with_name('config.example.json'), config)
    pages = []

    def root():
        page = NiceGuiApp(config)
        page.build()
        page.populate_categories([('1', 'Žáci')])
        pages.append(page)

    with patch.object(NiceGuiApp, '_stored_password', return_value=''), \
         patch.object(NiceGuiApp, '_schedule_first_run'), \
         patch.object(worker, 'smtp_send') as smtp, \
         patch.object(worker, 'send_pdf_via_mailsender') as resend:
        async with user_simulation(root) as user:
            await user.open('/')
            with user:
                page = pages[0]
                page._apply_daily_categories(['1'])
                page.wizard_only_cooking.value = False
                page.wizard_name.value = 'Denní export'
                page.wizard_recipients.input.value = 'invalid hidden email'
                page.wizard_output.pdf_only.value = True
                page.wizard_output.directory.value = str(tmp_path / 'Cílová složka')
                assert not page.wizard_output.mail_fields.visible
                assert page.wizard_output.pdf_fields.visible
                page._wizard_show_step(4)
            await user.should_see('Zapnout automatické vytváření PDF')
            user.find(marker='wizard-next').click()
            saved = load_tasks(task_file(tmp_path))
            assert len(saved) == 1
            assert saved[0].output_mode == 'pdf'
            assert saved[0].output_directory == str(tmp_path / 'Cílová složka')
            assert saved[0].recipients == ()
            assert not (tmp_path / 'Cílová složka').exists()
            smtp.assert_not_called()
            resend.assert_not_called()


@pytest.mark.asyncio
async def test_existing_export_task_keeps_destination_when_edited(tmp_path):
    profile = DailyProfile.from_dict({'name': 'Škola', 'categories': ['1']})
    save_profile(profile_file(tmp_path), profile)
    task = export_task(tmp_path, profile_id=profile.id)
    save_tasks(task_file(tmp_path), [task])
    with patch('services.web_mail_gui.resolve_task_date', return_value=date(2026, 10, 30)):
        async with user_simulation(lambda: build_mail_tasks_panel(tmp_path)) as user:
            await user.open('/')
            await user.should_see('Pouze PDF na disk:')
            user.find('Upravit').click()
            with user:
                user.find(marker='task-output-filename').elements.pop().value = 'Skola_{date}.pdf'
            user.find(marker='mail-task-save').click()
            updated = load_tasks(task_file(tmp_path))[0]
            assert updated.output_mode == 'pdf'
            assert updated.output_directory == task.output_directory
            assert updated.output_filename == 'Skola_{date}.pdf'
            assert updated.recipients == ()


@pytest.mark.asyncio
async def test_large_day_buttons_and_directory_picker(tmp_path):
    fields = []
    outputs = []
    def root():
        fields.append(day_stepper('Dní dopředu', 2))
        outputs.append(TaskOutputEditor(tmp_path))
    chosen = str(tmp_path / 'Zvolená složka')
    with patch('services.web_task_output.pick_local_directory', side_effect=[chosen, None]) as picker:
        async with user_simulation(root) as user:
            await user.open('/')
            plus = next(e for e in user.client.elements.values() if isinstance(e, ui.button) and e.props.get('aria-label') == 'Přidat den')
            minus = next(e for e in user.client.elements.values() if isinstance(e, ui.button) and e.props.get('aria-label') == 'Ubrat den')
            user.find(marker='day-plus').click()
            assert fields[0].value == 3
            user.find(marker='day-minus').click()
            assert fields[0].value == 2
            with user:
                fields[0].value = 0
                assert not minus.enabled
                fields[0].value = 370
                assert not plus.enabled
                outputs[0].pdf_only.value = True
            user.find(marker='browse-export-directory').click()
            await user.should_see(chosen)
            user.find(marker='browse-export-directory').click()
            await asyncio.sleep(.1)
            await user.should_see(chosen)
            assert picker.call_count == 2
